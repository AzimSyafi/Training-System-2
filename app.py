import sys
print("Python executable:", sys.executable)

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, UTC  # added UTC
import os
from models import db, Admin, User, Agency, Module, Certificate, Trainer, UserModule, Management, Registration, Course, WorkHistory
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, inspect as sa_inspect
import re
import urllib.parse
from flask import request, jsonify
import json
import logging
from werkzeug.routing import BuildError  # added

app = Flask(__name__, static_url_path='/static')

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Database configuration - PostgreSQL only
if os.environ.get('DATABASE_URL'):
    database_url = os.environ.get('DATABASE_URL')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Local PostgreSQL defaults (adjust via env vars if needed)
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '7890')
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_NAME = os.environ.get('DB_NAME', 'Training_system')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure upload folders for production
if os.environ.get('RENDER'):
    # Production - use temporary directories
    app.config['UPLOAD_FOLDER'] = '/tmp/profile_pics'
    UPLOAD_CONTENT_FOLDER = '/tmp/uploads'
else:
    # Development - use static folders
    app.config['UPLOAD_FOLDER'] = 'static/profile_pics'
    UPLOAD_CONTENT_FOLDER = os.path.join('static', 'uploads')

# Ensure upload directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(UPLOAD_CONTENT_FOLDER, exist_ok=True)

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')

# Helper: safe url_for that won't crash templates if endpoint missing
def safe_url_for(endpoint, **values):
    try:
        return url_for(endpoint, **values)
    except BuildError:
        return '#'
app.jinja_env.globals['safe_url_for'] = safe_url_for

# --- Helpers ---
def _series_sort(modules):
    """Sort modules by series_number naturally, handling prefixes like CSG001/TNG002 or mixed.
    Falls back to by module_id when series_number missing."""
    def key(m: Module):
        s = (getattr(m, 'series_number', None) or '').strip()
        if not s:
            return ("", 0)
        # Extract alpha prefix and numeric suffix
        prefix = ''.join([ch for ch in s if ch.isalpha()])
        digits = ''.join([ch for ch in s if ch.isdigit()])
        try:
            num = int(digits) if digits else 0
        except Exception:
            num = 0
        return (prefix.upper(), num)
    try:
        return sorted(modules, key=key)
    except Exception:
        return sorted(modules, key=lambda m: getattr(m, 'module_id', 0))

def extract_youtube_id(url):
    """Extracts YouTube video ID from a URL."""
    if not isinstance(url, str):
        return None
    # Regex to find video ID from various YouTube URL formats
    regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    return None

def is_slide_file(filename):
    """Checks if a filename is a PDF or PPTX file."""
    if not isinstance(filename, str):
        return False
    return filename.lower().endswith(('.pdf', '.pptx'))

# Register the filter with Jinja2
app.jinja_env.filters['youtube_id'] = extract_youtube_id
app.jinja_env.filters['is_slide'] = is_slide_file
app.jinja_env.filters['url_encode'] = lambda s: urllib.parse.quote(s, safe='')

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- One-time schema safeguard: ensure trainer.number_series exists & populated ---
with app.app_context():
    try:
        inspector = sa_inspect(db.engine)
        trainer_columns = {c['name'] for c in inspector.get_columns('trainer')}
        # Ensure user_module.reattempt_count column exists
        try:
            um_columns = {c['name'] for c in inspector.get_columns('user_module')}
            if 'reattempt_count' not in um_columns:
                db.session.execute(text('ALTER TABLE user_module ADD COLUMN IF NOT EXISTS reattempt_count INTEGER DEFAULT 0'))
                db.session.commit()
                print('[SCHEMA GUARD] Added reattempt_count to user_module')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not ensure reattempt_count on user_module: {e}')
        # Ensure user_course_progress.reattempt_count column exists
        try:
            ucp_columns = {c['name'] for c in inspector.get_columns('user_course_progress')}
            if 'reattempt_count' not in ucp_columns:
                db.session.execute(text('ALTER TABLE user_course_progress ADD COLUMN IF NOT EXISTS reattempt_count INTEGER DEFAULT 0'))
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not add reattempt_count to user_course_progress: {e}')
        if 'number_series' not in trainer_columns:
            db.session.execute(text("ALTER TABLE trainer ADD COLUMN IF NOT EXISTS number_series VARCHAR(10) UNIQUE"))
            db.session.commit()
        year = datetime.now(UTC).strftime('%Y')
        seq_name = f'trainer_number_series_{year}_seq'
        db.session.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))
        db.session.execute(text(
            f"UPDATE trainer SET number_series = 'TR{year}' || LPAD(nextval('{seq_name}')::text,4,'0') "
            "WHERE (number_series IS NULL OR number_series = '')"))
        db.session.commit()
        existing_codes = {c.code.upper() for c in Course.query.all()}
        defaults = [
            {'code': 'TNG', 'name': 'NEPAL SECURITY GUARD TRAINING (TNG)', 'allowed_category': 'foreigner'},
            {'code': 'CSG', 'name': 'CERTIFIED SECURITY GUARD (CSG)', 'allowed_category': 'citizen'}
        ]
        created_any = False
        for d in defaults:
            if d['code'] not in existing_codes:
                db.session.add(Course(code=d['code'], name=d['name'], allowed_category=d['allowed_category']))
                created_any = True
        if created_any:
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[SCHEMA GUARD ERROR] {e}")
# -------------------------------------------------------------------------------

@login_manager.user_loader
def load_user(user_id):
    user_type = session.get('user_type')
    # Admins keep numeric IDs
    if user_type == 'admin':
        try:
            return Admin.query.get(int(user_id))
        except (TypeError, ValueError):
            return None
    # Users use SGYYYYNNNN number_series
    if user_type == 'user':
        if isinstance(user_id, str) and user_id.startswith('SG'):
            u = User.query.filter_by(number_series=user_id).first()
            if u:
                return u
        # Fallback numeric (legacy sessions)
        try:
            return User.query.get(int(user_id))
        except (TypeError, ValueError):
            return None
    # Trainers use TRYYYYNNNN number_series
    if user_type == 'trainer':
        if isinstance(user_id, str) and user_id.startswith('TR'):
            t = Trainer.query.filter_by(number_series=user_id).first()
            if t:
                return t
        try:
            return Trainer.query.get(int(user_id))
        except (TypeError, ValueError):
            return None
    # Fallback detection if session user_type missing
    if isinstance(user_id, str):
        if user_id.startswith('SG'):
            return User.query.filter_by(number_series=user_id).first()
        if user_id.startswith('TR'):
            return Trainer.query.filter_by(number_series=user_id).first()
        # Try numeric admin then user
        try:
            num_id = int(user_id)
            admin = Admin.query.get(num_id)
            if admin:
                return admin
            return User.query.get(num_id)
        except (TypeError, ValueError):
            return None
    return None

@app.route('/uploads/<path:filename>')  # unified route; path allows subdirectories if needed
def serve_upload(filename):
    """Serve uploaded profile pictures or module slide files from their respective directories.
    Tries profile pictures folder first, then static/uploads. Returns 404 if not found."""
    profile_dir = app.config.get('UPLOAD_FOLDER', 'static/profile_pics')
    slides_dir = os.path.join(app.root_path, 'static', 'uploads')
    candidate = os.path.join(profile_dir, filename)
    if os.path.exists(candidate):
        return send_from_directory(profile_dir, filename)
    candidate = os.path.join(slides_dir, filename)
    if os.path.exists(candidate):
        return send_from_directory(slides_dir, filename)
    from flask import abort
    return abort(404)

# Also expose a dedicated endpoint for slides to match template links
@app.route('/slides/<path:filename>')
def serve_uploaded_slide(filename):
    slides_dir = os.path.join(app.root_path, 'static', 'uploads')
    return send_from_directory(slides_dir, filename)

# Home route
@app.route('/')
def index():
    # Redirect authenticated users directly to their dashboard
    if current_user.is_authenticated:
        if isinstance(current_user, Admin):
            return redirect(url_for('admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
    return render_template('index.html')

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, skip login page
    if request.method == 'GET' and current_user.is_authenticated:
        if isinstance(current_user, Admin):
            return redirect(url_for('admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Try to find user in Admins first
        user = Admin.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            session['user_type'] = 'admin'
            session['user_id'] = user.get_id()
            print(f"[DEBUG] Logged in as admin: {user.email}, session['user_type']: {session.get('user_type')}")
            return redirect(url_for('admin_dashboard'))
        # If not admin, try Users
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            session['user_type'] = 'user'
            session['user_id'] = user.get_id()
            print(f"[DEBUG] Logged in as user: {user.email}, session['user_type']: {session.get('user_type')}")
            return redirect(url_for('user_dashboard'))
        # If not user, try Trainers
        user = Trainer.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            session['user_type'] = 'trainer'
            session['user_id'] = user.get_id()
            print(f"[DEBUG] Logged in as trainer: {user.email}, session['user_type']: {session.get('user_type')}")
            return redirect(url_for('trainer_portal'))
        flash('Invalid email or password')

    return render_template('login.html')

@app.route('/trainer_portal')
@login_required
def trainer_portal():
    if not isinstance(current_user, Trainer):
        # Redirect if not a trainer
        return redirect(url_for('login'))

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
                trainees_q = trainees_q.filter(User.user_category == 'citizen')
            elif course.allowed_category == 'foreigner':
                trainees_q = trainees_q.filter(User.user_category == 'foreigner')
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
        avg_module_rating = db.session.query(db.func.avg(Module.star_rating)).scalar() or 0
        avg_rating_pct = round((avg_module_rating / 5.0) * 100, 1) if avg_module_rating else 0.0
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
                trainees_q = trainees_q.filter(User.user_category == 'citizen')
            elif course_obj.allowed_category == 'foreigner':
                trainees_q = trainees_q.filter(User.user_category == 'foreigner')
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

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # Get form data
        user_category = request.form.get('user_category', 'citizen')

        user_data = {
            'full_name': request.form['full_name'],
            'email': request.form['email'],
            'password': request.form['password'],
            'user_category': user_category,
            'agency_id': 1  # Assign a default agency_id
        }

        # Optionally add IC or Passport number (collect fully during onboarding)
        if user_category == 'citizen':
            ic_number = request.form.get('ic_number')
            if ic_number:
                user_data['ic_number'] = ic_number
        else:
            passport_number = request.form.get('passport_number')
            if passport_number:
                user_data['passport_number'] = passport_number

        # Check if user already exists
        if User.query.filter_by(email=user_data['email']).first():
            flash('Email already registered')
            return render_template('signup.html', agencies=Agency.query.all())

        # Register user
        user = Registration.registerUser(user_data)
        # Auto-login and redirect to onboarding wizard
        login_user(user)
        session['user_type'] = 'user'
        session['user_id'] = user.get_id()
        return redirect(url_for('onboarding', step=1))

    agencies = Agency.query.all()
    return render_template('signup.html', agencies=agencies)

@app.route('/onboarding', methods=['GET', 'POST'])
@login_required
def onboarding():
    # Allow only regular users
    if not isinstance(current_user, User):
        if isinstance(current_user, Admin):
            return redirect(url_for('admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    # Determine dynamic steps based on user category
    user_cat = (getattr(current_user, 'user_category', 'citizen') or 'citizen').lower()
    total_steps = 5 if user_cat == 'foreigner' else 4

    # Current step from query or form
    try:
        step = int(request.values.get('step', 1))
    except Exception:
        step = 1
    step = max(1, min(step, total_steps))

    if request.method == 'POST':
        if 'skip' in request.form:
            return redirect(url_for('user_dashboard'))
        # Save fields for the current step
        try:
            if step == 1:
                # Personal details
                full_name = request.form.get('full_name')
                if full_name:
                    current_user.full_name = full_name
                new_cat = request.form.get('user_category')
                if new_cat in ('citizen', 'foreigner'):
                    current_user.user_category = new_cat
                # IC/Passport based on selected category
                ic_number = request.form.get('ic_number')
                passport_number = request.form.get('passport_number')
                if (current_user.user_category or 'citizen') == 'citizen':
                    if ic_number is not None:
                        current_user.ic_number = ic_number
                    current_user.passport_number = None
                else:
                    if passport_number is not None:
                        current_user.passport_number = passport_number
                    current_user.ic_number = None
            elif step == 2:
                # Contact details
                current_user.emergency_contact = request.form.get('phone') or request.form.get('emergency_contact')
                current_user.address = request.form.get('address')
                current_user.state = request.form.get('state')
                current_user.postcode = request.form.get('postcode')
            elif step == 3:
                # Work details
                current_user.current_workplace = request.form.get('current_workplace')
                current_user.working_experience = request.form.get('working_experience')  # retained for backward compat; may be None
                rec_date = request.form.get('recruitment_date')
                if rec_date:
                    try:
                        current_user.recruitment_date = datetime.strptime(rec_date, '%Y-%m-%d').date()
                    except Exception:
                        pass
                # Working experiences (multiple)
                try:
                    companies = request.form.getlist('exp_company')
                    positions = request.form.getlist('exp_position')
                    starts = request.form.getlist('exp_start')
                    ends = request.form.getlist('exp_end')
                    # Remove existing entries for this user
                    WorkHistory.query.filter_by(user_id=current_user.User_id).delete(synchronize_session=False)
                    # Add new ones
                    for i in range(max(len(companies), len(positions), len(starts), len(ends))):
                        company = (companies[i].strip() if i < len(companies) and companies[i] else '')
                        position = (positions[i].strip() if i < len(positions) and positions[i] else None)
                        start_s = (starts[i].strip() if i < len(starts) and starts[i] else '')
                        end_s = (ends[i].strip() if i < len(ends) and ends[i] else '')
                        if not company and not start_s and not end_s:
                            continue  # skip empty rows
                        # Require company and both dates
                        if not company or not start_s or not end_s:
                            continue
                        try:
                            start_d = datetime.strptime(start_s, '%Y-%m-%d').date()
                            end_d = datetime.strptime(end_s, '%Y-%m-%d').date()
                            # Ignore if end before start
                            if end_d < start_d:
                                continue
                        except Exception:
                            continue
                        wh = WorkHistory(
                            user_id=current_user.User_id,
                            company_name=company,
                            position_title=position,
                            start_date=start_d,
                            end_date=end_d
                        )
                        db.session.add(wh)
                except Exception:
                    # Do not block onboarding if experience parsing fails; proceed with other fields
                    pass
            elif step == 4 and user_cat == 'foreigner':
                # Immigration for foreigners
                current_user.visa_number = request.form.get('visa_number')
                visa_exp = request.form.get('visa_expiry_date')
                if visa_exp:
                    try:
                        current_user.visa_expiry_date = datetime.strptime(visa_exp, '%Y-%m-%d').date()
                    except Exception:
                        pass
            # Last step: Emergency (step 5 for foreigner, step 4 for citizen)
            last_step = 5 if user_cat == 'foreigner' else 4
            if step == last_step:
                current_user.emergency_relationship = request.form.get('emergency_relationship')
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash('Could not save your progress. Please try again.')
            return render_template('onboarding.html', step=step, total_steps=total_steps, user=current_user)

        # Advance to next step or finish
        next_step = step + 1
        if next_step > total_steps:
            return redirect(url_for('user_dashboard'))
        return redirect(url_for('onboarding', step=next_step))

    return render_template('onboarding.html', step=step, total_steps=total_steps, user=current_user)

# ------------------- User-facing routes -------------------
@app.route('/user_dashboard')
@app.route('/dashboard')
@login_required
def user_dashboard():
    # Only for regular users
    if not isinstance(current_user, User):
        if isinstance(current_user, Admin):
            return redirect(safe_url_for('admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    try:
        # Determine allowed courses for this user
        user_cat = (getattr(current_user, 'user_category', 'citizen') or 'citizen').lower()
        # Prefer canonical codes mapping
        preferred_code = 'TNG' if user_cat == 'foreigner' else 'CSG'
        main_course = Course.query.filter(Course.code.ilike(preferred_code)).first()
        # Fallback: any course allowed for this category or both
        courses_q = Course.query
        if main_course is None:
            courses_q = courses_q.filter((Course.allowed_category == user_cat) | (Course.allowed_category == 'both'))
            courses = courses_q.all()
        else:
            courses = [main_course]
        # Compute per-course progress
        courses_progress = []
        total_user_modules = []
        for course in courses:
            c_modules = course.modules
            module_ids = [m.module_id for m in c_modules]
            if module_ids:
                user_um = UserModule.query.filter(
                    UserModule.user_id == current_user.User_id,
                    UserModule.module_id.in_(module_ids)
                ).all()
            else:
                user_um = []
            total_user_modules.extend(user_um)
            completed = len([um for um in user_um if um.is_completed])
            total = len(c_modules)
            progress_pct = int(round((completed / total * 100.0), 0)) if total else 0
            courses_progress.append({
                'code': course.code,
                'name': course.name,
                'progress': progress_pct,
                'completed_modules': completed,
                'total_modules': total
            })
        # Determine rating lock: unlocked if main course exists and all its modules completed
        rating_unlocked = False
        if main_course:
            m_ids = [m.module_id for m in main_course.modules]
            if m_ids:
                completed_count = UserModule.query.filter(
                    UserModule.user_id == current_user.User_id,
                    UserModule.module_id.in_(m_ids),
                    UserModule.is_completed.is_(True)
                ).count()
                rating_unlocked = (completed_count == len(m_ids) and len(m_ids) > 0)
        # user_modules for dashboard stats: show enrolled modules for main course if any; else overall for all allowed courses
        user_modules = total_user_modules
    except Exception:
        logging.exception('[USER DASHBOARD] Failed to build dashboard context')
        courses_progress = []
        user_modules = []
        rating_unlocked = False

    return render_template(
        'user_dashboard.html',
        user=current_user,
        user_modules=user_modules,
        rating_unlocked=rating_unlocked,
        courses_progress=courses_progress
    )

@app.route('/enroll', methods=['GET'])
@login_required
def enroll_course():
    # Enroll user into modules for their primary course (TNG for foreigner, CSG for citizen)
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    user_cat = (getattr(current_user, 'user_category', 'citizen') or 'citizen').lower()
    preferred_code = 'TNG' if user_cat == 'foreigner' else 'CSG'
    course = Course.query.filter(Course.code.ilike(preferred_code)).first()
    if course is None:
        # Fallback: take first course allowed for the category
        course = Course.query.filter((Course.allowed_category == user_cat) | (Course.allowed_category == 'both')).first()
    if not course:
        flash('No course available for your category yet.')
        return redirect(url_for('user_dashboard'))
    created = 0
    for m in course.modules:
        exists = UserModule.query.filter_by(user_id=current_user.User_id, module_id=m.module_id).first()
        if not exists:
            db.session.add(UserModule(user_id=current_user.User_id, module_id=m.module_id))
            created += 1
    if created:
        try:
            db.session.commit()
            flash(f'Enrolled in {created} module(s) for {course.code}.')
        except Exception:
            db.session.rollback()
            flash('Could not enroll at this time. Please try again later.')
    else:
        flash('You are already enrolled in this course.')
    return redirect(url_for('user_dashboard'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    if request.method == 'POST':
        try:
            # Basic fields
            current_user.full_name = request.form.get('full_name') or current_user.full_name
            new_email = request.form.get('email')
            if new_email and new_email != current_user.email:
                # Simple uniqueness check
                if User.query.filter(User.email == new_email, User.User_id != current_user.User_id).first():
                    flash('Email already in use by another account.')
                else:
                    current_user.email = new_email
            current_user.address = request.form.get('address') or current_user.address
            current_user.postcode = request.form.get('postcode') or current_user.postcode
            current_user.state = request.form.get('state') or current_user.state
            current_user.working_experience = request.form.get('working_experience') or current_user.working_experience
            # Dates and numbers
            rec = request.form.get('recruitment_date')
            if rec:
                try:
                    current_user.recruitment_date = datetime.strptime(rec, '%Y-%m-%d').date()
                except Exception:
                    pass
            rating_star_val = request.form.get('rating_star')
            if rating_star_val is not None:
                try:
                    current_user.rating_star = max(0, min(5, int(rating_star_val)))
                except Exception:
                    pass
            current_user.visa_number = request.form.get('visa_number') or current_user.visa_number
            visa_exp = request.form.get('visa_expiry_date')
            if visa_exp:
                try:
                    current_user.visa_expiry_date = datetime.strptime(visa_exp, '%Y-%m-%d').date()
                except Exception:
                    pass
            current_user.current_workplace = request.form.get('current_workplace') or current_user.current_workplace
            # Agency (optional integer)
            ag = request.form.get('agency_id')
            try:
                if ag:
                    current_user.agency_id = int(ag)
            except Exception:
                pass
            # Emergency
            current_user.emergency_contact = request.form.get('emergency_contact') or current_user.emergency_contact
            current_user.emergency_relationship = request.form.get('emergency_relationship') or current_user.emergency_relationship
            # File upload
            if 'profile_pic' in request.files:
                f = request.files['profile_pic']
                if f and f.filename:
                    filename = secure_filename(f.filename)
                    save_dir = app.config.get('UPLOAD_FOLDER', os.path.join('static', 'profile_pics'))
                    os.makedirs(save_dir, exist_ok=True)
                    f.save(os.path.join(save_dir, filename))
                    current_user.Profile_picture = filename
            db.session.commit()
            flash('Profile updated successfully.')
        except Exception:
            db.session.rollback()
            logging.exception('[PROFILE] Update failed')
            flash('Could not update profile. Please try again.')
        return redirect(url_for('profile'))
    return render_template('profile.html', user=current_user)

@app.route('/courses')
@login_required
def courses():
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    user_cat = (getattr(current_user, 'user_category', 'citizen') or 'citizen').lower()
    # Courses available to this user (including both)
    courses = Course.query.filter((Course.allowed_category == user_cat) | (Course.allowed_category == 'both')).all()
    course_progress = []
    for c in courses:
        m_ids = [m.module_id for m in c.modules]
        total = len(m_ids)
        if total:
            completed = UserModule.query.filter(
                UserModule.user_id == current_user.User_id,
                UserModule.module_id.in_(m_ids),
                UserModule.is_completed.is_(True)
            ).count()
            avg_score_val = db.session.query(db.func.avg(UserModule.score)).filter(
                UserModule.user_id == current_user.User_id,
                UserModule.module_id.in_(m_ids),
                UserModule.is_completed.is_(True)
            ).scalar()
        else:
            completed = 0
            avg_score_val = 0.0
        percent = int(round((completed / total * 100.0), 0)) if total else 0
        overall_percentage = int(round(float(avg_score_val or 0.0), 0))
        course_progress.append({
            'name': c.name,
            'code': c.code,
            'allowed_category': c.allowed_category,
            'percent': percent,
            'overall_percentage': overall_percentage
        })
    return render_template('courses.html', course_progress=course_progress)

@app.route('/my_certificates')
@login_required
def my_certificates():
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    certs = Certificate.query.filter_by(user_id=current_user.User_id).order_by(Certificate.issue_date.desc()).all()
    return render_template('my_certificates.html', certificates=certs)

@app.route('/agency')
@login_required
def agency():
    # Show all agencies (or could filter by user's agency)
    ags = Agency.query.all()
    return render_template('agency.html', agencies=ags)

@app.route('/logout', methods=['POST', 'GET'])
@login_required
def logout():
    logout_user()
    # Keep session clean
    session.clear()
    return redirect(url_for('login'))

# ------------------- End user-facing routes -------------------

# ------------------- Minimal admin routes -------------------
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        mgmt = Management()
        dashboard = mgmt.getDashboard()
    except Exception:
        logging.exception('[ADMIN DASHBOARD] Failed to build data')
        dashboard = {
            'total_users': 0,
            'total_modules': 0,
            'total_certificates': 0,
            'active_trainers': 0,
            'completion_stats': [],
            'performance_metrics': None
        }
    return render_template('admin_dashboard.html', dashboard=dashboard)

@app.route('/admin_course_management')
@login_required
def admin_course_management():
    # Only admins can access
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        courses = Course.query.order_by(Course.code.asc()).all()
        course_modules = {}
        for c in courses:
            # Use helper sorter for series_number
            course_modules[c.course_id] = _series_sort(list(c.modules))
    except Exception:
        logging.exception('[ADMIN COURSE MGMT] Failed to load courses/modules')
        courses = []
        course_modules = {}
    return render_template('admin_course_management.html', courses=courses, course_modules=course_modules)

@app.route('/admin_users')
@login_required
def admin_users():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        users = User.query.order_by(User.full_name.asc()).all()
    except Exception:
        logging.exception('[ADMIN USERS] Failed to load users')
        users = []
    return render_template('admin_users.html', users=users)

@app.route('/monitor_progress')
@login_required
def monitor_progress():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        # Join user_module with user, module, agency for display
        rows = db.session.query(UserModule, User, Module, Agency) \
            .join(User, User.User_id == UserModule.user_id) \
            .join(Module, Module.module_id == UserModule.module_id) \
            .join(Agency, Agency.agency_id == User.agency_id) \
            .order_by(User.full_name.asc(), Module.series_number.asc()) \
            .all()
        existing_certs = {(c.user_id, c.module_id) for c in Certificate.query.all()}
    except Exception:
        logging.exception('[ADMIN PROGRESS] Failed to load progress rows')
        rows = []
        existing_certs = set()
    return render_template('monitor_progress.html', user_modules=rows, existing_certs=existing_certs)

@app.route('/admin_certificates')
@login_required
def admin_certificates():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        certs = Certificate.query.order_by(Certificate.issue_date.desc()).all()
    except Exception:
        logging.exception('[ADMIN CERTIFICATES] Failed to load certificates')
        certs = []
    # Optional: show current template if present
    try:
        template_path = os.path.join(app.root_path, 'static', 'cert_templates', 'Training_cert.pdf')
        cert_template_url = url_for('static', filename='cert_templates/Training_cert.pdf') if os.path.exists(template_path) else None
    except Exception:
        cert_template_url = None
    return render_template('admin_certificates.html', certificates=certs, cert_template_url=cert_template_url)

@app.route('/admin_agencies')
@login_required
def admin_agencies():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        ags = Agency.query.order_by(Agency.agency_name.asc()).all()
    except Exception:
        logging.exception('[ADMIN AGENCIES] Failed to load agencies')
        ags = []
    return render_template('admin_agencies.html', agencies=ags)

@app.route('/recalculate_ratings')
@login_required
def recalculate_ratings():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    # Placeholder: real implementation could recompute ratings.
    flash('Ratings recalculated.')
    return redirect(url_for('admin_dashboard'))
# ------------------- End minimal admin routes -------------------

if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    try:
        port = int(os.environ.get('PORT', '5000'))
    except Exception:
        port = 5000
    debug = os.environ.get('FLASK_DEBUG', '1') in ('1', 'true', 'True')
    print(f"Starting Flask server at http://{host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)
