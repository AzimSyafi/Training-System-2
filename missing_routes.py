# Missing route implementations for Training System
# These need to be integrated into routes.py

# ===== 1. CREATE USER (Admin) =====
"""
@main_bp.route('/create_user', methods=['POST'])
@login_required
def create_user():
    if not isinstance(current_user, Admin):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.login'))
    
    try:
        role = request.form.get('role', '').strip()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not all([role, full_name, email, password]):
            flash('All fields are required', 'danger')
            return redirect(url_for('main.admin_users'))
        
        if role == 'admin':
            existing = Admin.query.filter_by(email=email).first()
            if existing:
                flash(f'Admin with email {email} already exists', 'warning')
                return redirect(url_for('main.admin_users'))
            
            new_admin = Admin(
                username=full_name.lower().replace(' ', '_'),
                email=email,
                role='admin'
            )
            new_admin.set_password(password)
            db.session.add(new_admin)
            db.session.commit()
            flash(f'Admin "{full_name}" created successfully', 'success')
            logging.info(f'[CREATE USER] Admin created: {email}')
            
        elif role == 'trainer':
            existing = Trainer.query.filter_by(email=email).first()
            if existing:
                flash(f'Trainer with email {email} already exists', 'warning')
                return redirect(url_for('main.admin_users'))
            
            year = datetime.now(UTC).strftime('%Y')
            seq_name = f'trainer_number_series_{year}_seq'
            
            new_trainer = Trainer(
                name=full_name,
                email=email,
                active_status=True
            )
            new_trainer.set_password(password)
            
            db.session.add(new_trainer)
            db.session.flush()
            
            db.session.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))
            seq_val = db.session.execute(text(f"SELECT nextval('{seq_name}')")).scalar()
            new_trainer.number_series = f"TR{year}{int(seq_val):04d}"
            
            db.session.commit()
            flash(f'Trainer "{full_name}" created successfully', 'success')
            logging.info(f'[CREATE USER] Trainer created: {email}')
        else:
            flash('Invalid role selected', 'danger')
            
    except Exception as e:
        db.session.rollback()
        logging.exception('[CREATE USER] Failed to create user')
        flash(f'Error creating user: {str(e)}', 'danger')
    
    return redirect(url_for('main.admin_users'))
"""

# ===== 2. COMPLETE MODULE (User) =====
"""
@main_bp.route('/complete_module/<int:module_id>', methods=['POST'])
@login_required
def complete_module(module_id):
    if not isinstance(current_user, User):
        flash('Only users can complete modules', 'danger')
        return redirect(url_for('main.login'))
    
    try:
        module = Module.query.get_or_404(module_id)
        user_id = current_user.User_id
        
        user_module = UserModule.query.filter_by(
            user_id=user_id,
            module_id=module_id
        ).first()
        
        if not user_module:
            user_module = UserModule(
                user_id=user_id,
                module_id=module_id,
                completion_status='completed',
                completion_date=datetime.now(UTC)
            )
            db.session.add(user_module)
        else:
            user_module.completion_status = 'completed'
            user_module.completion_date = datetime.now(UTC)
        
        db.session.commit()
        flash(f'Module "{module.module_name}" marked as completed!', 'success')
        logging.info(f'[COMPLETE MODULE] User {user_id} completed module {module_id}')
        
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[COMPLETE MODULE] Failed to complete module {module_id}')
        flash(f'Error completing module: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('main.user_dashboard'))
"""

# ===== 3. DELETE MODULE (Admin) =====
"""
@main_bp.route('/delete_module/<int:module_id>', methods=['POST'])
@login_required
def delete_module(module_id):
    if not isinstance(current_user, Admin):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.login'))
    
    try:
        module = Module.query.get_or_404(module_id)
        module_name = module.module_name
        
        UserModule.query.filter_by(module_id=module_id).delete()
        Certificate.query.filter_by(module_id=module_id).delete()
        
        db.session.delete(module)
        db.session.commit()
        flash(f'Module "{module_name}" deleted successfully', 'success')
        logging.info(f'[DELETE MODULE] Admin {current_user.username} deleted module {module_id}')
        
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[DELETE MODULE] Failed to delete module {module_id}')
        flash(f'Error deleting module: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('main.admin_dashboard'))
"""

# ===== 4. ONBOARDING (User post-signup) =====
"""
@main_bp.route('/onboarding/<int:id>/<int:step>', methods=['GET', 'POST'])
@login_required
def onboarding(id, step):
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            if 'ic_number' in request.form:
                user.ic_number = request.form.get('ic_number', '').strip()
            if 'passport_number' in request.form:
                user.passport_number = request.form.get('passport_number', '').strip()
            if 'address' in request.form:
                user.address = request.form.get('address', '').strip()
            if 'current_workplace' in request.form:
                user.current_workplace = request.form.get('current_workplace', '').strip()
            if 'recruitment_date' in request.form:
                date_str = request.form.get('recruitment_date')
                user.recruitment_date = safe_parse_date(date_str)
            if 'emergency_contact_name' in request.form:
                user.emergency_contact_name = request.form.get('emergency_contact_name', '').strip()
            if 'emergency_contact_phone' in request.form:
                user.emergency_contact_phone = request.form.get('emergency_contact_phone', '').strip()
            if 'emergency_contact_relationship' in request.form:
                user.emergency_contact_relationship = request.form.get('emergency_contact_relationship', '').strip()
            
            user.is_finalized = True
            db.session.commit()
            
            flash('Onboarding completed successfully!', 'success')
            return redirect(url_for('main.user_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            logging.exception(f'[ONBOARDING] Failed for user {id}')
            flash(f'Error during onboarding: {str(e)}', 'danger')
    
    return render_template('onboarding.html', user=user, id=id, step=step)
"""

# ===== 5. UPLOAD CERT TEMPLATE (Admin) =====
"""
@main_bp.route('/upload_cert_template', methods=['POST'])
@login_required
def upload_cert_template():
    if not isinstance(current_user, Admin):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.login'))
    
    try:
        if 'cert_template' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(url_for('main.admin_certificates'))
        
        file = request.files['cert_template']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('main.admin_certificates'))
        
        if file:
            filename = secure_filename(file.filename)
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            
            flash(f'Certificate template "{filename}" uploaded successfully', 'success')
            logging.info(f'[UPLOAD CERT TEMPLATE] Admin uploaded: {filename}')
            
    except Exception as e:
        logging.exception('[UPLOAD CERT TEMPLATE] Failed to upload')
        flash(f'Error uploading template: {str(e)}', 'danger')
    
    return redirect(url_for('main.admin_certificates'))
"""

# ===== 6. DELETE CERTIFICATES BULK (Admin) =====
"""
@main_bp.route('/delete_certificates_bulk', methods=['POST'])
@login_required
def delete_certificates_bulk():
    if not isinstance(current_user, Admin):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.login'))
    
    try:
        cert_ids = request.form.getlist('certificate_ids')
        if not cert_ids:
            flash('No certificates selected', 'warning')
            return redirect(url_for('main.admin_certificates'))
        
        count = 0
        for cert_id in cert_ids:
            cert = Certificate.query.get(int(cert_id))
            if cert:
                db.session.delete(cert)
                count += 1
        
        db.session.commit()
        flash(f'{count} certificate(s) deleted successfully', 'success')
        logging.info(f'[DELETE CERTS BULK] Admin deleted {count} certificates')
        
    except Exception as e:
        db.session.rollback()
        logging.exception('[DELETE CERTS BULK] Failed')
        flash(f'Error deleting certificates: {str(e)}', 'danger')
    
    return redirect(url_for('main.admin_certificates'))
"""

# ===== 7. AGENCY UPDATE DETAILS =====
"""
@main_bp.route('/agency_update_details', methods=['POST'])
@login_required
def agency_update_details():
    if not isinstance(current_user, AgencyAccount):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.login'))
    
    try:
        agency = current_user.agency
        if not agency:
            flash('No agency associated with this account', 'danger')
            return redirect(url_for('main.agency_portal'))
        
        if 'agency_name' in request.form:
            agency.agency_name = request.form.get('agency_name', '').strip()
        if 'PIC' in request.form:
            agency.PIC = request.form.get('PIC', '').strip()
        if 'contact_number' in request.form:
            agency.contact_number = request.form.get('contact_number', '').strip()
        if 'email' in request.form:
            agency.email = request.form.get('email', '').strip()
        if 'address' in request.form:
            agency.address = request.form.get('address', '').strip()
        
        db.session.commit()
        flash('Agency details updated successfully', 'success')
        logging.info(f'[AGENCY UPDATE] Agency {agency.agency_id} updated details')
        
    except Exception as e:
        db.session.rollback()
        logging.exception('[AGENCY UPDATE] Failed')
        flash(f'Error updating agency details: {str(e)}', 'danger')
    
    return redirect(url_for('main.agency_portal'))
"""

# ===== 8. AGENCY CREATE USER =====
"""
@main_bp.route('/agency_create_user', methods=['POST'])
@login_required
def agency_create_user():
    if not isinstance(current_user, AgencyAccount):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.login'))
    
    try:
        agency = current_user.agency
        if not agency:
            flash('No agency associated with this account', 'danger')
            return redirect(url_for('main.agency_portal'))
        
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        user_category = request.form.get('user_category', 'citizen').strip()
        
        if not all([full_name, email, password]):
            flash('Full name, email, and password are required', 'danger')
            return redirect(url_for('main.agency_portal'))
        
        user_data = {
            'full_name': full_name,
            'email': email,
            'password': password,
            'user_category': user_category,
            'agency_id': agency.agency_id
        }
        
        if user_category == 'citizen' and 'ic_number' in request.form:
            user_data['ic_number'] = request.form.get('ic_number', '').strip()
        elif user_category == 'foreigner':
            if 'passport_number' in request.form:
                user_data['passport_number'] = request.form.get('passport_number', '').strip()
            if 'country' in request.form:
                user_data['country'] = request.form.get('country', '').strip()
        
        user = Registration.registerUser(user_data)
        user.is_finalized = True
        db.session.commit()
        
        flash(f'User "{full_name}" created successfully', 'success')
        logging.info(f'[AGENCY CREATE USER] Agency {agency.agency_id} created user: {email}')
        
    except ValueError as ve:
        flash(str(ve), 'warning')
    except Exception as e:
        db.session.rollback()
        logging.exception('[AGENCY CREATE USER] Failed')
        flash(f'Error creating user: {str(e)}', 'danger')
    
    return redirect(url_for('main.agency_portal'))
"""

# ===== 9. AGENCY BULK CREATE USERS =====
"""
@main_bp.route('/agency_bulk_create_users', methods=['POST'])
@login_required
def agency_bulk_create_users():
    if not isinstance(current_user, AgencyAccount):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.login'))
    
    try:
        agency = current_user.agency
        if not agency:
            flash('No agency associated with this account', 'danger')
            return redirect(url_for('main.agency_portal'))
        
        if 'bulk_file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(url_for('main.agency_portal'))
        
        file = request.files['bulk_file']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('main.agency_portal'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash('Please upload an Excel file (.xlsx or .xls)', 'danger')
            return redirect(url_for('main.agency_portal'))
        
        import openpyxl
        workbook = openpyxl.load_workbook(file)
        sheet = workbook.active
        
        success_count = 0
        error_count = 0
        errors = []
        
        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            try:
                if not row or not any(row):
                    continue
                
                full_name, email, password, user_category = row[0], row[1], row[2], row[3] if len(row) > 3 else 'citizen'
                
                if not all([full_name, email, password]):
                    errors.append(f'Row {row_idx}: Missing required fields')
                    error_count += 1
                    continue
                
                user_data = {
                    'full_name': str(full_name).strip(),
                    'email': str(email).strip(),
                    'password': str(password).strip(),
                    'user_category': str(user_category).strip() if user_category else 'citizen',
                    'agency_id': agency.agency_id
                }
                
                user = Registration.registerUser(user_data)
                user.is_finalized = True
                success_count += 1
                
            except ValueError as ve:
                errors.append(f'Row {row_idx}: {str(ve)}')
                error_count += 1
            except Exception as e:
                errors.append(f'Row {row_idx}: {str(e)}')
                error_count += 1
        
        db.session.commit()
        
        msg = f'{success_count} user(s) created successfully'
        if error_count > 0:
            msg += f', {error_count} failed'
            flash(msg, 'warning')
            for error in errors[:5]:
                flash(error, 'danger')
        else:
            flash(msg, 'success')
        
        logging.info(f'[AGENCY BULK CREATE] Agency {agency.agency_id} created {success_count} users')
        
    except Exception as e:
        db.session.rollback()
        logging.exception('[AGENCY BULK CREATE] Failed')
        flash(f'Error processing bulk upload: {str(e)}', 'danger')
    
    return redirect(url_for('main.agency_portal'))
"""
