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

    # Determine allowed course code based on user category
    allowed_code = 'TNG' if current_user.user_category == 'foreigner' else 'CSG'

    # Only show modules belonging to the allowed course code
    user_modules = (UserModule.query
                     .join(Module, UserModule.module_id == Module.module_id)
                     .filter(UserModule.user_id == current_user.User_id,
                             Module.module_type == allowed_code)
                     .all())

    # Available modules limited to allowed course code (for potential UI usage)
    available_modules = Module.query.filter_by(module_type=allowed_code).all()

    # Precompute whether rating should be shown (all modules completed)
    rating_unlocked = current_user.has_completed_all_modules_in_course(allowed_code)

    return render_template('user_dashboard.html',
                         user=current_user,
                         user_modules=user_modules,
                         available_modules=available_modules,
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
    user_module = UserModule.query.filter_by(
        user_id=current_user.User_id,
        module_id=module_id
    ).first()

    # Get all modules for the same course/type as the current module
    modules = Module.query.filter_by(module_type=module.module_type).all()

    if not user_module:
        flash('You are not enrolled in this module.')
        return redirect(url_for('user_dashboard'))

    return render_template('module_view.html', module=module, user_module=user_module, modules=modules)

@app.route('/complete_module/<int:module_id>', methods=['POST'])
@login_required
def complete_module(module_id):
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))

    user_module = UserModule.query.filter_by(
        user_id=current_user.User_id,
        module_id=module_id
    ).first()

    if user_module:
        score = float(request.form['score'])
        user_module.complete_module(score)

        # Color coding based on score
        color = current_user.get_color_by_score(score)
        flash(f'Module completed with score: {score}% (Status: {color})')

        # Check if eligible for certificate
        if current_user.EligibleForCertificate():
            # Issue certificate
            admin = Admin.query.first()  # Get any admin for certificate issuance
            if admin:
                # fixed method name
                admin.issueCertificate(current_user.User_id, module_id)
                flash('Certificate issued successfully!')

        # Check if user completed all modules of this course type
        module = Module.query.get(module_id)
        if module:
            course_type = module.module_type
            # Debug output for certificate eligibility
            import sys
            print(f"[DEBUG] Checking certificate eligibility for user {current_user.User_id}", file=sys.stderr)
            print(f"[DEBUG] Module ID: {module_id}", file=sys.stderr)
            if module:
                course_type = module.module_type
                print(f"[DEBUG] Course type: {course_type}", file=sys.stderr)
                all_course_modules = Module.query.filter_by(module_type=course_type).all()
                all_module_ids = [m.module_id for m in all_course_modules]
                print(f"[DEBUG] All module IDs for course: {all_module_ids}", file=sys.stderr)
                completed_modules = UserModule.query.filter_by(user_id=current_user.User_id, is_completed=True).filter(UserModule.module_id.in_(all_module_ids)).all()
                print(f"[DEBUG] Completed modules: {[{'id': um.module_id, 'score': um.score} for um in completed_modules]}", file=sys.stderr)
                eligible = current_user.EligibleForCertificate(course_type)
                print(f"[DEBUG] Eligible for certificate: {eligible}", file=sys.stderr)
                if eligible:
                    # Calculate overall_percentage for this user and course_type
                    all_course_modules = Module.query.filter_by(module_type=course_type).all()
                    all_module_ids = [m.module_id for m in all_course_modules]
                    completed_modules = UserModule.query.filter_by(user_id=current_user.User_id, is_completed=True).filter(UserModule.module_id.in_(all_module_ids)).all()
                    total_correct = 0
                    total_questions = 0
                    import json
                    for um in completed_modules:
                        if um.quiz_answers:
                            try:
                                selected_indices = json.loads(um.quiz_answers)
                                module = Module.query.get(um.module_id)
                                if module and module.quiz_json:
                                    quiz = json.loads(module.quiz_json)
                                    for idx, selected in enumerate(selected_indices):
                                        if idx < len(quiz):
                                            total_questions += 1
                                            answers = quiz[idx].get('answers', [])
                                            if isinstance(selected, int) and 0 <= selected < len(answers):
                                                if answers[selected].get('isCorrect') in [True, 'true', 'True', 1, '1']:
                                                    total_correct += 1
                            except Exception:
                                continue
                    overall_percentage = int((total_correct / total_questions) * 100) if total_questions > 0 else 0
                    from generate_certificate import generate_certificate
                    cert_path = generate_certificate(current_user.User_id, course_type, overall_percentage)
                    print(f"[DEBUG] Certificate generated at: {cert_path}", file=sys.stderr)
                    flash(f'Congratulations! You have completed all modules for {course_type}. Certificate generated.')
                    # Ensure course progress exists upon completion through manual module completion path
                    try:
                        from models import UserCourseProgress, Course
                        course_obj = Course.query.filter(Course.code.ilike(course_type)).first()
                        if course_obj:
                            ucp = UserCourseProgress.query.filter_by(user_id=current_user.User_id, course_id=course_obj.course_id).first()
                            if not ucp:
                                db.session.add(UserCourseProgress(user_id=current_user.User_id, course_id=course_obj.course_id, reattempt_count=0))
                                db.session.commit()
                    except Exception as ce:
                        db.session.rollback()
                        print(f'[COURSE PROGRESS CREATE ERROR] {ce}')
    return redirect(url_for('user_dashboard'))

@app.route('/my_certificates')
@login_required
def my_certificates():
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))

    certificates = Certificate.query.filter_by(user_id=current_user.User_id).all()
    from models import UserModule, Module
    import json
    user_modules = UserModule.query.filter_by(user_id=current_user.User_id).all()
    total_correct = 0
    total_questions = 0
    for um in user_modules:
        if um.quiz_answers:
            try:
                # quiz_answers is a list of selected answer indices
                selected_indices = json.loads(um.quiz_answers)
                module = Module.query.get(um.module_id)
                if module and module.quiz_json:
                    quiz = json.loads(module.quiz_json)
                    for idx, selected in enumerate(selected_indices):
                        if idx < len(quiz):
                            answers = quiz[idx].get('answers', [])
                            total_questions += 1
                            if isinstance(selected, int) and 0 <= selected < len(answers):
                                if answers[selected].get('isCorrect') in [True, 'true', 'True', 1, '1']:
                                    total_correct += 1
            except Exception:
                continue
    overall_percentage = int((total_correct / total_questions) * 100) if total_questions > 0 else 0
    for cert in certificates:
        user_module = UserModule.query.filter_by(user_id=cert.user_id, module_id=cert.module_id).first()
        score = user_module.score if user_module else 0
        cert.star_rating = max(1, min(5, int(round(score / 20))))
        cert.overall_score = int(score) if user_module else 0
    return render_template('my_certificates.html', certificates=certificates, overall_percentage=overall_percentage)

# Admin Dashboard and Workflow
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    print(f"[DEBUG] Accessing admin_dashboard, session['user_type']: {session.get('user_type')}, current_user: {type(current_user)}")
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    # Get dashboard statistics
    management = Management.query.first()
    if not management:
        # Create default management entry
        management = Management(
            manager_name='System Administrator',
            designation='Admin',
            email=current_user.email
        )
        db.session.add(management)
        db.session.commit()

    dashboard_data = management.getDashboard()
    return render_template('admin_dashboard.html', dashboard=dashboard_data)

@app.route('/admin/modules')
@login_required
def admin_modules():
    # Deprecated: redirect to new course management page
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    return redirect(url_for('admin_course_management'))

# ------------------------
# Course Management (New)
# ------------------------
# Helper to sort modules by numeric part of series_number
import re as _re

def _series_sort(mods):
    def key(m):
        sn = (m.series_number or '').strip()
        match = _re.search(r'(\d+)$', sn)
        return (int(match.group(1)) if match else 0, sn)
    return sorted(mods, key=key)

@app.route('/admin/course_management')
@login_required
def admin_course_management():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    courses = Course.query.order_by(Course.name).all()
    # Preload modules grouped by course with proper numeric ordering
    course_modules = {}
    for c in courses:
        raw_mods = Module.query.filter_by(course_id=c.course_id).all()
        course_modules[c.course_id] = _series_sort(raw_mods)
    return render_template('admin_course_management.html', courses=courses, course_modules=course_modules)

@app.route('/admin/courses', methods=['POST'])
@login_required
def create_course():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    name = request.form.get('name')
    code = request.form.get('code')
    description = request.form.get('description')
    allowed_category = request.form.get('allowed_category', 'both')
    if not name or not code:
        flash('Name and Code are required', 'danger')
        return redirect(url_for('admin_course_management'))
    code = code.upper().strip()
    if Course.query.filter_by(code=code).first():
        flash('Course code already exists', 'danger')
        return redirect(url_for('admin_course_management'))
    course = Course(name=name, code=code, description=description, allowed_category=allowed_category)
    db.session.add(course)
    db.session.commit()
    flash('Course created', 'success')
    return redirect(url_for('admin_course_management'))

@app.route('/admin/courses/<int:course_id>/update', methods=['POST'])
@login_required
def update_course(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    course = Course.query.get_or_404(course_id)
    course.name = request.form.get('name', course.name)
    course.description = request.form.get('description', course.description)
    course.allowed_category = request.form.get('allowed_category', course.allowed_category)
    db.session.commit()
    flash('Course updated', 'success')
    return redirect(url_for('admin_course_management'))

@app.route('/admin/courses/<int:course_id>/delete', methods=['POST'])
@login_required
def delete_course(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    course = Course.query.get_or_404(course_id)
    if course.modules and len(course.modules) > 0:
        flash('Cannot delete course with existing modules. Remove modules first.', 'danger')
        return redirect(url_for('admin_course_management'))
    db.session.delete(course)
    db.session.commit()
    flash('Course deleted', 'success')
    return redirect(url_for('admin_course_management'))

@app.route('/admin/courses/<int:course_id>/modules', methods=['POST'])
@login_required
def add_course_module(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    course = Course.query.get_or_404(course_id)
    module_name = request.form.get('module_name')
    series_number = request.form.get('series_number')
    content = request.form.get('content')
    if not module_name:
        flash('Module name required', 'danger')
        return redirect(url_for('admin_course_management'))

    # Ensure PostgreSQL sequence is aligned with current max(module_id) to avoid duplicate key errors
    def ensure_module_sequence():
        try:
            from sqlalchemy import text
            max_id = db.session.execute(text("SELECT COALESCE(MAX(module_id),0) FROM module")).scalar() or 0
            # Advance sequence only if it's behind
            current_seq = db.session.execute(text("SELECT last_value FROM module_module_id_seq"))\
                .scalar() if db.session.bind.dialect.name == 'postgresql' else None
            if current_seq is None or current_seq < max_id:
                db.session.execute(text("SELECT setval('module_module_id_seq', :new_val, true)"), {'new_val': max_id})
                db.session.commit()
        except Exception as e:
            app.logger.warning(f"Module sequence sync skipped: {e}")

    if db.session.bind and db.session.bind.dialect.name == 'postgresql':
        ensure_module_sequence()

    module = Module(module_name=module_name,
                    module_type=course.code.upper(),
                    series_number=series_number,
                    content=content,
                    course_id=course.course_id)
    db.session.add(module)
    try:
        db.session.commit()
    except IntegrityError:
        # Retry once after forcing sequence realignment
        db.session.rollback()
        if db.session.bind and db.session.bind.dialect.name == 'postgresql':
            ensure_module_sequence()
        db.session.add(module)
        db.session.commit()
    flash('Module added', 'success')
    return redirect(url_for('admin_course_management'))

@app.route('/admin/modules/<int:module_id>/update', methods=['POST'])
@login_required
def update_course_module(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    module = Module.query.get_or_404(module_id)
    # module_type enforced by course; don't allow change
    module.module_name = request.form.get('module_name', module.module_name)
    module.series_number = request.form.get('series_number', module.series_number)
    module.content = request.form.get('content', module.content)
    db.session.commit()
    flash('Module updated', 'success')
    return redirect(url_for('admin_course_management'))

@app.route('/admin/modules/<int:module_id>/delete', methods=['POST'])
@login_required
def delete_course_module(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    module = Module.query.get_or_404(module_id)
    db.session.delete(module)
    db.session.commit()
    flash('Module deleted', 'success')
    return redirect(url_for('admin_course_management'))

@app.route('/admin/modules/<int:module_id>/content', methods=['POST'])
@login_required
def manage_module_content(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    module = Module.query.get_or_404(module_id)
    content_type = request.form.get('content_type')
    if content_type == 'slide':
        file = request.files.get('slide_file')
        if file and file.filename and file.filename.lower().endswith(('.pdf', '.pptx')):
            from werkzeug.utils import secure_filename
            filename = secure_filename(file.filename)
            # prevent collision
            base, ext = os.path.splitext(filename)
            counter = 1
            target_path = os.path.join(UPLOAD_CONTENT_FOLDER, filename)
            while os.path.exists(target_path):
                filename = f"{base}_{counter}{ext}"
                target_path = os.path.join(UPLOAD_CONTENT_FOLDER, filename)
                counter += 1
            file.save(target_path)
            module.slide_url = filename
            db.session.commit()
            flash('Slide uploaded', 'success')
        else:
            flash('Invalid slide file', 'danger')
    elif content_type == 'video':
        youtube_url = request.form.get('youtube_url')
        module.youtube_url = youtube_url
        db.session.commit()
        flash('Video URL saved', 'success')
    elif content_type == 'quiz':
        # Support up to 5 questions: quiz_question_1..5, answer_1_1..answer_5_5, correct_answer_1..5
        quiz_payload = []
        any_new_pattern = False
        for qn in range(1, 6):
            q_text = request.form.get(f'quiz_question_{qn}')
            if q_text:
                any_new_pattern = True
                answers = []
                correct_idx = request.form.get(f'correct_answer_{qn}')
                for an in range(1, 6):
                    ans_text = request.form.get(f'answer_{qn}_{an}')
                    if ans_text:
                        answers.append({
                            'text': ans_text,
                            'isCorrect': str(an) == str(correct_idx)
                        })
                if answers:
                    quiz_payload.append({'question': q_text, 'answers': answers})
        if not any_new_pattern:
            # Fallback to legacy single-question field names
            question = request.form.get('quiz_question')
            if question:
                answers = []
                correct_index = request.form.get('correct_answer')
                for i in range(1, 6):
                    ans_text = request.form.get(f'answer_{i}')
                    if ans_text:
                        answers.append({'text': ans_text, 'isCorrect': str(i) == str(correct_index)})
                if answers:
                    quiz_payload.append({'question': question, 'answers': answers})
        if quiz_payload:
            import json as _json
            module.quiz_json = _json.dumps(quiz_payload)
            db.session.commit()
            flash(f'Quiz saved ({len(quiz_payload)} question(s))', 'success')
        else:
            flash('Quiz data incomplete', 'danger')
    else:
        flash('Unknown content type', 'danger')
    return redirect(url_for('admin_course_management'))

@app.route('/trainer/upload_content', methods=['GET', 'POST'])
@login_required
def upload_content():
    """Trainer-facing content upload page (slides / video URL / quiz)."""
    if not isinstance(current_user, Trainer):
        # Only trainers permitted
        return redirect(url_for('login'))
    modules = Module.query.order_by(Module.module_type.asc(), Module.series_number.asc()).all()
    if request.method == 'POST':
        module_id = request.form.get('module_id')
        content_type = request.form.get('content_type')
        if not module_id or not content_type:
            flash('Module and content type required', 'danger')
            return redirect(url_for('upload_content'))
        module = Module.query.get(module_id)
        if not module:
            flash('Selected module not found', 'danger')
            return redirect(url_for('upload_content'))
        try:
            if content_type == 'slide':
                file = request.files.get('slide_file')
                if file and file.filename and file.filename.lower().endswith(('.pdf', '.pptx')):
                    filename = secure_filename(file.filename)
                    base, ext = os.path.splitext(filename)
                    counter = 1
                    target_path = os.path.join(UPLOAD_CONTENT_FOLDER, filename)
                    while os.path.exists(target_path):
                        filename = f"{base}_{counter}{ext}"
                        target_path = os.path.join(UPLOAD_CONTENT_FOLDER, filename)
                        counter += 1
                    file.save(target_path)
                    module.slide_url = filename
                    db.session.commit()
                    flash('Slide uploaded', 'success')
                else:
                    flash('Invalid slide file', 'danger')
            elif content_type == 'video':
                youtube_url = request.form.get('youtube_url')
                module.youtube_url = youtube_url
                db.session.commit()
                flash('Video URL saved', 'success')
            elif content_type == 'quiz':
                quiz_payload = []
                any_new_pattern = False
                for qn in range(1, 6):
                    q_text = request.form.get(f'quiz_question_{qn}')
                    if q_text:
                        any_new_pattern = True
                        answers = []
                        correct_idx = request.form.get(f'correct_answer_{qn}')
                        for an in range(1, 6):
                            ans_text = request.form.get(f'answer_{qn}_{an}')
                            if ans_text:
                                answers.append({'text': ans_text, 'isCorrect': str(an) == str(correct_idx)})
                        if answers:
                            quiz_payload.append({'question': q_text, 'answers': answers})
                if not any_new_pattern:
                    # Legacy single-question fallback
                    question = request.form.get('quiz_question')
                    if question:
                        answers = []
                        correct_index = request.form.get('correct_answer')
                        for i in range(1, 6):
                            ans_text = request.form.get(f'answer_{i}')
                            if ans_text:
                                answers.append({'text': ans_text, 'isCorrect': str(i) == str(correct_index)})
                        if answers:
                            quiz_payload.append({'question': question, 'answers': answers})
                if quiz_payload:
                    module.quiz_json = json.dumps(quiz_payload)
                    db.session.commit()
                    flash(f'Quiz saved ({len(quiz_payload)} question(s))', 'success')
                else:
                    flash('Quiz data incomplete', 'danger')
            else:
                flash('Unknown content type', 'danger')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Trainer content upload error: {e}')
            flash(f'Error saving content: {e}', 'danger')
        return redirect(url_for('upload_content'))
    return render_template('upload_content.html', modules=modules)

# API endpoints for dynamic data
@app.route('/api/user_progress/<int:user_id>')
@login_required
def get_user_progress(user_id):
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return jsonify({'error': 'Unauthorized'}), 403
        if isinstance(current_user, Trainer):
            return jsonify({'error': 'Unauthorized'}), 403
        return jsonify({'error': 'Unauthorized'}), 403

    user_modules = UserModule.query.filter_by(user_id=user_id).all()
    progress_data = []

    for um in user_modules:
        progress_data.append({
            'module_name': um.module.module_name,
            'is_completed': um.is_completed,
            'score': um.score,
            'completion_date': um.completion_date.isoformat() if um.completion_date and str(um.completion_date).strip() else None
        })

    return jsonify(progress_data)

@app.route('/courses')
@login_required
def courses():
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    user_category = getattr(current_user, 'user_category', 'citizen')
    expected_code = 'TNG' if user_category == 'foreigner' else 'CSG'
    base_q = Course.query.filter((Course.allowed_category == 'both') | (Course.allowed_category == user_category))
    available_courses = [c for c in base_q.order_by(Course.name).all() if c.code.upper() == expected_code]
    if not available_courses:
        flash('No courses available for your category yet.', 'warning')
        return render_template('courses.html', course_progress=[], user=current_user, user_category=user_category)
    course_progress = []
    import json as pyjson
    for course in available_courses:
        modules = course.modules or Module.query.filter(Module.module_type == course.code.upper()).all()
        total = len(modules)
        if total == 0:
            percent = 0
            overall_percentage = 0
        else:
            module_ids = [m.module_id for m in modules]
            completed_q = (UserModule.query
                           .filter_by(user_id=current_user.User_id, is_completed=True)
                           .filter(UserModule.module_id.in_(module_ids)))
            completed = completed_q.count()
            percent = int((completed / total) * 100)
            # overall score: aggregate all quiz answers correctness; fallback to avg score
            total_correct = 0; total_questions = 0
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
                overall_percentage = int(sum(scores)/len(scores))
        course_progress.append({
            'code': course.code.lower(),
            'name': course.name,
            'percent': percent,
            'overall_percentage': overall_percentage,
            'allowed_category': course.allowed_category
        })
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
    if course:
        modules = course.modules
        if not modules:
            modules = Module.query.filter(Module.module_type == normalized_code).order_by(Module.series_number).all()
        course_name = course.name
    else:
        modules = Module.query.filter(Module.module_type == normalized_code).order_by(Module.series_number).all()
        course_name = 'NEPAL SECURITY GUARD TRAINING (TNG)' if normalized_code == 'TNG' else 'CERTIFIED SECURITY GUARD (CSG)'
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
    from models import UserCourseProgress
    # Query all course progress for the current user
    user_course_progress = UserCourseProgress.query.filter_by(user_id=current_user.user_id).all()
    # Build a list of course dicts with progress and details
    user_courses = []
    for progress in user_course_progress:
        # For now, use course_id as name/id, since no Course model exists
        user_courses.append({
            'id': progress.course_id,
            'name': f'Course {progress.course_id}',
            'progress': 100 if progress.completed else 0,
            'module_type': 'TNG' if 'TNG' in str(progress.course_id) else 'CSG'  # Example logic
        })
    return render_template('user_courses_dashboard.html', user=current_user, user_courses=user_courses)

@app.route('/api/save_quiz', methods=['POST'])
def api_save_quiz():
    data = request.get_json()
    module_id = data.get('module_id')
    quiz = data.get('quiz')
    if not module_id or quiz is None:
        return jsonify({'success': False, 'error': 'Missing data'}), 400
    module = Module.query.get(module_id)
    if not module:
        return jsonify({'success': False, 'error': 'Module not found'}), 404
    module.quiz_json = json.dumps(quiz)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/load_quiz/<int:module_id>', methods=['GET'])
def api_load_quiz(module_id):
    from models import Module
    module = Module.query.get(module_id)
    if not module or not module.quiz_json:
        return jsonify([])
    try:
        return jsonify(json.loads(module.quiz_json))
    except Exception:
        return jsonify([])

@login_required
@app.route('/api/submit_quiz/<int:module_id>', methods=['POST'])
def api_submit_quiz(module_id):
    module = Module.query.get(module_id)
    if not module or not module.quiz_json:
        return jsonify({'success': False, 'message': 'No quiz found.'})
    quiz = json.loads(module.quiz_json)
    data = request.get_json()
    answers = data.get('answers', [])
    is_reattempt = bool(data.get('is_reattempt'))
    app.logger.debug(f'[QUIZ SUBMIT] module_id={module_id} is_reattempt={is_reattempt}')
    correct = 0
    total = len(quiz)
    # Get user ID
    user_id = None
    if hasattr(current_user, 'User_id'):
        user_id = current_user.User_id
    elif hasattr(current_user, 'id'):
        user_id = current_user.id

    if not user_id:
        return jsonify({'success': False, 'message': 'User not found.'}), 403

    user_module = UserModule.query.filter_by(user_id=user_id, module_id=module_id).first()
    if user_module:
        app.logger.debug(f'[QUIZ SUBMIT] Existing user_module id={user_module.id} reattempt_count(before)={user_module.reattempt_count}')
    # Prevent resubmission unless it's a reattempt
    if user_module and user_module.is_completed and not is_reattempt:
        app.logger.debug('[QUIZ SUBMIT] Blocking duplicate submit (not reattempt).')
        return jsonify({'success': False, 'message': 'Quiz already completed. You cannot submit again.', 'score': user_module.score, 'feedback': 'Quiz already completed.'}), 403

    # Calculate score
    for idx, q in enumerate(quiz):
        if idx < len(answers):
            ans_idx = answers[idx]
            if ans_idx is not None and 0 <= ans_idx < len(q['answers']):
                if q['answers'][ans_idx].get('isCorrect') in [True, 'true', 'True', 1, '1']:
                    correct += 1

    score = int((correct / total) * 100) if total > 0 else 0
    feedback = 'Great job!' if score >= 75 else ('Keep practicing.' if score >= 50 else 'Needs improvement.')

    if not user_module:
        user_module = UserModule(user_id=user_id, module_id=module_id, reattempt_count=0)
        db.session.add(user_module)
        app.logger.debug('[QUIZ SUBMIT] Created new user_module record.')
    if is_reattempt:
        user_module.reattempt_count = (user_module.reattempt_count or 0) + 1
        app.logger.debug(f'[QUIZ SUBMIT] Incremented module reattempt_count to {user_module.reattempt_count}')
        # Removed course-level reattempt sync: course reattempts now counted ONLY via /api/reattempt_course
        # (Previously we incremented UserCourseProgress here.)
    user_module.is_completed = True
    user_module.score = score
    user_module.completion_date = datetime.now()
    import json as pyjson
    user_module.quiz_answers = pyjson.dumps(answers)
    db.session.commit()
    app.logger.debug(f'[QUIZ SUBMIT] Final module reattempt_count={user_module.reattempt_count}')

    # Ensure course-level progress record exists if all modules for this course are now completed
    try:
        from models import UserCourseProgress, Course
        course = Course.query.filter(Course.code.ilike(module.module_type)).first()
        if course:
            all_course_modules = Module.query.filter_by(module_type=module.module_type).all()
            all_ids = [m.module_id for m in all_course_modules]
            completed_count = UserModule.query.filter_by(user_id=user_id, is_completed=True).filter(UserModule.module_id.in_(all_ids)).count()
            if completed_count == len(all_ids) and len(all_ids) > 0:
                ucp = UserCourseProgress.query.filter_by(user_id=user_id, course_id=course.course_id).first()
                if not ucp:
                    ucp = UserCourseProgress(user_id=user_id, course_id=course.course_id, reattempt_count=0)
                    db.session.add(ucp)
                    db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f'Failed to ensure UserCourseProgress after quiz submit: {e}')

    grade_letter = current_user.get_overall_grade_for_course(module.module_type) if hasattr(current_user, 'get_overall_grade_for_course') else user_module.get_grade_letter()

    return jsonify({
        'success': True,
        'score': score,
        'feedback': feedback,
        'reattempt_count': user_module.reattempt_count,
        'grade_letter': grade_letter
    })

@app.route('/admin/agencies')
@login_required
def admin_agencies():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    agencies = Agency.query.all()
    return render_template('admin_agencies.html', agencies=agencies)

@app.route('/admin/add_agency', methods=['POST'])
@login_required
def add_agency():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    agency_name = request.form.get('agency_name')
    PIC = request.form.get('PIC')
    contact_number = request.form.get('contact_number')
    email = request.form.get('email')
    address = request.form.get('address')
    Reg_of_Company = request.form.get('Reg_of_Company')
    new_agency = Agency(
        agency_name=agency_name,
        PIC=PIC,
        contact_number=contact_number,
        email=email,
        address=address,
        Reg_of_Company=Reg_of_Company
    )
    db.session.add(new_agency)
    db.session.commit()
    flash('Agency added successfully!', 'success')
    return redirect(url_for('admin_agencies'))

@app.route('/admin/edit_agency/<int:agency_id>', methods=['POST'])
@login_required
def edit_agency(agency_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    agency = Agency.query.get_or_404(agency_id)
    agency.agency_name = request.form.get('agency_name')
    agency.PIC = request.form.get('PIC')
    agency.contact_number = request.form.get('contact_number')
    agency.email = request.form.get('email')
    agency.address = request.form.get('address')
    agency.Reg_of_Company = request.form.get('Reg_of_Company')
    db.session.commit()
    flash('Agency updated successfully!', 'success')
    return redirect(url_for('admin_agencies'))

@app.route('/admin/reset_user_progress', methods=['POST'])
@login_required
def reset_user_progress():
    if not hasattr(current_user, 'role') or current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    try:
        uid = int(user_id)
    except ValueError:
        return jsonify({'error': 'Invalid user ID'}), 400
    user = User.query.get(uid)
    if not user:
        return jsonify({'error': f'User {user_id} not found'}), 404
    # Reset per-module progress
    user_modules = UserModule.query.filter_by(user_id=uid).all()
    for um in user_modules:
        um.is_completed = False
        um.score = 0.0
        um.completion_date = None
    # Reset user rating
    user.rating_star = 0
    user.rating_label = ''
    db.session.commit()
    return jsonify({'success': True, 'message': f'Progress and rating reset for user {user_id}.'})

@app.route('/clear_slide/<int:module_id>', methods=['POST'])
def clear_slide(module_id):
    module = Module.query.get(module_id)
    if module and module.slide_url:
        # Optionally, delete the file from disk
        slide_path = os.path.join(app.root_path, 'instance', 'uploads', module.slide_url)
        if os.path.exists(slide_path):
            try:
                os.remove(slide_path)
            except Exception:
                pass  # Ignore file delete errors
        module.slide_url = None
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Module or slide not found'}), 404

@app.route('/api/user_quiz_answers/<int:module_id>', methods=['GET'])
@login_required
def api_user_quiz_answers(module_id):
    from models import UserModule
    user_id = None
    if hasattr(current_user, 'User_id'):
        user_id = current_user.User_id
    elif hasattr(current_user, 'id'):
        user_id = current_user.id
    if not user_id:
        return jsonify([])
    user_module = UserModule.query.filter_by(user_id=user_id, module_id=module_id).first()
    if user_module and user_module.quiz_answers:
        try:
            return jsonify(json.loads(user_module.quiz_answers))
        except Exception:
            return jsonify([])
    return jsonify([])

@app.route('/api/save_quiz_progress/<int:module_id>', methods=['POST'])
@login_required
def api_save_quiz_progress(module_id):
    data = request.get_json()
    partial_answers = data.get('partial_answers', [])
    user_id = getattr(current_user, 'User_id', getattr(current_user, 'id', None))
    if not user_id:
        return jsonify({'success': False, 'error': 'User not found'}), 403
    user_module = UserModule.query.filter_by(user_id=user_id, module_id=module_id).first()
    if not user_module:
        user_module = UserModule(user_id=user_id, module_id=module_id)
        db.session.add(user_module)
    user_module.quiz_partial_answers = json.dumps(partial_answers)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/get_quiz_progress/<int:module_id>', methods=['GET'])
@login_required
def api_get_quiz_progress(module_id):
    user_id = getattr(current_user, 'User_id', getattr(current_user, 'id', None))
    if not user_id:
        return jsonify([])
    user_module = UserModule.query.filter_by(user_id=user_id, module_id=module_id).first()
    if user_module and user_module.quiz_partial_answers:
        try:
            return jsonify(json.loads(user_module.quiz_partial_answers))
        except Exception:
            return jsonify([])
    return jsonify([])

@app.route('/api/complete_quiz', methods=['POST'])
def api_complete_quiz():
    module = Module.query.get(module_id)
    if not module or not module.quiz_json:
        return jsonify({'success': False, 'message': 'No quiz found.'})
    quiz = json.loads(module.quiz_json)
    data = request.get_json()
    answers = data.get('answers', [])
    is_reattempt = data.get('is_reattempt', False)
    correct = 0
    total = len(quiz)

    # Get user ID
    user_id = None
    if hasattr(current_user, 'User_id'):
        user_id = current_user.User_id
    elif hasattr(current_user, 'id'):
        user_id = current_user.id

    if not user_id:
        return jsonify({'success': False, 'message': 'User not found.'}), 403

    # Check existing completion status
    user_module = UserModule.query.filter_by(user_id=user_id, module_id=module_id).first()

    # Prevent resubmission unless it's a reattempt
    if user_module and user_module.is_completed and not is_reattempt:
        return jsonify({'success': False, 'message': 'Quiz already completed. You cannot submit again.', 'score': user_module.score, 'feedback': 'Quiz already completed.'}), 403

    # Calculate score
    for idx, q in enumerate(quiz):
        if idx < len(answers):
            ans_idx = answers[idx]
            if ans_idx is not None and 0 <= ans_idx < len(q['answers']):
                if q['answers'][ans_idx].get('isCorrect') in [True, 'true', 'True', 1, '1']:
                    correct += 1

    score = int((correct / total) * 100) if total > 0 else 0
    feedback = 'Great job!' if score >= 75 else ('Keep practicing.' if score >= 50 else 'Needs improvement.')

    if not user_module:
        user_module = UserModule(user_id=user_id, module_id=module_id, reattempt_count=0)
        db.session.add(user_module)

    # If this is a reattempt, increment the count
    if is_reattempt:
        user_module.reattempt_count = (user_module.reattempt_count or 0) + 1
        app.logger.debug(f'[QUIZ SUBMIT] Incremented module reattempt_count to {user_module.reattempt_count}')
        # Removed course-level reattempt sync here as well.
    user_module.is_completed = True
    user_module.score = score
    user_module.completion_date = datetime.now()
    import json as pyjson
    user_module.quiz_answers = pyjson.dumps(answers)
    db.session.commit()

    # Ensure course-level progress record exists if all modules for this course are now completed
    try:
        from models import UserCourseProgress, Course
        course = Course.query.filter(Course.code.ilike(module.module_type)).first()
        if course:
            all_course_modules = Module.query.filter_by(module_type=module.module_type).all()
            all_ids = [m.module_id for m in all_course_modules]
            completed_count = UserModule.query.filter_by(user_id=user_id, is_completed=True).filter(UserModule.module_id.in_(all_ids)).count()
            if completed_count == len(all_ids) and len(all_ids) > 0:
                ucp = UserCourseProgress.query.filter_by(user_id=user_id, course_id=course.course_id).first()
                if not ucp:
                    ucp = UserCourseProgress(user_id=user_id, course_id=course.course_id, reattempt_count=0)
                    db.session.add(ucp)
                    db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f'Failed to ensure UserCourseProgress after quiz submit: {e}')

    grade_letter = current_user.get_overall_grade_for_course(module.module_type) if hasattr(current_user, 'get_overall_grade_for_course') else user_module.get_grade_letter()

    return jsonify({
        'success': True,
        'score': score,
        'feedback': feedback,
        'reattempt_count': user_module.reattempt_count,
        'grade_letter': grade_letter
    })

@app.route('/admin/certificates')
@login_required
def admin_certificates():
    # Admin-only access guard consistent with other admin routes
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    # Fetch all certificates (newest first)
    certificates = Certificate.query.order_by(Certificate.issue_date.desc()).all()

    # Determine current template availability
    template_rel_path = os.path.join('static', 'cert_templates', 'Training_cert.pdf')
    cert_template_url = None
    if os.path.exists(template_rel_path):
        cert_template_url = url_for('static', filename='cert_templates/Training_cert.pdf')

    # Backfill certificate_url if missing (legacy rows)
    updated = False
    for cert in certificates:
        if not cert.certificate_url:
            expected_path = os.path.join('static', 'certificates', f"certificate_{cert.user_id}_{cert.module_type}.pdf")
            if os.path.exists(expected_path):
                cert.certificate_url = expected_path.replace('static/', '/static/')
                updated = True
            else:
                # Fallback to a no-op anchor to avoid broken links
                cert.certificate_url = '#'
    if updated:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return render_template('admin_certificates.html', certificates=certificates, cert_template_url=cert_template_url)

@app.route('/admin/upload_cert_template', methods=['POST'])
@login_required
def upload_cert_template():
    from werkzeug.utils import secure_filename
    if not hasattr(current_user, 'role') or current_user.role != 'admin':
        flash('Unauthorized', 'danger')
        return redirect(url_for('admin_certificates'))
    file = request.files.get('cert_template')
    if not file:
        flash('No file selected', 'danger')
        return redirect(url_for('admin_certificates'))
    filename = secure_filename(file.filename)
    cert_folder = os.path.join('static', 'cert_templates')
    os.makedirs(cert_folder, exist_ok=True)
    save_path = os.path.join(cert_folder, 'Training_cert.pdf')
    file.save(save_path)
    flash('Certificate template uploaded successfully!', 'success')
    return redirect(url_for('admin_certificates'))

@app.route('/admin/delete_certificate/<int:cert_id>', methods=['POST'])
@login_required
def delete_certificate(cert_id):
    if not isinstance(current_user, Admin):
        flash('Unauthorized action.')
        return redirect(url_for('admin_certificates'))
    from models import Certificate, db
    certificate = Certificate.query.get_or_404(cert_id)
    db.session.delete(certificate)
    db.session.commit()
    flash('Certificate deleted successfully!')
    return redirect(url_for('admin_certificates'))

@app.route('/admin/delete_certificates_bulk', methods=['POST'])
@login_required
def delete_certificates_bulk():
    if not hasattr(current_user, 'role') or current_user.role != 'admin':
        flash('Unauthorized action.')
        return redirect(url_for('admin_certificates'))
    from models import Certificate, db
    cert_ids = request.form.getlist('cert_ids')
    if not cert_ids:
        flash('No certificates selected.', 'warning')
        return redirect(url_for('admin_certificates'))
    deleted = 0
    for cert_id in cert_ids:
        cert = Certificate.query.get(cert_id)
        if cert:
            db.session.delete(cert)
            deleted += 1
    db.session.commit()
    flash(f'{deleted} certificate(s) deleted successfully!', 'success')
    return redirect(url_for('admin_certificates'))

@app.route('/admin/assign_trainer', methods=['GET', 'POST'])
@login_required
def assign_trainer():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    from models import User, Trainer
    users = User.query.all()
    trainers = Trainer.query.all()
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        trainer_id = request.form.get('trainer_id')
        user = User.query.get(user_id)
        if user and trainer_id:
            user.trainer_id = trainer_id
            from models import db
            db.session.commit()
            flash('Trainer assigned successfully!', 'success')
        return redirect(url_for('assign_trainer'))
    return render_template('assign_trainer.html', users=users, trainers=trainers)

@app.route('/admin/users')
@login_required
def admin_users():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    users = Registration.getUserList()
    trainers = Trainer.query.order_by(Trainer.name.asc()).all()
    modules = Module.query.order_by(Module.module_type.asc()).all()
    # Added courses for course-only assignment in account management
    courses = Course.query.order_by(Course.name.asc()).all()
    return render_template('admin_accounts.html', users=users, trainers=trainers, modules=modules, courses=courses)

# --- Trainer management endpoints for account management page ---
@app.route('/admin/trainer/<int:trainer_id>/update', methods=['POST'])
@login_required
def update_trainer(trainer_id):
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    trainer = Trainer.query.get_or_404(trainer_id)
    name = request.form.get('name')
    email = request.form.get('email')
    course = request.form.get('course')  # now storing course code only
    availability = request.form.get('availability')
    contact_number_raw = request.form.get('contact_number', '').strip()
    # Update fields if provided
    if name: trainer.name = name
    if email: trainer.email = email
    trainer.course = course if course else None
    trainer.availability = availability
    # Contact number sanitation
    if contact_number_raw == '':
        trainer.contact_number = None
    else:
        # Accept only digits; reject otherwise
        if contact_number_raw.isdigit():
            try:
                trainer.contact_number = int(contact_number_raw)
            except ValueError:
                return jsonify({'success': False, 'message': 'Contact number out of range'}), 400
        else:
            return jsonify({'success': False, 'message': 'Invalid contact number (digits only)'}), 400
    # Clear module assignment (course-level only for now)
    trainer.module_id = None
    try:
        db.session.commit()
        return jsonify({'success': True, 'trainer': {
            'id': trainer.trainer_id,
            'name': trainer.name,
            'email': trainer.email,
            'course': trainer.course,
            'availability': trainer.availability,
            'contact_number': trainer.contact_number if trainer.contact_number is not None else '',
            'active_status': trainer.active_status
        }})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/trainer/<int:trainer_id>/toggle_active', methods=['POST'])
@login_required
def toggle_trainer_active(trainer_id):
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    trainer = Trainer.query.get_or_404(trainer_id)
    trainer.active_status = not trainer.active_status
    try:
        db.session.commit()
        return jsonify({'success': True, 'active_status': trainer.active_status})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/trainer/<int:trainer_id>/delete', methods=['POST'])
@login_required
def delete_trainer(trainer_id):
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    trainer = Trainer.query.get_or_404(trainer_id)
    try:
        db.session.delete(trainer)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/monitor_progress')
@login_required
def monitor_progress():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    # Gather user module progress with related user, module, agency
    user_modules = []
    try:
        # Eager load minimal fields
        all_user_modules = UserModule.query.all()
        # Build cert lookup
        existing_certs = {(c.user_id, c.module_id) for c in Certificate.query.all()}
        # Cache lookups to reduce queries
        users_cache = {u.User_id: u for u in User.query.all()}
        modules_cache = {m.module_id: m for m in Module.query.all()}
        agencies_cache = {a.agency_id: a for a in Agency.query.all()}
        for um in all_user_modules:
            user = users_cache.get(um.user_id)
            module = modules_cache.get(um.module_id)
            agency = agencies_cache.get(user.agency_id) if user else None
            if user and module and agency:
                user_modules.append((um, user, module, agency))
    except Exception as e:
        flash(f'Error loading progress: {e}', 'danger')
        user_modules = []
        existing_certs = set()
    return render_template('monitor_progress.html', user_modules=user_modules, existing_certs=existing_certs)

@app.route('/admin/issue_certificate', methods=['POST'])
@login_required
def issue_certificate():
    if not isinstance(current_user, Admin):
        flash('Unauthorized', 'danger')
        return redirect(url_for('monitor_progress'))
    user_id = request.form.get('user_id')
    module_id = request.form.get('module_id')
    if not user_id or not module_id:
        flash('Missing user or module id', 'warning')
        return redirect(url_for('monitor_progress'))
    try:
        uid = int(user_id)
        mid = int(module_id)
    except ValueError:
        flash('Invalid identifiers supplied', 'danger')
        return redirect(url_for('monitor_progress'))
    user_module = UserModule.query.filter_by(user_id=uid, module_id=mid).first()
    module = Module.query.get(mid)
    user = User.query.get(uid)
    if not user or not module or not user_module:
        flash('Record not found', 'danger')
        return redirect(url_for('monitor_progress'))
    if not user_module.is_completed or user_module.score < 50:
        flash('User not eligible for certificate (must complete with score >= 50).', 'warning')
        return redirect(url_for('monitor_progress'))
    # Prevent duplicates
    existing_cert = Certificate.query.filter_by(user_id=uid, module_id=mid).order_by(Certificate.issue_date.desc()).first()
    if existing_cert:
        flash('Certificate already issued for this module.', 'info')
        return redirect(url_for('monitor_progress'))
    # Compute overall percentage across course/module_type for better rating consistency
    course_type = module.module_type
    related_modules = Module.query.filter_by(module_type=course_type).all()
    related_ids = [m.module_id for m in related_modules]
    completed_related = UserModule.query.filter_by(user_id=uid, is_completed=True).filter(UserModule.module_id.in_(related_ids)).all()
    total_correct = 0
    total_questions = 0
    import json as pyjson
    for um in completed_related:
        if um.quiz_answers:
            try:
                selected = pyjson.loads(um.quiz_answers)
                mod = modules_cache.get(um.module_id) if 'modules_cache' in globals() else Module.query.get(um.module_id)
                if mod and mod.quiz_json:
                    quiz = pyjson.loads(mod.quiz_json)
                for idx, sel in enumerate(selected):
                    if idx < len(quiz):
                        answers = quiz[idx].get('answers', [])
                        total_questions += 1
                        if isinstance(sel, int) and 0 <= sel < len(answers):
                            if answers[sel].get('isCorrect') in [True, 'true', 'True', 1, '1']:
                                total_correct += 1
            except Exception:
                continue
    overall_percentage = int((total_correct / total_questions) * 100) if total_questions else int(user_module.score)
    try:
        from generate_certificate import generate_certificate
        generate_certificate(uid, course_type, overall_percentage)
        flash('Certificate issued successfully!', 'success')
    except Exception as e:
        flash(f'Failed to generate certificate: {e}', 'danger')
    return redirect(url_for('monitor_progress'))

@app.route('/admin/recalculate_ratings')
@login_required
def recalculate_ratings():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    try:
        users = User.query.all()
        for user in users:
            completed = [um for um in user.user_modules if um.is_completed]
            if not completed:
                user.rating_star = 0
                user.rating_label = ''
                continue
            avg_score = sum(um.score for um in completed) / len(completed)
            if avg_score < 50:
                stars = 1; label = 'Needs Improvement'
            elif avg_score > 75:
                stars = 5; label = 'Great Job'
            else:
                stars = 3; label = 'Keep Practicing'
            user.rating_star = stars
            user.rating_label = label
        db.session.commit()
        flash('User ratings recalculated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error recalculating ratings: {e}', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/modules/create', methods=['GET', 'POST'])
@login_required
def create_module():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    if request.method == 'POST':
        module_name = request.form.get('module_name')
        module_type = request.form.get('module_type')
        series_number = request.form.get('series_number')
        content = request.form.get('content')
        if not module_name or not module_type:
            flash('Module name and type are required', 'danger')
            return render_template('create_module.html')
        # Create legacy/standalone module (course_id left null). Keeps backward compat with old templates.
        m = Module(module_name=module_name.strip(),
                   module_type=module_type.strip().upper(),
                   series_number=series_number.strip() if series_number else None,
                   content=content)
        db.session.add(m)
        try:
            db.session.commit()
            flash('Module created', 'success')
            return redirect(url_for('admin_course_management'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating module: {e}', 'danger')
    return render_template('create_module.html')

@app.route('/admin/create_user', methods=['GET', 'POST'])
@login_required
def create_user():
    # Only admins can access
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        role = request.form.get('role')
        if not full_name or not email or not password or role not in ['admin', 'trainer']:
            flash('All fields are required and role must be admin or trainer', 'danger')
            return render_template('create_user.html')
        # Prevent duplicate across Admin & Trainer tables
        existing_admin = Admin.query.filter_by(email=email).first()
        existing_trainer = Trainer.query.filter_by(email=email).first()
        if existing_admin or existing_trainer:
            flash('Email already in use', 'danger')
            return render_template('create_user.html')
        try:
            if role == 'admin':
                new_admin = Admin(username=full_name, email=email)
                new_admin.set_password(password)
                db.session.add(new_admin)
            else:  # trainer
                # Generate prefixed number_series TRYYYYNNNN
                from datetime import datetime, UTC
                year = datetime.now(UTC).strftime('%Y')
                prefix = f'TR{year}'
                # Find max existing sequence for this year
                existing_series = [t.number_series for t in Trainer.query.filter(Trainer.number_series.like(f'{prefix}%')).all() if t.number_series]
                next_seq = 1
                if existing_series:
                    try:
                        seq_numbers = []
                        for s in existing_series:
                            tail = s.replace(prefix, '')
                            if tail.isdigit():
                                seq_numbers.append(int(tail))
                        if seq_numbers:
                            next_seq = max(seq_numbers) + 1
                    except Exception:
                        pass
                series = f"{prefix}{str(next_seq).zfill(4)}"
                new_trainer = Trainer(name=full_name, email=email, active_status=True, number_series=series)
                new_trainer.set_password(password)
                db.session.add(new_trainer)
            db.session.commit()
            flash(f'{role.capitalize()} account created successfully', 'success')
            return redirect(url_for('admin_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating account: {e}', 'danger')
    return render_template('create_user.html')

@app.route('/admin/user/delete', methods=['POST'])
@login_required
def delete_user():
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    user_id = request.form.get('user_id') or request.json.get('user_id') if request.is_json else None
    if not user_id:
        return jsonify({'success': False, 'message': 'user_id required'}), 400
    try:
        uid = int(user_id)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid user_id'}), 400
    user = User.query.get(uid)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    try:
        # Delete related objects explicitly (if no cascading FK constraints)
        UserModule.query.filter_by(user_id=uid).delete()
        Certificate.query.filter_by(user_id=uid).delete()
        try:
            from models import WorkHistory
            WorkHistory.query.filter_by(user_id=uid).delete()
        except Exception:
            pass
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': f'User {uid} deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error deleting user: {e}'})

@app.route('/api/complete_course', methods=['POST'])
@login_required
def api_complete_course():
    """Complete a course explicitly from Courses page and auto-issue certificate if eligible.
    Expects JSON: {course_code: "TNG"}
    Success if user has completed all modules for that course and overall course score >=50.
    Returns certificate_url if newly generated or already exists."""
    if not isinstance(current_user, User):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        data = request.get_json(silent=True) or {}
        course_code = (data.get('course_code') or '').strip().upper()
        if not course_code:
            return jsonify({'success': False, 'message': 'course_code missing'}), 400
        course = Course.query.filter_by(code=course_code).first()
        if not course:
            return jsonify({'success': False, 'message': 'Course not found'}), 404
        if course.allowed_category not in ['both', current_user.user_category]:
            return jsonify({'success': False, 'message': 'Course not allowed for your category'}), 403
        modules = course.modules
        if not modules:
            modules = Module.query.filter(Module.module_type == course_code).all()
        module_ids = [m.module_id for m in modules]
        if not module_ids:
            return jsonify({'success': False, 'message': 'No modules defined for this course yet'}), 400
        user_modules = UserModule.query.filter_by(user_id=current_user.User_id, is_completed=True).\
            filter(UserModule.module_id.in_(module_ids)).all()
        all_completed = len(user_modules) == len(module_ids)
        if not all_completed:
            return jsonify({'success': False, 'message': 'You have not completed all modules yet'}), 400
        # Compute overall_percentage (aggregate quiz correctness; fallback to avg score)
        import json as pyjson
        total_correct = 0
        total_questions = 0
        for um in user_modules:
            if not um.quiz_answers:
                continue
            try:
                selected_indices = pyjson.loads(um.quiz_answers)
            except Exception:
                continue
            module_obj = next((m for m in modules if m.module_id == um.module_id), None)
            if module_obj and module_obj.quiz_json:
                try:
                    quiz = pyjson.loads(module_obj.quiz_json)
                except Exception:
                    quiz = []
                for idx, sel in enumerate(selected_indices):
                    if idx < len(quiz):
                        answers = quiz[idx].get('answers', [])
                        total_questions += 1
                        if isinstance(sel, int) and 0 <= sel < len(answers):
                            if answers[sel].get('isCorrect') in [True, 'true', 'True', 1, '1']:
                                total_correct += 1
        overall_percentage = int((total_correct / total_questions) * 100) if total_questions else int(user_module.score)
        if overall_percentage < 50:
            return jsonify({'success': False, 'message': f'Course average score {overall_percentage}% is below 50%. Improve any module score and retry.', 'overall_percentage': overall_percentage}), 400
        # Update user rating based on overall_percentage (aligned with certificate star logic thresholds)
        if overall_percentage < 20:
            stars = 1
        elif overall_percentage < 40:
            stars = 2
        elif overall_percentage < 60:
            stars = 3
        elif overall_percentage < 70:
            stars = 4
        else:
            stars = 5
        if overall_percentage < 50:
            label = 'Needs Improvement'
        elif overall_percentage > 75:
            label = 'Great Job'
        else:
            label = 'Keep Practicing'
        try:
            current_user.rating_star = stars
            current_user.rating_label = label
            db.session.commit()
        except Exception:
            db.session.rollback()
        # Correct certificate lookup by module_type
        existing_cert = Certificate.query.filter_by(user_id=current_user.User_id, module_type=course_code).order_by(Certificate.issue_date.desc()).first()
        if existing_cert:
            return jsonify({'success': True, 'message': 'Certificate already issued previously', 'certificate_url': existing_cert.certificate_url, 'overall_percentage': overall_percentage, 'stars': stars, 'rating_label': label})
        try:
            from generate_certificate import generate_certificate
            cert_path = generate_certificate(current_user.User_id, course_code, overall_percentage)
        except Exception as e:
            app.logger.exception('Certificate generation failed')
            return jsonify({'success': False, 'message': f'Certificate generation failed: {e}'}), 500
        new_cert = Certificate.query.filter_by(user_id=current_user.User_id, module_type=course_code).order_by(Certificate.issue_date.desc()).first()
        cert_url = new_cert.certificate_url if new_cert else None
        return jsonify({'success': True, 'certificate_url': cert_url, 'overall_percentage': overall_percentage, 'stars': stars, 'rating_label': label})
    except Exception as e:
        app.logger.exception('Unexpected error completing course')
        return jsonify({'success': False, 'message': f'Unexpected error: {e}'}), 500

@app.route('/api/reattempt_course/<string:course_code>', methods=['POST'])
@login_required
def api_reattempt_course(course_code: str):
    """Reset a course's module progress so user can reattempt (allowed if completed but under threshold)."""
    if not isinstance(current_user, User):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    code = (course_code or '').strip().upper()
    course = Course.query.filter_by(code=code).first()
    if not course:
        return jsonify({'success': False, 'message': 'Course not found'}), 404
    if course.allowed_category not in ['both', current_user.user_category]:
        return jsonify({'success': False, 'message': 'Course not allowed for your category'}), 403
    modules = course.modules
    if not modules:
        modules = Module.query.filter(Module.module_type == code).all()
    if not modules:
        return jsonify({'success': False, 'message': 'No modules for this course'}), 400
    module_ids = [m.module_id for m in modules]
    # Determine current overall percentage (like above) to ensure reattempt makes sense
    import json as pyjson
    user_modules = UserModule.query.filter_by(user_id=current_user.User_id).filter(UserModule.module_id.in_(module_ids)).all()
    total_correct = 0; total_questions = 0
    for um in user_modules:
        if not um.quiz_answers:
            continue
        try:
            selected_indices = pyjson.loads(um.quiz_answers)
        except Exception:
            continue
        module_obj = next((m for m in modules if m.module_id == um.module_id), None)
        if module_obj and module_obj.quiz_json:
            try:
                quiz = pyjson.loads(module_obj.quiz_json)
            except Exception:
                quiz = []
            for idx, sel in enumerate(selected_indices):
                if idx < len(quiz):
                    answers = quiz[idx].get('answers', [])
                    total_questions += 1
                    if isinstance(sel, int) and 0 <= sel < len(answers):
                        if answers[sel].get('isCorrect') in [True, 'true', 'True', 1, '1']:
                            total_correct += 1
    overall_percentage = int((total_correct / total_questions) * 100) if total_questions else 0
    has_cert = Certificate.query.filter_by(user_id=current_user.User_id, module_type=code).first() is not None
    # Correct all_completed calculation without undefined user_progress
    all_completed = len([um for um in user_modules if um.is_completed]) == len(module_ids)
    if not (all_completed or has_cert):
        return jsonify({'success': False, 'message': 'You must finish the course before reattempting'}), 400
    if overall_percentage >= 50:
        return jsonify({'success': False, 'message': 'Reattempt allowed only if overall score below 50%'}), 400
    # Reset
    for um in user_modules:
        if um.module_id in module_ids:
            um.is_completed = False
            um.score = 0
            um.quiz_answers = None
            um.completion_date = None
    try:
        # Increment / create course progress reattempt_count
        from models import UserCourseProgress
        ucp = UserCourseProgress.query.filter_by(user_id=current_user.User_id, course_id=course.course_id).first()
        if not ucp:
            ucp = UserCourseProgress(user_id=current_user.User_id, course_id=course.course_id, reattempt_count=1)
            db.session.add(ucp)
        else:
            ucp.reattempt_count = (ucp.reattempt_count or 0) + 1
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Failed to record course reattempt: {e}'}), 500
    course_grade = current_user.get_overall_grade_for_course(code)
    return jsonify({'success': True, 'message': 'Course progress reset', 'overall_percentage_before_reset': overall_percentage, 'course_grade': course_grade, 'course_reattempt_count': ucp.reattempt_count})

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
