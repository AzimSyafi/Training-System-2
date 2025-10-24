"""
Routes for Training System app, using Flask Blueprint.
All route functions from app.py are moved here.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory, abort, current_app
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import logging
from models import db, Admin, User, Agency, Module, Certificate, Trainer, UserModule, Management, Registration, Course, WorkHistory, UserCourseProgress, AgencyAccount, CertificateTemplate
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, or_
from utils import safe_url_for, normalized_user_category, safe_parse_date, extract_youtube_id, is_slide_file, allowed_file
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Message
import smtplib
from email.mime.text import MIMEText

main_bp = Blueprint('main', __name__)

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
            return redirect(url_for('main.onboarding', id=new_user.User_id))
        except ValueError as ve:
            flash(str(ve), 'danger')
        except Exception as e:
            logging.exception('[SIGNUP] Registration failed')
            flash('Registration failed due to server error. Please try again later.', 'danger')
        return render_template('signup.html', agencies=agencies, countries=countries)
    return render_template('signup.html', agencies=agencies, countries=countries)

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
            return redirect(url_for('main.agency_portal'))
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
            mods = c.modules
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
            modules = list(c.modules)
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
        modules = list(course.modules)
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
                    current_user.profile_pic = filename

            # Handle working experiences
            # First, delete existing experiences
            WorkHistory.query.filter_by(user_id=current_user.User_id).delete()

            # Get experience data from form
            exp_companies = request.form.getlist('exp_company')
            exp_positions = request.form.getlist('exp_position')
            exp_recruitments = request.form.getlist('exp_recruitment')
            exp_starts = request.form.getlist('exp_start')
            exp_ends = request.form.getlist('exp_end')
            exp_visas = request.form.getlist('exp_visa_number')
            exp_visa_expiries = request.form.getlist('exp_visa_expiry')

            for i in range(len(exp_companies)):
                if exp_companies[i].strip():  # Only save if company is provided
                    exp = WorkHistory(
                        user_id=current_user.User_id,
                        company_name=exp_companies[i],
                        position_title=exp_positions[i] if i < len(exp_positions) else None,
                        recruitment_date=safe_parse_date(exp_recruitments[i]) if i < len(exp_recruitments) else None,
                        start_date=safe_parse_date(exp_starts[i]) if i < len(exp_starts) else None,
                        end_date=safe_parse_date(exp_ends[i]) if i < len(exp.ends) else None,
                        visa_number=exp_visas[i] if i < len(exp_visas) else None,
                        visa_expiry_date=safe_parse_date(exp_visa_expiries[i]) if i < len(exp_visa_expiries) else None
                    )
                    db.session.add(exp)

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
            ag = getattr(current_user, 'agency', None)
            return render_template('agency.html', agency=ag)
    except Exception:
        if isinstance(current_user, Admin):
            agencies = []
            return render_template('admin_agencies.html', agencies=agencies)
        else:
            ag = None
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
            modules = course.modules
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
                    'course_name': course.name,
                    'course_code': course.code,
                    'agency_name': user.agency.agency_name if user.agency else '',
                    'completed_modules': completed_for_user,
                    'total_modules': total_for_course,
                    'progress_pct': round(user_progress_pct, 1),
                    'score': avg_user_score,
                    'last_activity': last_activity,
                    'status': 'Active' if user_progress_pct < 100 else 'Completed'
                })
        progress_rows.sort(key=lambda r: (r['last_activity'] or datetime.min), reverse=True)
        progress_rows = progress_rows[:25]
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

# Admin users
@main_bp.route('/admin_users')
@login_required
def admin_users():
    if not (current_user.is_authenticated and isinstance(current_user, Admin)):
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
        for u in users:
            if q and (q not in (u.full_name or '').lower() and q not in (u.email or '').lower() and q not in (u.number_series or '').lower()):
                continue
            user_role = getattr(u, 'role', 'agency')
            if user_role == 'authority':
                if role_filter not in ('all', 'authority'):
                    continue
                merged_accounts.append({
                    'type': 'authority',
                    'id': u.User_id,
                    'number_series': u.number_series,
                    'name': u.full_name,
                    'email': u.email,
                    'agency': getattr(getattr(u, 'agency', None), 'agency_name', ''),
                    'active_status': True,
                })
            else:
                if role_filter not in ('all','user'):
                    continue
                merged_accounts.append({
                    'type': 'user',
                    'id': u.User_id,
                    'number_series': u.number_series,
                    'name': u.full_name,
                    'email': u.email,
                    'agency': getattr(getattr(u, 'agency', None), 'agency_name', ''),
                    'active_status': True,
                })
        trainers = Trainer.query.all()
        for t in trainers:
            if q and (q not in (t.name or '').lower() and q not in (t.email or '').lower() and q not in (t.number_series or '').lower()):
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
    return render_template('admin_users.html', merged_accounts=merged_accounts, agencies=agencies)

# Admin course management
@main_bp.route('/admin_course_management')
@login_required
def admin_course_management():
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        courses = Course.query.order_by(Course.name).all()
        modules = Module.query.order_by(Module.module_name).all()
        # Group modules by course_id
        course_modules = {}
        for module in modules:
            course_id = module.course_id
            if course_id not in course_modules:
                course_modules[course_id] = []
            course_modules[course_id].append(module)
    except Exception:
        logging.exception('[ADMIN COURSE MANAGEMENT] Failed loading data')
        courses = []
        modules = []
        course_modules = {}
    return render_template('admin_course_management.html', courses=courses, modules=modules, course_modules=course_modules)

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

# Monitor progress
@main_bp.route('/monitor_progress')
@login_required
def monitor_progress():
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        # Filters
        q = request.args.get('q', '').strip().lower()
        agency_id = request.args.get('agency_id')
        course_id = request.args.get('course_id')
        status_filter = request.args.get('status', '').lower()

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
            if q and (q not in (user.full_name or '').lower() and q not in (user.email or '').lower() and q not in (user.number_series or '').lower() and q not in (user.agency.agency_name if user.agency else '').lower()):
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
                if status_filter:
                    if status_filter == 'completed' and user_progress_pct < 100:
                        continue
                    if status_filter == 'active' and user_progress_pct >= 100:
                        continue
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

        filters = SimpleNamespace(q=q, agency_id=agency_id, course_id=course_id, status=status_filter)

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
