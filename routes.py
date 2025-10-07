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
from models import db, Admin, User, Agency, Module, Certificate, Trainer, UserModule, Management, Registration, Course, WorkHistory, UserCourseProgress, AgencyAccount
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, or_
from utils import safe_url_for, normalized_user_category, safe_parse_date, extract_youtube_id, is_slide_file, allowed_file

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
        return render_template('signup.html', agencies=agencies)
    return render_template('signup.html', agencies=agencies)

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

# Profile
@main_bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

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
        ag = db.session.get(Agency, getattr(current_user, 'agency_id', None)) if hasattr(current_user, 'agency_id') else None
    except Exception:
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
                    'course_code': code,
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

# Admin monitor progress
@main_bp.route('/monitor_progress')
@login_required
def monitor_progress():
    if not (current_user.is_authenticated and isinstance(current_user, Admin)):
        return redirect(url_for('main.login'))
    try:
        q = request.args.get('q', '').strip().lower()
        agency_id = request.args.get('agency_id')
        course_id = request.args.get('course_id')
        status = request.args.get('status', '').lower()
        min_progress = request.args.get('min_progress')
        max_progress = request.args.get('max_progress')

        agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
        courses = Course.query.order_by(Course.name.asc()).all()

        # Base query for users
        users_query = User.query
        if agency_id:
            users_query = users_query.filter(User.agency_id == int(agency_id))

        users = users_query.all()

        course_progress_rows = []
        for user in users:
            # Get user's agency
            agency = user.agency.agency_name if user.agency else ''

            # Filter courses based on user's category
            user_cat = normalized_user_category(user)
            courses_for_user = [c for c in courses if c.allowed_category in (user_cat, 'both')]

            if course_id:
                courses_for_user = [c for c in courses_for_user if c.course_id == int(course_id)]

            for course in courses_for_user:
                # Check if user name/email matches query
                if q and q not in user.full_name.lower() and q not in (user.email or '').lower() and q not in agency.lower() and q not in course.name.lower() and q not in course.code.lower():
                    continue

                # Get modules for this course
                modules = course.modules
                total_modules = len(modules)
                if total_modules == 0:
                    continue

                module_ids = [m.module_id for m in modules]

                # Get completed modules for this user
                completed_q = UserModule.query.filter(
                    UserModule.user_id == user.User_id,
                    UserModule.module_id.in_(module_ids),
                    UserModule.is_completed == True
                )
                completed_modules = completed_q.count()
                progress_pct = (completed_modules / total_modules) * 100

                # Filter by progress range
                if min_progress:
                    try:
                        if progress_pct < float(min_progress):
                            continue
                    except ValueError:
                        pass
                if max_progress:
                    try:
                        if progress_pct > float(max_progress):
                            continue
                    except ValueError:
                        pass

                # Filter by status
                if status == 'in_progress' and progress_pct >= 100:
                    continue
                elif status == 'completed' and progress_pct < 100:
                    continue

                # Average score
                scores = [um.score for um in completed_q.all() if um.score is not None]
                avg_score = sum(scores) / len(scores) if scores else None

                course_progress_rows.append({
                    'user_name': user.full_name,
                    'course_name': course.name,
                    'course_code': course.code,
                    'agency_name': agency,
                    'completed_modules': completed_modules,
                    'total_modules': total_modules,
                    'progress_pct': round(progress_pct, 1),
                    'avg_score': round(avg_score, 1) if avg_score else None
                })

        # Sort by progress descending
        course_progress_rows.sort(key=lambda x: x['progress_pct'], reverse=True)

        filters = SimpleNamespace(q=q, agency_id=agency_id, course_id=course_id, status=status, min_progress=min_progress, max_progress=max_progress)

    except Exception:
        logging.exception('[MONITOR PROGRESS] Failed building context')
        course_progress_rows = []
        agencies = []
        courses = []
        filters = SimpleNamespace(q='', agency_id=None, course_id=None, status='', min_progress=None, max_progress=None)

    return render_template('monitor_progress.html', course_progress_rows=course_progress_rows, agencies=agencies, courses=courses, filters=filters)

# Admin agencies
@main_bp.route('/admin_agencies')
@login_required
def admin_agencies():
    if not (current_user.is_authenticated and isinstance(current_user, Admin)):
        return redirect(url_for('main.login'))
    try:
        agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
    except Exception:
        logging.exception('[ADMIN AGENCIES] Failed loading agencies')
        agencies = []
    return render_template('admin_agencies.html', agencies=agencies)

@main_bp.route('/add_agency', methods=['POST'])
@login_required
def add_agency():
    if not (current_user.is_authenticated and isinstance(current_user, Admin)):
        return redirect(url_for('main.login'))
    try:
        agency_name = request.form.get('agency_name', '').strip()
        contact_number = request.form.get('contact_number', '').strip()
        address = request.form.get('address', '').strip()
        reg_of_company = request.form.get('Reg_of_Company', '').strip()
        pic = request.form.get('PIC', '').strip()
        email = request.form.get('email', '').strip()

        if not all([agency_name, contact_number, address, reg_of_company, pic, email]):
            flash('All fields are required', 'error')
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
        flash(f'Agency "{agency_name}" added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logging.exception('[ADD AGENCY] Failed to add agency')
        flash(f'Failed to add agency: {str(e)}', 'error')
    return redirect(url_for('main.admin_agencies'))

@main_bp.route('/edit_agency/<int:agency_id>', methods=['POST'])
@login_required
def edit_agency(agency_id):
    if not (current_user.is_authenticated and isinstance(current_user, Admin)):
        return redirect(url_for('main.login'))
    try:
        agency = Agency.query.get_or_404(agency_id)
        agency.agency_name = request.form.get('agency_name', '').strip()
        agency.contact_number = request.form.get('contact_number', '').strip()
        agency.address = request.form.get('address', '').strip()
        agency.Reg_of_Company = request.form.get('Reg_of_Company', '').strip()
        agency.PIC = request.form.get('PIC', '').strip()
        agency.email = request.form.get('email', '').strip()

        if not all([agency.agency_name, agency.contact_number, agency.address, agency.Reg_of_Company, agency.PIC, agency.email]):
            flash('All fields are required', 'error')
            return redirect(url_for('main.admin_agencies'))

        db.session.commit()
        flash(f'Agency "{agency.agency_name}" updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logging.exception('[EDIT AGENCY] Failed to edit agency')
        flash(f'Failed to update agency: {str(e)}', 'error')
    return redirect(url_for('main.admin_agencies'))

@main_bp.route('/admin_create_agency_account/<int:agency_id>', methods=['POST'])
@login_required
def admin_create_agency_account(agency_id):
    if not (current_user.is_authenticated and isinstance(current_user, Admin)):
        return redirect(url_for('main.login'))
    try:
        agency = Agency.query.get_or_404(agency_id)

        # Check if account already exists
        existing = AgencyAccount.query.filter_by(agency_id=agency_id).first()
        if existing:
            flash(f'Agency "{agency.agency_name}" already has a login account!', 'warning')
            return redirect(url_for('main.admin_agencies'))

        # Create agency account using agency email
        new_account = AgencyAccount(
            agency_id=agency_id,
            email=agency.email,
            role='agency'
        )
        # Set a default password (agency should change this on first login)
        default_password = f"agency{agency_id}@2025"
        new_account.set_password(default_password)

        db.session.add(new_account)
        db.session.commit()

        flash(f'Login created for "{agency.agency_name}"! Email: {agency.email}, Password: {default_password}', 'success')
    except IntegrityError:
        db.session.rollback()
        flash(f'Email {agency.email} is already in use', 'error')
    except Exception as e:
        db.session.rollback()
        logging.exception('[CREATE AGENCY ACCOUNT] Failed')
        flash(f'Failed to create login: {str(e)}', 'error')
    return redirect(url_for('main.admin_agencies'))

# Agency create user
@main_bp.route('/agency_create_user', methods=['POST'])
@login_required
def agency_create_user():
    if not isinstance(current_user, AgencyAccount):
        return redirect(url_for('main.login'))

    agency = getattr(current_user, 'agency', None)
    if not agency:
        flash('Agency not found.', 'danger')
        return redirect(url_for('main.agency_portal'))

    try:
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user_category = request.form.get('user_category', 'citizen').strip().lower()

        if not full_name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('main.agency_portal'))

        data = {
            'full_name': full_name,
            'email': email,
            'password': password,
            'user_category': 'foreigner' if user_category == 'foreigner' else 'citizen',
            'agency_id': agency.agency_id
        }

        new_user = Registration.registerUser(data)
        flash(f'User "{full_name}" created successfully.', 'success')
    except ValueError as ve:
        flash(str(ve), 'danger')
    except Exception:
        logging.exception('[AGENCY CREATE USER] Failed')
        flash('Failed to create user.', 'danger')

    return redirect(url_for('main.agency_portal'))

# Admin course management
@main_bp.route('/admin_course_management')
@login_required
def admin_course_management():
    if not (current_user.is_authenticated and isinstance(current_user, Admin)):
        return redirect(url_for('main.login'))
    try:
        courses = Course.query.order_by(Course.name.asc()).all()
        course_modules = {}
        for c in courses:
            mods = Module.query.filter_by(course_id=c.course_id).order_by(Module.series_number.asc()).all()
            course_modules[c.course_id] = mods
    except Exception:
        logging.exception('[ADMIN COURSE MGMT] Error loading courses')
        courses = []
        course_modules = {}
    return render_template('admin_course_management.html', courses=courses, course_modules=course_modules)

# ===== Admin: Course & Module CRUD =====
@main_bp.route('/create_course', methods=['POST'])
@login_required
def create_course():
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        name = (request.form.get('name') or '').strip()
        code = (request.form.get('code') or '').strip()
        allowed = (request.form.get('allowed_category') or 'both').strip().lower()
        if not name or not code:
            flash('Name and code are required', 'danger')
            return redirect(url_for('main.admin_course_management'))
        if allowed not in ('citizen', 'foreigner', 'both'):
            allowed = 'both'
        c = Course(name=name, code=code.upper(), allowed_category=allowed)
        db.session.add(c)
        db.session.commit()
        flash('Course created', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[CREATE COURSE] failed')
        flash('Failed to create course', 'danger')
    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/update_course/<int:course_id>', methods=['POST'])
@login_required
def update_course(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        c = db.session.get(Course, course_id)
        if not c:
            flash('Course not found', 'danger')
            return redirect(url_for('main.admin_course_management'))
        c.name = (request.form.get('name') or c.name or '').strip()
        allowed = (request.form.get('allowed_category') or c.allowed_category or 'both').strip().lower()
        if allowed in ('citizen','foreigner','both'):
            c.allowed_category = allowed
        db.session.commit()
        flash('Course updated', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[UPDATE COURSE] failed')
        flash('Failed to update course', 'danger')
    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/delete_course/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        c = db.session.get(Course, course_id)
        if not c:
            flash('Course not found', 'danger')
            return redirect(url_for('main.admin_course_management'))
        # Optionally cascade delete modules
        for m in list(c.modules):
            db.session.delete(m)
        db.session.delete(c)
        db.session.commit()
        flash('Course deleted', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[DELETE COURSE] failed')
        flash('Failed to delete course', 'danger')
    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/add_course_module/<int:course_id>', methods=['POST'])
@login_required
def add_course_module(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        course = db.session.get(Course, course_id)
        if not course:
            flash('Course not found', 'danger')
            return redirect(url_for('main.admin_course_management'))
        name = (request.form.get('module_name') or '').strip()
        series = (request.form.get('series_number') or '').strip()
        if not name:
            flash('Module name is required', 'danger')
            return redirect(url_for('main.admin_course_management'))
        m = Module(module_name=name, series_number=series or None, module_type=course.code, course_id=course.course_id)
        db.session.add(m)
        db.session.commit()
        flash('Module created', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[ADD MODULE] failed')
        flash('Failed to add module', 'danger')
    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/update_course_module/<int:module_id>', methods=['POST'])
@login_required
def update_course_module(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        m = db.session.get(Module, module_id)
        if not m:
            flash('Module not found', 'danger')
            return redirect(url_for('main.admin_course_management'))
        m.module_name = (request.form.get('module_name') or m.module_name or '').strip()
        m.series_number = (request.form.get('series_number') or '').strip() or None
        db.session.commit()
        flash('Module updated', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[UPDATE MODULE] failed')
        flash('Failed to update module', 'danger')
    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/delete_course_module/<int:module_id>', methods=['POST'])
@login_required
def delete_course_module(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        m = db.session.get(Module, module_id)
        if not m:
            flash('Module not found', 'danger')
            return redirect(url_for('main.admin_course_management'))
        db.session.delete(m)
        db.session.commit()
        flash('Module deleted', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[DELETE MODULE] failed')
        flash('Failed to delete module', 'danger')
    return redirect(url_for('main.admin_course_management'))

@main_bp.route('/manage_module_content/<int:module_id>', methods=['POST'])
@login_required
def manage_module_content(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('main.login'))
    try:
        m = db.session.get(Module, module_id)
        if not m:
            flash('Module not found', 'danger')
            return redirect(url_for('main.admin_course_management'))
        ctype = (request.form.get('content_type') or '').strip().lower()
        if ctype == 'slide':
            file = request.files.get('slide_file')
            slide_text = request.form.get('slide_text')
            if file and file.filename:
                fname = secure_filename(file.filename)
                # ensure unique filename
                name, ext = os.path.splitext(fname)
                upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                candidate = fname
                i = 1
                while os.path.exists(os.path.join(upload_dir, candidate)):
                    candidate = f"{name}_{i}{ext}"
                    i += 1
                file.save(os.path.join(upload_dir, candidate))
                m.slide_url = candidate
            if slide_text is not None:
                m.content = slide_text
            db.session.commit()
            flash('Slides saved', 'success')
        elif ctype == 'video':
            youtube_url = (request.form.get('youtube_url') or '').strip()
            m.youtube_url = youtube_url or None
            db.session.commit()
            flash('Video saved', 'success')
        elif ctype == 'quiz':
            import json as _json
            # Prefer explicit JSON
            quiz_data = request.form.get('quiz_data')
            quiz_list = None
            if quiz_data:
                try:
                    quiz_list = _json.loads(quiz_data)
                except Exception:
                    quiz_list = None
            if not isinstance(quiz_list, list):
                # Fallback: reconstruct from numbered fields
                quiz_list = []
                # Attempt up to 50 questions
                for qi in range(1, 51):
                    qtext = (request.form.get(f'quiz_question_{qi}') or '').strip()
                    if not qtext:
                        continue
                    answers = []
                    # up to 5 answers
                    for ai in range(1, 6):
                        atext = (request.form.get(f'answer_{qi}_{ai}') or '').strip()
                        if atext:
                            answers.append({'text': atext, 'isCorrect': False})
                    corr_raw = request.form.get(f'correct_answer_{qi}')
                    try:
                        corr_idx = int(corr_raw) - 1 if corr_raw else 0
                    except Exception:
                        corr_idx = 0
                    if answers:
                        if 0 <= corr_idx < len(answers):
                            answers[corr_idx]['isCorrect'] = True
                        else:
                            answers[0]['isCorrect'] = True
                        quiz_list.append({'text': qtext, 'answers': answers})
            # Persist
            m.quiz_json = _json.dumps(quiz_list or [], ensure_ascii=False)
            db.session.commit()
            flash('Quiz saved', 'success')
        else:
            flash('Unknown content type', 'danger')
    except Exception:
        db.session.rollback()
        logging.exception('[MANAGE MODULE CONTENT] failed')
        flash('Failed to save content', 'danger')
    return redirect(url_for('main.admin_course_management'))

# Admin certificates
@main_bp.route('/admin_certificates')
@login_required
def admin_certificates():
    if not (current_user.is_authenticated and isinstance(current_user, Admin)):
        return redirect(url_for('main.login'))
    certs = []
    try:
        certs = Certificate.query.order_by(Certificate.issue_date.desc()).all()
    except Exception:
        logging.exception('[ADMIN CERTIFICATES] Failed loading certificates')
    return render_template('admin_certificates.html', certificates=certs)

# File serving routes
@main_bp.route('/uploads/<path:filename>')
def serve_upload(filename):
    profile_dir = os.path.join('static', 'profile_pics')
    slides_dir = os.path.join('static', 'uploads')
    candidate = os.path.join(profile_dir, filename)
    if os.path.exists(candidate):
        return send_from_directory(profile_dir, filename)
    candidate = os.path.join(slides_dir, filename)
    if os.path.exists(candidate):
        return send_from_directory(slides_dir, filename)
    return abort(404)

@main_bp.route('/slides/<path:filename>')
@login_required
def serve_uploaded_slide(filename):
    slides_dir = os.path.join('static', 'uploads')
    return send_from_directory(slides_dir, filename)

# Agency portal
@main_bp.route('/agency_portal')
@login_required
def agency_portal():
    if not isinstance(current_user, AgencyAccount):
        if isinstance(current_user, Admin):
            return redirect(url_for('main.admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('main.trainer_portal'))
        if isinstance(current_user, User):
            return redirect(url_for('main.user_dashboard'))
        return redirect(url_for('main.login'))

    # Get agency details from current_user
    agency = getattr(current_user, 'agency', None)
    agency_id = getattr(agency, 'agency_id', None)

    # Query users belonging to this agency
    agency_users = []
    if agency_id:
        try:
            agency_users = User.query.filter_by(agency_id=agency_id).order_by(User.full_name.asc()).all()
        except Exception as e:
            logging.exception('[AGENCY PORTAL] Failed to load agency users')
            agency_users = []

    return render_template('agency_portal.html', account=current_user, agency=agency, agency_users=agency_users)

# Agency progress monitor
@main_bp.route('/agency_progress_monitor')
@login_required
def agency_progress_monitor():
    if not isinstance(current_user, AgencyAccount):
        return redirect(url_for('main.login'))

    agency = getattr(current_user, 'agency', None)
    if not agency:
        flash('Agency not found.', 'danger')
        return redirect(url_for('main.agency_portal'))

    agency_id = agency.agency_id

    try:
        # Get all users in this agency
        users = User.query.filter_by(agency_id=agency_id).all()

        # Get all courses
        courses = Course.query.order_by(Course.name.asc()).all()

        progress_rows = []
        for user in users:
            user_cat = normalized_user_category(user)
            courses_for_user = [c for c in courses if c.allowed_category in (user_cat, 'both')]

            for course in courses_for_user:
                modules = course.modules
                total_modules = len(modules)
                if total_modules == 0:
                    continue

                module_ids = [m.module_id for m in modules]

                # Get completed modules for this user
                completed_q = UserModule.query.filter(
                    UserModule.user_id == user.User_id,
                    UserModule.module_id.in_(module_ids),
                    UserModule.is_completed == True
                )
                completed_modules = completed_q.count()
                progress_pct = (completed_modules / total_modules) * 100

                # Average score
                scores = [um.score for um in completed_q.all() if um.score is not None]
                avg_score = sum(scores) / len(scores) if scores else None

                status = 'Completed' if progress_pct >= 100 else 'In Progress'

                progress_rows.append({
                    'user_name': user.full_name,
                    'user_number_series': user.number_series,
                    'user_category': user_cat,
                    'course_name': course.name,
                    'course_code': course.code,
                    'progress_pct': round(progress_pct, 1),
                    'completed_modules': completed_modules,
                    'total_modules': total_modules,
                    'avg_score': round(avg_score, 1) if avg_score else None,
                    'status': status
                })

        # Sort by user name, then course
        progress_rows.sort(key=lambda x: (x['user_name'], x['course_name']))

    except Exception:
        logging.exception('[AGENCY PROGRESS MONITOR] Failed building context')
        progress_rows = []

    return render_template('agency_progress_monitor.html', progress_rows=progress_rows, agency=agency)

# Agency update details
@main_bp.route('/agency_update_details', methods=['POST'])
@login_required
def agency_update_details():
    if not isinstance(current_user, AgencyAccount):
        return redirect(url_for('main.login'))

    agency = getattr(current_user, 'agency', None)
    if not agency:
        flash('Agency not found.', 'danger')
        return redirect(url_for('main.agency_portal'))

    try:
        agency.agency_name = request.form.get('agency_name', '').strip()
        agency.PIC = request.form.get('PIC', '').strip()
        agency.email = request.form.get('email', '').strip()
        agency.contact_number = request.form.get('contact_number', '').strip()
        agency.address = request.form.get('address', '').strip()

        db.session.commit()
        flash('Agency details updated successfully.', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[AGENCY UPDATE DETAILS] Failed')
        flash('Failed to update agency details.', 'danger')

    return redirect(url_for('main.agency_portal'))

# Onboarding route (referenced in signup)
@main_bp.route('/onboarding/<int:id>', methods=['GET', 'POST'])
@login_required
def onboarding(id):
    if not isinstance(current_user, User) or current_user.User_id != id:
        return redirect(url_for('main.index'))

    total_steps = 4  # Adjust this number based on your actual onboarding steps

    if request.method == 'POST':
        step = int(request.form.get('step', 1))
        if 'skip' in request.form:
            return redirect(url_for('main.user_dashboard'))

        # Update user based on step
        if step == 1:
            current_user.full_name = request.form.get('full_name', '').strip()
            current_user.user_category = request.form.get('user_category', 'citizen').strip().lower()
            if current_user.user_category == 'citizen':
                current_user.ic_number = request.form.get('ic_number', '').strip()
                current_user.passport_number = None
            else:
                current_user.passport_number = request.form.get('passport_number', '').strip()
                current_user.ic_number = None
            # Handle profile pic upload
            if 'profile_pic' in request.files:
                file = request.files['profile_pic']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    upload_dir = os.path.join(current_app.root_path, 'static', 'profile_pics')
                    os.makedirs(upload_dir, exist_ok=True)
                    file_path = os.path.join(upload_dir, filename)
                    file.save(file_path)
                    current_user.Profile_picture = filename
        elif step == 2:
            current_user.emergency_contact_phone = request.form.get('emergency_contact_phone', '').strip()
            current_user.postcode = request.form.get('postcode', '').strip()
            current_user.address = request.form.get('address', '').strip()
            current_user.state = request.form.get('state', '').strip()
            current_user.country = request.form.get('country', '').strip()
        elif step == 3:
            current_user.current_workplace = request.form.get('current_workplace', '').strip()
            current_user.recruitment_date = safe_parse_date(request.form.get('recruitment_date'))
            # Handle work histories
            WorkHistory.query.filter_by(user_id=id).delete()
            exp_companies = request.form.getlist('exp_company')
            exp_positions = request.form.getlist('exp_position')
            exp_recruitments = request.form.getlist('exp_recruitment')
            exp_starts = request.form.getlist('exp_start')
            exp_ends = request.form.getlist('exp_end')
            exp_visa_numbers = request.form.getlist('exp_visa_number')
            exp_visa_expiries = request.form.getlist('exp_visa_expiry')
            for i in range(len(exp_companies)):
                company = exp_companies[i].strip() if i < len(exp_companies) else ''
                if not company:
                    continue
                position = exp_positions[i].strip() if i < len(exp_positions) else ''
                recruitment_date = safe_parse_date(exp_recruitments[i] if i < len(exp_recruitments) else '')
                start_date = safe_parse_date(exp_starts[i] if i < len(exp_starts) else '')
                end_date = safe_parse_date(exp_ends[i] if i < len(exp_ends) else '')
                visa_number = (exp_visa_numbers[i].strip() if i < len(exp_visa_numbers) and exp_visa_numbers[i] else None)
                visa_expiry = safe_parse_date(exp_visa_expiries[i] if i < len(exp_visa_expiries) else '')
                # start_date and end_date are required (NOT NULL) on WorkHistory
                if not start_date or not end_date:
                    continue
                wh = WorkHistory(
                    user_id=id,
                    company_name=company,
                    position_title=position,
                    recruitment_date=recruitment_date,
                    start_date=start_date,
                    end_date=end_date,
                    visa_number=visa_number,
                    visa_expiry_date=visa_expiry
                )
                db.session.add(wh)
        elif step == 4:
            # Finalize onboarding
            current_user.is_finalized = True
        # Commit changes for any step
        try:
            db.session.commit()
            if step >= total_steps:
                flash('Onboarding complete. Welcome aboard!', 'success')
                return redirect(url_for('main.user_dashboard'))
            else:
                flash('Your progress has been saved.', 'success')
                return redirect(url_for('main.onboarding', id=id))
        except Exception:
            db.session.rollback()
            logging.exception('[ONBOARDING] Failed to save step %s', step)
            flash('Failed to save your changes. Please try again.', 'danger')
    # GET request: render onboarding page
    current_step = int(request.args.get('step', 1))
    return render_template('onboarding.html', user=current_user, step=current_step, total_steps=total_steps)

# Course modules page
@main_bp.route('/modules/<string:course_code>')
@login_required
def course_modules(course_code):
    # Only users, trainers, admins, or agency accounts may access; for users, filter by allowed_category
    try:
        course = Course.query.filter(Course.code.ilike(course_code)).first()
    except Exception:
        course = None
    if not course:
        return abort(404)
    # Build modules list and user progress
    try:
        modules = Module.query.filter_by(course_id=course.course_id).order_by(Module.series_number.asc()).all()
    except Exception:
        modules = []
    # Fallback by module_type if no course linkage
    if not modules:
        try:
            modules = Module.query.filter(Module.module_type.ilike(course_code)).order_by(Module.series_number.asc()).all()
        except Exception:
            modules = []
    # User progress mapping
    user_progress = {}
    try:
        if isinstance(current_user, User):
            ums = UserModule.query.filter(UserModule.user_id == current_user.User_id, UserModule.module_id.in_([m.module_id for m in modules])).all()
            user_progress = {um.module_id: um for um in ums}
    except Exception:
        user_progress = {}
    # Determine unlocked status: first is unlocked; next unlocked only if previous completed
    prev_completed = True
    ordered = modules
    for m in ordered:
        unlocked = bool(prev_completed)
        setattr(m, 'unlocked', unlocked)
        um = user_progress.get(m.module_id)
        prev_completed = bool(um and um.is_completed)
    # Compute overall percentage for header (average of scores for modules in this course)
    try:
        scores = [um.score for um in user_progress.values() if um.score is not None]
        overall_percentage = round(sum(scores) / len(scores), 1) if scores else 0
    except Exception:
        overall_percentage = 0
    return render_template(
        'course_modules.html',
        course_name=course.name,
        modules=ordered,
        user_progress=user_progress,
        overall_percentage=overall_percentage
    )

def _normalize_quiz_items(raw_list):
    """Normalize a list of quiz items to [{text:str, answers:[{text:str,isCorrect:bool}]}]."""
    import json as _json
    norm = []
    if not isinstance(raw_list, list):
        return norm
    for q in raw_list:
        if isinstance(q, str):
            # String question unsupported without answers
            continue
        if not isinstance(q, dict):
            continue
        # Extract question text from known keys
        q_text = (q.get('text') or q.get('question') or q.get('title') or q.get('q') or '').strip()
        answers_raw = q.get('answers') or q.get('options') or q.get('choices') or []
        correct_index = None
        # Common patterns for correct index stored at question level
        for ck in ('correct', 'correct_index', 'correctAnswer', 'correct_answer'):
            if ck in q:
                try:
                    # Accept 1-based or 0-based; transform to 0-based
                    val = int(q.get(ck))
                    correct_index = val - 1 if val > 0 else val
                except Exception:
                    correct_index = None
                break
        a_norm = []
        if isinstance(answers_raw, list):
            for idx, a in enumerate(answers_raw):
                if isinstance(a, dict):
                    a_text = (a.get('text') or a.get('answer') or a.get('label') or a.get('option') or '').strip()
                    is_corr = bool(a.get('isCorrect') or a.get('correct') or False)
                else:
                    # Primitive answer (string or number)
                    a_text = str(a)
                    is_corr = False
                # If no per-answer correctness, apply question-level correct_index
                if not is_corr and correct_index is not None and idx == correct_index:
                    is_corr = True
                if a_text == '':
                    continue
                a_norm.append({'text': a_text, 'isCorrect': bool(is_corr)})
        # Fallback: some shapes use keys answer_1..answer_5
        if not a_norm:
            tmp = []
            for i in range(1, 6):
                key = f'answer_{i}'
                if key in q and str(q.get(key)).strip():
                    tmp.append(str(q.get(key)).strip())
            if tmp:
                for idx, txt in enumerate(tmp):
                    is_corr = (correct_index is not None and idx == correct_index)
                    a_norm.append({'text': txt, 'isCorrect': is_corr})
        # Ensure at least two answers and a question text
        if q_text and len(a_norm) >= 2:
            # Ensure at least one correct
            if not any(a.get('isCorrect') for a in a_norm):
                a_norm[0]['isCorrect'] = True
            norm.append({'text': q_text, 'answers': a_norm})
    return norm

# Load quiz JSON for a module
@main_bp.route('/api/load_quiz/<int:module_id>')
@login_required
def api_load_quiz(module_id):
    try:
        m = db.session.get(Module, module_id)
    except Exception:
        m = None
    if not m:
        return jsonify({'error': 'Module not found'}), 404
    import json as _json
    def _normalize_quiz(obj):
        # Accept list directly
        if isinstance(obj, list):
            return obj
        # Accept dicts with common keys: quiz, questions, data, items
        if isinstance(obj, dict):
            for key in ('quiz', 'questions', 'data', 'items'):
                val = obj.get(key)
                if isinstance(val, list):
                    return val
        # Fallback empty
        return []
    try:
        raw = m.quiz_json or '[]'
        data = _json.loads(raw)
        # Handle double-encoded JSON strings
        if isinstance(data, str):
            try:
                data = _json.loads(data)
            except Exception:
                data = []
        data = _normalize_quiz(data)
        data = _normalize_quiz_items(data)
    except Exception:
        data = []
    return jsonify(data)

# Quiz page for a module
@main_bp.route('/module/<int:module_id>/quiz')
@login_required
def module_quiz(module_id):
    try:
        module = db.session.get(Module, module_id)
    except Exception:
        module = None
    if not module:
        return abort(404)
    # Resolve course for back navigation
    course = None
    if module.course_id:
        try:
            course = db.session.get(Course, module.course_id)
        except Exception:
            course = None
    if not course:
        try:
            course = Course.query.filter(Course.code.ilike(module.module_type)).first()
        except Exception:
            course = None
    # Pass user progress for this module so template can reflect completion
    user_module = None
    try:
        if isinstance(current_user, User):
            user_module = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module_id).first()
    except Exception:
        user_module = None
    return render_template('quiz_take.html', module=module, course=course, user_module=user_module)

# Check if user agreed to disclaimer for a module
@main_bp.route('/api/check_module_disclaimer/<int:module_id>')
@login_required
def api_check_module_disclaimer(module_id):
    if not isinstance(current_user, User):
        return jsonify({'success': False, 'message': 'Only users can perform this action'}), 403
    try:
        agreed = current_user.has_agreed_to_module_disclaimer(module_id)
        return jsonify({'success': True, 'has_agreed': bool(agreed)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Record disclaimer agreement
@main_bp.route('/api/agree_module_disclaimer/<int:module_id>', methods=['POST'])
@login_required
def api_agree_module_disclaimer(module_id):
    if not isinstance(current_user, User):
        return jsonify({'success': False, 'message': 'Only users can perform this action'}), 403
    try:
        ok = current_user.agree_to_module_disclaimer(module_id)
        return jsonify({'success': bool(ok)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# ========== Quiz authoring/admin endpoints ==========
@main_bp.route('/api/save_quiz', methods=['POST'])
@login_required
def api_save_quiz():
    """Save quiz content for a module (admin/trainer only).
    Expected JSON: { module_id: int, quiz: [ { text, answers: [ {text,isCorrect}, ... ] }, ... ] }
    """
    # Allow Admins and Trainers to save quizzes
    if not (isinstance(current_user, Admin) or isinstance(current_user, Trainer)):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    import json as _json
    try:
        payload = request.get_json(silent=True) or {}
        module_id = int(payload.get('module_id') or 0)
        raw_quiz = payload.get('quiz')
        if not module_id or raw_quiz is None:
            return jsonify({'success': False, 'message': 'module_id and quiz are required'}), 400
        m = db.session.get(Module, module_id)
        if not m:
            return jsonify({'success': False, 'message': 'Module not found'}), 404
        # Ensure quiz is a list
        if not isinstance(raw_quiz, list):
            # Try common wrapper keys
            if isinstance(raw_quiz, dict):
                raw_quiz = raw_quiz.get('quiz') or raw_quiz.get('questions') or []
            else:
                return jsonify({'success': False, 'message': 'quiz must be an array'}), 400
        # Lightweight validation/normalization
        norm = []
        for q in raw_quiz:
            if not isinstance(q, dict):
                continue
            text = str(q.get('text') or '').strip()
            answers = q.get('answers') or []
            if not text:
                continue
            if not isinstance(answers, list) or len(answers) < 2:
                continue
            # Trim to max 5 answers for safety; ensure at least one correct
            a_norm = []
            any_correct = False
            for a in answers[:5]:
                if not isinstance(a, dict):
                    continue
                at = str(a.get('text') or '').strip()
                ic = bool(a.get('isCorrect'))
                if at == '':
                    continue
                any_correct = any_correct or ic
                a_norm.append({'text': at, 'isCorrect': ic})
            if not a_norm:
                continue
            if not any_correct:
                # default first as correct if none marked
                a_norm[0]['isCorrect'] = True
            norm.append({'text': text, 'answers': a_norm})
        # Persist
        m.quiz_json = _json.dumps(norm, ensure_ascii=False)
        db.session.commit()
        return jsonify({'success': True, 'count': len(norm)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# ========== Quiz player endpoints ==========
@main_bp.route('/api/user_quiz_answers/<int:module_id>')
@login_required
def api_user_quiz_answers(module_id):
    if not isinstance(current_user, User):
        return jsonify([])
    import json as _json
    try:
        um = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module_id).first()
        if not um or not um.quiz_answers:
            return jsonify([])
        data = _json.loads(um.quiz_answers)
        return jsonify(data if isinstance(data, list) else [])
    except Exception:
        return jsonify([])

@main_bp.route('/api/save_quiz_answers/<int:module_id>', methods=['POST'])
@login_required
def api_save_quiz_answers(module_id):
    if not isinstance(current_user, User):
        return jsonify({'success': False, 'message': 'Only users can perform this action'}), 403
    import json as _json
    try:
        payload = request.get_json(silent=True) or {}
        answers = payload.get('answers')
        if not isinstance(answers, list):
            return jsonify({'success': False, 'message': 'answers must be an array'}), 400
        # Upsert user-module row
        um = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module_id).first()
        if not um:
            um = UserModule(user_id=current_user.User_id, module_id=module_id, is_completed=False, reattempt_count=0)
            db.session.add(um)
        um.quiz_answers = _json.dumps(answers)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/api/submit_quiz/<int:module_id>', methods=['POST'])
@login_required
def api_submit_quiz(module_id):
    if not isinstance(current_user, User):
        return jsonify({'success': False, 'message': 'Only users can perform this action'}), 403
    import json as _json
    # Load module and quiz
    m = None
    try:
        m = db.session.get(Module, module_id)
    except Exception:
        m = None
    if not m:
        return jsonify({'success': False, 'message': 'Module not found'}), 404
    # Parse quiz
    try:
        raw = m.quiz_json or '[]'
        qdata = _json.loads(raw)
        if isinstance(qdata, str):
            qdata = _json.loads(qdata)
    except Exception:
        qdata = []
    if isinstance(qdata, dict):
        qdata = qdata.get('quiz') or qdata.get('questions') or qdata.get('data') or qdata.get('items') or []
    # Normalize items so we can score reliably
    qdata = _normalize_quiz_items(qdata)
    if not isinstance(qdata, list) or len(qdata) == 0:
        return jsonify({'success': False, 'message': 'No quiz configured'}), 400
    # Read submitted answers
    payload = request.get_json(silent=True) or {}
    answers = payload.get('answers')
    is_reattempt = bool(payload.get('is_reattempt'))
    if not isinstance(answers, list):
        # If not provided, fallback to saved partial
        try:
            um_prev = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module_id).first()
            answers = _json.loads(um_prev.quiz_answers) if (um_prev and um_prev.quiz_answers) else []
        except Exception:
            answers = []
    # Compute score
    total = len(qdata)
    correct = 0
    correct_indices = []
    for qi, q in enumerate(qdata):
        ans_list = q.get('answers') if isinstance(q, dict) else None
        corr_idx = None
        if isinstance(ans_list, list):
            for ai, a in enumerate(ans_list):
                if isinstance(a, dict) and a.get('isCorrect'):
                    corr_idx = ai
                    break
        correct_indices.append(corr_idx if corr_idx is not None else -1)
        chosen = answers[qi] if (isinstance(answers, list) and qi < len(answers)) else None
        if isinstance(chosen, int) and corr_idx is not None and chosen == corr_idx:
            correct += 1
    score_pct = round((correct / total) * 100.0, 1)
    # Upsert user-module record and mark complete
    try:
        um = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module_id).first()
        if not um:
            um = UserModule(user_id=current_user.User_id, module_id=module_id)
            db.session.add(um)
        if is_reattempt and um.is_completed:
            um.reattempt_count = (um.reattempt_count or 0) + 1
        um.quiz_answers = _json.dumps(answers if isinstance(answers, list) else [])
        um.score = score_pct
        um.is_completed = True
        um.completion_date = datetime.now()
        db.session.commit()
        # Compute grade letter from per-module attempts
        grade_letter = um.get_grade_letter() if hasattr(um, 'get_grade_letter') else 'A'
        return jsonify({
            'success': True,
            'score': score_pct,
            'correct': correct,
            'total': total,
            'correct_indices': correct_indices,
            'grade_letter': grade_letter,
            'reattempt_count': (um.reattempt_count or 0)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# Quick maintenance: Recalculate certificate star ratings from scores
@main_bp.route('/recalculate_ratings', methods=['GET'])
@login_required
def recalculate_ratings():
    # Only admins can trigger this
    if not isinstance(current_user, Admin):
        if isinstance(current_user, Trainer):
            return redirect(url_for('main.trainer_portal'))
        if isinstance(current_user, User):
            return redirect(url_for('main.user_dashboard'))
        return redirect(url_for('main.login'))
    try:
        updated = 0
        skipped = 0
        # Map a numeric score (0..100) to 1..5 stars
        def score_to_stars(score: float | int | None) -> int | None:
            if score is None:
                return None
            try:
                s = float(score)
            except Exception:
                return None
            if s < 0:
                s = 0
            if s > 100:
                s = 100
            # 0-19.999:1, 20-39.999:2, 40-59.999:3, 60-79.999:4, 80-100:5
            if s < 20:
                return 1
            if s < 40:
                return 2
            if s < 60:
                return 3
            if s < 80:
                return 4
            return 5
        certs = Certificate.query.all()
        for c in certs:
            new_star = score_to_stars(c.score)
            if new_star != c.star_rating:
                c.star_rating = new_star
                updated += 1
            else:
                skipped += 1
        db.session.commit()
        flash(f'Recalculated star ratings. Updated: {updated}, Unchanged: {skipped}.', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[RECALCULATE RATINGS] Failed')
        flash('Failed to recalculate ratings due to a server error.', 'danger')
    return redirect(url_for('main.admin_dashboard'))
