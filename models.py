from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, UTC  # added UTC
from flask_login import UserMixin
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError  # added

db = SQLAlchemy()

class Admin(UserMixin, db.Model):
    __tablename__ = 'admin'

    admin_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='admin')

    def get_id(self):
        return str(self.admin_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def profile_pic(self):
        return None

    @property
    def displayed_id(self):
        return str(self.admin_id)

    def login(self, email, password):
        admin = Admin.query.filter_by(email=email).first()
        if admin and admin.check_password(password):
            return admin
        return None

    def createModule(self, module_data):
        module = Module(**module_data)
        db.session.add(module)
        db.session.commit()
        return module

    def updateModule(self, module_id, module_data):
        module = Module.query.get(module_id)
        if module:
            for key, value in module_data.items():
                setattr(module, key, value)
            db.session.commit()
        return module

    def deleteModule(self, module_id):
        module = Module.query.get(module_id)
        if module:
            db.session.delete(module)
            db.session.commit()
            return True
        return False

    def viewAllModules(self):
        return Module.query.all()

    def issueCertificate(self, user_id, module_id):
        certificate_url = f"/certificates/{user_id}_{module_id}.pdf"
        # Assuming Certificate is a model and you want to create and add it
        certificate = Certificate(user_id=user_id, module_id=module_id, certificate_url=certificate_url)
        db.session.add(certificate)
        db.session.commit()
        return Certificate.query.all()

    def viewIssuedCertificates(self):
        return Certificate.query.all()

class Agency(db.Model):
    __tablename__ = 'agency'

    agency_id = db.Column(db.Integer, primary_key=True)
    agency_name = db.Column(db.String(255), nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    Reg_of_Company = db.Column(db.String(100), nullable=False)
    PIC = db.Column(db.String(100), nullable=False)  # Person in Charge
    email = db.Column(db.String(120), nullable=False)

    # Relationship
    users = db.relationship('User', backref='agency', lazy=True)
    # New: optional one-to-one agency login account
    account = db.relationship('AgencyAccount', backref='agency', uselist=False, lazy=True)

    def getInfo(self):
        return {
            'agency_id': self.agency_id,
            'agency_name': self.agency_name,
            'contact_number': self.contact_number,
            'address': self.address,
            'Reg_of_Company': self.Reg_of_Company,
            'PIC': self.PIC,
            'email': self.email
        }

class AgencyAccount(UserMixin, db.Model):
    __tablename__ = 'agency_account'

    account_id = db.Column(db.Integer, primary_key=True)
    agency_id = db.Column(db.Integer, db.ForeignKey('agency.agency_id'), nullable=False, unique=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='agency')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))  # timezone-aware

    def get_id(self):
        return str(self.account_id)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # Provide template-friendly properties used by base.html
    @property
    def username(self):
        try:
            # Prefer agency name if available
            if getattr(self, 'agency', None) and getattr(self.agency, 'agency_name', None):
                return self.agency.agency_name
        except Exception:
            pass
        return self.email

    @property
    def profile_pic(self):
        # Agency accounts don’t have avatars by default
        return None

    @property
    def displayed_id(self):
        return str(self.account_id)

class User(UserMixin, db.Model):
    __tablename__ = 'user'

    User_id = db.Column(db.Integer, primary_key=True)
    Profile_picture = db.Column(db.String(255))
    # Updated to 10 chars: Prefix 'SG' + YYYY + NNNN
    number_series = db.Column(db.String(10), unique=True)  # Format: SGYYYYNNNN
    full_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    user_category = db.Column(db.String(20), nullable=False, default='citizen')  # 'citizen' or 'foreigner'
    is_finalized = db.Column(db.Boolean, nullable=False, default=False)  # signup finalized after onboarding
    visa_expiry_date = db.Column(db.Date)
    emergency_contact_phone = db.Column(db.String(20))
    emergency_contact_name = db.Column(db.String(100))  # Emergency contact's name
    emergency_contact_relationship = db.Column(db.String(100))
    working_experience = db.Column(db.String(255))
    recruitment_date = db.Column(db.Date)
    current_workplace = db.Column(db.String(255))
    state = db.Column(db.String(50))
    postcode = db.Column(db.String(10))
    remarks = db.Column(db.Text)
    agency_id = db.Column(db.Integer, db.ForeignKey('agency.agency_id'), nullable=False)
    address = db.Column(db.Text)
    visa_number = db.Column(db.String(50))
    ic_number = db.Column(db.String(50), nullable=True)  # Required for citizens
    passport_number = db.Column(db.String(50), nullable=True)  # Required for foreigners
    # New column to track module disclaimer agreements (JSON format: {"module_id": timestamp})
    module_disclaimer_agreements = db.Column(db.Text, default='{}')

    # Relationship
    certificates = db.relationship('Certificate', backref='user', lazy=True)
    user_modules = db.relationship('UserModule', backref='user', lazy=True)
    work_histories = db.relationship('WorkHistory', back_populates='user', lazy=True)

    @property
    def profile_pic_url(self):
        from flask import url_for
        if self.Profile_picture:
            # Serve via unified uploads route so it works in dev/prod
            return url_for('serve_upload', filename=self.Profile_picture)
        return None

    @property
    def username(self):
        return self.full_name

    @property
    def profile_pic(self):
        return self.Profile_picture

    def get_id(self):
        # Return formatted series ID for authentication/session
        return self.number_series or str(self.User_id)

    @property
    def displayed_id(self):
        return self.number_series or str(self.User_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def login(self, email, password):
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            return user
        return None

    def updateProfile(self, profile_data):
        for key, value in profile_data.items():
            if hasattr(self, key):
                setattr(self, key, value)
        db.session.commit()

    def EligibleForCertificate(self, course_type=None):
        """
        Returns True if the user has completed ALL modules of the given course_type and the overall average score is >= 50.
        If course_type is None, returns False.
        """
        if not course_type:
            return False
        from models import Module, UserModule  # Use absolute import to avoid ImportError
        # Get all modules for the course_type
        all_modules = Module.query.filter_by(module_type=course_type).all()
        if not all_modules:
            return False
        all_module_ids = [m.module_id for m in all_modules]
        # Get all completed modules for this user in this course_type
        completed_modules = UserModule.query.filter_by(user_id=self.User_id, is_completed=True).filter(UserModule.module_id.in_(all_module_ids)).all()
        if len(completed_modules) != len(all_modules):
            return False
        # Overall average (ignore None)
        scores = [um.score for um in completed_modules if um.score is not None]
        if not scores:
            return False
        average = sum(scores) / len(scores)
        return average >= 50

    def generateUserid(self):
        last_user = User.query.filter_by(agency_id=self.agency_id).order_by(User.User_id.desc()).first()
        if last_user:
            return last_user.User_id + 1
        return 1

    def get_color_by_score(self, score):
        if score <= 50:
            return 'red'
        elif score > 75:
            return 'green'
        else:
            return 'blue'

    def has_completed_all_modules_in_course(self, course_type):
        """Check if user has completed ALL modules in a given course type"""
        all_modules = Module.query.filter_by(module_type=course_type).all()
        if not all_modules:
            return False

        completed_modules = UserModule.query.filter_by(
            user_id=self.User_id,
            is_completed=True
        ).filter(UserModule.module_id.in_([m.module_id for m in all_modules])).all()

        return len(completed_modules) == len(all_modules)

    def get_overall_grade_for_course(self, course_type):
        """Return overall letter grade based ONLY on course-level reattempt_count.
        A = 0 course reattempts, B = 1, etc. >=26 => Z+.
        If course not found, return 'N/A'. If no progress row yet, treat as 0 (A)."""
        from models import Course, UserCourseProgress
        course = Course.query.filter(Course.code.ilike(course_type)).first()
        if not course:
            return 'N/A'
        ucp = UserCourseProgress.query.filter_by(user_id=self.User_id, course_id=course.course_id).first()
        attempts = (ucp.reattempt_count if ucp and ucp.reattempt_count else 0)
        if attempts >= 26:
            return 'Z+'
        return chr(ord('A') + attempts)

    def has_agreed_to_module_disclaimer(self, module_id):
        """Check if user has agreed to disclaimer for a specific module"""
        import json
        try:
            agreements = json.loads(self.module_disclaimer_agreements or '{}')
            return str(module_id) in agreements
        except (json.JSONDecodeError, TypeError):
            return False

    def agree_to_module_disclaimer(self, module_id):
        """Record user's agreement to module disclaimer"""
        import json
        try:
            agreements = json.loads(self.module_disclaimer_agreements or '{}')
        except (json.JSONDecodeError, TypeError):
            agreements = {}

        agreements[str(module_id)] = datetime.now(UTC).isoformat()
        self.module_disclaimer_agreements = json.dumps(agreements)
        db.session.commit()
        return True

class Course(db.Model):
    __tablename__ = 'course'

    course_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)  # e.g., TNG, CSG
    description = db.Column(db.Text)
    allowed_category = db.Column(db.String(20), default='both')  # citizen / foreigner / both

    # Relationship
    modules = db.relationship('Module', backref='course', lazy=True)

    def to_dict(self):
        return {
            'course_id': self.course_id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'allowed_category': self.allowed_category,
            'module_count': len(self.modules)
        }

class Module(db.Model):
    __tablename__ = 'module'

    module_id = db.Column(db.Integer, primary_key=True)
    module_name = db.Column(db.String(255), nullable=False)
    module_type = db.Column(db.String(100), nullable=False)
    series_number = db.Column(db.String(50))
    scoring_float = db.Column(db.Float, default=0.0)
    content = db.Column(db.Text)
    youtube_url = db.Column(db.String(255))  # New field for YouTube video URL
    quiz_json = db.Column(db.Text)  # New field for storing quiz as JSON
    quiz_image = db.Column(db.String(255))  # Filename for quiz image
    slide_url = db.Column(db.String(255))  # Field for uploaded slide filename/path
    course_id = db.Column(db.Integer, db.ForeignKey('course.course_id'))  # Optional link to Course

    # Relationships
    certificates = db.relationship('Certificate', backref='module', lazy=True)
    user_modules = db.relationship('UserModule', backref='module', lazy=True)
    trainers = db.relationship('Trainer', backref='module', lazy=True)

    def getModuleDetails(self):
        return {
            'module_id': self.module_id,
            'module_name': self.module_name,
            'module_type': self.module_type,
            'series_number': self.series_number,
            'scoring_float': self.scoring_float,
            'content': self.content
        }

    def editScoring(self, new_score):
        self.scoring_float = new_score
        db.session.commit()

    def to_dict(self):
        return {
            'module_id': self.module_id,
            'module_name': self.module_name,
            'module_type': self.module_type,
            'series_number': self.series_number,
            'scoring_float': self.scoring_float,
            'content': self.content,
            'youtube_url': self.youtube_url,
            'quiz_json': self.quiz_json,
            'quiz_image': self.quiz_image,
            'slide_url': self.slide_url,
            'course_id': self.course_id
        }

class Certificate(db.Model):
    __tablename__ = 'certificate'

    certificate_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.User_id'), nullable=False)
    module_type = db.Column(db.String(100))
    module_id = db.Column(db.Integer, db.ForeignKey('module.module_id'), nullable=False)
    issue_date = db.Column(db.Date, nullable=False)
    score = db.Column(db.Float, default=0.0)
    certificate_url = db.Column(db.String(255))

    def generateCertificate(self):
        # Generate certificate URL/path
        self.certificate_url = f"/certificates/{self.user_id}_{self.module_id}_{self.issue_date}.pdf"
        db.session.commit()
        return self.certificate_url

    def download(self):
        return self.certificate_url

    def validateCertificate(self):
        # Validate certificate authenticity
        return self.certificate_id is not None and self.issue_date is not None

class Trainer(UserMixin, db.Model):
    __tablename__ = 'trainer'

    trainer_id = db.Column(db.Integer, primary_key=True)
    profile_image = db.Column(db.String(255))
    name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.Text)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    active_status = db.Column(db.Boolean, default=True)
    availability = db.Column(db.String(100))
    contact_number = db.Column(db.Integer)
    course = db.Column(db.String(255))
    module_id = db.Column(db.Integer, db.ForeignKey('module.module_id'))
    # New prefixed series for trainers: TRYYYYNNNN
    number_series = db.Column(db.String(10), unique=True)

    def get_id(self):
        return self.number_series or str(self.trainer_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if self.password_hash:
            return check_password_hash(self.password_hash, password)
        return False

class UserModule(db.Model):
    __tablename__ = 'user_module'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.User_id'), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('module.module_id'), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    score = db.Column(db.Float)
    completion_date = db.Column(db.DateTime)
    quiz_answers = db.Column(db.Text)
    reattempt_count = db.Column(db.Integer, default=0)  # added

    def get_completion_status(self):
        return self.is_completed

    def markCompleted(self):
        self.is_completed = True
        self.completion_date = datetime.now()
        db.session.commit()

    def updateScore(self, new_score):
        # Only update if better
        if self.score is None or new_score > self.score:
            self.score = new_score
            db.session.commit()

    def get_grade_letter(self):
        """Return letter grade based on per-module reattempt count if available; fallback to A."""
        attempts = self.reattempt_count or 0
        if attempts >= 26:
            return 'Z+'
        return chr(ord('A') + attempts)

class UserCourseProgress(db.Model):
    __tablename__ = 'user_course_progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.User_id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.course_id'), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    completion_date = db.Column(db.Date)
    reattempt_count = db.Column(db.Integer, default=0)

class Management:
    def getDashboard(self):
        from sqlalchemy.sql import func
        total_users = User.query.count()
        total_modules = Module.query.count()
        total_certificates = Certificate.query.count()
        active_trainers = Trainer.query.filter_by(active_status=True).count()
        # Completion stats: number of completed modules per user
        completion_stats = (
            db.session.query(User.full_name, func.count(UserModule.id))
            .join(UserModule, User.User_id == UserModule.user_id)
            .filter(UserModule.is_completed.is_(True))
            .group_by(User.full_name)
            .all()
        )
        # Placeholder
        performance_metrics = None
        return {
            'total_users': total_users,
            'total_modules': total_modules,
            'total_certificates': total_certificates,
            'active_trainers': active_trainers,
            'completion_stats': completion_stats,
            'performance_metrics': performance_metrics
        }

class Registration:
    @staticmethod
    def registerUser(user_data):
        # Check if email already exists
        existing_user = User.query.filter_by(email=user_data['email']).first()
        if existing_user:
            raise ValueError(f"Email {user_data['email']} is already registered. Please use a different email or login instead.")

        # Create a new user with number_series automatically generated
        user = User(
            full_name=user_data['full_name'],
            email=user_data['email'],
            user_category=user_data['user_category'],
            agency_id=user_data['agency_id'],
            is_finalized=False
        )
        user.set_password(user_data['password'])

        # Define these variables outside try-except so they're always available
        year = datetime.now(UTC).strftime('%Y')
        seq_name = f'user_number_series_{year}_seq'

        try:
            db.session.add(user)
            db.session.flush()
            # Set number_series with prefix SG + current year + 4-digit sequence per-year
            db.session.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))
            seq_val = db.session.execute(text(f"SELECT nextval('{seq_name}')")).scalar()
            user.number_series = f"SG{year}{int(seq_val):04d}"
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            # Check if this is a duplicate email error (shouldn't happen due to pre-check, but just in case)
            if 'user_email_key' in str(e.orig) or 'duplicate key value violates unique constraint' in str(e.orig):
                raise ValueError(f"Email {user_data['email']} is already registered. Please use a different email.")

            # If it's a different integrity error (like sequence conflicts), retry once
            try:
                seq_val = db.session.execute(text(f"SELECT nextval('{seq_name}')")).scalar()
                user.number_series = f"SG{year}{int(seq_val):04d}"
                db.session.add(user)
                db.session.commit()
            except IntegrityError as retry_error:
                db.session.rollback()
                raise RuntimeError(f"Failed to register user after retry: {str(retry_error)}")
        return user

class WorkHistory(db.Model):
    __tablename__ = 'work_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.User_id'), nullable=False)
    company_name = db.Column(db.String(255), nullable=False)
    position_title = db.Column(db.String(255))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    user = db.relationship('User', back_populates='work_histories')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'company_name': self.company_name,
            'position_title': self.position_title,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None
        }
