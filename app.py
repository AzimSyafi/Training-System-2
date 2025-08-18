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

# Database configuration - handle both development and production
if os.environ.get('DATABASE_URL'):
    # Production database (PostgreSQL on Render)
    database_url = os.environ.get('DATABASE_URL')
    # Fix for newer SQLAlchemy versions - replace postgres:// with postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Local development - you can choose PostgreSQL or SQLite
    use_local_postgresql = True  # Set to False if you want to use SQLite

    if use_local_postgresql:
        # Local PostgreSQL configuration
        DB_USER = 'postgres'  # default postgres user
        DB_PASSWORD = '7890'
        DB_HOST = 'localhost'
        DB_PORT = '5432'
        DB_NAME = 'Training_system'

        app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    else:
        # Local SQLite database (fallback)
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        DB_PATH = os.path.join(BASE_DIR, 'instance', 'security_training.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'

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
        if 'number_series' not in trainer_columns:
            if db.engine.dialect.name == 'postgresql':
                db.session.execute(text("ALTER TABLE trainer ADD COLUMN IF NOT EXISTS number_series VARCHAR(10) UNIQUE"))
            else:
                # SQLite fallback (requires table rebuild); skip automatic mutation to avoid data risk
                print('[SCHEMA WARNING] trainer.number_series absent and non-PostgreSQL dialect; manual migration needed for SQLite.')
            db.session.commit()
        # Backfill any NULL/empty values using TRYYYYNNNN pattern
        year = datetime.now(UTC).strftime('%Y')  # updated
        if db.engine.dialect.name == 'postgresql':
            seq_name = f'trainer_number_series_{year}_seq'
            db.session.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))
            db.session.execute(text(
                f"UPDATE trainer SET number_series = 'TR{year}' || LPAD(nextval('{seq_name}')::text,4,'0') "
                "WHERE (number_series IS NULL OR number_series = '')"))
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
    return render_template('trainer_portal.html', trainer=current_user)

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

    # Get user's module progress
    user_modules = UserModule.query.filter_by(user_id=current_user.User_id).all()
    available_modules = Module.query.all()

    return render_template('user_dashboard.html',
                         user=current_user,
                         user_modules=user_modules,
                         available_modules=available_modules,
                         rating_star=current_user.rating_star)

@app.route('/enroll_course')
@login_required
def enroll_course():
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))

    # Enroll user in Security Guard Training course
    modules = Module.query.all()
    for module in modules:
        # Check if user is already enrolled in this module
        existing = UserModule.query.filter_by(
            user_id=current_user.User_id,
            module_id=module.module_id
        ).first()

        if not existing:
            user_module = UserModule(
                user_id=current_user.User_id,
                module_id=module.module_id
            )
            db.session.add(user_module)

    db.session.commit()
    flash('Successfully enrolled in Security Guard Training course!')
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
                            total_questions += 1
                            answers = quiz[idx].get('answers', [])
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
    # Preload modules grouped by course
    course_modules = {c.course_id: Module.query.filter_by(course_id=c.course_id).order_by(Module.series_number).all() for c in courses}
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

    # Filter courses based on user category
    user_category = getattr(current_user, 'user_category', 'citizen')

    if user_category == 'citizen':
        # Citizens can only access CSG courses
        course_defs = [
            {"code": "csg", "name": "CERTIFIED SECURITY GUARD (CSG)"}
        ]
    else:  # foreigner
        # Foreigners can only access TNG courses
        course_defs = [
            {"code": "tng", "name": "NEPAL SECURITY GUARD TRAINING (TNG)"}
        ]

    course_progress = []
    for course in course_defs:
        modules = Module.query.filter(Module.module_type == course["code"].upper()).all()
        total = len(modules)
        if total == 0:
            percent = 0
        else:
            completed = UserModule.query.filter_by(user_id=current_user.User_id, is_completed=True).filter(UserModule.module_id.in_([m.module_id for m in modules])).count()
            percent = int((completed / total) * 100)
        course_progress.append({
            "code": course["code"],
            "name": course["name"],
            "percent": percent
        })
    return render_template('courses.html', course_progress=course_progress)

@app.route('/modules/<string:course_code>')
@login_required
def course_modules(course_code):
    if isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if isinstance(current_user, Trainer):
        return redirect(url_for('trainer_portal'))
    if not isinstance(current_user, User):
        return redirect(url_for('login'))

    # Filter modules based on the course code (e.g., 'TNG' or 'CSG')
    modules = Module.query.filter(Module.module_type == course_code.upper()).order_by(Module.series_number).all()

    if not modules:
        flash('No modules found for this course.')
        return redirect(url_for('courses'))

    # Get user's progress for these modules
    user_progress = {
        um.module_id: um for um in UserModule.query.filter(
            UserModule.user_id == current_user.User_id,
            UserModule.module_id.in_([m.module_id for m in modules])
        ).all()
    }

    # Sequential unlocking logic
    unlocked_modules = set()
    for idx, module in enumerate(modules):
        if idx == 0:
            unlocked_modules.add(module.module_id)
        else:
            prev_module = modules[idx - 1]
            prev_progress = user_progress.get(prev_module.module_id)
            if prev_progress and prev_progress.is_completed:
                unlocked_modules.add(module.module_id)

    # Attach unlocked status to each module
    for module in modules:
        module.unlocked = module.module_id in unlocked_modules

    course_name = "NEPAL SECURITY GUARD TRAINING (TNG)" if course_code.lower() == 'tng' else "CERTIFIED SECURITY GUARD (CSG)"

    return render_template('course_modules.html', modules=modules, course_name=course_name, user_progress=user_progress)

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

@app.route('/api/submit_quiz/<int:module_id>', methods=['POST'])
def api_submit_quiz(module_id):
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
    
    # Save result to UserModule
    from datetime import datetime
    if not user_module:
        user_module = UserModule(user_id=user_id, module_id=module_id, reattempt_count=0)
        db.session.add(user_module)
    
    # If this is a reattempt, increment the count
    if is_reattempt and user_module.is_completed:
        user_module.reattempt_count += 1
    
    user_module.is_completed = True
    user_module.score = score
    user_module.completion_date = datetime.now()
    import json as pyjson
    user_module.quiz_answers = pyjson.dumps(answers)
    db.session.commit()
    
    grade_letter = user_module.get_grade_letter()
    
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
    data = request.get_json()
    user_id = data.get('user_id')
    module_id = data.get('module_id')
    user_answers = data.get('user_answers')
    from models import UserModule, Module, db
    from datetime import datetime
    if not user_id or not module_id:
        return jsonify({'status': 'error', 'message': 'Missing user_id or module_id'}), 400
    user_module = UserModule.query.filter_by(user_id=user_id, module_id=module_id).first()
    if not user_module:
        user_module = UserModule(user_id=user_id, module_id=module_id)
        db.session.add(user_module)
    user_module.is_completed = True
    user_module.completion_date = datetime.now()
    # Securely recalculate score from quiz data
    module = Module.query.get(module_id)
    quiz = []
    if module and module.quiz_json:
        import json as pyjson
        quiz = pyjson.loads(module.quiz_json)
    correct = 0
    total = len(quiz)
    if user_answers and quiz:
        for idx, q in enumerate(quiz):
            if idx < len(user_answers):
                ans_idx = user_answers[idx]
                if isinstance(ans_idx, int) and 0 <= ans_idx < len(q['answers']):
                    if q['answers'][ans_idx].get('isCorrect') in [True, 'true', 'True', 1, '1']:
                        correct += 1
    user_module.score = int((correct / total) * 100) if total else 0
    if user_answers is not None:
        import json as pyjson
        user_module.quiz_answers = pyjson.dumps(user_answers)
    db.session.commit()
    # --- Certificate issuance logic ---
    # Check if all modules in the course are completed
    module = Module.query.get(module_id)
    if module:
        course_type = module.module_type
        all_course_modules = Module.query.filter_by(module_type=course_type).all()
        all_module_ids = [m.module_id for m in all_course_modules]
        completed_modules = UserModule.query.filter_by(user_id=user_id, is_completed=True).filter(UserModule.module_id.in_(all_module_ids)).all()
        if len(completed_modules) == len(all_course_modules):
            # Calculate average score for star rating
            avg_score = sum([um.score for um in completed_modules]) / len(completed_modules)
            if avg_score <= 50:
                stars = 1
                label = 'Needs Improvement'
            elif avg_score > 75:
                stars = 5
                label = 'Great Job'
            else:
                stars = 3
                label = 'Keep Practicing'
            user = User.query.get(user_id)
            if user:
                user.rating_star = stars
                user.rating_label = label
                db.session.commit()
            # Issue certificate if not already issued
            cert_exists = Certificate.query.filter_by(user_id=user_id, module_id=module_id).first()
            if not cert_exists:
                cert = Certificate(user_id=user_id,
                                   module_id=module.module_id,
                                   module_type=module.module_type,
                                   issue_date=datetime.now().date(),
                                   star_rating=stars,
                                   score=avg_score)
                db.session.add(cert)
                db.session.commit()
    return jsonify({'status': 'success', 'message': 'Quiz results saved.', 'correct': correct, 'total': total})

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

@app.route('/admin/recalculate_ratings')
@login_required
def recalculate_ratings():
    if not hasattr(current_user, 'role') or current_user.role != 'admin':
        return 'Unauthorized', 403
    from models import User, UserModule, db
    users = User.query.all()
    updated = 0
    for user in users:
        user_modules = UserModule.query.filter_by(user_id=user.User_id, is_completed=True).all()
        if user_modules:
            avg_score = sum([um.score for um in user_modules]) / len(user_modules)
            if avg_score <= 50:
                stars = 1
                label = 'Needs Improvement'
            elif avg_score > 75:
                stars = 5
                label = 'Great Job'
            else:
                stars = 3
                label = 'Keep Practicing'
            user.rating_star = stars
            user.rating_label = label
            updated += 1
    db.session.commit()
    flash(f"Recalculated ratings for {updated} users.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/api/complete_course', methods=['POST'])
@login_required
def api_complete_course():
    data = request.get_json()
    course_code = data.get('course_code')
    # Use numeric primary key for DB queries
    user_id = getattr(current_user, 'User_id', None)
    if user_id is None:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    # Find course type from course_code (assuming course_code is module_type)
    course_type = course_code.upper()
    try:
        from generate_certificate import generate_certificate
        from models import UserModule, Module
        all_course_modules = Module.query.filter_by(module_type=course_type).all()
        all_module_ids = [m.module_id for m in all_course_modules]
        completed_modules = UserModule.query.filter_by(user_id=user_id, is_completed=True).\
            filter(UserModule.module_id.in_(all_module_ids)).all()
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
        generate_certificate(user_id, course_type, overall_percentage)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/reattempt_course/<string:course_code>', methods=['POST'])
@login_required
def reattempt_course(course_code):
    """Reset all user progress for a course to allow reattempt"""
    if not isinstance(current_user, User):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    course_type = course_code.upper()
    user_id = current_user.User_id

    # Check if user has completed all modules in this course
    if not current_user.has_completed_all_modules_in_course(course_type):
        return jsonify({'success': False, 'message': 'You must complete all modules before reattempting'}), 400

    try:
        # Get all modules for this course
        all_modules = Module.query.filter_by(module_type=course_type).all()
        module_ids = [m.module_id for m in all_modules]

        # Update reattempt count for all user modules in this course
        user_modules = UserModule.query.filter_by(user_id=user_id).filter(
            UserModule.module_id.in_(module_ids)
        ).all()

        for user_module in user_modules:
            user_module.reattempt_count += 1
            user_module.is_completed = False
            user_module.score = 0.0
            user_module.completion_date = None
            user_module.quiz_answers = None

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Course reset for reattempt. You can now retake all quizzes.',
            'reattempt_count': user_modules[0].reattempt_count if user_modules else 0
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

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
    modules = Module.query.order_by(Module.module_type.asc(), Module.series_number.asc()).all()
    return render_template('admin_accounts.html', users=users, trainers=trainers, modules=modules)

@app.route('/admin/trainers')
@login_required
def admin_trainers():
    # Unified accounts page now; keep route for backward compatibility
    return redirect(url_for('admin_users'))

@app.route('/admin/certificates')
@login_required
def admin_certificates():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    certificates = current_user.viewIssuedCertificates() if hasattr(current_user, 'viewIssuedCertificates') else []
    from models import UserModule
    for cert in certificates:
        user_module = UserModule.query.filter_by(user_id=cert.user_id, module_id=cert.module_id).first()
        score = user_module.score if user_module else 0
        cert.star_rating = max(1, min(5, int(round(score / 20))))
    return render_template('admin_certificates.html', certificates=certificates)

@app.route('/monitor_progress')
@login_required
def monitor_progress():
    """Admin view showing all users' module progress."""
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    # Query joined data
    rows = db.session.query(UserModule, User, Module, Agency) \
        .join(User, User.User_id == UserModule.user_id) \
        .join(Module, Module.module_id == UserModule.module_id) \
        .join(Agency, Agency.agency_id == User.agency_id) \
        .order_by(User.full_name.asc(), Module.module_name.asc()).all()
    # Existing certificates set for quick lookup
    existing_certs = set((c.user_id, c.module_id) for c in Certificate.query.all())
    return render_template('monitor_progress.html', user_modules=rows, existing_certs=existing_certs)

@app.route('/issue_certificate', methods=['POST'])
@login_required
def issue_certificate():
    if not isinstance(current_user, Admin):
        flash('Unauthorized', 'danger')
        return redirect(url_for('login'))
    try:
        user_id = int(request.form.get('user_id'))
        module_id = int(request.form.get('module_id'))
    except (TypeError, ValueError):
        flash('Invalid request', 'danger')
        return redirect(url_for('monitor_progress'))

    um = UserModule.query.filter_by(user_id=user_id, module_id=module_id).first()
    if not um:
        flash('Record not found', 'danger')
        return redirect(url_for('monitor_progress'))
    if not um.is_completed or um.score <= 50:
        flash('Module not eligible for certificate (must be completed with score > 50)', 'warning')
        return redirect(url_for('monitor_progress'))

    existing = Certificate.query.filter_by(user_id=user_id, module_id=module_id).first()
    if existing:
        flash('Certificate already issued', 'info')
        return redirect(url_for('monitor_progress'))

    # Attempt to generate a course-level certificate PDF (optional)
    try:
        from generate_certificate import generate_certificate
        # Use module_type as course_type and score as overall percentage fallback
        course_type = um.module.module_type
        overall_percentage = int(um.score)
        generate_certificate(user_id, course_type, overall_percentage)
        # If generation creates an entry already, re-fetch
        existing = Certificate.query.filter_by(user_id=user_id, module_id=module_id).first()
        if existing:
            flash('Certificate generated', 'success')
            return redirect(url_for('monitor_progress'))
    except Exception as e:
        # Fall back to simple DB creation
        pass

    from datetime import date as _date
    stars = max(1, min(5, int(round(um.score / 20.0))))
    cert = Certificate(user_id=user_id,
                       module_id=module_id,
                       issue_date=_date.today(),
                       star_rating=stars,
                       score=um.score,
                       certificate_url=f"/static/certificates/certificate_{user_id}_{module_id}.pdf")
    db.session.add(cert)
    db.session.commit()
    flash('Certificate issued (no PDF generated)', 'success')
    return redirect(url_for('monitor_progress'))

@app.route('/admin/create_module', methods=['GET', 'POST'])
@login_required
def create_module():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form.get('module_name')
        mtype = request.form.get('module_type')  # In legacy template this is a category (Theory/Practical...)
        series = request.form.get('series_number')
        content = request.form.get('content')
        # Optional course_code to align with new course system
        course_code = request.args.get('course_code')
        course_id = None
        if course_code:
            from models import Course
            course = Course.query.filter_by(code=course_code.upper()).first()
            if course:
                course_id = course.course_id
                # If user selected a generic type (Theory/Practical) keep it in series_number suffix, but set module_type to course code
                mtype = course.code.upper()
        if not name or not mtype:
            flash('Module Name and Type are required', 'danger')
            return render_template('create_module.html')
        module = Module(module_name=name, module_type=mtype.upper(), series_number=series, content=content, course_id=course_id)
        db.session.add(module)
        db.session.commit()
        flash('Module created', 'success')
        # Prefer redirect to new course management if course context provided
        if course_id:
            return redirect(url_for('admin_course_management'))
        return redirect(url_for('admin_modules'))
    return render_template('create_module.html')

@app.route('/admin/create_user', methods=['GET', 'POST'])
@login_required
def create_user():
    if not isinstance(current_user, Admin):
        return redirect(url_for('index'))
    # Creation handled via modal on admin_users page now
    if request.method == 'GET':
        # Visiting the old URL directly should open the modal automatically
        return redirect(url_for('admin_users', show_create_modal=1))
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    password = request.form.get('password')
    role = (request.form.get('role') or '').lower()
    if not (full_name and email and password and role):
        flash('Full name, email, password and role are required.', 'danger')
        return redirect(url_for('admin_users', show_create_modal=1))
    if role not in ['admin', 'trainer']:
        flash('Invalid role selected.', 'danger')
        return redirect(url_for('admin_users', show_create_modal=1))
    if User.query.filter_by(email=email).first() or Admin.query.filter_by(email=email).first() or Trainer.query.filter_by(email=email).first():
        flash('Email already exists.', 'warning')
        return redirect(url_for('admin_users', show_create_modal=1))
    try:
        if role == 'admin':
            base_username = re.sub(r'[^a-zA-Z0-9_]+', '', (full_name or '').replace(' ', '_').lower()) or email.split('@')[0]
            username = base_username
            counter = 1
            while Admin.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1
            admin = Admin(username=username, email=email, role='admin')
            admin.set_password(password)
            db.session.add(admin)
        else:
            trainer = Trainer(name=full_name, email=email, active_status=True)
            trainer.set_password(password)
            db.session.add(trainer)
        db.session.commit()
        flash(f'{role.capitalize()} account created successfully.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Database integrity error creating account.', 'danger')
        return redirect(url_for('admin_users', show_create_modal=1))
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating account: {e}', 'danger')
        return redirect(url_for('admin_users', show_create_modal=1))
    return redirect(url_for('admin_users'))

# Utility: consistent user_id extraction
def _extract_user_id():
    uid = None
    # JSON body
    if request.is_json:
        data = request.get_json(silent=True) or {}
        uid = data.get('user_id')
    # Form data
    if not uid:
        uid = request.form.get('user_id')
    # Query param
    if not uid:
        uid = request.args.get('user_id')
    return uid

@app.route('/admin/delete_user', methods=['POST'])
@login_required
def delete_user():
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    user_id = _extract_user_id()
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
        UserModule.query.filter_by(user_id=uid).delete()
        Certificate.query.filter_by(user_id=uid).delete()
        from models import WorkHistory
        WorkHistory.query.filter_by(user_id=uid).delete()
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': f'User {uid} deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# Alternative RESTful style endpoint supporting DELETE with path parameter
@app.route('/admin/users/<int:uid>', methods=['DELETE'])
@login_required
def delete_user_rest(uid):
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    user = User.query.get(uid)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    try:
        UserModule.query.filter_by(user_id=uid).delete()
        Certificate.query.filter_by(user_id=uid).delete()
        from models import WorkHistory
        WorkHistory.query.filter_by(user_id=uid).delete()
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': f'User {uid} deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# --- Application entry point ---
if __name__ == '__main__':
    # Initialize database (safe / idempotent)
    with app.app_context():
        try:
            init_db()
        except Exception as e:
            print(f"[INIT ERROR] {e}")
    # Run development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=debug)
