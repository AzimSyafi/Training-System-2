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
                current_user.working_experience = request.form.get('working_experience')
                rec_date = request.form.get('recruitment_date')
                if rec_date:
                    try:
                        current_user.recruitment_date = datetime.strptime(rec_date, '%Y-%m-%d').date()
                    except Exception:
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
