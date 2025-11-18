"""
Routes for Training System app, using Flask Blueprint.
All route functions from app.py are moved here.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory, abort, current_app, make_response
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import logging
from models import db, Admin, User, Agency, Module, Certificate, Trainer, UserModule, Management, Registration, Course, WorkHistory, UserCourseProgress, AgencyAccount, CertificateTemplate
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, or_
from utils import safe_url_for, normalized_user_category, safe_parse_date, extract_youtube_id, is_slide_file, allowed_file, allowed_slide_file
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Message
import smtplib
from email.mime.text import MIMEText
import re

main_bp = Blueprint('main', __name__)

def resolve_uid():
    """Return numeric User.User_id for the currently-authenticated user when possible.
    - If `current_user` is a User instance, return `current_user.User_id`.
    - Else try to use `session['user_id']` and `session['user_type']` to locate the User record.
    - Returns None when no user id can be resolved.
    """
    try:
        # If current_user is a User model instance, prefer that
        if hasattr(current_user, 'User_id') and getattr(current_user, 'User_id'):
            return getattr(current_user, 'User_id')
    except Exception:
        pass
    try:
        sid = session.get('user_id')
    except Exception:
        sid = None
    if not sid:
        return None
    # If sid looks like an integer string, try using it as User_id
    try:
        if isinstance(sid, int):
            candidate = User.query.filter_by(User_id=int(sid)).first()
            if candidate:
                return candidate.User_id
        s = str(sid).strip()
        if s.isdigit():
            candidate = User.query.filter_by(User_id=int(s)).first()
            if candidate:
                return candidate.User_id
        # Otherwise, session may store number_series (e.g. 'SG20250001'), try to find by number_series
        candidate = User.query.filter_by(number_series=s).first()
        if candidate:
            return candidate.User_id
    except Exception:
        # Any DB error -> return None
        logging.exception('[resolve_uid] Failed resolving user id from session')
        return None
    return None

# New helper: canonical sort for modules by their series_number.
# Series numbers are often strings like 'TNG001' or 'CSG1' — this helper will try to sort
# by the last numeric group in the series (numeric natural sort), falling back to
# lexicographic order when no digits are present.
def _module_series_sort_key(m):
    try:
        s = (getattr(m, 'series_number', None) or '').strip()
        if not s:
            # ensure modules without series go last
            return (float('inf'), '')
        # find the last contiguous group of digits in the string
        matches = re.findall(r"(\d+)", s)
        if matches:
            # use integer value of the last digit group first, then full string as tiebreaker
            num = int(matches[-1])
            return (num, s)
        # no digits, sort lexicographically but put after numeric ones by returning large first element
        return (float('inf'), s)
    except Exception:
        return (float('inf'), getattr(m, 'series_number', '') or '')

# Home route
@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        if isinstance(current_user, Admin):
            return redirect(url_for('main.admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('main.trainer_portal'))
        if isinstance(current_user, User):
            return redirect(url_for('main.user_dashboard'))
        from models import AgencyAccount as _AA
        if isinstance(current_user, _AA):
            return redirect(url_for('main.agency_portal'))
    return render_template('index.html')

# Signup route
@main_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        if isinstance(current_user, Admin):
            return redirect(url_for('main.admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('main.trainer_portal'))
        if isinstance(current_user, User):
            return redirect(url_for('main.user_dashboard'))
        return redirect(url_for('main.index'))
    agencies = []
    try:
        agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
    except Exception:
        logging.exception('[SIGNUP] Failed loading agencies')
        agencies = []
    countries = ['Malaysia', 'Indonesia', 'Singapore', 'Thailand', 'Philippines', 'Vietnam', 'Brunei', 'Cambodia', 'Laos', 'Myanmar', 'China', 'India', 'Bangladesh', 'Pakistan', 'Nepal', 'Sri Lanka', 'Japan', 'South Korea', 'North Korea', 'Taiwan', 'Hong Kong', 'Macau', 'Mongolia', 'Russia', 'Kazakhstan', 'Kyrgyzstan', 'Tajikistan', 'Turkmenistan', 'Uzbekistan', 'Afghanistan', 'Iran', 'Iraq', 'Jordan', 'Kuwait', 'Lebanon', 'Oman', 'Qatar', 'Saudi Arabia', 'Syria', 'Turkey', 'United Arab Emirates', 'Yemen', 'Egypt', 'Libya', 'Morocco', 'Tunisia', 'Algeria', 'Sudan', 'Ethiopia', 'Kenya', 'Tanzania', 'Uganda', 'Rwanda', 'Burundi', 'South Africa', 'Zimbabwe', 'Zambia', 'Botswana', 'Namibia', 'Angola', 'Mozambique', 'Madagascar', 'Mauritius', 'Seychelles', 'Comoros', 'Djibouti', 'Somalia', 'Eritrea', 'Australia', 'New Zealand', 'Papua New Guinea', 'Solomon Islands', 'Vanuatu', 'Fiji', 'Samoa', 'Tonga', 'Kiribati', 'Tuvalu', 'Nauru', 'Marshall Islands', 'Micronesia', 'Palau', 'United States', 'Canada', 'Mexico', 'Brazil', 'Argentina', 'Chile', 'Peru', 'Colombia', 'Venezuela', 'Ecuador', 'Bolivia', 'Paraguay', 'Uruguay', 'Guyana', 'Suriname', 'French Guiana', 'United Kingdom', 'Ireland', 'France', 'Germany', 'Italy', 'Spain', 'Portugal', 'Belgium', 'Netherlands', 'Luxembourg', 'Switzerland', 'Austria', 'Denmark', 'Sweden', 'Norway', 'Finland', 'Iceland', 'Greenland', 'Poland', 'Czech Republic', 'Slovakia', 'Hungary', 'Romania', 'Bulgaria', 'Greece', 'Serbia', 'Croatia', 'Bosnia and Herzegovina', 'Montenegro', 'Kosovo', 'Albania', 'North Macedonia', 'Slovenia', 'Ukraine', 'Belarus', 'Moldova', 'Lithuania', 'Latvia', 'Estonia', 'Georgia', 'Armenia', 'Azerbaijan']
    if request.method == 'POST':
        form = request.form
        full_name = form.get('full_name','').strip()
        email = form.get('email','').strip().lower()
        password = form.get('password','')
        user_category = form.get('user_category','citizen').strip().lower()
        agency_id = form.get('agency_id')
        ic_number = form.get('ic_number','').strip() or None
        passport_number = form.get('passport_number','').strip() or None
        country = form.get('country','').strip() or None
        if not full_name or not email or not password or not agency_id:
            flash('All required fields must be filled: name, email, password, agency.', 'danger')
            return render_template('signup.html', agencies=agencies)
        try:
            agency_id_int = int(agency_id)
        except (ValueError, TypeError):
            flash('Invalid agency selected.', 'danger')
            return render_template('signup.html', agencies=agencies)
        try:
            agency_obj = db.session.get(Agency, agency_id_int)
            if not agency_obj:
                flash('Selected agency does not exist.', 'danger')
                return render_template('signup.html', agencies=agencies)
        except Exception:
            flash('Database error checking agency.', 'danger')
            return render_template('signup.html', agencies=agencies)
        data = {
            'full_name': full_name,
            'email': email,
            'password': password,
            'user_category': 'foreigner' if user_category == 'foreigner' else 'citizen',
            'agency_id': agency_id_int
        }
        if ic_number:
            data['ic_number'] = ic_number
        if passport_number:
            data['passport_number'] = passport_number
        if country and user_category == 'foreigner':
            data['country'] = country
        try:
            new_user = Registration.registerUser(data)
            login_user(new_user)
            session['user_type'] = 'user'
            session['user_id'] = new_user.get_id()
            flash('Account created successfully! Complete your profile to finalize registration.', 'success')
            return redirect(url_for('main.onboarding', id=new_user.User_id, step=1))
        except ValueError as ve:
            flash(str(ve), 'danger')
        except Exception as e:
            logging.exception('[SIGNUP] Registration failed')
            flash('Registration failed due to server error. Please try again later.', 'danger')
        return render_template('signup.html', agencies=agencies, countries=countries)
    return render_template('signup.html', agencies=agencies, countries=countries)

@main_bp.route('/onboarding/<int:id>/<int:step>', methods=['GET', 'POST'])
@login_required
def onboarding(id, step):
    user = User.query.get_or_404(id)
    
    # Authorization check: only the user themselves, admins, or their agency can access onboarding
    # Must check BEFORE any template rendering to prevent PII leakage
    is_authorized = False
    if isinstance(current_user, Admin):
        is_authorized = True
    elif isinstance(current_user, User) and current_user.User_id == id:
        is_authorized = True
    elif isinstance(current_user, AgencyAccount) and user.agency_id == current_user.agency_id:
        is_authorized = True
    
    if not is_authorized:
        abort(403)
    
    # Define total number of onboarding steps
    total_steps = 4  # Four-step onboarding flow
    
    # Comprehensive list of all countries (excluding Israel)
    countries = [
        'Afghanistan', 'Albania', 'Algeria', 'Andorra', 'Angola', 'Antigua and Barbuda', 'Argentina', 'Armenia', 'Australia', 'Austria',
        'Azerbaijan', 'Bahamas', 'Bahrain', 'Bangladesh', 'Barbados', 'Belarus', 'Belgium', 'Belize', 'Benin', 'Bhutan',
        'Bolivia', 'Bosnia and Herzegovina', 'Botswana', 'Brazil', 'Brunei', 'Bulgaria', 'Burkina Faso', 'Burundi', 'Cambodia', 'Cameroon',
        'Canada', 'Cape Verde', 'Central African Republic', 'Chad', 'Chile', 'China', 'Colombia', 'Comoros', 'Congo', 'Costa Rica',
        'Croatia', 'Cuba', 'Cyprus', 'Czech Republic', 'Denmark', 'Djibouti', 'Dominica', 'Dominican Republic', 'East Timor', 'Ecuador',
        'Egypt', 'El Salvador', 'Equatorial Guinea', 'Eritrea', 'Estonia', 'Eswatini', 'Ethiopia', 'Fiji', 'Finland', 'France',
        'Gabon', 'Gambia', 'Georgia', 'Germany', 'Ghana', 'Greece', 'Grenada', 'Guatemala', 'Guinea', 'Guinea-Bissau',
        'Guyana', 'Haiti', 'Honduras', 'Hungary', 'Iceland', 'India', 'Indonesia', 'Iran', 'Iraq', 'Ireland',
        'Italy', 'Jamaica', 'Japan', 'Jordan', 'Kazakhstan', 'Kenya', 'Kiribati', 'Kosovo', 'Kuwait', 'Kyrgyzstan',
        'Laos', 'Latvia', 'Lebanon', 'Lesotho', 'Liberia', 'Libya', 'Liechtenstein', 'Lithuania', 'Luxembourg', 'Madagascar',
        'Malawi', 'Malaysia', 'Maldives', 'Mali', 'Malta', 'Marshall Islands', 'Mauritania', 'Mauritius', 'Mexico', 'Micronesia',
        'Moldova', 'Monaco', 'Mongolia', 'Montenegro', 'Morocco', 'Mozambique', 'Myanmar', 'Namibia', 'Nauru', 'Nepal',
        'Netherlands', 'New Zealand', 'Nicaragua', 'Niger', 'Nigeria', 'North Korea', 'North Macedonia', 'Norway', 'Oman', 'Pakistan',
        'Palau', 'Palestine', 'Panama', 'Papua New Guinea', 'Paraguay', 'Peru', 'Philippines', 'Poland', 'Portugal', 'Qatar',
        'Romania', 'Russia', 'Rwanda', 'Saint Kitts and Nevis', 'Saint Lucia', 'Saint Vincent and the Grenadines', 'Samoa', 'San Marino', 'Sao Tome and Principe', 'Saudi Arabia',
        'Senegal', 'Serbia', 'Seychelles', 'Sierra Leone', 'Singapore', 'Slovakia', 'Slovenia', 'Solomon Islands', 'Somalia', 'South Africa',
        'South Korea', 'South Sudan', 'Spain', 'Sri Lanka', 'Sudan', 'Suriname', 'Sweden', 'Switzerland', 'Syria', 'Taiwan',
        'Tajikistan', 'Tanzania', 'Thailand', 'Togo', 'Tonga', 'Trinidad and Tobago', 'Tunisia', 'Turkey', 'Turkmenistan', 'Tuvalu',
        'Uganda', 'Ukraine', 'United Arab Emirates', 'United Kingdom', 'United States', 'Uruguay', 'Uzbekistan', 'Vanuatu', 'Vatican City', 'Venezuela',
        'Vietnam', 'Yemen', 'Zambia', 'Zimbabwe'
    ]
    
    if request.method == 'POST':
        try:
            # Process fields based on current step
            if step == 1:
                # Personal Details (Step 1)
                if 'full_name' in request.form:
                    user.full_name = request.form.get('full_name', '').strip()
                if 'user_category' in request.form:
                    user.user_category = request.form.get('user_category', 'citizen').strip().lower()
                if 'ic_number' in request.form:
                    user.ic_number = request.form.get('ic_number', '').strip() or None
                if 'passport_number' in request.form:
                    user.passport_number = request.form.get('passport_number', '').strip() or None
                # Handle profile picture upload
                if 'profile_pic' in request.files:
                    file = request.files['profile_pic']
                    if file and file.filename and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filename = f"user{user.User_id}_{filename}"
                        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profile_pics', filename)
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        file.save(file_path)
                        # Set Profile_picture field (not profile_pic_url property which has no setter)
                        user.Profile_picture = f"profile_pics/{filename}"
                        
            elif step == 2:
                # Contact Details (Step 2) - Note: emergency_contact_phone here is actually "Phone Number"
                if 'postcode' in request.form:
                    user.postcode = request.form.get('postcode', '').strip()
                if 'address' in request.form:
                    user.address = request.form.get('address', '').strip()
                if 'state' in request.form:
                    user.state = request.form.get('state', '').strip()
                if 'country' in request.form:
                    user.country = request.form.get('country', '').strip()
                # Store phone number (field name is confusingly emergency_contact_phone but it's just the user's phone)
                if 'emergency_contact_phone' in request.form:
                    user.emergency_contact_phone = request.form.get('emergency_contact_phone', '').strip()
                    
            elif step == 3:
                # Work Details (Step 3)
                if 'current_workplace' in request.form:
                    user.current_workplace = request.form.get('current_workplace', '').strip()
                if 'recruitment_date' in request.form:
                    date_str = request.form.get('recruitment_date')
                    user.recruitment_date = safe_parse_date(date_str)
                # Handle work experience entries
                companies = request.form.getlist('exp_company')
                positions = request.form.getlist('exp_position')
                recruitments = request.form.getlist('exp_recruitment')
                starts = request.form.getlist('exp_start')
                ends = request.form.getlist('exp_end')
                visas = request.form.getlist('exp_visa_number')
                visa_expiries = request.form.getlist('exp_visa_expiry')
                # Delete existing work histories for this user
                WorkHistory.query.filter_by(user_id=user.User_id).delete()
                # Add new work histories
                for i in range(len(companies)):
                    if companies[i].strip():
                        wh = WorkHistory(
                            user_id=user.User_id,
                            company_name=companies[i].strip(),
                            position_title=positions[i].strip() if i < len(positions) else '',
                            recruitment_date=safe_parse_date(recruitments[i]) if i < len(recruitments) else None,
                            start_date=safe_parse_date(starts[i]) if i < len(starts) else None,
                            end_date=safe_parse_date(ends[i]) if i < len(ends) else None,
                            visa_number=visas[i].strip() if i < len(visas) else '',
                            visa_expiry_date=safe_parse_date(visa_expiries[i]) if i < len(visa_expiries) else None
                        )
                        db.session.add(wh)
                        
            elif step == 4:
                # Emergency Contact (Step 4)
                if 'emergency_contact_name' in request.form:
                    user.emergency_contact_name = request.form.get('emergency_contact_name', '').strip()
                if 'emergency_contact_relationship' in request.form:
                    user.emergency_contact_relationship = request.form.get('emergency_contact_relationship', '').strip()
                # Yes, this field appears in both step 2 and step 4, overwriting is fine
                if 'emergency_contact_phone' in request.form:
                    user.emergency_contact_phone = request.form.get('emergency_contact_phone', '').strip()
            
            # Commit changes for current step
            db.session.commit()
            
            # Determine next action
            if step < total_steps:
                # Move to next step
                flash(f'Step {step} saved! Continue to step {step + 1}.', 'success')
                return redirect(url_for('main.onboarding', id=id, step=step + 1))
            else:
                # Final step complete - finalize user
                user.is_finalized = True
                db.session.commit()
                flash('Onboarding completed successfully!', 'success')
                return redirect(url_for('main.user_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            logging.exception(f'[ONBOARDING] Failed for user {id} at step {step}')
            flash(f'Error during onboarding: {str(e)}', 'danger')
    
    return render_template('onboarding.html', user=user, id=id, step=step, total_steps=total_steps, countries=countries)

# Login route
@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET' and current_user.is_authenticated:
        if isinstance(current_user, Admin):
            return redirect(url_for('main.admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('main.trainer_portal'))
        if isinstance(current_user, User):
            return redirect(url_for('main.user_dashboard'))
        from models import AgencyAccount as _AA
        if isinstance(current_user, _AA):
            return redirect(url_for('main.agency_portal'))
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            user = Admin.query.filter_by(email=email).first()
            if user and user.check_password(password):
                login_user(user)
                session['user_type'] = 'admin'
                session['user_id'] = user.get_id()
                return redirect(url_for('main.admin_dashboard'))
            user = User.query.filter_by(email=email).first()
            if user and user.check_password(password):
                # Check if user has trainer role - login as trainer instead
                if hasattr(user, 'role') and user.role == 'trainer':
                    # Find corresponding trainer account
                    trainer = Trainer.query.filter_by(email=email).first()
                    if trainer:
                        login_user(trainer)
                        session['user_type'] = 'trainer'
                        session['user_id'] = trainer.get_id()
                        return redirect(url_for('main.trainer_portal'))
                    else:
                        # Trainer role but no trainer record - this shouldn't happen with new logic
                        flash('Trainer account setup incomplete. Please contact admin.', 'warning')
                        return redirect(url_for('main.login'))
                
                # Regular user login
                login_user(user)
                session['user_type'] = 'user'
                session['user_id'] = user.get_id()
                return redirect(url_for('main.user_dashboard'))
            user = Trainer.query.filter_by(email=email).first()
            if user and user.check_password(password):
                login_user(user)
                session['user_type'] = 'trainer'
                session['user_id'] = user.get_id()
                return redirect(url_for('main.trainer_portal'))
            acct = AgencyAccount.query.filter_by(email=email).first()
            if acct and acct.check_password(password):
                login_user(acct)
                session['user_type'] = 'agency'
                session['user_id'] = acct.get_id()
                return redirect(url_for('main.agency_portal'))
            flash('Invalid email or password')
        except Exception as e:
            logging.exception('[LOGIN] Database error during authentication')
            flash('Database error. Please check server database connection.')
    return render_template('login.html')

# User dashboard
@main_bp.route('/user_dashboard')
@login_required
def user_dashboard():
    if not isinstance(current_user, User):
        if isinstance(current_user, Admin):
            return redirect(url_for('main.admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('main.trainer_portal'))
        from models import AgencyAccount as _AA
        if isinstance(current_user, _AA):
            return redirect(url_for('main.agency'))
        return redirect(url_for('main.login'))
    try:
        cat = normalized_user_category(current_user)
        courses_q = Course.query.filter(or_(Course.allowed_category == cat, Course.allowed_category == 'both'))
        courses = courses_q.order_by(Course.name.asc()).all()
        if not courses:
            courses = Course.query.order_by(Course.name.asc()).all()
    except Exception:
        logging.exception('[USER DASHBOARD] Failed loading courses')
        courses = []
    courses_progress = []
    course_completed_count = 0
    for c in courses:
        try:
            # Ensure modules are presented in ascending series order
            mods = sorted(list(c.modules), key=_module_series_sort_key)
            total_modules = len(mods)
            if total_modules == 0:
                completed_modules = 0
                progress_pct = 0.0
            else:
                module_ids = [m.module_id for m in mods]
                completed_modules = UserModule.query.filter(
                    UserModule.user_id == current_user.User_id,
                    UserModule.module_id.in_(module_ids),
                    UserModule.is_completed.is_(True)
                ).count()
                progress_pct = round((completed_modules / total_modules) * 100.0, 1) if total_modules else 0.0
            if total_modules > 0 and completed_modules == total_modules:
                course_completed_count += 1
            courses_progress.append({
                'course_id': c.course_id,
                'name': c.name,
                'code': c.code,
                'total_modules': total_modules,
                'completed_modules': completed_modules,
                'progress': progress_pct
            })
        except Exception:
            logging.exception('[USER DASHBOARD] Error computing progress for course %s', getattr(c, 'code', '?'))
    course_enrolled_count = len([c for c in courses if len(c.modules) > 0])
    return render_template(
        'user_dashboard.html',
        user=current_user,
        courses=courses,
        courses_progress=courses_progress,
        course_enrolled_count=course_enrolled_count,
        course_completed_count=course_completed_count
    )

# Courses
@main_bp.route('/courses')
@login_required
def courses():
    try:
        if isinstance(current_user, Admin) or isinstance(current_user, Trainer) or getattr(current_user, 'role', None) == 'authority' or isinstance(current_user, AgencyAccount):
            courses_q = Course.query
        else:
            cat = normalized_user_category(current_user)
            courses_q = Course.query.filter(or_(Course.allowed_category == cat, Course.allowed_category == 'both'))
        all_courses = courses_q.order_by(Course.name.asc()).all()
    except Exception:
        logging.exception('[COURSES] Failed loading courses')
        all_courses = []
    visible_courses = [c for c in all_courses if getattr(c, 'is_visible_to', lambda u: True)(current_user)]
    course_progress = []
    for c in visible_courses:
        try:
            allowed = c.allowed_category or 'both'
            # Present modules sorted by series number
            modules = sorted(list(c.modules), key=_module_series_sort_key)
            module_ids = [m.module_id for m in modules]
            total_modules = len(modules)
            if total_modules == 0:
                percent = 0
                overall_percentage = 0
            else:
                completed_q = UserModule.query.filter(
                    UserModule.user_id == current_user.User_id,
                    UserModule.module_id.in_(module_ids),
                    UserModule.is_completed.is_(True)
                )
                completed_count = completed_q.count()
                percent = round((completed_count / total_modules) * 100) if total_modules else 0
                scores = [um.score for um in completed_q.all() if um.score is not None]
                overall_percentage = round(sum(scores)/len(scores),1) if scores else 0
            course_progress.append({
                'name': c.name,
                'code': c.code,
                'allowed_category': allowed,
                'locked': False,
                'percent': percent,
                'overall_percentage': overall_percentage
            })
        except Exception:
            logging.exception('[COURSES] Error computing progress for course %s', getattr(c,'code','?'))
    return render_template('courses.html', course_progress=course_progress)

# User modules page
@main_bp.route('/course/<int:course_id>')
@login_required
def user_modules_page(course_id):
    try:
        course = db.session.get(Course, course_id)
        if not course:
            abort(404)
        # Load user with agency
        user = db.session.query(User).options(db.joinedload(User.agency)).filter_by(User_id=current_user.User_id).first()
        if not user:
            abort(403)
        # Check if user can access this course
        if not (isinstance(user, Admin) or isinstance(user, Trainer) or getattr(user, 'role', None) == 'authority' or isinstance(user, AgencyAccount)):
            cat = normalized_user_category(user)
            if course.allowed_category not in (cat, 'both'):
                abort(403)
        # Load modules in defined order (by series number)
        modules = sorted(list(course.modules), key=_module_series_sort_key)
        # Compute progress for each module
        module_progress = []
        for m in modules:
            try:
                um = UserModule.query.filter_by(user_id=user.User_id, module_id=m.module_id).first()
                completed = um.is_completed if um else False
                score = um.score if um else None
                module_progress.append({
                    'module': m,
                    'completed': completed,
                    'score': score
                })
            except Exception:
                module_progress.append({
                    'module': m,
                    'completed': False,
                    'score': None
                })
    except Exception:
        logging.exception('[USER MODULES PAGE] Failed loading course')
        abort(500)
    return render_template('user_courses_dashboard.html', user=user, course=course, module_progress=module_progress)

# Course modules page (by course code)
@main_bp.route('/modules/<course_code>')
@login_required
def course_modules(course_code):
    """Render the modules page for a course identified by its code (case-insensitive)."""
    try:
        # Find course by code (case-insensitive)
        course = Course.query.filter(Course.code.ilike(course_code)).first()
        if not course:
            abort(404)
        # Permission check: ensure user can access this course
        if not (isinstance(current_user, Admin) or isinstance(current_user, Trainer) or getattr(current_user, 'role', None) == 'authority' or isinstance(current_user, AgencyAccount)):
            cat = normalized_user_category(current_user)
            if course.allowed_category not in (cat, 'both'):
                abort(403)
        # Load modules in defined order (by series number)
        modules = sorted(list(course.modules), key=_module_series_sort_key)
        # Build user progress map for these modules
        module_ids = [m.module_id for m in modules]
        user_modules = {}
        if module_ids:
            ums = UserModule.query.filter(UserModule.user_id == current_user.User_id, UserModule.module_id.in_(module_ids)).all()
            user_modules = {um.module_id: um for um in ums}
        # Determine unlocked status: first module unlocked by default; subsequent unlocked if previous completed
        prev_completed = True
        for idx, m in enumerate(modules):
            if idx == 0:
                m.unlocked = True
                prev_completed = user_modules.get(m.module_id).is_completed if user_modules.get(m.module_id) else False
            else:
                m.unlocked = bool(prev_completed)
                prev_completed = user_modules.get(m.module_id).is_completed if user_modules.get(m.module_id) else False
        # Compute overall percentage across completed modules (ignore None)
        scores = [um.score for um in user_modules.values() if um and um.is_completed and um.score is not None]
        overall_percentage = round(sum(scores)/len(scores),1) if scores else None
    except Exception:
        logging.exception('[COURSE MODULES] Failed building course modules page')
        abort(500)
    return render_template('course_modules.html', modules=modules, course_name=course.name, user_progress=user_modules, overall_percentage=overall_percentage)


# API: check module disclaimer agreement status
@main_bp.route('/api/check_module_disclaimer/<int:module_id>')
@login_required
def api_check_module_disclaimer(module_id):
    try:
        mod = db.session.get(Module, module_id)
        if not mod:
            return jsonify({'success': False, 'message': 'Module not found'}), 404
        # Ensure we operate on a User instance (current_user should be a User for trainees)
        if not hasattr(current_user, 'has_agreed_to_module_disclaimer'):
            # Try to load the user record from DB if possible
            try:
                user = User.query.filter_by(User_id=resolve_uid()).first()
            except Exception:
                user = None
            if not user:
                return jsonify({'success': False, 'message': 'Not a trainee user'}), 400
            has_agreed = user.has_agreed_to_module_disclaimer(module_id)
        else:
            has_agreed = current_user.has_agreed_to_module_disclaimer(module_id)
        return jsonify({'success': True, 'has_agreed': bool(has_agreed)})
    except Exception:
        logging.exception('[API] check_module_disclaimer')
        return jsonify({'success': False, 'message': 'Server error'}), 500


# API: record agreement to module disclaimer
@main_bp.route('/api/agree_module_disclaimer/<int:module_id>', methods=['POST'])
@login_required
def api_agree_module_disclaimer(module_id):
    try:
        mod = db.session.get(Module, module_id)
        if not mod:
            return jsonify({'success': False, 'message': 'Module not found'}), 404
        if not hasattr(current_user, 'agree_to_module_disclaimer'):
            try:
                user = User.query.filter_by(User_id=resolve_uid()).first()
            except Exception:
                user = None
            if not user:
                return jsonify({'success': False, 'message': 'Not a trainee user'}), 400
            user.agree_to_module_disclaimer(module_id)
        else:
            current_user.agree_to_module_disclaimer(module_id)
        return jsonify({'success': True})
    except Exception:
        logging.exception('[API] agree_module_disclaimer')
        return jsonify({'success': False, 'message': 'Server error'}), 500

# Profile
@main_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # Handle form submission
        try:
            # Update user fields
            current_user.full_name = request.form.get('full_name', current_user.full_name)
            current_user.email = request.form.get('email', current_user.email)
            current_user.address = request.form.get('address', current_user.address)
            current_user.postcode = request.form.get('postcode', current_user.postcode)
            current_user.state = request.form.get('state', current_user.state)
            current_user.country = request.form.get('country', current_user.country)
            current_user.working_experience = request.form.get('working_experience', current_user.working_experience)
            current_user.recruitment_date = safe_parse_date(request.form.get('recruitment_date'))
            current_user.visa_number = request.form.get('visa_number', current_user.visa_number)
            current_user.visa_expiry_date = safe_parse_date(request.form.get('visa_expiry_date'))
            current_user.current_workplace = request.form.get('current_workplace', current_user.current_workplace)
            current_user.emergency_contact_name = request.form.get('emergency_contact_name', current_user.emergency_contact_name)
            current_user.emergency_contact_relationship = request.form.get('emergency_contact_relationship', current_user.emergency_contact_relationship)
            current_user.emergency_contact_phone = request.form.get('emergency_contact_phone', current_user.emergency_contact_phone)

            # Handle profile picture upload
            if 'profile_pic' in request.files:
                file = request.files['profile_pic']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profile_pics', filename)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    file.save(file_path)
                    # Store relative path (including subfolder) so serve_uploaded_slide can locate it
                    # Use forward slashes for URL compatibility across platforms
                    current_user.Profile_picture = f"profile_pics/{filename}"

            # Handle working experiences
            # First, delete existing experiences
            WorkHistory.query.filter_by(user_id=current_user.User_id).delete()

            # Get experience data from form (updated field names to match template)
            exp_companies = request.form.getlist('exp_company')
            exp_positions = request.form.getlist('exp_position')
            exp_start_dates = request.form.getlist('exp_start_date')
            exp_end_dates = request.form.getlist('exp_end_date')

            for i in range(len(exp_companies)):
                if exp_companies[i].strip():  # Only save if company is provided
                    work_exp = WorkHistory(
                        user_id=current_user.User_id,
                        company_name=exp_companies[i],
                        position_title=exp_positions[i] if i < len(exp_positions) else None,
                        start_date=safe_parse_date(exp_start_dates[i]) if i < len(exp_start_dates) else None,
                        end_date=safe_parse_date(exp_end_dates[i]) if i < len(exp_end_dates) else None
                    )
                    db.session.add(work_exp)

            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('main.profile'))
        except Exception as e:
            db.session.rollback()
            logging.exception('[PROFILE UPDATE] Failed to update profile')
            flash('Failed to update profile. Please try again.', 'danger')
            return redirect(url_for('main.profile'))

    # GET request: render the template
    try:
        experiences = WorkHistory.query.filter_by(user_id=current_user.User_id).order_by(WorkHistory.start_date.desc()).all()
    except Exception:
        experiences = []

    malaysian_states = ['Johor', 'Kedah', 'Kelantan', 'Melaka', 'Negeri Sembilan', 'Pahang', 'Perak', 'Perlis', 'Pulau Pinang', 'Sabah', 'Sarawak', 'Selangor', 'Terengganu', 'Wilayah Persekutuan Kuala Lumpur', 'Wilayah Persekutuan Labuan', 'Wilayah Persekutuan Putrajaya']

    return render_template('profile.html', user=current_user, experiences=experiences, malaysian_states=malaysian_states)

# My certificates
@main_bp.route('/my_certificates')
@login_required
def my_certificates():
    certs = []
    try:
        certs = Certificate.query.filter_by(user_id=current_user.User_id).order_by(Certificate.issue_date.desc()).all()
    except Exception:
        logging.exception('[MY CERTIFICATES] Failed loading certificates')
    return render_template('my_certificates.html', certificates=certs)

# Agency
@main_bp.route('/agency')
@login_required
def agency():
    try:
        if isinstance(current_user, Admin):
            agencies = Agency.query.order_by(Agency.agency_name).all()
            return render_template('admin_agencies.html', agencies=agencies)
        else:
            ag = None
            if hasattr(current_user, 'agency_id') and current_user.agency_id:
                ag = db.session.query(Agency).filter_by(agency_id=current_user.agency_id).first()
            elif hasattr(current_user, 'agency'):
                ag = current_user.agency
            return render_template('agency.html', agency=ag)
    except Exception:
        if isinstance(current_user, Admin):
            agencies = []
            return render_template('admin_agencies.html', agencies=agencies)
        else:
            ag = None
            if hasattr(current_user, 'agency_id') and current_user.agency_id:
                ag = db.session.query(Agency).filter_by(agency_id=current_user.agency_id).first()
            elif hasattr(current_user, 'agency'):
                ag = current_user.agency
            return render_template('agency.html', agency=ag)

# Logout
@main_bp.route('/logout', methods=['POST', 'GET'])
@login_required
def logout():
    try:
        logout_user()
    except Exception:
        pass
    try:
        session.clear()
    except Exception:
        pass
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.login'))

# Change Password route
@main_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Allow authenticated users to change their password."""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not current_password or not new_password or not confirm_password:
            flash('All fields are required.', 'danger')
            return render_template('change_password.html')

        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'danger')
            return render_template('change_password.html')

        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'danger')
            return render_template('change_password.html')

        if current_password == new_password:
            flash('New password must be different from your current password.', 'warning')
            return render_template('change_password.html')

        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html')

        try:
            current_user.set_password(new_password)
            db.session.commit()
            logging.info(f'[CHANGE PASSWORD] User {current_user.get_id()} changed password successfully.')
            logout_user()
            session.clear()
            flash('Password changed successfully! Please log in with your new password.', 'success')
            return redirect(url_for('main.login'))
        except Exception as e:
            db.session.rollback()
            logging.exception(f'[CHANGE PASSWORD] Failed to update password for user {current_user.get_id()}')
            flash('An error occurred while updating your password. Please try again later.', 'danger')
            return render_template('change_password.html')

    return render_template('change_password.html')

# Trainer portal
@main_bp.route('/trainer_portal')
@login_required
def trainer_portal():
    if not isinstance(current_user, Trainer):
        return redirect(url_for('main.login'))
    try:
        courses_query = Course.query
        if getattr(current_user, 'course', None):
            courses_query = courses_query.filter(Course.code == current_user.course)
        courses = courses_query.all()
        course_stats = []
        modules_by_course = {}
        for course in courses:
            # Sort modules by series for consistent display and stats
            modules = sorted(list(course.modules), key=_module_series_sort_key)
            module_ids = [m.module_id for m in modules]
            modules_by_course[course.code] = [{'id': m.module_id, 'name': m.module_name} for m in modules]
            trainees_q = User.query
            if course.allowed_category == 'citizen':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'citizen')
            elif course.allowed_category == 'foreigner':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'foreigner')
            trainees = trainees_q.all()
            trainee_ids = [u.User_id for u in trainees]
            completed_count = 0; avg_score = 0.0; last_activity = None
            if module_ids and trainee_ids:
                completed_q = UserModule.query.filter(
                    UserModule.module_id.in_(module_ids),
                    UserModule.user_id.in_(trainee_ids),
                    UserModule.is_completed.is_(True)
                )
                completed_count = completed_q.count()
                avg_score_val = completed_q.with_entities(db.func.avg(UserModule.score)).scalar()
                avg_score = float(avg_score_val or 0.0)
                last_activity = completed_q.with_entities(db.func.max(UserModule.completion_date)).scalar()
            total_pairs = (len(modules) * len(trainees))
            progress_pct = (completed_count / total_pairs * 100.0) if total_pairs else 0.0
            course_stats.append({
                'code': course.code,
                'name': course.name,
                'trainee_count': len(trainees),
                'avg_score': round(avg_score, 1),
                'progress_pct': round(progress_pct, 1),
                'modules_count': len(modules),
                'completed_pairs': completed_count,
                'last_activity': last_activity
            })
        active_trainees = User.query.count()
        certificates_issued = Certificate.query.count()
        avg_rating_pct = 0.0
        my_courses = len(course_stats)
        progress_rows = []
        for course_stat in course_stats:
            code = course_stat['code']
            course_obj = next((c for c in courses if c.code == code), None)
            if not course_obj:
                continue
            course_module_ids = [m.module_id for m in course_obj.modules]
            if not course_module_ids:
                continue
            trainees_q = User.query
            if course_obj.allowed_category == 'citizen':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'citizen')
            elif course_obj.allowed_category == 'foreigner':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'foreigner')
            trainees = trainees_q.all()
            for user in trainees:
                user_completed_q = UserModule.query.filter(
                    UserModule.user_id == user.User_id,
                    UserModule.module_id.in_(course_module_ids),
                    UserModule.is_completed.is_(True)
                )
                completed_for_user = user_completed_q.count()
                total_for_course = len(course_module_ids)
                user_progress_pct = (completed_for_user / total_for_course * 100.0) if total_for_course else 0.0
                avg_user_score_val = user_completed_q.with_entities(db.func.avg(UserModule.score)).scalar()
                avg_user_score = round(float(avg_user_score_val or 0.0), 1)
                last_activity = user_completed_q.with_entities(db.func.max(UserModule.completion_date)).scalar()
                progress_rows.append({
                    'user_name': user.full_name,
                    'user_number_series': user.number_series,
                    'user_category': user.user_category,
                    'course_name': course.name,
                    'course_code': course.code,
                    'agency_name': user.agency.agency_name if user.agency else '',
                    'progress_pct': round(user_progress_pct, 1),
                    'completed_modules': completed_for_user,
                    'total_modules': total_for_course,
                    'score': avg_user_score,
                    'last_activity': last_activity,
                    'status': 'Completed' if user_progress_pct >= 100 else 'Active'
                })
        active_trainees = User.query.count()
        certificates_issued = Certificate.query.count()
        avg_rating_pct = 0.0
        my_courses = len(course_stats)
        progress_rows = []
        for course_stat in course_stats:
            code = course_stat['code']
            course_obj = next((c for c in courses if c.code == code), None)
            if not course_obj:
                continue
            course_module_ids = [m.module_id for m in course_obj.modules]
            if not course_module_ids:
                continue
            trainees_q = User.query
            if course_obj.allowed_category == 'citizen':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'citizen')
            elif course_obj.allowed_category == 'foreigner':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'foreigner')
            trainees = trainees_q.all()
            for user in trainees:
                user_completed_q = UserModule.query.filter(
                    UserModule.user_id == user.User_id,
                    UserModule.module_id.in_(course_module_ids),
                    UserModule.is_completed.is_(True)
                )
                completed_for_user = user_completed_q.count()
                total_for_course = len(course_module_ids)
                user_progress_pct = (completed_for_user / total_for_course * 100.0) if total_for_course else 0.0
                avg_user_score_val = user_completed_q.with_entities(db.func.avg(UserModule.score)).scalar()
                avg_user_score = round(float(avg_user_score_val or 0.0), 1)
                last_activity = user_completed_q.with_entities(db.func.max(UserModule.completion_date)).scalar()
                progress_rows.append({
                    'user_name': user.full_name,
                    'user_number_series': user.number_series,
                    'user_category': user.user_category,
                    'course_name': course.name,
                    'course_code': course.code,
                    'agency_name': user.agency.agency_name if user.agency else '',
                    'progress_pct': round(user_progress_pct, 1),
                    'completed_modules': completed_for_user,
                    'total_modules': total_for_course,
                    'score': avg_user_score,
                    'last_activity': last_activity,
                    'status': 'Completed' if user_progress_pct >= 100 else 'Active'
                })
        active_trainees = User.query.count()
        certificates_issued = Certificate.query.count()
        avg_rating_pct = 0.0
        my_courses = len(course_stats)
        progress_rows = []
        for course_stat in course_stats:
            code = course_stat['code']
            course_obj = next((c for c in courses if c.code == code), None)
            if not course_obj:
                continue
            course_module_ids = [m.module_id for m in course_obj.modules]
            if not course_module_ids:
                continue
            trainees_q = User.query
            if course_obj.allowed_category == 'citizen':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'citizen')
            elif course_obj.allowed_category == 'foreigner':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'foreigner')
            trainees = trainees_q.all()
            for user in trainees:
                user_completed_q = UserModule.query.filter(
                    UserModule.user_id == user.User_id,
                    UserModule.module_id.in_(course_module_ids),
                    UserModule.is_completed.is_(True)
                )
                completed_for_user = user_completed_q.count()
                total_for_course = len(course_module_ids)
                user_progress_pct = (completed_for_user / total_for_course * 100.0) if total_for_course else 0.0
                avg_user_score_val = user_completed_q.with_entities(db.func.avg(UserModule.score)).scalar()
                avg_user_score = round(float(avg_user_score_val or 0.0), 1)
                last_activity = user_completed_q.with_entities(db.func.max(UserModule.completion_date)).scalar()
                progress_rows.append({
                    'user_name': user.full_name,
                    'user_number_series': user.number_series,
                    'user_category': user.user_category,
                    'course_name': course.name,
                    'course_code': course.code,
                    'agency_name': user.agency.agency_name if user.agency else '',
                    'progress_pct': round(user_progress_pct, 1),
                    'completed_modules': completed_for_user,
                    'total_modules': total_for_course,
                    'score': avg_user_score,
                    'last_activity': last_activity,
                    'status': 'Completed' if user_progress_pct >= 100 else 'Active'
                })
    except Exception as e:
        logging.exception('[TRAINER PORTAL] Error building dynamic stats')
        course_stats = []
        progress_rows = []
        modules_by_course = {}
        active_trainees = 0
        certificates_issued = 0
        avg_rating_pct = 0
        my_courses = 0
    return render_template(
        'trainer_portal.html',
        trainer=current_user,
        active_trainees=active_trainees,
        my_courses=my_courses,
        certificates_issued=certificates_issued,
        avg_rating_pct=avg_rating_pct,
        course_stats=course_stats,
        progress_rows=progress_rows,
        modules_by_course=modules_by_course
    )

# Admin dashboard
@main_bp.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, Trainer):
            return redirect(url_for('main.trainer_portal'))
        if isinstance(current_user, User):
            return redirect(url_for('main.user_dashboard'))
        return redirect(url_for('main.login'))
    try:
        mgr = Management()
        dashboard = mgr.getDashboard()
    except Exception:
        dashboard = {
            'total_users': 0,
            'total_modules': 0,
            'total_certificates': 0,
            'active_trainers': 0,
            'completion_stats': [],
            'performance_metrics': None,
        }
    return render_template('admin_dashboard.html', dashboard=dashboard)

from types import SimpleNamespace

# Ensure templates always have a safe `pagination` variable to avoid Jinja UndefinedError
@main_bp.app_context_processor
def inject_pagination_defaults():
    try:
        default = SimpleNamespace(page=1, per_page=50, total_pages=1, total_count=0)
    except Exception:
        default = {'page': 1, 'per_page': 50, 'total_pages': 1, 'total_count': 0}
    return {'pagination': default}

# Admin users
@main_bp.route('/admin_users')
@login_required
def admin_users():
    if not (current_user.is_authenticated and (isinstance(current_user, Admin) or isinstance(current_user, AgencyAccount))):
        return redirect(url_for('main.login'))
    try:
        q = request.args.get('q', '').strip().lower()
        role_filter = request.args.get('role', 'all').lower()
        agency_id = request.args.get('agency_id')
        agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
        merged_accounts = []
        users_q = User.query
        if agency_id:
            try:
                users_q = users_q.filter(User.agency_id == int(agency_id))
            except ValueError:
                pass
        users = users_q.all()
        
        # Track trainer emails to avoid duplicates
        trainer_emails = set()
        trainers = Trainer.query.all()
        for t in trainers:
            trainer_emails.add(t.email.lower() if t.email else '')
        
        for u in users:
            if q and (q not in (u.full_name or '').lower() and q not in (u.email or '').lower()):
                continue
            user_role = getattr(u, 'role', 'agency')

            # Map User.role to display type
            if user_role == 'authority':
                display_type = 'authority'
            elif user_role == 'admin':
                display_type = 'admin'
            elif user_role == 'trainer':
                # Skip users with trainer role if they have a Trainer record (avoid duplicates)
                user_email = (u.email or '').lower()
                if user_email in trainer_emails:
                    continue
                display_type = 'trainer'
            else:  # 'agency' or default
                display_type = 'user'

            # Filter by role if specified
            if role_filter not in ('all', display_type):
                continue

            merged_accounts.append({
                'type': display_type,
                'id': u.User_id,
                'number_series': u.number_series,
                'name': u.full_name,
                'email': u.email,
                'agency': getattr(getattr(u, 'agency', None), 'agency_name', ''),
                'active_status': True,
            })
        
        # Add trainers from Trainer table
        for t in trainers:
            if q and (q not in (t.name or '').lower() and q not in (t.email or '').lower()):
                continue
            if role_filter not in ('all','trainer'):
                continue
            merged_accounts.append({
                'type': 'trainer',
                'id': t.trainer_id,
                'number_series': t.number_series,
                'name': t.name,
                'email': t.email,
                'agency': '',
                'active_status': t.active_status,
            })
        admins = Admin.query.all()
        for a in admins:
            if q and (q not in (a.username or '').lower() and q not in (a.email or '').lower()):
                continue
            if role_filter not in ('all','admin'):
                continue
            merged_accounts.append({
                'type': 'admin',
                'id': a.admin_id,
                'number_series': None,
                'name': a.username,
                'email': a.email,
                'agency': '',
                'active_status': True,
            })
        filters = SimpleNamespace(q=q, role=role_filter, agency_id=agency_id, status=request.args.get('status','all'))
    except Exception:
        logging.exception('[ADMIN USERS] Failed building context')
        merged_accounts = []
        agencies = []
        filters = SimpleNamespace(q='', role='all', agency_id=None, status='all')
    if isinstance(current_user, AgencyAccount):
        agency_users = User.query.filter_by(agency_id=current_user.agency_id).all()
        return render_template('agency_portal.html', agency=current_user.agency, agency_users=agency_users)
    
    # Get all courses for the course assignment dropdown
    try:
        courses = Course.query.order_by(Course.name.asc()).all()
    except Exception:
        logging.exception('[ADMIN USERS] Failed loading courses')
        courses = []
    
    return render_template('admin_users.html', merged_accounts=merged_accounts, agencies=agencies, filters=filters, courses=courses)

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
            
            year = datetime.utcnow().strftime('%Y')
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

# Admin course management
@main_bp.route('/admin_course_management', methods=['GET', 'POST'])
@login_required
def admin_course_management():
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    if request.method == 'POST':
        try:
            module_id = request.form.get('module_id')
            quiz_json = request.form.get('quiz_data')
            if not module_id or not quiz_json:
                flash('Missing module_id or quiz_json', 'danger')
                return redirect(url_for('main.admin_course_management'))
            module = db.session.get(Module, int(module_id))
            if not module:
                flash('Module not found', 'danger')
                return redirect(url_for('main.admin_course_management'))
            module.quiz_json = quiz_json
            db.session.commit()
            flash('Quiz updated successfully', 'success')
        except Exception as e:
            db.session.rollback()
            logging.exception('[ADMIN COURSE MANAGEMENT] Failed to update quiz')
            flash(f'Error updating quiz: {e}', 'danger')
        return redirect(url_for('main.admin_course_management'))
    try:
        courses = Course.query.order_by(Course.name).all()
        modules = Module.query.order_by(Module.series_number.asc()).all()

        # Debug: Log quiz data status
        logging.info(f'[ADMIN COURSE MANAGEMENT] Loaded {len(modules)} modules')
        for module in modules:
            has_quiz = bool(module.quiz_json)
            quiz_len = len(module.quiz_json) if module.quiz_json else 0
            logging.info(f'[ADMIN COURSE MANAGEMENT] Module {module.module_id} ({module.module_name}): has_quiz={has_quiz}, quiz_json_length={quiz_len}')

        # Group modules by course_id
        course_modules = {}
        for module in modules:
            course_id = module.course_id
            if course_id not in course_modules:
                course_modules[course_id] = []
            course_modules[course_id].append(module)
        # Ensure each course's module list is sorted by series (numeric-aware)
        for k in list(course_modules.keys()):
            course_modules[k] = sorted(course_modules[k], key=_module_series_sort_key)
    except Exception:
        logging.exception('[ADMIN COURSE MANAGEMENT] Failed loading data')
        courses = []
        modules = []
        course_modules = {}
    return render_template('admin_course_management.html', courses=courses, modules=modules, course_modules=course_modules)

@main_bp.route('/debug/quiz_data/<int:module_id>')
@login_required
def debug_quiz_data(module_id):
    """Debug endpoint to inspect quiz data for a module"""
    if not isinstance(current_user, Admin):
        return jsonify({'error': 'Not authorized'}), 403

    module = db.session.get(Module, module_id)
    if not module:
        return jsonify({'error': 'Module not found'}), 404

    import json
    debug_info = {
        'module_id': module.module_id,
        'module_name': module.module_name,
        'series_number': module.series_number,
        'course_id': module.course_id,
        'has_quiz_json': bool(module.quiz_json),
        'quiz_json_length': len(module.quiz_json) if module.quiz_json else 0,
        'quiz_json_raw': module.quiz_json[:500] if module.quiz_json else None,
    }

    if module.quiz_json:
        try:
            parsed = json.loads(module.quiz_json)
            debug_info['quiz_json_valid'] = True
            debug_info['quiz_json_type'] = type(parsed).__name__
            if isinstance(parsed, list):
                debug_info['question_count'] = len(parsed)
                if len(parsed) > 0:
                    debug_info['first_question'] = parsed[0]
            elif isinstance(parsed, dict):
                debug_info['quiz_keys'] = list(parsed.keys())
                if 'questions' in parsed:
                    debug_info['question_count'] = len(parsed.get('questions', []))
        except json.JSONDecodeError as e:
            debug_info['quiz_json_valid'] = False
            debug_info['parse_error'] = str(e)

    return jsonify(debug_info)

@main_bp.route('/create_course', methods=['POST'])
@login_required
def create_course():
    if not isinstance(current_user, Admin):
        flash('You are not authorized to perform this action.', 'danger')
        return redirect(url_for('main.admin_dashboard'))

    try:
        name = request.form.get('name')
        code = request.form.get('code')
        allowed_category = request.form.get('allowed_category')

        if not name or not code:
            flash('Course name and code are required.', 'danger')
            return redirect(url_for('main.admin_course_management'))

        if Course.query.filter_by(code=code).first():
            flash('A course with this code already exists.', 'danger')
            return redirect(url_for('main.admin_course_management'))

        new_course = Course(
            name=name,
            code=code,
            allowed_category=allowed_category
        )
        db.session.add(new_course)
        db.session.commit()
        flash('Course created successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logging.exception('[CREATE COURSE] Failed to create course')
        flash(f'Error creating course: {e}', 'danger')

    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/delete_course/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    if not isinstance(current_user, Admin):
        flash('You are not authorized to perform this action.', 'danger')
        return redirect(url_for('main.admin_dashboard'))

    try:
        course = db.session.get(Course, course_id)
        if not course:
            flash('Course not found.', 'danger')
            return redirect(url_for('main.admin_course_management'))

        # Manually delete related modules and user module progress
        modules = Module.query.filter_by(course_id=course.course_id).all()
        for module in modules:
            UserModule.query.filter_by(module_id=module.module_id).delete()
            db.session.delete(module)

        db.session.delete(course)
        db.session.commit()
        flash('Course and all its modules have been deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[DELETE COURSE] Failed to delete course {course_id}')
        flash(f'Error deleting course: {e}', 'danger')

    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/update_course/<int:course_id>', methods=['POST'])
@login_required
def update_course(course_id):
    if not isinstance(current_user, Admin):
        flash('You are not authorized to perform this action.', 'danger')
        return redirect(url_for('main.admin_dashboard'))

    try:
        course = db.session.get(Course, course_id)
        if not course:
            flash('Course not found.', 'danger')
            return redirect(url_for('main.admin_course_management'))

        name = request.form.get('name')
        allowed_category = request.form.get('allowed_category')

        if not name:
            flash('Course name cannot be empty.', 'danger')
        else:
            course.name = name
            course.allowed_category = allowed_category
            db.session.commit()
            flash('Course updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[UPDATE COURSE] Failed to update course {course_id}')
        flash(f'Error updating course: {e}', 'danger')

    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/add_course_module/<int:course_id>', methods=['POST'])
@login_required
def add_course_module(course_id):
    if not isinstance(current_user, Admin):
        flash('You are not authorized to perform this action.', 'danger')
        return redirect(url_for('main.admin_dashboard'))

    try:
        course = db.session.get(Course, course_id)
        if not course:
            flash('Course not found.', 'danger')
            return redirect(url_for('main.admin_course_management'))

        module_name = request.form.get('module_name')
        series_number = request.form.get('series_number')
        module_type = request.form.get('module_type', course.code)  # Default to course code

        if not module_name:
            flash('Module name is required.', 'danger')
        else:
            new_module = Module(
                module_name=module_name,
                series_number=series_number,
                course_id=course_id,
                module_type=module_type
            )
            db.session.add(new_module)
            db.session.commit()
            flash('Module added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[ADD MODULE] Failed to add module to course {course_id}')
        flash(f'Error adding module: {e}', 'danger')

    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/delete_course_module/<int:module_id>', methods=['POST'])
@login_required
def delete_course_module(module_id):
    if not isinstance(current_user, Admin):
        flash('You are not authorized to perform this action.', 'danger')
        return redirect(url_for('main.admin_dashboard'))

    try:
        module = db.session.get(Module, module_id)
        if not module:
            flash('Module not found.', 'danger')
            return redirect(url_for('main.admin_course_management'))

        # Also delete user progress for this module
        UserModule.query.filter_by(module_id=module.module_id).delete()

        db.session.delete(module)
        db.session.commit()
        flash('Module deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[DELETE MODULE] Failed to delete module {module_id}')
        flash(f'Error deleting module: {e}', 'danger')

    return redirect(url_for('main.admin_course_management'))

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
                completion_date=datetime.utcnow()
            )
            db.session.add(user_module)
        else:
            user_module.completion_status = 'completed'
            user_module.completion_date = datetime.utcnow()
        
        db.session.commit()
        flash(f'Module "{module.module_name}" marked as completed!', 'success')
        logging.info(f'[COMPLETE MODULE] User {user_id} completed module {module_id}')
        
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[COMPLETE MODULE] Failed to complete module {module_id}')
        flash(f'Error completing module: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('main.user_dashboard'))

@main_bp.route('/delete_user', methods=['POST'])
@login_required
def delete_user():
    if not (isinstance(current_user, Admin) or isinstance(current_user, AgencyAccount)):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        user_id = request.form.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'User ID is required'}), 400

        user = db.session.get(User, int(user_id))
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # Delete related records
        UserModule.query.filter_by(user_id=user.User_id).delete()
        UserCourseProgress.query.filter_by(user_id=user.User_id).delete()
        Certificate.query.filter_by(user_id=user.User_id).delete()
        WorkHistory.query.filter_by(user_id=user.User_id).delete()

        db.session.delete(user)
        db.session.commit()

        logging.info(f'[DELETE USER] User {user_id} deleted by {current_user}')
        return jsonify({'success': True, 'message': 'User deleted successfully'})
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[DELETE USER] Failed to delete user {request.form.get("user_id", "unknown")}')
        return jsonify({'success': False, 'message': f'Error deleting user: {str(e)}'}), 500

@main_bp.route('/delete_trainer', methods=['POST'])
@login_required
def delete_trainer():
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        trainer_id = request.form.get('trainer_id')
        if not trainer_id:
            return jsonify({'success': False, 'message': 'Trainer ID is required'}), 400

        trainer = db.session.get(Trainer, int(trainer_id))
        if not trainer:
            return jsonify({'success': False, 'message': 'Trainer not found'}), 404

        db.session.delete(trainer)
        db.session.commit()

        logging.info(f'[DELETE TRAINER] Trainer {trainer_id} deleted by {current_user}')
        return jsonify({'success': True, 'message': 'Trainer deleted successfully'})
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[DELETE TRAINER] Failed to delete trainer {request.form.get("trainer_id", "unknown")}')
        return jsonify({'success': False, 'message': f'Error deleting trainer: {str(e)}'}), 500

@main_bp.route('/assign_trainer_course', methods=['POST'])
@login_required
def assign_trainer_course():
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        trainer_id = request.form.get('trainer_id')
        course_code = request.form.get('course_code', '').strip()

        if not trainer_id:
            return jsonify({'success': False, 'message': 'Trainer ID is required'}), 400

        trainer = db.session.get(Trainer, int(trainer_id))
        if not trainer:
            return jsonify({'success': False, 'message': 'Trainer not found'}), 404

        # Assign course (empty string means all courses)
        trainer.course = course_code if course_code else None

        db.session.commit()

        course_name = course_code if course_code else "All Courses"
        logging.info(f'[ASSIGN COURSE] Trainer {trainer_id} assigned to course: {course_name} by {current_user}')
        
        return jsonify({
            'success': True, 
            'message': f'Trainer successfully assigned to {course_name}'
        })
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[ASSIGN COURSE] Failed to assign course to trainer {request.form.get("trainer_id", "unknown")}')
        return jsonify({'success': False, 'message': f'Error assigning course: {str(e)}'}), 500

@main_bp.route('/change_role', methods=['POST'])
@login_required
def change_role():
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        user_id = request.form.get('user_id')
        new_role = request.form.get('new_role')
        orig_type = request.form.get('orig_type')

        if not user_id or not new_role:
            return jsonify({'success': False, 'message': 'User ID and new role are required'}), 400

        # Map frontend role names to User model role values
        # User table supports: agency (regular user), authority, admin, trainer
        role_mapping = {
            'user': 'agency',      # Regular user (agency role)
            'authority': 'authority',  # Authority user (certificate approver)
            'admin': 'admin',      # Admin role
            'trainer': 'trainer'   # Trainer role
        }

        # Check if it's a valid role
        if new_role not in role_mapping:
            return jsonify({'success': False, 'message': f'Invalid role. Must be one of: user, authority, admin, trainer'}), 400

        # Only allow role changes for user accounts (not trainers/admins from separate tables)
        if orig_type not in ['user', 'authority']:
            return jsonify({'success': False, 'message': 'Can only change roles for user accounts. To create Trainers or Admins from separate tables, use the appropriate creation forms.'}), 400

        user = db.session.get(User, int(user_id))
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        old_role = user.role
        mapped_role = role_mapping[new_role]
        user.role = mapped_role
        
        # If changing to trainer role, create/sync Trainer record
        if mapped_role == 'trainer':
            existing_trainer = Trainer.query.filter_by(email=user.email).first()
            if not existing_trainer:
                # Create new Trainer record
                year = datetime.utcnow().strftime('%Y')
                seq_name = f'trainer_number_series_{year}_seq'
                
                new_trainer = Trainer(
                    name=user.full_name,
                    email=user.email,
                    address=user.address,
                    active_status=True
                )
                # Copy password from user
                new_trainer.password_hash = user.password_hash
                
                db.session.add(new_trainer)
                db.session.flush()
                
                # Generate trainer number series
                db.session.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))
                seq_val = db.session.execute(text(f"SELECT nextval('{seq_name}')")).scalar()
                new_trainer.number_series = f"TR{year}{int(seq_val):04d}"
                
                logging.info(f'[CHANGE ROLE] Created Trainer record for user {user_id} with series {new_trainer.number_series}')
            else:
                # Sync existing trainer
                existing_trainer.name = user.full_name
                existing_trainer.address = user.address
                existing_trainer.password_hash = user.password_hash
                existing_trainer.active_status = True
                logging.info(f'[CHANGE ROLE] Synced existing Trainer record for user {user_id}')
        
        db.session.commit()

        logging.info(f'[CHANGE ROLE] User {user_id} role changed from {old_role} to {mapped_role} (requested: {new_role}) by {current_user}')
        return jsonify({'success': True, 'message': f'Role successfully changed to {new_role}. {"Trainer account created." if mapped_role == "trainer" else ""}'})
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[CHANGE ROLE] Failed to change role for user {request.form.get("user_id", "unknown")}')
        return jsonify({'success': False, 'message': f'Error changing role: {str(e)}'}), 500

@main_bp.route('/update_course_module/<int:module_id>', methods=['POST'])
@login_required
def update_course_module(module_id):
    if not isinstance(current_user, Admin):
        flash('You are not authorized to perform this action.', 'danger')
        return redirect(url_for('main.admin_dashboard'))

    try:
        module = db.session.get(Module, module_id)
        if not module:
            flash('Module not found.', 'danger')
            return redirect(url_for('main.admin_course_management'))

        module_name = request.form.get('module_name')
        series_number = request.form.get('series_number')

        if not module_name:
            flash('Module name cannot be empty.', 'danger')
        else:
            module.module_name = module_name
            module.series_number = series_number
            db.session.commit()
            flash('Module updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[UPDATE MODULE] Failed to update module {module_id}')
        flash(f'Error updating module: {e}', 'danger')

    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/manage_module_content/<int:module_id>', methods=['POST'])
@login_required
def manage_module_content(module_id):
    if not isinstance(current_user, (Admin, Trainer)):
        flash('You are not authorized to perform this action.', 'danger')
        return redirect(url_for('main.login'))

    try:
        module = db.session.get(Module, module_id)
        if not module:
            flash('Module not found.', 'danger')
            return redirect(url_for('main.admin_course_management'))

        content_type = request.form.get('content_type')

        if content_type == 'slide':
            slide_text = request.form.get('slide_text')
            module.content = slide_text
            if 'slide_file' in request.files:
                file = request.files['slide_file']
                if file and allowed_slide_file(file.filename):
                    filename = secure_filename(file.filename)
                    # Prepend module ID to avoid filename conflicts
                    filename = f"mod{module.module_id}_{filename}"
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'slides', filename)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    file.save(file_path)
                    module.slide_url = f"slides/{filename}"
                    flash('Slide content updated successfully!', 'success')
                else:
                    flash('Invalid file type. Only PDF and PPTX files are allowed.', 'warning')
            else:
                flash('Slide text updated successfully!', 'success')

        elif content_type == 'video':
            youtube_url = request.form.get('youtube_url')
            module.youtube_url = youtube_url
            flash('Video content updated successfully!', 'success')

        else:
            flash('Invalid content type specified.', 'danger')

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        logging.exception(f'[MANAGE CONTENT] Failed for module {module_id}')
        flash(f'Error managing content: {e}', 'danger')

    # Redirect back with hash to preserve scroll position and module focus
    # Include course_id in hash so JavaScript can expand the correct panel
    course_id = module.course_id if module else None
    
    # Redirect to appropriate dashboard based on user type
    redirect_route = 'main.trainer_portal' if isinstance(current_user, Trainer) else 'main.admin_course_management'
    
    if course_id:
        return redirect(url_for(redirect_route, section='content') + f'#course-{course_id}-module-{module_id}')
    return redirect(url_for(redirect_route, section='content') + f'#module-{module_id}')

# Admin certificates
@main_bp.route('/admin_certificates')
@login_required
def admin_certificates():
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        # Get filter parameters
        search_query = request.args.get('q', '').strip()
        status_filter = request.args.get('status', 'all').lower()
        agency_id = request.args.get('agency_id')
        course_id = request.args.get('course_id')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        min_score = request.args.get('min_score')
        max_score = request.args.get('max_score')

        # Get agencies and courses for filters
        agencies = Agency.query.order_by(Agency.agency_name).all()
        courses = Course.query.order_by(Course.name).all()

        # Base query
        certificates_query = Certificate.query.join(User, Certificate.user_id == User.User_id).join(Module).outerjoin(Course, Course.course_id == Module.course_id)

        # Apply search filter
        if search_query:
            certificates_query = certificates_query.filter(
                or_(
                    User.full_name.ilike(f'%{search_query}%'),
                    User.email.ilike(f'%{search_query}%'),
                    Module.module_name.ilike(f'%{search_query}%'),
                    Course.name.ilike(f'%{search_query}%') if Course else True
                )
            )

        # Apply agency filter
        if agency_id:
            try:
                certificates_query = certificates_query.filter(User.agency_id == int(agency_id))
            except ValueError:
                pass

        # Apply course filter
        if course_id:
            try:
                certificates_query = certificates_query.filter(Course.course_id == int(course_id))
            except ValueError:
                pass

        # Apply date range
        if date_from:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d')
                certificates_query = certificates_query.filter(Certificate.issue_date >= from_date)
            except ValueError:
                pass
        if date_to:
            try:
                to_date = datetime.strptime(date_to, '%Y-%m-%d')
                certificates_query = certificates_query.filter(Certificate.issue_date <= to_date)
            except ValueError:
                pass

        # Apply score range
        if min_score:
            try:
                min_s = float(min_score)
                certificates_query = certificates_query.filter(Certificate.score >= min_s)
            except ValueError:
                pass
        if max_score:
            try:
                max_s = float(max_score)
                certificates_query = certificates_query.filter(Certificate.score <= max_s)
            except ValueError:
                pass

        # Apply status filter
        if status_filter == 'pending':
            certificates_query = certificates_query.filter(Certificate.certificate_path == None)
        elif status_filter == 'issued':
            certificates_query = certificates_query.filter(Certificate.certificate_path != None)

        certificates = certificates_query.order_by(Certificate.issue_date.desc()).all()

        filters = SimpleNamespace(q=search_query, status=status_filter, agency_id=agency_id, course_id=course_id, date_from=date_from, date_to=date_to, min_score=min_score, max_score=max_score)

    except Exception:
        logging.exception('[ADMIN CERTIFICATES] Failed loading certificates')
        certificates = []
        agencies = []
        courses = []
        filters = SimpleNamespace(q='', status='all', agency_id=None, course_id=None, date_from=None, date_to=None, min_score=None, max_score=None)

    return render_template('admin_certificates.html', certificates=certificates, agencies=agencies, courses=courses, filters=filters)

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
            template_folder = os.path.join(upload_folder, 'certificate_templates')
            os.makedirs(template_folder, exist_ok=True)
            filepath = os.path.join(template_folder, filename)
            file.save(filepath)
            
            # Create template record with correct field names
            template = CertificateTemplate(
                name=filename  # Use 'name' not 'template_name'
            )
            db.session.add(template)
            db.session.commit()
            
            flash(f'Certificate template "{filename}" uploaded successfully', 'success')
            logging.info(f'[UPLOAD CERT TEMPLATE] Admin uploaded: {filename}')
            
    except Exception as e:
        db.session.rollback()
        logging.exception('[UPLOAD CERT TEMPLATE] Failed to upload')
        flash(f'Error uploading template: {str(e)}', 'danger')
    
    return redirect(url_for('main.admin_certificates'))

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

@main_bp.route('/generate_and_download_certificate/<int:certificate_id>')
@login_required
def generate_and_download_certificate(certificate_id):
    """Generate and download a certificate PDF for approved certificates."""
    try:
        # Get the certificate
        cert = Certificate.query.get_or_404(certificate_id)
        
        # Authorization: only the certificate owner or admin can download
        if isinstance(current_user, User):
            if current_user.User_id != cert.user_id:
                abort(403)
        elif not isinstance(current_user, Admin):
            abort(403)
        
        # Check if certificate is approved
        if cert.status != 'approved':
            flash('Certificate must be approved before downloading', 'warning')
            return redirect(url_for('main.my_certificates'))
        
        # Import the generate_certificate function
        from generate_certificate import generate_certificate
        
        # Get the module directly from the certificate
        module = Module.query.get_or_404(cert.module_id)
        
        # Get user's average score for this course
        user = User.query.get(cert.user_id)
        modules_in_course = Module.query.filter_by(module_type=module.module_type).all()
        module_ids = [m.module_id for m in modules_in_course]
        user_modules = UserModule.query.filter(
            UserModule.user_id == cert.user_id,
            UserModule.module_id.in_(module_ids),
            UserModule.is_completed == True
        ).all()
        
        # Calculate average score
        scores = [um.score for um in user_modules if um.score is not None]
        overall_percentage = sum(scores) / len(scores) if scores else 0
        
        # Generate certificate PDF using the module's type and ID
        pdf_path = generate_certificate(
            user_id=cert.user_id,
            course_type=module.module_type,
            overall_percentage=overall_percentage,
            cert_id=f"CERT-{cert.certificate_id}",
            module_id=module.module_id
        )
        
        # Update certificate URL in database
        cert.certificate_url = pdf_path.replace('static/', '/static/')
        db.session.commit()
        
        # Send the file
        from flask import send_file
        return send_file(pdf_path, as_attachment=True, download_name=f"certificate_{cert.user_id}_{cert.module_type}.pdf")
        
    except Exception as e:
        logging.exception('[GENERATE CERTIFICATE] Error')
        flash(f'Error generating certificate: {str(e)}', 'danger')
        return redirect(url_for('main.my_certificates'))

# Monitor progress
@main_bp.route('/monitor_progress')
@login_required
def monitor_progress():
    if not (isinstance(current_user, Admin) or isinstance(current_user, AgencyAccount)):
        return redirect(url_for('main.login'))
    try:
        # Filters
        q = request.args.get('q', '').strip().lower()
        agency_id = request.args.get('agency_id')
        course_id = request.args.get('course_id')
        status_filter = request.args.get('status', '').lower()

        # For AgencyAccount, default to their agency if no agency_id specified
        if isinstance(current_user, AgencyAccount) and not agency_id:
            agency_id = current_user.agency_id

        # Get agencies and courses for filters
        agencies = Agency.query.order_by(Agency.agency_name).all()
        courses = Course.query.order_by(Course.name).all()

        # Get users
        users_q = User.query.options(db.joinedload(User.agency))
        if agency_id:
            try:
                users_q = users_q.filter(User.agency_id == int(agency_id))
            except ValueError:
                pass
        users = users_q.all()

        progress_rows = []
        for user in users:
            if q and (q not in (user.full_name or '').lower() and q not in (user.email or '').lower() and q not in (user.agency.agency_name if user.agency else '').lower()):
                continue
            for course in courses:
                if course_id and str(course.course_id) != course_id:
                    continue
                course_module_ids = [m.module_id for m in course.modules]
                if not course_module_ids:
                    continue
                user_completed_q = UserModule.query.filter(
                    UserModule.user_id == user.User_id,
                    UserModule.module_id.in_(course_module_ids),
                    UserModule.is_completed.is_(True)
                )
                completed_for_user = user_completed_q.count()
                total_for_course = len(course_module_ids)
                user_progress_pct = (completed_for_user / total_for_course * 100.0) if total_for_course else 0.0
                avg_user_score_val = user_completed_q.with_entities(db.func.avg(UserModule.score)).scalar()
                avg_user_score = round(float(avg_user_score_val or 0.0), 1)
                last_activity = user_completed_q.with_entities(db.func.max(UserModule.completion_date)).scalar()
                progress_rows.append({
                    'user_name': user.full_name,
                    'course_name': course.name,
                    'course_code': course.code,
                    'agency_name': user.agency.agency_name if user.agency else '',
                    'progress_pct': round(user_progress_pct, 1),
                    'score': avg_user_score,
                    'last_activity': last_activity,
                    'status': 'Completed' if user_progress_pct >= 100 else 'Active'
                })

        # Sort by last_activity desc
        progress_rows.sort(key=lambda r: (r['last_activity'] or datetime.min), reverse=True)
        # Limit to 500
        progress_rows = progress_rows[:500]

        filters = SimpleNamespace(q=q, agency_id=agency_id, course_id=course_id, status='')

    except Exception:
        logging.exception('[MONITOR PROGRESS] Failed loading progress data')
        progress_rows = []
        agencies = []
        courses = []
        filters = SimpleNamespace(q='', agency_id=None, course_id=None, status='')

    return render_template('monitor_progress.html', course_progress_rows=progress_rows, agencies=agencies, courses=courses, filters=filters)

# Admin agencies
@main_bp.route('/admin_agencies')
@login_required
def admin_agencies():
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        agencies = Agency.query.order_by(Agency.agency_name).all()

        # Get user count per agency
        agency_stats = []
        for agency in agencies:
            user_count = User.query.filter_by(agency_id=agency.agency_id).count()
            agency_stats.append({
                'agency': agency,
                'user_count': user_count
            })

    except Exception:
        logging.exception('[ADMIN AGENCIES] Failed loading agencies')
        agencies = []

    return render_template('admin_agencies.html', agencies=agencies)

@main_bp.route('/add_agency', methods=['POST'])
@login_required
def add_agency():
    if not isinstance(current_user, Admin):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.login'))
    
    try:
        agency_name = request.form.get('agency_name', '').strip()
        contact_number = request.form.get('contact_number', '').strip()
        address = request.form.get('address', '').strip()
        reg_of_company = request.form.get('Reg_of_Company', '').strip()
        pic = request.form.get('PIC', '').strip()
        email = request.form.get('email', '').strip()
        
        if not all([agency_name, contact_number, address, reg_of_company, pic, email]):
            flash('All fields are required', 'danger')
            return redirect(url_for('main.admin_agencies'))
        
        existing_agency = Agency.query.filter_by(agency_name=agency_name).first()
        if existing_agency:
            flash(f'Agency "{agency_name}" already exists', 'warning')
            return redirect(url_for('main.admin_agencies'))
        
        new_agency = Agency(
            agency_name=agency_name,
            contact_number=contact_number,
            address=address,
            Reg_of_Company=reg_of_company,
            PIC=pic,
            email=email
        )
        
        db.session.add(new_agency)
        db.session.commit()
        
        flash(f'Agency "{agency_name}" added successfully', 'success')
        logging.info(f'[ADD AGENCY] Admin {current_user.username} added agency: {agency_name}')
        
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[ADD AGENCY] Failed to add agency')
        flash(f'Error adding agency: {str(e)}', 'danger')
    
    return redirect(url_for('main.admin_agencies'))

@main_bp.route('/edit_agency/<int:agency_id>', methods=['POST'])
@login_required
def edit_agency(agency_id):
    if not isinstance(current_user, Admin):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.login'))
    
    try:
        agency = Agency.query.get_or_404(agency_id)
        
        agency_name = request.form.get('agency_name', '').strip()
        contact_number = request.form.get('contact_number', '').strip()
        address = request.form.get('address', '').strip()
        reg_of_company = request.form.get('Reg_of_Company', '').strip()
        pic = request.form.get('PIC', '').strip()
        email = request.form.get('email', '').strip()
        
        if not all([agency_name, contact_number, address, reg_of_company, pic, email]):
            flash('All fields are required', 'danger')
            return redirect(url_for('main.admin_agencies'))
        
        existing_agency = Agency.query.filter(
            Agency.agency_name == agency_name,
            Agency.agency_id != agency_id
        ).first()
        if existing_agency:
            flash(f'Agency name "{agency_name}" is already used by another agency', 'warning')
            return redirect(url_for('main.admin_agencies'))
        
        agency.agency_name = agency_name
        agency.contact_number = contact_number
        agency.address = address
        agency.Reg_of_Company = reg_of_company
        agency.PIC = pic
        agency.email = email
        
        db.session.commit()
        
        flash(f'Agency "{agency_name}" updated successfully', 'success')
        logging.info(f'[EDIT AGENCY] Admin {current_user.username} updated agency ID {agency_id}: {agency_name}')
        
    except Exception as e:
        db.session.rollback()
        logging.exception(f'[EDIT AGENCY] Failed to update agency {agency_id}')
        flash(f'Error updating agency: {str(e)}', 'danger')
    
    return redirect(url_for('main.admin_agencies'))

# --- Added: Agency account endpoints (portal + agency-specific progress monitor) ---
@main_bp.route('/agency_portal')
@login_required
def agency_portal():
    """Render the agency portal for AgencyAccount users."""
    # Only AgencyAccount users may view their portal
    if not isinstance(current_user, AgencyAccount):
        return redirect(url_for('main.login'))
    try:
        agency = None
        if getattr(current_user, 'agency', None):
            agency = current_user.agency
        elif getattr(current_user, 'agency_id', None):
            agency = db.session.query(Agency).filter_by(agency_id=current_user.agency_id).first()
        agency_users = []
        if agency:
            agency_users = User.query.filter_by(agency_id=agency.agency_id).all()
    except Exception:
        logging.exception('[AGENCY PORTAL] Failed loading agency users')
        agency = getattr(current_user, 'agency', None) or None
        agency_users = []
    return render_template('agency_portal.html', agency=agency, agency_users=agency_users)

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

@main_bp.route('/agency_progress_monitor')
@login_required
def agency_progress_monitor():
    """Monitor progress scoped to the logged-in agency account.
    Mirrors admin monitor_progress but locked to a single agency.
    """
    # Allow Admins to view the agency monitor as well for debugging/oversight
    if not (isinstance(current_user, AgencyAccount) or isinstance(current_user, Admin)):
        return redirect(url_for('main.login'))
    try:
        q = request.args.get('q', '').strip().lower()
        course_id = request.args.get('course_id')
        # For AgencyAccount, force agency_id to their own agency
        if isinstance(current_user, AgencyAccount):
            agency_id = current_user.agency_id
        else:
            agency_id = request.args.get('agency_id')

        courses = Course.query.order_by(Course.name).all()

        users_q = User.query.options(db.joinedload(User.agency))
        if agency_id:
            try:
                users_q = users_q.filter(User.agency_id == int(agency_id))
            except Exception:
                pass
        users = users_q.all()

        progress_rows = []
        for user in users:
            if q and (q not in (user.full_name or '').lower() and q not in (user.email or '').lower() and q not in (user.agency.agency_name if user.agency else '').lower()):
                continue
            for course in courses:
                if course_id and str(course.course_id) != course_id:
                    continue
                course_module_ids = [m.module_id for m in course.modules]
                if not course_module_ids:
                    continue
                user_completed_q = UserModule.query.filter(
                    UserModule.user_id == user.User_id,
                    UserModule.module_id.in_(course_module_ids),
                    UserModule.is_completed.is_(True)
                )
                completed_for_user = user_completed_q.count()
                total_for_course = len(course_module_ids)
                user_progress_pct = (completed_for_user / total_for_course * 100.0) if total_for_course else 0.0
                avg_user_score_val = user_completed_q.with_entities(db.func.avg(UserModule.score)).scalar()
                avg_user_score = round(float(avg_user_score_val or 0.0), 1)
                last_activity = user_completed_q.with_entities(db.func.max(UserModule.completion_date)).scalar()
                progress_rows.append({
                    'user_name': user.full_name,
                    'user_category': user.category if hasattr(user, 'category') else 'citizen',
                    'course_name': course.name,
                    'course_code': course.code,
                    'agency_name': user.agency.agency_name if user.agency else '',
                    'progress_pct': round(user_progress_pct, 1),
                    'completed_modules': completed_for_user,
                    'total_modules': total_for_course,
                    'avg_score': avg_user_score,
                    'score': avg_user_score,
                    'last_activity': last_activity,
                    'status': 'Completed' if user_progress_pct >= 100 else 'Active'
                })

        # Sort by last_activity desc
        progress_rows.sort(key=lambda r: (r['last_activity'] or datetime.min), reverse=True)
        progress_rows = progress_rows[:500]

        # Get agency for display
        agency = None
        if isinstance(current_user, AgencyAccount):
            agency = current_user.agency
        
        users_count = len(users)
        courses_with_modules_count = sum(1 for c in courses if len(c.modules) > 0)

    except Exception:
        logging.exception('[AGENCY PROGRESS] Failed loading progress data')
        progress_rows = []
        agency = None
        users_count = 0
        courses_with_modules_count = 0

    return render_template('agency_progress_monitor.html', progress_rows=progress_rows, agency=agency, users_count=users_count, courses_with_modules_count=courses_with_modules_count)

# Certificate template editor
@main_bp.route('/certificate_template_editor')
@login_required
def certificate_template_editor():
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        template = CertificateTemplate.query.filter_by(is_active=True).first()
        if not template:
            # Create default template if none exists
            template = CertificateTemplate(
                name='Default Template',
                name_x=425, name_y=290, name_font_size=28, name_visible=True,
                ic_x=425, ic_y=260, ic_font_size=14, ic_visible=True,
                course_type_x=425, course_type_y=230, course_type_font_size=14, course_type_visible=True,
                percentage_x=425, percentage_y=200, percentage_font_size=14, percentage_visible=True,
                grade_x=425, grade_y=185, grade_font_size=14, grade_visible=True,
                text_x=425, text_y=170, text_font_size=12, text_visible=True,
                date_x=425, date_y=150, date_font_size=12, date_visible=True,
                is_active=True
            )
            db.session.add(template)
            db.session.commit()
    except Exception:
        logging.exception('[CERTIFICATE TEMPLATE EDITOR] Failed loading template')
        template = None
    return render_template('certificate_template_editor.html', template=template)

# Update certificate template
@main_bp.route('/update_certificate_template', methods=['POST'])
@login_required
def update_certificate_template():
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Not authorized'}), 403
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        template = CertificateTemplate.query.filter_by(is_active=True).first()
        if not template:
            template = CertificateTemplate(is_active=True)
            db.session.add(template)

        # Update fields
        template.name_x = data.get('name_x', template.name_x)
        template.name_y = data.get('name_y', template.name_y)
        template.name_font_size = data.get('name_font_size', template.name_font_size)
        template.name_visible = data.get('name_visible', template.name_visible)

        template.ic_x = data.get('ic_x', template.ic_x)
        template.ic_y = data.get('ic_y', template.ic_y)
        template.ic_font_size = data.get('ic_font_size', template.ic_font_size)
        template.ic_visible = data.get('ic_visible', template.ic_visible)

        template.course_type_x = data.get('course_type_x', template.course_type_x)
        template.course_type_y = data.get('course_type_y', template.course_type_y)
        template.course_type_font_size = data.get('course_type_font_size', template.course_type_font_size)
        template.course_type_visible = data.get('course_type_visible', template.course_type_visible)

        template.percentage_x = data.get('percentage_x', template.percentage_x)
        template.percentage_y = data.get('percentage_y', template.percentage_y)
        template.percentage_font_size = data.get('percentage_font_size', template.percentage_font_size)
        template.percentage_visible = data.get('percentage_visible', template.percentage_visible)

        template.grade_x = data.get('grade_x', template.grade_x)
        template.grade_y = data.get('grade_y', template.grade_y)
        template.grade_font_size = data.get('grade_font_size', template.grade_font_size)
        template.grade_visible = data.get('grade_visible', template.grade_visible)

        template.text_x = data.get('text_x', template.text_x)
        template.text_y = data.get('text_y', template.text_y)
        template.text_font_size = data.get('text_font_size', template.text_font_size)
        template.text_visible = data.get('text_visible', template.text_visible)

        template.date_x = data.get('date_x', template.date_x)
        template.date_y = data.get('date_y', template.date_y)
        template.date_font_size = data.get('date_font_size', template.date_font_size)
        template.date_visible = data.get('date_visible', template.date_visible)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Template updated successfully'})
    except Exception:
        db.session.rollback()
        logging.exception('[UPDATE CERTIFICATE TEMPLATE] Failed')
        return jsonify({'success': False, 'message': 'Failed to update template'}), 500

# Get active certificate template PDF path
@main_bp.route('/api/get_active_certificate_template', methods=['GET'])
@login_required
def get_active_certificate_template():
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Not authorized'}), 403
    
    try:
        template = CertificateTemplate.query.filter_by(is_active=True).first()
        if not template or not template.name:
            return jsonify({'success': False, 'message': 'No active template found'})
        
        # The template filename is stored in the 'name' field
        template_path = url_for('static', filename='uploads/certificate_templates/' + template.name)
        return jsonify({
            'success': True,
            'template_path': template_path,
            'template_name': template.name
        })
    except Exception as e:
        logging.exception('[GET CERTIFICATE TEMPLATE] Failed')
        return jsonify({'success': False, 'message': str(e)}), 500

# Upload content
@main_bp.route('/upload_content', methods=['GET', 'POST'])
@login_required
def upload_content():
    if not isinstance(current_user, Trainer):
        return redirect(url_for('main.login'))
    if request.method == 'POST':
        # Handle upload logic here
        # For now, just flash a message
        flash('Content uploaded successfully!', 'success')
        return redirect(url_for('main.upload_content'))
    try:
        modules = Module.query.all()
    except Exception:
        modules = []
    return render_template('upload_content.html', modules=modules)

# Serve uploaded slides
@main_bp.route('/uploads/<path:filename>')
@login_required
def serve_uploaded_slide(filename):
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
    if not os.path.isabs(upload_folder):
        upload_folder = os.path.join(current_app.root_path, upload_folder)
    return send_from_directory(upload_folder, filename)

# Debug database connection
@main_bp.route('/debug_db')
@login_required
def debug_db():
    if not isinstance(current_user, Admin):
        return jsonify({'error': 'Not authorized'}), 403
    try:
        agency_count = Agency.query.count()
        cert_count = Certificate.query.count()
        user_count = User.query.count()
        module_count = Module.query.count()
        return jsonify({
            'agencies': agency_count,
            'certificates': cert_count,
            'users': user_count,
            'modules': module_count,
            'status': 'Database connected'
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'Database connection failed'
        }), 500

# Admin create agency account
@main_bp.route('/admin_create_agency_account/<int:agency_id>', methods=['POST'])
@login_required
def admin_create_agency_account(agency_id):
    if not isinstance(current_user, Admin):
        abort(403)
    try:
        agency = db.session.get(Agency, agency_id)
        if not agency:
            flash('Agency not found.', 'danger')
            return redirect(url_for('main.admin_agencies'))
        if agency.account:
            flash('Agency already has an account.', 'warning')
            return redirect(url_for('main.admin_agencies'))
        # Create account with default email and password
        email = f"{agency.agency_name.lower().replace(' ', '')}@agency.com"
        password = 'password123'  # default
        account = AgencyAccount(email=email, agency=agency)
        account.set_password(password)
        db.session.add(account)
        db.session.commit()
        flash(f'Agency account created. Email: {email}, Password: {password}', 'success')
        return redirect(url_for('main.admin_agencies'))
    except Exception as e:
        db.session.rollback()
        logging.exception('[ADMIN CREATE AGENCY ACCOUNT] Failed')
        flash('Failed to create agency account.', 'danger')
        return redirect(url_for('main.admin_agencies'))

@main_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """Handle 'forgot password' requests: generate a token and email a reset link.
    We do not reveal whether an account exists for the provided email.
    """
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter your email address.', 'danger')
            return render_template('forgot_password.html')

        # Look up any account associated with this email (do not reveal existence)
        try:
            user = User.query.filter_by(email=email).first()
            if not user:
                user = Admin.query.filter_by(email=email).first()
            if not user:
                user = Trainer.query.filter_by(email=email).first()
            if not user:
                user = AgencyAccount.query.filter_by(email=email).first()
        except Exception:
            logging.exception('[FORGOT PASSWORD] DB lookup failed')
            user = None

        # Create a token regardless; if no user exists token won't be useful but we don't disclose that.
        try:
            serializer = URLSafeTimedSerializer(current_app.config.get('SECRET_KEY'))
            token = serializer.dumps(email, salt='password-reset-salt')
            reset_link = url_for('main.reset_password', token=token, _external=True)

            subject = 'Password reset for Security Training System'
            body = f"""Hello,\n\nWe received a request to reset the password for the account associated with this email.\n\nIf this was you, click the link below to reset your password (link expires in 1 hour):\n\n{reset_link}\n\nIf you did not request this, please ignore this message.\n\n-- Security Training System"""

            # Try to use Flask-Mail if available
            mail_ext = current_app.extensions.get('mail') if hasattr(current_app, 'extensions') else None
            if mail_ext:
                try:
                    msg = Message(subject=subject, recipients=[email], body=body)
                    mail_ext.send(msg)
                except Exception:
                    # Fall back to direct SMTP send below
                    logging.exception('[FORGOT PASSWORD] Flask-Mail send failed, falling back to SMTP')
                    mail_ext = None

            if not mail_ext:
                # Fallback: send via localhost SMTP (MailHog/Dev SMTP)
                try:
                    smtp_host = current_app.config.get('MAIL_SERVER', 'localhost')
                    smtp_port = current_app.config.get('MAIL_PORT', 1025)
                    from_addr = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@example.com')
                    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
                        msg = MIMEText(body)
                        msg['Subject'] = subject
                        msg['From'] = from_addr
                        msg['To'] = email
                        smtp.sendmail(from_addr, [email], msg.as_string())
                except Exception:
                    logging.exception('[FORGOT PASSWORD] SMTP send failed')
                    # In development/debug mode, surface the reset link in the server logs so developers can copy it
                    try:
                        if current_app.debug or str(current_app.config.get('ENV','')).lower() == 'development':
                            logging.info('[FORGOT PASSWORD] Reset link (dev): %s', reset_link)
                            flash('Development: password reset link has been logged to the server console.', 'info')
                            return redirect(url_for('main.login'))
                    except Exception:
                        # ignore any failure while trying to log or flash
                        pass
                    # Don't reveal technical details in production; show generic message
                    flash('Failed to send reset email. Please contact support.', 'danger')
                    return redirect(url_for('main.login'))

            # Always show a neutral message so attackers cannot confirm account existence
            flash('If an account with that email exists, a password reset link has been sent.', 'info')
        except Exception:
            logging.exception('[FORGOT PASSWORD] Error generating or sending reset link')
            flash('An error occurred. Please try again later.', 'danger')
        return redirect(url_for('main.login'))

    return render_template('forgot_password.html')


@main_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Allow user to reset password using a token sent by email."""
    serializer = URLSafeTimedSerializer(current_app.config.get('SECRET_KEY'))
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)  # 1 hour
    except Exception:
        flash('The password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('main.forgot_password'))

    # Lookup user by email
    try:
        user = User.query.filter_by(email=email).first()
        if not user:
            user = Admin.query.filter_by(email=email).first()
        if not user:
            user = Trainer.query.filter_by(email=email).first()
        if not user:
            user = AgencyAccount.query.filter_by(email=email).first()
    except Exception:
        logging.exception('[RESET PASSWORD] DB lookup failed')
        user = None

    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        if not new_password or not confirm_password:
            flash('Please provide and confirm your new password.', 'danger')
            return render_template('reset_password.html', token=token)
        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'danger')
            return render_template('reset_password.html', token=token)
        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'danger')
            return render_template('reset_password.html', token=token)

        if not user:
            # If no user exists for this email, don't reveal it.
            flash('Password reset completed. Please log in with your new password.', 'success')
            return redirect(url_for('main.login'))

        try:
            user.set_password(new_password)
            db.session.commit()
            flash('Your password has been reset successfully. Please log in with your new password.', 'success')
            return redirect(url_for('main.login'))
        except Exception:
            db.session.rollback()
            logging.exception('[RESET PASSWORD] Failed to update password')
            flash('Failed to reset password. Please try again later.', 'danger')
            return render_template('reset_password.html', token=token)

    return render_template('reset_password.html', token=token)

# Module quiz player
@main_bp.route('/module/<int:module_id>/quiz')
@login_required
def module_quiz(module_id):
    """Render the quiz player for a specific module."""
    try:
        module = db.session.get(Module, module_id)
        if not module:
            abort(404)
        course = None
        try:
            if getattr(module, 'course_id', None):
                course = db.session.get(Course, module.course_id)
        except Exception:
            course = None
        # Load user_module progress if available
        user_module = None
        try:
            if hasattr(current_user, 'User_id'):
                user_module = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module_id).first()
            else:
                # fallback: attempt to resolve a User and load progress
                u = None
                try:
                    u = User.query.filter_by(User_id=resolve_uid()).first()
                except Exception:
                    u = None
                if u:
                    user_module = UserModule.query.filter_by(user_id=u.User_id, module_id=module_id).first()
        except Exception:
            user_module = None
        return render_template('quiz_take.html', module=module, course=course, user_module=user_module)
    except Exception:
        logging.exception('[MODULE QUIZ] Failed loading quiz page')
        abort(500)

# Quiz APIs
@main_bp.route('/api/load_quiz/<int:module_id>')
@login_required
def api_load_quiz(module_id):
    """Return quiz data for a module as JSON (list of questions).
    Supports multiple storage shapes for Module.quiz_json.
    """
    try:
        mod = db.session.get(Module, module_id)
        if not mod:
            return jsonify([]), 404
        raw = mod.quiz_json
        if not raw:
            return jsonify([])
        import json
        try:
            parsed = json.loads(raw)
        except Exception:
            # If it's not valid JSON, return empty
            return jsonify([])
        # Normalize to a list of questions: support list, or dict with 'questions'/'quiz' keys
        questions = []
        if isinstance(parsed, list):
            questions = parsed
        elif isinstance(parsed, dict):
            # Try common keys
            if 'questions' in parsed and isinstance(parsed['questions'], list):
                questions = parsed['questions']
            elif 'quiz' in parsed and isinstance(parsed['quiz'], list):
                questions = parsed['quiz']
            else:
                # If dict looks like a single question, wrap it
                # Accept keys 'text' and 'answers'
                if 'text' in parsed and 'answers' in parsed:
                    questions = [parsed]
                else:
                    # Unknown structure -> return empty
                    questions = []
        else:
            questions = []
        # Ensure each question has answers array with 'text' and optional 'isCorrect'
        out = []
        for q in questions:
            if not isinstance(q, dict):
                continue
            q_text = q.get('text') or q.get('question') or ''
            answers = []
            raw_answers = q.get('answers') or q.get('choices') or []
            if isinstance(raw_answers, dict):
                # convert dict to list of {text:..., isCorrect:...}
                for k, v in raw_answers.items():
                    if isinstance(v, dict):
                        answers.append({'text': v.get('text', str(v)), 'isCorrect': bool(v.get('isCorrect', False))})
                    else:
                        answers.append({'text': str(v), 'isCorrect': False})
            elif isinstance(raw_answers, list):
                for a in raw_answers:
                    if isinstance(a, dict):
                        answers.append({'text': a.get('text', ''), 'isCorrect': bool(a.get('isCorrect', False))})
                    else:
                        answers.append({'text': str(a), 'isCorrect': False})
            # Find correct index
            correct_idx = -1
            if isinstance(q, dict):
                if isinstance(q.get('correctIndex'), int):
                    correct_idx = q.get('correctIndex')
                elif isinstance(q.get('correct'), int):
                    correct_idx = q.get('correct')
                elif isinstance(q.get('correct'), str) and q.get('correct').isdigit():
                    correct_idx = int(q.get('correct'))
            # Inspect answers for isCorrect
            if isinstance(raw_answers, list):
                for i, a in enumerate(raw_answers):
                    if isinstance(a, dict):
                        if a.get('isCorrect') or a.get('is_correct') or a.get('correct') is True or a.get('isAnswer') or a.get('answer_is_correct'):
                            correct_idx = i
                            break
            # Set isCorrect on the correct answer
            if correct_idx != -1 and correct_idx < len(answers):
                answers[correct_idx]['isCorrect'] = True
            out.append({'text': q_text, 'answers': answers, 'correctIndex': correct_idx})
        return jsonify(out)
    except Exception:
        logging.exception('[API] load_quiz')
        return jsonify([]), 500


@main_bp.route('/api/user_quiz_answers/<int:module_id>')
@login_required
def api_get_user_quiz_answers(module_id):
    """Return saved answers array for the current user and module.
    Simpler, robust behavior:
    - Resolve the current user id.
    - Return parsed JSON array when possible.
    - If stored value is a non-JSON string or otherwise unparsable, attempt a safe fallback parsing (comma/bracket split) and return an array of values or nulls.
    """
    try:
        # Resolve user id
        uid = None
        try:
            uid = resolve_uid()
        except Exception:
            uid = getattr(current_user, 'User_id', None)
        if not uid:
            try:
                uid = int(session.get('user_id'))
            except Exception:
                uid = None
        if not uid:
            logging.info('[API user_quiz_answers] No user id available')
            return jsonify([]), 400

        um = UserModule.query.filter_by(user_id=uid, module_id=module_id).first()
        if not um or not getattr(um, 'quiz_answers', None):
            return jsonify([])

        raw = um.quiz_answers
        # If already a Python list, return it
        if isinstance(raw, (list, tuple)):
            return jsonify(list(raw))

        # If it's bytes, decode
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode('utf-8')
            except Exception:
                try:
                    raw = raw.decode('latin-1')
                except Exception:
                    raw = str(raw)

        # If it's a string, try JSON first
        if isinstance(raw, str):
            s = raw.strip()
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return jsonify(parsed)
                # Some systems may have stored a quoted JSON string, try again
                if isinstance(parsed, str):
                    try:
                        parsed2 = json.loads(parsed)
                        if isinstance(parsed2, list):
                            return jsonify(parsed2)
                    except Exception:
                        pass
            except Exception:
                pass

            # Fallback: simple bracket or comma-split parsing
            if s.startswith('[') and s.endswith(']'):
                inner = s[1:-1].strip()
                if inner == '':
                    return jsonify([])
                parts = [p.strip() for p in inner.split(',')]
                out = []
                for p in parts:
                    if p.lower() in ('null', 'none'):
                        out.append(None)
                    elif (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
                        out.append(p[1:-1])
                    else:
                        # try numeric
                        try:
                            if '.' in p:
                                f = float(p)
                                if f.is_integer():
                                    out.append(int(f))
                                else:
                                    out.append(f)
                            else:
                                out.append(int(p))
                        except Exception:
                            out.append(p)
                return jsonify(out)

            # Comma-separated without brackets
            if ',' in s:
                parts = [p.trim() if hasattr(p, 'trim') else p.strip() for p in s.split(',')]
                out = []
                for p in parts:
                    if p.lower() in ('null', 'none'):
                        out.append(None)
                    else:
                        try:
                            out.append(int(p))
                        except Exception:
                            try:
                                f = float(p)
                                out.append(int(f) if f.is_integer() else f)
                            except Exception:
                                out.append(p)
                return jsonify(out)

        # As a last resort, return the raw string as single-element array
        return jsonify([raw])
    except Exception:
        logging.exception('[API] user_quiz_answers')
        return jsonify([]), 500


@main_bp.route('/api/save_quiz_answers/<int:module_id>', methods=['POST'])
@login_required
def api_save_quiz_answers(module_id):
    """Save partial answers for the logged-in user for a module.
    This implementation accepts JSON bodies and will persist whatever array is provided (including arrays containing nulls).
    """
    try:
        # Accept JSON body or raw data; prefer JSON
        data = None
        try:
            data = request.get_json(force=False, silent=True)
        except Exception:
            data = None
        if not data:
            # Try raw bytes / form data
            try:
                raw = request.data or request.get_data(as_text=True)
                import json
                if raw:
                    data = json.loads(raw)
            except Exception:
                data = None
        answers = None
        if isinstance(data, dict):
            answers = data.get('answers')
        # Also accept direct array payload (e.g., POST with raw JSON array)
        if answers is None and isinstance(data, list):
            answers = data
        # If still None, try form value
        if answers is None and 'answers' in request.form:
            try:
                import json
                answers = json.loads(request.form.get('answers'))
            except Exception:
                answers = None

        if answers is None:
            # Nothing usable provided
            return jsonify({'success': False, 'message': 'No answers provided'}), 400

        # Resolve numeric user id robustly
        uid = None
        try:
            uid = resolve_uid()
        except Exception:
            uid = getattr(current_user, 'User_id', None)
        if not uid:
            try:
                uid = int(session.get('user_id'))
            except Exception:
                uid = None
        if not uid:
            return jsonify({'success': False, 'message': 'User not identified'}), 400

        import json
        um = UserModule.query.filter_by(user_id=uid, module_id=module_id).first()
        if not um:
            um = UserModule(user_id=uid, module_id=module_id, quiz_answers=json.dumps(answers))
            db.session.add(um)
        else:
            um.quiz_answers = json.dumps(answers)
        db.session.commit()
        return jsonify({'success': True})
    except Exception:
        logging.exception('[API] save_quiz_answers')
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Server error'}), 500


@main_bp.route('/api/debug_quiz_raw/<int:module_id>')
@login_required
def api_debug_quiz_raw(module_id):
    """Return raw UserModule.quiz_answers for debugging (only for logged-in user).
    Simpler debug output: raw stored value and a best-effort parsed JSON.
    """
    try:
        # Resolve numeric user id robustly
        uid = None
        try:
            uid = resolve_uid()
        except Exception:
            uid = getattr(current_user, 'User_id', None)
        if not uid:
            try:
                uid = int(session.get('user_id'))
            except Exception:
                uid = None
        if not uid:
            return jsonify({'success': False, 'message': 'User not identified'}), 400
        um = UserModule.query.filter_by(user_id=uid, module_id=module_id).first()
        if not um:
            return jsonify({'success': False, 'message': 'No UserModule found', 'raw': None})
        raw = um.quiz_answers
        parsed = None
        try:
            import json
            if isinstance(raw, str):
                parsed = json.loads(raw)
            elif isinstance(raw, (list, tuple)):
                parsed = list(raw)
        except Exception:
            parsed = None
        return jsonify({
            'success': True,
            'raw': raw,
            'parsed': parsed,
            'module_id': module_id,
            'user_id': uid
        })
    except Exception:
        logging.exception('[API] debug_quiz_raw')
        return jsonify({'success': False, 'message': 'Server error'}), 500

@main_bp.route('/api/submit_quiz/<int:module_id>', methods=['POST'])
@login_required
def api_submit_quiz(module_id):
    """Evaluate submitted answers, update UserModule, and return score/grade."""
    try:
        payload = request.get_json() or {}
        answers = payload.get('answers') if isinstance(payload, dict) else None
        is_reattempt = bool(payload.get('is_reattempt')) if isinstance(payload, dict) else False
        if answers is None:
            return jsonify({'success': False, 'message': 'No answers provided'}), 400

        mod = db.session.get(Module, module_id)
        if not mod:
            return jsonify({'success': False, 'message': 'Module not found'}), 404

        # Load quiz canonical data
        import json
        try:
            parsed = json.loads(mod.quiz_json) if mod.quiz_json else []
        except Exception:
            parsed = []

        # Normalize to questions list (reuse same shape as api_load_quiz)
        questions = []
        if isinstance(parsed, list):
            questions = parsed
        elif isinstance(parsed, dict):
            if 'questions' in parsed and isinstance(parsed['questions'], list):
                questions = parsed['questions']
            elif 'quiz' in parsed and isinstance(parsed['quiz'], list):
                questions = parsed['quiz']
            elif 'text' in parsed and 'answers' in parsed:
                questions = [parsed]
            else:
                questions = []

        # Extract correct indices using the robust detection rules
        correct_indices = []
        for q in questions:
            raw_answers = q.get('answers') if isinstance(q, dict) else []
            correct_idx = -1
            # check question-level keys
            if isinstance(q, dict):
                if isinstance(q.get('correctIndex'), int):
                    correct_idx = q.get('correctIndex')
                elif isinstance(q.get('correct'), int):
                    correct_idx = q.get('correct')
                elif isinstance(q.get('correct'), str) and q.get('correct').isdigit():
                    correct_idx = int(q.get('correct'))
            # inspect answers
            if isinstance(raw_answers, list):
                for i, a in enumerate(raw_answers):
                    if isinstance(a, dict):
                        if a.get('isCorrect') or a.get('is_correct') or a.get('correct') is True or a.get('isAnswer') or a.get('answer_is_correct'):
                            correct_idx = i
                            break
                        # if 'correct' is numeric index stored on an answer dict, handled above
            correct_indices.append(correct_idx)

        # Score calculation
        total = len(correct_indices)
        if total == 0:
            score = 0
        else:
            correct_count = 0
            for i in range(min(len(answers), total)):
                try:
                    user_ans = int(answers[i])
                except Exception:
                    user_ans = None
                if user_ans is not None and user_ans == correct_indices[i] and correct_indices[i] != -1:
                    correct_count += 1
            score = round((correct_count / total) * 100, 0)

        # Persist to UserModule
        # Resolve numeric user id robustly
        uid = None
        try:
            uid = resolve_uid()
        except Exception:
            uid = getattr(current_user, 'User_id', None)
        if not uid:
            try:
                uid = int(session.get('user_id'))
            except Exception:
                uid = None
        if not uid:
            return jsonify({'success': False, 'message': 'User not identified'}), 400

        um = UserModule.query.filter_by(user_id=uid, module_id=module_id).first()
        if not um:
            um = UserModule(user_id=uid, module_id=module_id, quiz_answers=json.dumps(answers), is_completed=True, score=float(score), completion_date=datetime.utcnow(), reattempt_count=1 if is_reattempt else 0)
            db.session.add(um)
        else:
            # Update answers
            um.quiz_answers = json.dumps(answers)
            # Increase reattempt count when reattempt
            if is_reattempt:
                um.reattempt_count = (um.reattempt_count or 0) + 1
            # Mark completed and update score only if it's better
            um.is_completed = True
            if um.score is None or float(score) > float(um.score):
                um.score = float(score)
            um.completion_date = datetime.utcnow()
        db.session.commit()
        grade_letter = um.get_grade_letter() if um else 'A'
        return jsonify({'success': True, 'score': int(score), 'grade_letter': grade_letter, 'reattempt_count': um.reattempt_count if um else 0, 'answers': answers, 'correct_indices': correct_indices})
    except Exception:
        logging.exception('[API] submit_quiz')
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Server error'}), 500

@main_bp.route('/api/complete_course', methods=['POST'])
@login_required
def api_complete_course():
    """Complete a course and create pending certificate for authority approval."""
    try:
        payload = request.get_json() or {}
        course_code = payload.get('course_code')
        
        if not course_code:
            return jsonify({'success': False, 'message': 'Course code required'}), 400
        
        # Get current user
        uid = resolve_uid()
        if not uid:
            return jsonify({'success': False, 'message': 'User not identified'}), 400
        
        user = User.query.get(uid)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Check if user is eligible for certificate
        if not user.EligibleForCertificate(course_code):
            return jsonify({'success': False, 'message': 'Not eligible. Complete all modules with 50% average score.'}), 400
        
        # Check if certificate already exists for this course
        existing_cert = Certificate.query.filter_by(user_id=uid, module_type=course_code).first()
        if existing_cert:
            if existing_cert.status == 'pending':
                return jsonify({'success': True, 'already_submitted': True, 'message': 'Already submitted for approval'}), 200
            elif existing_cert.status == 'approved':
                return jsonify({'success': True, 'already_approved': True, 'message': 'Certificate already approved'}), 200
        
        # Get all modules for this course to associate certificate with one
        modules = Module.query.filter_by(module_type=course_code).all()
        if not modules:
            return jsonify({'success': False, 'message': 'No modules found for this course'}), 404
        
        # Sort modules to pick a representative one (first by series or id)
        try:
            modules_sorted = sorted(modules, key=lambda m: (m.series_number or '', m.module_id))
            representative_module = modules_sorted[0]
        except Exception:
            representative_module = modules[0]
        
        # Create pending certificate
        from datetime import date
        new_cert = Certificate(
            user_id=uid,
            module_type=course_code,
            module_id=representative_module.module_id,
            issue_date=date.today(),
            status='pending'
        )
        db.session.add(new_cert)
        db.session.commit()
        
        logging.info(f'[COURSE_COMPLETE] User {uid} completed course {course_code}, pending certificate created')
        return jsonify({'success': True, 'submitted': True, 'message': 'Course completed! Sent for approval.'}), 200
        
    except Exception as e:
        logging.exception('[API] complete_course error')
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@main_bp.route('/admin_debug_quiz/<int:module_id>')
@login_required
def admin_debug_quiz(module_id):
    """Admin helper: return raw and normalized quiz JSON for a module.
    Useful to inspect shapes that the admin quiz builder will try to load.
    """
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Not authorized'}), 403
    try:
        mod = db.session.get(Module, module_id)
        if not mod:
            return jsonify({'success': False, 'message': 'Module not found'}), 404
        raw = mod.quiz_json
        if not raw:
            return jsonify({'success': True, 'raw': None, 'normalized': []})
        import json
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
        # Try to normalize similar to the admin preloadExisting logic
        def normalize(obj):
            if obj is None:
                return []
            # If it's already a list of new-format
            if isinstance(obj, list) and obj:
                first = obj[0]
                if isinstance(first, dict) and (first.get('text') or isinstance(first.get('answers'), list) and isinstance(first.get('answers')[0] if first.get('answers') else None, dict)):
                    return obj
                # legacy list with question/answers
                if isinstance(first, dict) and (first.get('question') or isinstance(first.get('answers'), list)):
                    out = []
                    for q in obj:
                        raw_answers = q.get('answers') or q.get('choices') or []
                        mapped = []
                        if isinstance(raw_answers, list):
                            for i,a in enumerate(raw_answers):
                                if isinstance(a, dict):
                                    mapped.append({'text': a.get('text', str(a)), 'isCorrect': bool(a.get('isCorrect', False))})
                                else:
                                    is_corr = False
                                    try:
                                        is_corr = (q.get('correct') is not None and int(q.get('correct')) == (i+1))
                                    except Exception:
                                        is_corr = False
                                    mapped.append({'text': str(a), 'isCorrect': is_corr})
                        out.append({'text': q.get('question') or q.get('text') or '', 'answers': mapped})
                    return out
            # object with questions key
            if isinstance(obj, dict):
                if isinstance(obj.get('questions'), list):
                    return normalize(obj.get('questions'))
                if isinstance(obj.get('quiz'), list):
                    return normalize(obj.get('quiz'))
                if obj.get('text') and obj.get('answers'):
                    raw_answers = obj.get('answers') or []
                    mapped = []
                    if isinstance(raw_answers, list):
                        for a in raw_answers:
                            if isinstance(a, dict):
                                mapped.append({'text': a.get('text', str(a)), 'isCorrect': bool(a.get('isCorrect', False))})
                            else:
                                mapped.append({'text': str(a), 'isCorrect': False})
                    return [{'text': obj.get('text'), 'answers': mapped}]
            return []
        normalized = normalize(parsed)
        return jsonify({'success': True, 'raw': raw, 'parsed_sample': parsed if isinstance(parsed, (list, dict)) else None, 'normalized': normalized})
    except Exception:
        logging.exception('[ADMIN DEBUG QUIZ]')
        return jsonify({'success': False, 'message': 'Server error'}), 500
