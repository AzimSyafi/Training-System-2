import sys
print("Python executable:", sys.executable)

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, UTC  # added UTC
import os
from models import db, Admin, User, Agency, Module, Certificate, Trainer, UserModule, Management, Registration, Course
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, inspect as sa_inspect
import re
import urllib.parse
from flask import request, jsonify
import json
import logging

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

        # Add IC number or passport number based on user category
        if user_category == 'citizen':
            ic_number = request.form.get('ic_number')
            if not ic_number:
                flash('IC Number is required for Malaysian citizens')
                return render_template('signup.html', agencies=Agency.query.all())
            user_data['ic_number'] = ic_number
        else:  # foreigner
            passport_number = request.form.get('passport_number')
            if not passport_number:
                flash('Passport Number is required for foreigners')
                return render_template('signup.html', agencies=Agency.query.all())
            user_data['passport_number'] = passport_number

        # Check if user already exists
        if User.query.filter_by(email=user_data['email']).first():
            flash('Email already registered')
            return render_template('signup.html', agencies=Agency.query.all())

        # Register user
        user = Registration.registerUser(user_data)
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    agencies = Agency.query.all()
    return render_template('signup.html', agencies=agencies)

@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    session.pop('user_type', None)
    return redirect(url_for('index'))

# User Dashboard and Training Workflow
@app.route('/user_dashboard')
@login_required
def user_dashboard():
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))

    # Determine allowed course code based on user category (legacy single-course logic)
    allowed_code = 'TNG' if current_user.user_category == 'foreigner' else 'CSG'

    # Only show modules belonging to the allowed course code (legacy behavior retained)
    user_modules = (UserModule.query
                     .join(Module, UserModule.module_id == Module.module_id)
                     .filter(UserModule.user_id == current_user.User_id,
                             Module.module_type == allowed_code)
                     .all())

    # Available modules limited to allowed course code (for potential UI usage)
    available_modules = Module.query.filter_by(module_type=allowed_code).all()

    # Precompute whether rating should be shown (all modules completed)
    rating_unlocked = current_user.has_completed_all_modules_in_course(allowed_code)

    # NEW: Build per-course progress cards (all eligible courses for user category)
    from models import Course
    eligible_courses = Course.query.filter(
        (Course.allowed_category == 'both') | (Course.allowed_category == current_user.user_category)
    ).all()
    courses_progress = []
    user_cat = (getattr(current_user, 'user_category', 'citizen') or 'citizen').lower()
    for course in eligible_courses:
        code_u = (course.code or '').upper()
        # Hard mapping guard: hide CSG for foreigners and TNG for citizens
        if (code_u == 'CSG' and user_cat != 'citizen') or (code_u == 'TNG' and user_cat != 'foreigner'):
            continue
        # Prefer explicit relation; fall back by module_type code if relation not set
        course_modules = list(course.modules) if getattr(course, 'modules', None) else []
        if not course_modules:
            course_modules = Module.query.filter(Module.module_type == course.code.upper()).all()
        # Apply natural series sorting for consistency
        course_modules = _series_sort(course_modules)
        module_ids = [m.module_id for m in course_modules]
        total = len(module_ids)
        if total:
            completed_count = UserModule.query.filter(
                UserModule.user_id == current_user.User_id,
                UserModule.is_completed.is_(True),
                UserModule.module_id.in_(module_ids)
            ).count()
        else:
            completed_count = 0
        progress_pct = int((completed_count / total) * 100) if total > 0 else 0
        courses_progress.append({
            'id': course.course_id,
            'code': course.code,
            'name': course.name,
            'progress': progress_pct,
            'total_modules': total,
            'completed_modules': completed_count
        })

    return render_template('user_dashboard.html',
                         user=current_user,
                         user_modules=user_modules,
                         available_modules=available_modules,
                         courses_progress=courses_progress,
                         rating_star=current_user.rating_star,
                         rating_unlocked=rating_unlocked)

@app.route('/enroll_course')
@login_required
def enroll_course():
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))

    # Enroll user only in modules for their category's course (foreigner->TNG, citizen->CSG)
    allowed_code = 'TNG' if current_user.user_category == 'foreigner' else 'CSG'
    modules = Module.query.filter_by(module_type=allowed_code).all()

    created = 0
    for module in modules:
        existing = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module.module_id).first()
        if not existing:
            db.session.add(UserModule(user_id=current_user.User_id, module_id=module.module_id))
            created += 1
    db.session.commit()

    # (Optional) Remove any accidental enrollments in other course codes to keep data clean
    # We will not delete automatically to avoid unintended data loss; instead we ignore them in UI.
    # If cleanup is desired uncomment the deletion block below.
    # other_enrollments = (UserModule.query
    #     .join(Module, UserModule.module_id == Module.module_id)
    #     .filter(UserModule.user_id == current_user.User_id, Module.module_type != allowed_code).all())
    # for oe in other_enrollments:
    #     db.session.delete(oe)
    # db.session.commit()

    if created:
        flash(f'Successfully enrolled in {allowed_code} modules ({created} added).')
    else:
        flash('Already enrolled in all available modules for your course.')
    return redirect(url_for('user_dashboard'))

@app.route('/module/<int:module_id>')
@login_required
def view_module(module_id):
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))

    module = Module.query.get_or_404(module_id)
    # Enforce access based on module's course/category
    code = (module.module_type or '').upper()
    course = Course.query.filter_by(code=code).first() if code else None
    user_cat = (getattr(current_user, 'user_category', 'citizen') or 'citizen').lower()
    if course:
        course_cat = (course.allowed_category or 'both').lower()
        if course_cat not in ('both', user_cat):
            flash('This module belongs to a course not available for your category.', 'warning')
            return redirect(url_for('courses'))
    else:
        if (code == 'CSG' and user_cat != 'citizen') or (code == 'TNG' and user_cat != 'foreigner'):
            flash('This module belongs to a course not available for your category.', 'warning')
            return redirect(url_for('courses'))

    user_module = UserModule.query.filter_by(
        user_id=current_user.User_id,
        module_id=module_id
    ).first()

    modules = Module.query.filter_by(module_type=module.module_type).all()

    if not user_module:
        flash('You are not enrolled in this module.')
        return redirect(url_for('user_dashboard'))

    return render_template('module_view.html', module=module, user_module=user_module, modules=modules)

# ---- Admin Accounts: missing endpoints ----
@app.route('/admin/users')
@login_required
def admin_users():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))

        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    users = User.query.order_by(User.User_id.asc()).all()
    trainers = Trainer.query.order_by(Trainer.trainer_id.asc()).all()
    courses = Course.query.order_by(Course.name.asc()).all()
    return render_template('admin_accounts.html', users=users, trainers=trainers, courses=courses)

@app.route('/create_user', methods=['POST'])
@login_required
def create_user():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    role = request.form.get('role')
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    password = request.form.get('password')
    if not role or not full_name or not email or not password:
        flash('All fields are required', 'danger')
        return redirect(url_for('admin_users', show_create_modal=1))
    try:
        if role == 'admin':
            if Admin.query.filter_by(email=email).first():
                flash('Email already in use', 'danger')
                return redirect(url_for('admin_users', show_create_modal=1))
            a = Admin(username=full_name, email=email, role='admin')
            a.set_password(password)
            db.session.add(a)
        elif role == 'trainer':
            if Trainer.query.filter_by(email=email).first():
                flash('Email already in use', 'danger')
                return redirect(url_for('admin_users', show_create_modal=1))
            t = Trainer(name=full_name, email=email)
            t.set_password(password)
            db.session.add(t)
        else:
            flash('Invalid role', 'danger')
            return redirect(url_for('admin_users', show_create_modal=1))
        db.session.commit()
        flash('Account created', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating account: {e}', 'danger')
    return redirect(url_for('admin_users'))

@app.route('/admin/trainer/<int:trainer_id>/update', methods=['POST'])
@login_required
def update_trainer(trainer_id):
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    t = Trainer.query.get_or_404(trainer_id)
    t.name = request.form.get('name', t.name)
    t.email = request.form.get('email', t.email)
    t.course = request.form.get('course', t.course)
    t.availability = request.form.get('availability', t.availability)
    t.contact_number = request.form.get('contact_number', t.contact_number)
    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/trainer/<int:trainer_id>/toggle_active', methods=['POST'])
@login_required
def toggle_trainer_active(trainer_id):
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    t = Trainer.query.get_or_404(trainer_id)
    t.active_status = not bool(t.active_status)
    try:
        db.session.commit()
        return jsonify({'success': True, 'active_status': t.active_status})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/trainer/<int:trainer_id>/delete', methods=['POST'])
@login_required
def delete_trainer(trainer_id):
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    t = Trainer.query.get_or_404(trainer_id)
    try:
        db.session.delete(t)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/reset_user_progress', methods=['POST'])
@login_required
def reset_user_progress():
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'user_id required'}), 400
    u = User.query.get(user_id)
    if not u:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    try:
        UserModule.query.filter_by(user_id=u.User_id).delete()
        Certificate.query.filter_by(user_id=u.User_id).delete()
        u.rating_star = 0
        u.rating_label = ''
        db.session.commit()
        return jsonify({'success': True, 'message': 'Progress reset'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/delete_user', methods=['POST'])
@login_required
def delete_user():
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'user_id required'}), 400
    u = User.query.get(user_id)
    if not u:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    try:
        UserModule.query.filter_by(user_id=u.User_id).delete()
        Certificate.query.filter_by(user_id=u.User_id).delete()
        from models import WorkHistory
        WorkHistory.query.filter_by(user_id=u.User_id).delete()
        db.session.delete(u)
        db.session.commit()
        return jsonify({'success': True, 'message': 'User deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/courses')
@login_required
def courses():
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    user_category = (getattr(current_user, 'user_category', 'citizen') or 'citizen').lower()
    # Fetch only courses allowed for this user's category (case-insensitive)
    all_courses = (Course.query
                   .filter((db.func.lower(Course.allowed_category) == 'both') | (db.func.lower(Course.allowed_category) == user_category))
                   .order_by(Course.name)
                   .all())
    course_progress = []
    import json as pyjson
    for course in all_courses:
        code_u = (course.code or '').upper()
        # Hard mapping guard: hide CSG for foreigners and TNG for citizens
        if (code_u == 'CSG' and user_category != 'citizen') or (code_u == 'TNG' and user_category != 'foreigner'):
            continue
        course_cat = (course.allowed_category or 'both').lower()
        allowed = True  # by query filter and hard mapping, these are allowed
        percent = 0
        overall_percentage = 0
        try:
            modules = course.modules or Module.query.filter(Module.module_type == course.code.upper()).all()
            total = len(modules)
            if allowed and total:
                module_ids = [m.module_id for m in modules]
                completed_q = (UserModule.query
                               .filter_by(user_id=current_user.User_id, is_completed=True)
                               .filter(UserModule.module_id.in_(module_ids)))
                completed = completed_q.count()
                percent = int((completed / total) * 100) if total else 0
                # overall score: aggregate all quiz answers correctness; fallback to avg score
                total_correct = 0
                total_questions = 0
                user_modules = completed_q.all()
                for um in user_modules:
                    if not um.quiz_answers:
                        continue
                    try:
                        selected_indices = pyjson.loads(um.quiz_answers)
                    except Exception:
                        continue
                    mod_obj = next((m for m in modules if m.module_id == um.module_id), None)
                    if mod_obj and mod_obj.quiz_json:
                        try:
                            quiz = pyjson.loads(mod_obj.quiz_json)
                        except Exception:
                            quiz = []
                        for idx, sel in enumerate(selected_indices):
                            if idx < len(quiz):
                                answers = quiz[idx].get('answers', [])
                                total_questions += 1
                                if isinstance(sel, int) and 0 <= sel < len(answers):
                                    if answers[sel].get('isCorrect') in [True, 'true', 'True', 1, '1']:
                                        total_correct += 1
                if total_questions:
                    overall_percentage = int((total_correct / total_questions) * 100)
                else:
                    # fallback average score across completed modules
                    scores = [um.score for um in user_modules] or [0]
                    overall_percentage = int(sum(scores)/len(scores)) if scores else 0
        except Exception as e:
            app.logger.error(f"Error computing progress for course {course.code}: {e}")
            percent = percent or 0
            overall_percentage = overall_percentage or 0
        course_progress.append({
            'code': course.code.lower(),
            'name': course.name,
            'percent': percent,
            'overall_percentage': overall_percentage,
            'allowed_category': course.allowed_category,
            'locked': not allowed
        })
    # If there are no courses at all
    if not course_progress:
        flash('No courses available yet.', 'warning')
    return render_template('courses.html', course_progress=course_progress, user=current_user, user_category=user_category)

@app.route('/modules/<string:course_code>')
@login_required
def course_modules(course_code):
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    normalized_code = course_code.upper()
    course = Course.query.filter_by(code=normalized_code).first()
    # Enforce access restriction by category (with fallback inference if course missing)
    user_cat = (getattr(current_user, 'user_category', 'citizen') or 'citizen').lower()
    if course:
        course_cat = (course.allowed_category or 'both').lower()
        if course_cat not in ('both', user_cat):
            flash('This course is not available for your category.', 'warning')
            return redirect(url_for('courses'))
    else:
        # Infer default policy for known codes
        if (normalized_code == 'CSG' and user_cat != 'citizen') or (normalized_code == 'TNG' and user_cat != 'foreigner'):
            flash('This course is not available for your category.', 'warning')
            return redirect(url_for('courses'))
    modules = course.modules if course and course.modules else Module.query.filter(Module.module_type == normalized_code).order_by(Module.series_number).all()
    course_name = (course.name if course else ('NEPAL SECURITY GUARD TRAINING (TNG)' if normalized_code == 'TNG' else 'CERTIFIED SECURITY GUARD (CSG)'))
    if not modules:
        flash('No modules found for this course.')
        return redirect(url_for('courses'))
    # Apply numeric sorting fix
    modules = _series_sort(modules)
    user_progress = {um.module_id: um for um in UserModule.query.filter(
        UserModule.user_id == current_user.User_id,
        UserModule.module_id.in_([m.module_id for m in modules])
    ).all()}
    unlocked_modules = set()
    for idx, module in enumerate(modules):
        if idx == 0:
            unlocked_modules.add(module.module_id)
        else:
            prev_module = modules[idx - 1]
            prev_progress = user_progress.get(prev_module.module_id)
            if prev_progress and prev_progress.is_completed:
                unlocked_modules.add(module.module_id)
    for module in modules:
        module.unlocked = module.module_id in unlocked_modules
    # Compute overall percentage (across all quizzes) for reattempt condition
    def _compute_overall_percentage(uid:int, mods):
        total_correct = 0
        total_questions = 0
        import json as pyjson
        for m in mods:
            um = user_progress.get(m.module_id)
            if not um or not um.is_completed or not um.quiz_answers:
                continue
            try:
                selected_indices = pyjson.loads(um.quiz_answers)
            except Exception:
                continue
            if m.quiz_json:
                try:
                    quiz = pyjson.loads(m.quiz_json)
                except Exception:
                    quiz = []
                for idx, sel in enumerate(selected_indices):
                    if idx < len(quiz):
                        answers = quiz[idx].get('answers', [])
                        total_questions += 1
                        if isinstance(sel, int) and 0 <= sel < len(answers):
                            if answers[sel].get('isCorrect') in [True, 'true', 'True', 1, '1']:
                                total_correct += 1
        return int((total_correct / total_questions) * 100) if total_questions else 0
    overall_percentage = _compute_overall_percentage(current_user.User_id, modules)
    # Determine if all modules in this course are completed by the user
    all_completed = all((user_progress.get(m.module_id) and user_progress.get(m.module_id).is_completed) for m in modules)
    return render_template('course_modules.html', modules=modules, course_name=course_name, user_progress=user_progress, overall_percentage=overall_percentage, all_completed=all_completed)

# User profile route
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))

    # Ensure upload folder exists
    upload_folder = app.config.get('UPLOAD_FOLDER', 'static/profile_pics')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name', current_user.full_name)
        current_user.email = request.form.get('email', current_user.email)
        current_user.emergency_contact = request.form.get('emergency_contact', current_user.emergency_contact)
        current_user.working_experience = request.form.get('working_experience', current_user.working_experience)
        current_user.current_workplace = request.form.get('current_workplace', current_user.current_workplace)
        current_user.emergency_relationship = request.form.get('emergency_relationship', current_user.emergency_relationship)
        current_user.address = request.form.get('address', current_user.address)
        current_user.postcode = request.form.get('postcode', current_user.postcode)
        current_user.state = request.form.get('state', current_user.state)

        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file_path = os.path.join(upload_folder, filename)
                file.save(file_path)
                current_user.Profile_picture = filename

        db.session.commit()
        flash('Your profile has been updated.')
        return redirect(url_for('profile'))

    return render_template('profile.html', user=current_user)

# New route to display agency info for regular users (fix for missing 'agency' endpoint)
@app.route('/agency')
@login_required
def agency():
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_agencies'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    agencies = []
    user_agency_id = getattr(current_user, 'agency_id', None)
    if user_agency_id:
        ag = Agency.query.get(user_agency_id)
        if ag:
            agencies = [ag]
    if not agencies:
        agencies = Agency.query.all()
    return render_template('agency.html', agencies=agencies)

# Register a safe url_for for templates to avoid BuildErrors if an endpoint is missing
from flask import url_for as _flask_url_for

def safe_url_for(endpoint, **values):
    try:
        return _flask_url_for(endpoint, **values)
    except Exception:
        return '#'

app.jinja_env.globals['safe_url_for'] = safe_url_for

# ------------------------
# Admin: Dashboard
# ------------------------
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    try:
        dashboard = Management().getDashboard()
    except Exception:
        dashboard = {
            'total_users': User.query.count(),
            'total_modules': Module.query.count(),
            'total_certificates': Certificate.query.count(),
            'active_trainers': Trainer.query.filter_by(active_status=True).count(),
            'completion_stats': [],
            'performance_metrics': None
        }
    return render_template('admin_dashboard.html', dashboard=dashboard)

# ------------------------
# Admin: Course Management
# ------------------------
@app.route('/admin_course_management')
@login_required
def admin_course_management():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    courses = Course.query.order_by(Course.name.asc()).all()
    # Build mapping of course_id -> sorted modules list
    course_modules = {}
    for c in courses:
        mods = list(c.modules) if c.modules else []
        course_modules[c.course_id] = _series_sort(mods)
    return render_template('admin_course_management.html', courses=courses, course_modules=course_modules)

@app.route('/courses/create', methods=['POST'])
@login_required
def create_course():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    name = request.form.get('name', '').strip()
    code = (request.form.get('code', '') or '').strip().upper()
    allowed_category = request.form.get('allowed_category', 'both')
    description = request.form.get('description')
    if not name or not code:
        flash('Name and code are required', 'danger')
        return redirect(url_for('admin_course_management'))
    if Course.query.filter(Course.code.ilike(code)).first():
        flash('A course with this code already exists', 'warning')
        return redirect(url_for('admin_course_management'))
    try:
        c = Course(name=name, code=code, allowed_category=allowed_category, description=description)
        db.session.add(c)
        db.session.commit()
        flash('Course created', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to create course: {e}', 'danger')
    return redirect(url_for('admin_course_management'))

@app.route('/courses/<int:course_id>/update', methods=['POST'])
@login_required
def update_course(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    c = Course.query.get_or_404(course_id)
    c.name = request.form.get('name', c.name)
    c.allowed_category = request.form.get('allowed_category', c.allowed_category)
    c.description = request.form.get('description', c.description)
    try:
        db.session.commit()
        flash('Course updated', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update course: {e}', 'danger')
    return redirect(url_for('admin_course_management'))

@app.route('/courses/<int:course_id>/delete', methods=['POST'])
@login_required
def delete_course(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    c = Course.query.get_or_404(course_id)
    try:
        # Optionally prevent delete if modules exist
        if c.modules:
            for m in list(c.modules):
                # Detach modules rather than hard delete to avoid cascading issues
                m.course_id = None
        db.session.delete(c)
        db.session.commit()
        flash('Course deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to delete course: {e}', 'danger')
    return redirect(url_for('admin_course_management'))

@app.route('/courses/<int:course_id>/modules/add', methods=['POST'])
@login_required
def add_course_module(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    c = Course.query.get_or_404(course_id)
    name = request.form.get('module_name', '').strip()
    series = request.form.get('series_number', '')
    content = request.form.get('content')
    if not name:
        flash('Module name is required', 'danger')
        return redirect(url_for('admin_course_management'))
    try:
        m = Module(module_name=name, series_number=series, content=content, course_id=c.course_id, module_type=c.code)
        db.session.add(m)
        db.session.commit()
        flash('Module created', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to create module: {e}', 'danger')
    return redirect(url_for('admin_course_management'))

@app.route('/modules/<int:module_id>/update', methods=['POST'])
@login_required
def update_course_module(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    m = Module.query.get_or_404(module_id)
    m.module_name = request.form.get('module_name', m.module_name)
    m.series_number = request.form.get('series_number', m.series_number)
    m.content = request.form.get('content', m.content)
    try:
        db.session.commit()
        flash('Module updated', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update module: {e}', 'danger')
    return redirect(url_for('admin_course_management'))

@app.route('/modules/<int:module_id>/delete', methods=['POST'])
@login_required
def delete_course_module(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    m = Module.query.get_or_404(module_id)
    try:
        # Clean up related user modules and certificates to maintain integrity
        UserModule.query.filter_by(module_id=m.module_id).delete()
        Certificate.query.filter_by(module_id=m.module_id).delete()
        db.session.delete(m)
        db.session.commit()
        flash('Module deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to delete module: {e}', 'danger')
    return redirect(url_for('admin_course_management'))

@app.route('/modules/<int:module_id>/content', methods=['POST'])
@login_required
def manage_module_content(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    m = Module.query.get_or_404(module_id)
    ctype = request.form.get('content_type')
    try:
        if ctype == 'slide':
            f = request.files.get('slide_file')
            if f and f.filename:
                os.makedirs(os.path.join(app.root_path, 'static', 'uploads'), exist_ok=True)
                fname = secure_filename(f.filename)
                target = os.path.join(app.root_path, 'static', 'uploads', fname)
                f.save(target)
                m.slide_url = fname
        elif ctype == 'video':
            m.youtube_url = request.form.get('youtube_url')
        elif ctype == 'quiz':
            # Build quiz JSON from dynamic fields quiz_question_{i}, answer_{i}_{j}, correct_answer_{i}
            questions = []
            # Determine how many questions by scanning keys
            indices = []
            for k in request.form.keys():
                if k.startswith('quiz_question_'):
                    try:
                        indices.append(int(k.split('_')[-1]))
                    except Exception:
                        pass
            indices = sorted(set(indices))
            for i in indices:
                qtext = request.form.get(f'quiz_question_{i}', '').strip()
                if not qtext:
                    continue
                answers = []
                for j in range(1, 6):
                    atext = request.form.get(f'answer_{i}_{j}')
                    if atext:
                        answers.append({'text': atext, 'isCorrect': False})
                correct_idx = request.form.get(f'correct_answer_{i}')
                try:
                    correct_idx = int(correct_idx)
                except Exception:
                    correct_idx = 1
                # Mark correct answer (1-based index)
                if 1 <= correct_idx <= len(answers):
                    answers[correct_idx - 1]['isCorrect'] = True
                questions.append({'question': qtext, 'answers': answers})
            # Optional quiz image
            qimg = request.files.get('quiz_image')
            if qimg and qimg.filename:
                os.makedirs(os.path.join(app.root_path, 'static', 'uploads'), exist_ok=True)
                qname = secure_filename(qimg.filename)
                qpath = os.path.join(app.root_path, 'static', 'uploads', qname)
                qimg.save(qpath)
                m.quiz_image = qname
            m.quiz_json = json.dumps(questions)
        db.session.commit()
        flash('Content saved', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to save content: {e}', 'danger')
    return redirect(url_for('admin_course_management'))

# ------------------------
# Admin: Maintenance
# ------------------------
@app.route('/recalculate_ratings')
@login_required
def recalculate_ratings():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        # Recalculate module star ratings from average scores
        mods = Module.query.all()
        for m in mods:
            scores = [um.score for um in UserModule.query.filter_by(module_id=m.module_id, is_completed=True).all() if um.score is not None]
            if scores:
                avg = sum(scores) / len(scores)
                stars = max(1, min(5, int(round(avg / 20))))
                m.star_rating = stars
            else:
                m.star_rating = 0
        # Recalculate user rating_star as average stars across completed modules
        users = User.query.all()
        for u in users:
            ums = UserModule.query.filter_by(user_id=u.User_id, is_completed=True).all()
            scores = [um.score for um in ums if um.score is not None]
            if scores:
                avg = sum(scores) / len(scores)
                u.rating_star = max(1, min(5, int(round(avg / 20))))
            else:
                u.rating_star = 0
        db.session.commit()
        flash('Ratings recalculated', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to recalculate ratings: {e}', 'danger')
    return redirect(url_for('admin_dashboard'))

# ------------------------
# User: My Certificates
# ------------------------
@app.route('/my_certificates')
@login_required
def my_certificates():
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    certs = Certificate.query.filter_by(user_id=current_user.User_id).order_by(Certificate.issue_date.desc()).all()
    return render_template('my_certificates.html', certificates=certs, user=current_user)

# ------------------------
# Admin: Certificates
# ------------------------
@app.route('/admin_certificates')
@login_required
def admin_certificates():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    certificates = Certificate.query.order_by(Certificate.certificate_id.desc()).all()
    # Determine current template URL if exists
    tpl_path = os.path.join(app.root_path, 'static', 'cert_templates', 'Training_cert.pdf')
    cert_template_url = _flask_url_for('static', filename='cert_templates/Training_cert.pdf') if os.path.exists(tpl_path) else None
    return render_template('admin_certificates.html', certificates=certificates, cert_template_url=cert_template_url)

@app.route('/admin_certificates/upload_template', methods=['POST'])
@login_required
def upload_cert_template():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    file = request.files.get('cert_template')
    if not file or file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('admin_certificates'))
    try:
        target_dir = os.path.join(app.root_path, 'static', 'cert_templates')
        os.makedirs(target_dir, exist_ok=True)
        filename = secure_filename(file.filename)
        target_path = os.path.join(target_dir, filename)
        file.save(target_path)
        flash('Template uploaded', 'success')
    except Exception as e:
        flash(f'Upload failed: {e}', 'danger')
    return redirect(url_for('admin_certificates'))

@app.route('/admin_certificates/delete', methods=['POST'])
@login_required
def delete_certificates_bulk():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    ids = request.form.getlist('cert_ids')
    if not ids:
        flash('No certificates selected', 'warning')
        return redirect(url_for('admin_certificates'))
    try:
        for cid in ids:
            c = Certificate.query.get(cid)
            if c:
                db.session.delete(c)
        db.session.commit()
        flash('Selected certificates deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Deletion failed: {e}', 'danger')
    return redirect(url_for('admin_certificates'))

# ------------------------
# Admin: Progress Monitor
# ------------------------
@app.route('/monitor_progress')
@login_required
def monitor_progress():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    # Join user modules with users, modules, agencies
    user_modules = (db.session.query(UserModule, User, Module, Agency)
        .join(User, UserModule.user_id == User.User_id)
        .join(Module, UserModule.module_id == Module.module_id)
        .join(Agency, User.agency_id == Agency.agency_id)
        .order_by(UserModule.completion_date.desc())
        .all())
    existing_certs = {(c.user_id, c.module_id) for c in Certificate.query.all()}
    return render_template('monitor_progress.html', user_modules=user_modules, existing_certs=existing_certs)

@app.route('/issue_certificate', methods=['POST'])
@login_required
def issue_certificate():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    user_id = request.form.get('user_id')
    module_id = request.form.get('module_id')
    if not user_id or not module_id:
        flash('Missing user or module ID', 'danger')
        return redirect(url_for('monitor_progress'))
    um = UserModule.query.filter_by(user_id=user_id, module_id=module_id).first()
    module = Module.query.get(module_id)
    if not um or not module:
        flash('Record not found', 'danger')
        return redirect(url_for('monitor_progress'))
    if not um.is_completed or (um.score or 0) <= 50:
        flash('User not eligible for certificate', 'warning')
        return redirect(url_for('monitor_progress'))
    try:
        # Create certificate entry
        rating = max(1, min(5, int(round((um.score or 0) / 20))))
        cert = Certificate(user_id=um.user_id,
                           module_id=um.module_id,
                           module_type=module.module_type,
                           issue_date=date.today(),
                           star_rating=rating,
                           score=(um.score or 0),
                           certificate_url='#')
        db.session.add(cert)
        db.session.commit()
        flash('Certificate issued', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to issue certificate: {e}', 'danger')
    return redirect(url_for('monitor_progress'))

# ------------------------
# Admin: Agencies
# ------------------------
@app.route('/admin_agencies')
@login_required
def admin_agencies():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
    return render_template('admin_agencies.html', agencies=agencies)

@app.route('/admin_agencies/add', methods=['POST'])
@login_required
def add_agency():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        a = Agency(
            agency_name=request.form.get('agency_name'),
            PIC=request.form.get('PIC'),
            contact_number=request.form.get('contact_number'),
            email=request.form.get('email'),
            address=request.form.get('address'),
            Reg_of_Company=request.form.get('Reg_of_Company')
        )
        db.session.add(a)
        db.session.commit()
        flash('Agency added', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to add agency: {e}', 'danger')
    return redirect(url_for('admin_agencies'))

@app.route('/admin_agencies/<int:agency_id>/edit', methods=['POST'])
@login_required
def edit_agency(agency_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    a = Agency.query.get_or_404(agency_id)
    try:
        a.agency_name = request.form.get('agency_name', a.agency_name)
        a.PIC = request.form.get('PIC', a.PIC)
        a.contact_number = request.form.get('contact_number', a.contact_number)
        a.email = request.form.get('email', a.email)
        a.address = request.form.get('address', a.address)
        a.Reg_of_Company = request.form.get('Reg_of_Company', a.Reg_of_Company)
        db.session.commit()
        flash('Agency updated', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update agency: {e}', 'danger')
    return redirect(url_for('admin_agencies'))

# ------------------------
# Legacy/stub routes
# ------------------------
@app.route('/admin_modules')
@login_required
def admin_modules():
    # Redirect old modules page links to new course management
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    return redirect(url_for('admin_course_management'))

# Initialize database function
def init_db():
    with app.app_context():
        db.create_all()

        # Create default agency if not exists
        if not Agency.query.first():
            agency = Agency(
                agency_name='Default Security Agency',
                contact_number='+1234567890',
                address='123 Security Street, Safety City',
                Reg_of_Company='REG123456',
                PIC='Default PIC',  # was 'John Doe'
                email='contact@defaultagency.com'
            )
            db.session.add(agency)
            db.session.commit()

        # Create default admin if not exists
        if not Admin.query.first():
            # Admin Account
            admin = Admin(
                username='admin',
                email='admin@security-training.com',
                role='admin'
            )
            admin.set_password('admin123')
            db.session.add(admin)

            # Secondary Admin Account
            admin2 = Admin(
                username='manager',
                email='manager@security-training.com',
                role='admin'
            )
            admin2.set_password('manager123')
            db.session.add(admin2)

            db.session.commit()

        # Create default modules
        # For debugging: clear existing modules to ensure fresh data
        # db.session.query(Module).delete()
        # db.session.commit()

        # modules = [
        #     {
        #         'module_name': 'TNG: Basic Security Principles',
        #         'module_type': 'Theory',
        #         'series_number': 'TNG001',
        #         'content': 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
        #     },
        #     {
        #         'module_name': 'TNG: Emergency Response Procedures',
        #         'module_type': 'Practical',
        #         'series_number': 'TNG002',
        #         'content': 'Emergency response procedures and protocols for TNG. Learn how to handle various emergency situations including fire, medical emergencies, and security breaches.'
        #     },
        #     {
        #         'module_name': 'CSG: Communication Skills',
        #         'module_type': 'Theory',
        #         'series_number': 'CSG001',
        #         'content': 'Effective communication in security situations for CSG. This module teaches proper communication techniques with clients, colleagues, and emergency services.'
        #     },
        #     {
        #         'module_name': 'CSG: Legal Aspects of Security',
        #         'module_type': 'Theory',
        #         'series_number': 'CSG002',
        #         'content': 'Legal framework and regulations for CSG security personnel. Understanding your rights and responsibilities as a security guard.'
        #     }
        # ]

        # for module_data in modules:
        #     module = Module(**module_data)
        #     db.session.add(module)

        # db.session.commit()

        # Create mock trainer accounts
        if not Trainer.query.first():
            # Get the first module for trainer assignment
            first_module = Module.query.first()

            trainer1 = Trainer(
                name='Sarah Johnson',
                email='sarah.trainer@security-training.com',
                address='456 Training Ave, Education City',
                active_status=True,
                availability='Monday-Friday 9AM-5PM',
                contact_number=1234567890,
                course='Security Guard Training',
                module_id=first_module.module_id if first_module else None
            )
            trainer1.set_password('sarah123')
            db.session.add(trainer1)

            trainer2 = Trainer(
                name='Mike Thompson',
                email='mike.trainer@security-training.com',
                address='789 Instructor St, Learning Town',
                active_status=True,
                availability='Monday-Wednesday 10AM-6PM',
                contact_number=1234567891,
                course='Advanced Security Training',
                module_id=first_module.module_id if first_module else None
            )
            trainer2.set_password('mike123')
            db.session.add(trainer2)

            db.session.commit()

        # Create management entry
        if not Management.query.first():
            management = Management(
                manager_name='David Administrator',
                designation='Training Manager',
                email='david.admin@security-training.com',
                signature='D. Administrator'
            )
            db.session.add(management)
            db.session.commit()

        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        try:
            module_columns = [c['name'] for c in inspector.get_columns('module')]
        except Exception:
            module_columns = []
        # Add course_id column if missing
        if 'course_id' not in module_columns:
            try:
                db.session.execute(text('ALTER TABLE module ADD COLUMN course_id INTEGER NULL'))
                # Add FK constraint if course table exists
                course_tables = inspector.get_table_names()
                if 'course' in course_tables:
                    # Attempt to add constraint (ignore if fails)
                    try:
                        db.session.execute(text('ALTER TABLE module ADD CONSTRAINT module_course_id_fkey FOREIGN KEY (course_id) REFERENCES course (course_id) ON DELETE SET NULL'))
                    except Exception:
                        pass
                db.session.commit()
                print('[INIT_DB] Added course_id column to module table.')
            except Exception as e:
                db.session.rollback()
                print(f'[INIT_DB] Skipped adding course_id (possibly already in progress or permissions issue): {e}')
        # Ensure default courses for existing module_type codes
        try:
            # Create course table if somehow not created (db.create_all should do this)
            if 'course' not in inspector.get_table_names():
                db.create_all()
            existing_codes = {c.code for c in Course.query.all()}
            distinct_types = [row[0] for row in db.session.query(Module.module_type).distinct().all() if row[0]]
            for code in distinct_types:
                ucode = code.upper()
                if ucode not in existing_codes and len(ucode) <= 50:
                    course = Course(name=f'{ucode} Course', code=ucode, description=f'Auto-generated course for {ucode}', allowed_category='both')
                    db.session.add(course)
            db.session.commit()
            # Map modules without course_id
            code_to_course = {c.code.upper(): c.course_id for c in Course.query.all()}
            unmapped_modules = Module.query.filter(Module.course_id.is_(None)).all()
            changed = 0
            for m in unmapped_modules:
                cid = code_to_course.get(m.module_type.upper())
                if cid:
                    m.course_id = cid
                    changed += 1
            if changed:
                db.session.commit()
                print(f'[INIT_DB] Linked {changed} existing modules to courses.')
        except Exception as e:
            db.session.rollback()
            print(f'[INIT_DB] Course backfill skipped: {e}')

        # Auto-remove legacy hardcoded sample users if they still exist (they were previously inserted in older versions)
        # Set env var KEEP_SAMPLE_USERS=1 to skip removal.
        if not os.environ.get('KEEP_SAMPLE_USERS'):
            legacy_sample_emails = [
                'john.doe@trainee.com',
                'jane.smith@trainee.com',
                'robert.wilson@trainee.com'
            ]
            from models import WorkHistory
            removed = 0
            for em in legacy_sample_emails:
                u = User.query.filter_by(email=em).first()
                if u:
                    UserModule.query.filter_by(user_id=u.User_id).delete()
                    Certificate.query.filter_by(user_id=u.User_id).delete()
                    WorkHistory.query.filter_by(user_id=u.User_id).delete()
                    db.session.delete(u)
                    removed += 1
            if removed:
                try:
                    db.session.commit()
                    print(f"[INIT_DB] Removed {removed} legacy sample user(s).")
                except Exception as e:
                    db.session.rollback()
                    print(f"[INIT_DB] Failed removing legacy sample users: {e}")

@app.route('/cleanup-db-for-mockup')
def cleanup_db_for_mockup():
    try:
        # --- Clean legacy sample Users ---
        legacy_names = ['John Doe', 'Jane Smith', 'Robert Wilson']
        legacy_emails = ['john.doe@trainee.com','jane.smith@trainee.com','robert.wilson@trainee.com']
        legacy_users = User.query.filter( (User.full_name.in_(legacy_names)) | (User.email.in_(legacy_emails)) ).all()
        for user in legacy_users:
            UserModule.query.filter_by(user_id=user.User_id).delete()
            Certificate.query.filter_by(user_id=user.User_id).delete()
            from models import WorkHistory
            WorkHistory.query.filter_by(user_id=user.User_id).delete()
            db.session.delete(user)
        # --- Optionally keep a single admin/trainer baseline; no change to existing logic ---
        db.session.commit()
        flash("Legacy sample users removed (if any existed).")
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred during cleanup: {e}")
    return redirect(url_for('index'))

@app.route('/user_courses_dashboard')
@login_required
def user_courses_dashboard():
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))

    # Import required models
    from models import UserCourseProgress, Course, Module, UserModule

    # Determine eligible courses for this user based on allowed_category
    user_category = current_user.user_category or 'citizen'
    eligible_courses = Course.query.filter(
        (Course.allowed_category == 'both') | (Course.allowed_category == user_category)
    ).all()

    # Fetch existing course progress rows for user (keyed by course_id)
    progress_rows = {p.course_id: p for p in UserCourseProgress.query.filter_by(user_id=current_user.User_id).all()}

    user_courses = []
    created_any = False
    for course in eligible_courses:
        code_u = (course.code or '').upper()
        # Hard mapping guard: hide CSG for foreigners and TNG for citizens
        if (code_u == 'CSG' and user_category != 'citizen') or (code_u == 'TNG' and user_category != 'foreigner'):
            continue
        # Gather modules belonging to this course
        course_modules = Module.query.filter_by(course_id=course.course_id).all()
        if not course_modules:
            course_modules = Module.query.filter(Module.module_type == code_u).all()
        module_ids = [m.module_id for m in course_modules]
        total = len(module_ids)
        if total:
            completed_count = UserModule.query.filter(
                UserModule.user_id == current_user.User_id,
                UserModule.is_completed.is_(True),
                UserModule.module_id.in_(module_ids)
            ).count()
        else:
            completed_count = 0
        progress_pct = int((completed_count / total) * 100) if total > 0 else 0
        is_complete = total > 0 and completed_count == total

        # Ensure a UserCourseProgress row exists so other grade logic works
        ucp = progress_rows.get(course.course_id)
        if not ucp:
            ucp = UserCourseProgress(user_id=current_user.User_id, course_id=course.course_id, completed=is_complete)
            db.session.add(ucp)
            progress_rows[course.course_id] = ucp
            created_any = True
        else:
            # Update completion flag if status changed
            if ucp.completed != is_complete:
                ucp.completed = is_complete
        user_courses.append({
            'id': course.course_id,
            'name': course.name,
            'progress': progress_pct,
            'module_type': course.code
        })

    if created_any:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"Failed committing new UserCourseProgress rows: {e}")
    else:
        # Commit only if any existing progress rows updated
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return render_template('user_courses_dashboard.html', user=current_user, user_courses=user_courses)

# --- Application entrypoint ---
if __name__ == '__main__':
    # Initialize DB (idempotent)
    try:
        init_db()
    except Exception as e:
        print(f'[INIT ERROR] {e}')
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0' if os.environ.get('RENDER') else '127.0.0.1'
    print(f"[START] Flask app starting on {host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)
