from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date
import os
from models import db, Admin, User, Agency, Module, Certificate, Trainer, UserModule, Management, Registration
from sqlalchemy.exc import IntegrityError
import re
import urllib.parse
from flask import request, jsonify
import json

app = Flask(__name__, static_url_path='/static')
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Use absolute path for SQLite DB
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'security_training.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/profile_pics'

UPLOAD_CONTENT_FOLDER = os.path.join('instance', 'uploads')
os.makedirs(UPLOAD_CONTENT_FOLDER, exist_ok=True)

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

@login_manager.user_loader
def load_user(user_id):
    # Use session to determine user type if available
    user_type = session.get('user_type')
    if user_type == 'admin':
        return Admin.query.get(int(user_id))
    elif user_type == 'user':
        return User.query.get(int(user_id))
    elif user_type == 'trainer':
        return Trainer.query.get(int(user_id))
    # Fallback: try Admin first, then User
    admin = Admin.query.get(int(user_id))
    if admin:
        return admin
    return User.query.get(int(user_id))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Home route
@app.route('/')
def index():
    return render_template('index.html')

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Try to find user in Admins first
        user = Admin.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            session['user_type'] = 'admin'
            session['user_id'] = user.get_id()
            return redirect(url_for('index'))
        # If not admin, try Users
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            session['user_type'] = 'user'
            session['user_id'] = user.get_id()
            return redirect(url_for('index'))
        # If not user, try Trainers
        user = Trainer.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            session['user_type'] = 'trainer'
            session['user_id'] = user.get_id()
            return redirect(url_for('index'))
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
        user_data = {
            'full_name': request.form['full_name'],
            'email': request.form['email'],
            'password': request.form['password'],
            'agency_id': request.form['agency_id'],
            'recruitment_date': datetime.now().date(),
            'number_series': f"SG{datetime.now().year}{Registration.generateUserid():04d}"
        }

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
                         available_modules=available_modules)

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
                certificate = admin.issueCerticate(current_user.User_id, module_id)
                flash('Certificate issued successfully!')

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
    return render_template('my_certificates.html', certificates=certificates)

# Admin Dashboard and Workflow
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
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
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    modules = current_user.viewAllModules()
    return render_template('admin_modules.html', modules=modules)

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
        module_data = {
            'module_name': request.form['module_name'],
            'module_type': request.form['module_type'],
            'series_number': request.form['series_number'],
            'content': request.form['content']
        }

        module = current_user.createModule(module_data)
        flash('Module created successfully!')
        return redirect(url_for('admin_modules'))

    return render_template('create_module.html')

@app.route('/admin/edit_module/<int:module_id>', methods=['GET', 'POST'])
@login_required
def edit_module(module_id):
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    module = Module.query.get_or_404(module_id)

    if request.method == 'POST':
        module_data = {
            'module_name': request.form['module_name'],
            'module_type': request.form['module_type'],
            'series_number': request.form['series_number'],
            'content': request.form['content']
        }

        current_user.updateModule(module_id, module_data)
        flash('Module updated successfully!')
        return redirect(url_for('admin_modules'))

    return render_template('edit_module.html', module=module)

@app.route('/admin/delete_module/<int:module_id>', methods=['POST'])
@login_required
def delete_module(module_id):
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    if current_user.deleteModule(module_id):
        flash('Module deleted successfully!')
    else:
        flash('Module not found!')

    return redirect(url_for('admin_modules'))

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
    return render_template('admin_users.html', users=users)

@app.route('/admin/create_user', methods=['GET', 'POST'])
@login_required
def create_user():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_data = {
            'full_name': request.form['full_name'],
            'email': request.form['email'],
            'password': request.form['password'],
            'agency_id': request.form['agency_id'],
            'recruitment_date': datetime.now().date(),
            'number_series': f"SG{datetime.now().year}{Registration.generateUserid():04d}"
        }

        user = Registration.registerUser(user_data)
        flash('User created successfully!')
        return redirect(url_for('admin_users'))

    agencies = Registration.getAgencyList()
    return render_template('create_user.html', agencies=agencies)

@app.route('/admin/monitor_progress')
@login_required
def monitor_progress():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    # Get all user modules with progress
    user_modules = db.session.query(UserModule, User, Module).join(User).join(Module).all()
    return render_template('monitor_progress.html', user_modules=user_modules)

@app.route('/admin/certificates')
@login_required
def admin_certificates():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    certificates = current_user.viewIssueCerticate()
    return render_template('admin_certificates.html', certificates=certificates)

@app.route('/agency')
@login_required
def agency():
    agencies = Agency.query.all()
    return render_template('agency.html', agencies=agencies)

@app.route('/admin/issue_certificate', methods=['POST'])
@login_required
def issue_certificate():
    if not isinstance(current_user, Admin):
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        return redirect(url_for('login'))

    user_id = request.form['user_id']
    module_id = request.form['module_id']

    certificate = current_user.issueCerticate(user_id, module_id)
    flash('Certificate issued successfully!')

    return redirect(url_for('admin_certificates'))

@app.route('/modules_by_type/<module_type>')
def modules_by_type(module_type):
    from models import Module
    modules = Module.query.filter_by(module_type=module_type).all()
    modules_data = [
        {'module_id': m.module_id, 'module_name': m.module_name}
        for m in modules
    ]
    return jsonify({'modules': modules_data})

@app.route('/upload_content', methods=['GET', 'POST'])
def upload_content():
    from models import Module  # ensure import in case of circular import
    # Get all unique module types for the dropdown
    module_types = [row[0] for row in Module.query.with_entities(Module.module_type).distinct().all()]
    modules = Module.query.all()
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        content_type = request.form.get('content_type')
        result = {'title': title, 'description': description, 'content_type': content_type}
        if content_type == 'slide':
            file = request.files.get('slide_file')
            if file and file.filename and file.filename.lower().endswith(('.pdf', '.pptx')):
                filename = secure_filename(file.filename)
                filepath = os.path.join(UPLOAD_CONTENT_FOLDER, filename)
                file.save(filepath)
                result['slide_file'] = filepath
                flash('Slide uploaded successfully!', 'success')
            else:
                flash('Please upload a valid PDF or PPTX file.', 'danger')
                return render_template('upload_content.html', modules=modules)
        elif content_type == 'video':
            youtube_url = request.form.get('youtube_url')
            module_id = request.form.get('module_id')
            module = Module.query.get(module_id)
            if module:
                module.youtube_url = youtube_url
                db.session.commit()
                flash('YouTube video saved!', 'success')
            else:
                flash('Module not found.', 'danger')
            return redirect(url_for('upload_content'))
        elif content_type == 'quiz':
            question = request.form.get('quiz_question')
            answer1 = request.form.get('quiz_answer1')
            answer2 = request.form.get('quiz_answer2')
            answer3 = request.form.get('quiz_answer3')
            result['quiz'] = {'question': question, 'answers': [answer1, answer2, answer3]}
            flash('Quiz saved!', 'success')
        else:
            flash('Invalid content type.', 'danger')
            return render_template('upload_content.html', modules=modules)
        # TODO: Save 'result' to the database as needed
        return redirect(url_for('upload_content'))
    return render_template('upload_content.html', modules=modules, module_types=module_types)

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
            'completion_date': um.completion_date.isoformat() if um.completion_date else None
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
    # Example: Replace with your actual Course model and query if available
    # courses = Course.query.all()
    # For now, use a placeholder list
    courses = []
    return render_template('courses.html', courses=courses)

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
    modules = Module.query.filter(Module.module_type == course_code.upper()).all()

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
                PIC='John Doe',
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

        # Create mock user accounts
        if not User.query.filter_by(email='john.doe@trainee.com').first():
            # Get the default agency
            default_agency = Agency.query.first()

            # Mock User 1
            user1 = User(
                full_name='John Doe',
                email='john.doe@trainee.com',
                visa_expiry_date=date(2025, 12, 31),
                emergency_contact='+1234567892',
                emergency_relationship='Spouse',
                recruitment_date=date(2024, 1, 15),
                current_workplace='Downtown Mall',
                future_posting_location='City Center',
                state='California',
                postcode='90210',
                remarks='Excellent trainee with strong work ethic',
                rating_star=4,
                trainer='Sarah Johnson',
                agency_id=default_agency.agency_id if default_agency else 1,
                number_series='SG20240001'
            )
            user1.set_password('john123')
            db.session.add(user1)

            # Mock User 2
            user2 = User(
                full_name='Jane Smith',
                email='jane.smith@trainee.com',
                visa_expiry_date=date(2026, 6, 30),
                emergency_contact='+1234567893',
                emergency_relationship='Parent',
                recruitment_date=date(2024, 2, 1),
                current_workplace='Office Complex',
                future_posting_location='Business District',
                state='California',
                postcode='90211',
                remarks='Quick learner with good communication skills',
                rating_star=5,
                trainer='Mike Thompson',
                agency_id=default_agency.agency_id if default_agency else 1,
                number_series='SG20240002'
            )
            user2.set_password('jane123')
            db.session.add(user2)

            # Mock User 3
            user3 = User(
                full_name='Robert Wilson',
                email='robert.wilson@trainee.com',
                visa_expiry_date=date(2025, 9, 15),
                emergency_contact='+1234567894',
                emergency_relationship='Brother',
                recruitment_date=date(2024, 3, 10),
                current_workplace='Residential Complex',
                future_posting_location='Suburb Area',
                state='California',
                postcode='90212',
                remarks='Dedicated worker with attention to detail',
                rating_star=3,
                trainer='Sarah Johnson',
                agency_id=default_agency.agency_id if default_agency else 1,
                number_series='SG20240003'
            )
            user3.set_password('robert123')
            db.session.add(user3)

            db.session.commit()

            # Create some sample progress for the users
            modules = Module.query.all()
            if modules:
                # User 1 progress - completed some modules
                for i, module in enumerate(modules[:2]):
                    user_module = UserModule(
                        user_id=user1.User_id,
                        module_id=module.module_id,
                        is_completed=True,
                        score=85.0 if i == 0 else 72.0,
                        completion_date=datetime.now()
                    )
                    db.session.add(user_module)

                # User 2 progress - completed all modules
                for i, module in enumerate(modules):
                    user_module = UserModule(
                        user_id=user2.User_id,
                        module_id=module.module_id,
                        is_completed=True,
                        score=90.0 + i,
                        completion_date=datetime.now()
                    )
                    db.session.add(user_module)

                # User 3 progress - only enrolled, not completed
                for module in modules:
                    user_module = UserModule(
                        user_id=user3.User_id,
                        module_id=module.module_id,
                        is_completed=False,
                        score=0.0
                    )
                    db.session.add(user_module)

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

# Call init_db when the app starts
init_db()

@app.route('/api/profile', methods=['POST'])
def insert_profile():
    data = request.get_json()
    required_fields = [
        'full_name', 'email', 'agency_id', 'number_series', 'visa_expiry_date',
        'state', 'postcode', 'trainer', 'emergency_contact', 'emergency_relationship',
        'work_history', 'profile_picture'
    ]
    # Validate required fields
    for field in required_fields:
        if field not in data:
            return jsonify({'success': False, 'message': f'Missing field: {field}'}), 400
    # Validate email
    if not re.match(r"[^@]+@[^@]+\.[^@]+", data['email']):
        return jsonify({'success': False, 'message': 'Invalid email format'}), 400
    # Validate work history is a list
    if not isinstance(data['work_history'], list):
        return jsonify({'success': False, 'message': 'Work history must be a list'}), 400
    try:
        with db.session.begin_nested():
            user = User(
                full_name=data['full_name'],
                Profile_picture=data.get('profile_picture'),
                email=data['email'],
                number_series=data['number_series'],
                visa_expiry_date=datetime.strptime(data['visa_expiry_date'], '%Y-%m-%d').date() if data['visa_expiry_date'] else None,
                state=data['state'],
                postcode=data['postcode'],
                trainer=data['trainer'],
                rating_star=data.get('rating_star', 0),
                emergency_contact=data['emergency_contact'],
                emergency_relationship=data['emergency_relationship'],
                agency_id=data['agency_id']
            )
            # Set password if provided
            if 'password' in data:
                user.set_password(data['password'])
            db.session.add(user)
            db.session.flush()  # Get user.User_id
            for wh in data['work_history']:
                wh_required = ['company_name', 'start_date']
                for whf in wh_required:
                    if whf not in wh:
                        raise ValueError(f'Missing work history field: {whf}')
                work_history = WorkHistory(
                    user_id=user.User_id,
                    company_name=wh['company_name'],
                    position_title=wh.get('position_title'),
                    start_date=datetime.strptime(wh['start_date'], '%Y-%m-%d').date(),
                    end_date=datetime.strptime(wh['end_date'], '%Y-%m-%d').date() if wh.get('end_date') else None,
                    location=wh.get('location')
                )
                db.session.add(work_history)
            db.session.commit()
        return jsonify({'success': True, 'message': 'Profile and work history inserted successfully.'}), 201
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Integrity error: ' + str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/cleanup-db-for-mockup')
def cleanup_db_for_mockup():
    try:
        # --- Clean Users ---
        user_to_keep = User.query.filter_by(username='john').first()
        if user_to_keep:
            users_to_delete = User.query.filter(User.username != 'john').all()
            for user in users_to_delete:
                UserModule.query.filter_by(user_id=user.User_id).delete()
                Certificate.query.filter_by(user_id=user.User_id).delete()
                db.session.delete(user)

        # --- Clean Trainers ---
        trainer_to_keep = Trainer.query.filter_by(username='sarah').first()
        if trainer_to_keep:
            trainers_to_delete = Trainer.query.filter(Trainer.username != 'sarah').all()
            for trainer in trainers_to_delete:
                db.session.delete(trainer)

        # --- Clean Admins ---
        admin_to_keep = Admin.query.filter_by(username='admin').first()
        if admin_to_keep:
            admins_to_delete = Admin.query.filter(Admin.username != 'admin').all()
            for admin in admins_to_delete:
                db.session.delete(admin)

        db.session.commit()
        flash("Database cleaned successfully. Only 'john', 'sarah', and 'admin' remain.")
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
    # You can customize the data passed to the template as needed
    return render_template('user_courses_dashboard.html', user=current_user)

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
        return jsonify({'score': 0, 'feedback': 'No quiz found.'})
    quiz = json.loads(module.quiz_json)
    data = request.get_json()
    answers = data.get('answers', [])
    correct = 0
    total = len(quiz)
    for idx, q in enumerate(quiz):
        if idx < len(answers):
            ans_idx = answers[idx]
            if 0 <= ans_idx < len(q['answers']) and q['answers'][ans_idx].get('isCorrect'):
                correct += 1
    score = int((correct / total) * 100) if total > 0 else 0
    feedback = 'Great job!' if score >= 75 else ('Keep practicing.' if score >= 50 else 'Needs improvement.')
    return jsonify({'score': score, 'feedback': feedback})

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

if __name__ == '__main__':
    app.run(debug=True)
