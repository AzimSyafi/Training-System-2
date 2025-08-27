from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, UTC  # added UTC
from flask_login import UserMixin
from sqlalchemy import event, text

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
    visa_expiry_date = db.Column(db.Date)
    emergency_contact = db.Column(db.String(20))
    emergency_relationship = db.Column(db.String(100))
    working_experience = db.Column(db.String(255))
    recruitment_date = db.Column(db.Date)
    current_workplace = db.Column(db.String(255))
    state = db.Column(db.String(50))
    postcode = db.Column(db.String(10))
    remarks = db.Column(db.Text)
    rating_star = db.Column(db.Integer, default=0)
    rating_label = db.Column(db.String(50), default='')
    agency_id = db.Column(db.Integer, db.ForeignKey('agency.agency_id'), nullable=False)
    address = db.Column(db.Text)
    visa_number = db.Column(db.String(50))
    ic_number = db.Column(db.String(50), nullable=True)  # Required for citizens
    passport_number = db.Column(db.String(50), nullable=True)  # Required for foreigners

    # Relationship
    certificates = db.relationship('Certificate', backref='user', lazy=True)
    user_modules = db.relationship('UserModule', backref='user', lazy=True)
    work_histories = db.relationship('WorkHistory', back_populates='user', lazy=True)

    @property
    def profile_pic_url(self):
        from flask import url_for
        if self.Profile_picture:
            return url_for('static', filename=f'profile_pics/{self.Profile_picture}')
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
    star_rating = db.Column(db.Integer, default=0)
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
            'star_rating': self.star_rating,
            'content': self.content
        }

    def editScoring(self, new_score):
        self.scoring_float = new_score
        db.session.commit()

    def setStarRating(self, rating):
        self.star_rating = rating
        db.session.commit()

    def to_dict(self):
        return {
            'module_id': self.module_id,
            'module_name': self.module_name,
            'module_type': self.module_type,
            'series_number': self.series_number,
            'scoring_float': self.scoring_float,
            'star_rating': self.star_rating,
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
    star_rating = db.Column(db.Integer, default=0)
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

    @property
    def username(self):
        return self.name

    @property
    def profile_pic(self):
        return self.profile_image

    @property
    def displayed_id(self):
        return self.number_series or str(self.trainer_id)

    def assignModule(self, module_id):
        self.module_id = module_id
        db.session.commit()

    def getAssignedUsers(self):
        return User.query.filter_by(trainer=self.name).all()

    def getSchedule(self):
        # Return trainer's schedule
        return {
            'trainer_id': self.trainer_id,
            'availability': self.availability,
            'assigned_module': self.module_id
        }

    def updateAvailability(self, new_availability):
        self.availability = new_availability
        db.session.commit()

class UserModule(db.Model):
    __tablename__ = 'user_module'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.User_id'), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('module.module_id'), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    score = db.Column(db.Float, default=0.0)
    completion_date = db.Column(db.DateTime)
    quiz_answers = db.Column(db.Text)  # Store user's quiz answers as JSON string
    reattempt_count = db.Column(db.Integer, default=0)  # Track number of reattempts

    def complete_module(self, score):
        self.is_completed = True
        self.score = score
        self.completion_date = datetime.now()
        db.session.commit()

    def get_grade_letter(self):
        """Get grade letter based on reattempt count: A=0, B=1, C=2, etc."""
        if self.reattempt_count >= 26:
            return 'Z+'
        return chr(ord('A') + self.reattempt_count)

class Management(db.Model):
    __tablename__ = 'management'

    id = db.Column(db.Integer, primary_key=True)
    manager_name = db.Column(db.String(255), nullable=False)
    designation = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    signature = db.Column(db.String(255))

    def generateReport(self):
        # Generate comprehensive training report
        total_users = User.query.count()
        completed_modules = UserModule.query.filter_by(is_completed=True).count()
        issued_certificates = Certificate.query.count()

        return {
            'total_users': total_users,
            'completed_modules': completed_modules,
            'issued_certificates': issued_certificates,
            'completion_rate': (completed_modules / total_users) * 100 if total_users > 0 else 0
        }

    def getCompletionStatistics(self):
        # Get detailed completion statistics
        stats = db.session.query(
            Module.module_name,
            db.func.count(UserModule.id).label('total_attempts'),
            db.func.count(db.case((UserModule.is_completed == True, 1))).label('completed'),
            db.func.avg(UserModule.score).label('avg_score')
        ).join(UserModule).group_by(Module.module_id).all()

        return stats

    def exportModuleData(self):
        # Export module data for analysis
        return Module.query.all()

    def getPerformanceMetrics(self):
        # Get performance metrics
        metrics = db.session.query(
            db.func.avg(UserModule.score).label('avg_score'),
            db.func.max(UserModule.score).label('max_score'),
            db.func.min(UserModule.score).label('min_score')
        ).filter(UserModule.is_completed == True).first()

        return metrics

    def getDashboard(self):
        # Get dashboard data
        return {
            'total_users': User.query.count(),
            'total_modules': Module.query.count(),
            'total_certificates': Certificate.query.count(),
            'active_trainers': Trainer.query.filter_by(active_status=True).count(),
            'completion_stats': self.getCompletionStatistics(),
            'performance_metrics': self.getPerformanceMetrics()
        }

class Registration:
    @staticmethod
    def registerUser(user_data):
        # Remove 'password' from user_data before creating User
        password = user_data.pop('password', None)

        # Check if agency_id exists in the database
        agency_id = user_data.get('agency_id')
        if agency_id:
            agency = Agency.query.get(agency_id)
            if not agency:
                # Create a default agency if it doesn't exist
                agency = Agency(agency_id=agency_id, agency_name=f"Default Agency {agency_id}")
                db.session.add(agency)
                try:
                    db.session.flush()  # Check if agency can be added without committing
                except Exception as e:
                    db.session.rollback()
                    raise Exception(f"Could not create default agency: {str(e)}")

        user = User(**user_data)
        if password:
            user.set_password(password)
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            if 'violates foreign key constraint' in str(e) and 'agency_id' in str(e):
                # Specifically handle agency_id foreign key violations
                raise Exception("Agency does not exist. Please select a valid agency.")
            raise e

        return user

    @staticmethod
    def assignAgency(user_id, agency_id):
        user = User.query.get(user_id)
        if user:
            user.agency_id = agency_id
            db.session.commit()
            return True
        return False

    @staticmethod
    def getUserList():
        return User.query.all()

    @staticmethod
    def getAgencyList():
        return Agency.query.all()

    @staticmethod
    def getModuleList():
        return Module.query.all()

    @staticmethod
    def generateUserid():
        last_user = User.query.order_by(User.User_id.desc()).first()
        return (last_user.User_id + 1) if last_user else 1

class WorkHistory(db.Model):
    __tablename__ = 'work_history'
    work_history_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.User_id'), nullable=False)
    company_name = db.Column(db.String(255), nullable=False)
    position_title = db.Column(db.String(255))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    # Relationship
    user = db.relationship('User', back_populates='work_histories', lazy=True)

    def getWorkDuration(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days
        return 0

    def getCompanyName(self):
        return self.company_name

    def getPositionTitle(self):
        return self.position_title

    def getWorkHistoryDetails(self):
        return {
            'work_history_id': self.work_history_id,
            'user_id': self.user_id,
            'company_name': self.company_name,
            'position_title': self.position_title,
            'start_date': self.start_date,
            'end_date': self.end_date
        }

class UserCourseProgress(db.Model):
    __tablename__ = 'user_course_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.User_id'), nullable=False)
    course_id = db.Column(db.Integer, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    completion_date = db.Column(db.DateTime)
    certificate_url = db.Column(db.String(255))
    # New: Track how many full course reattempts (resets) the user has done
    reattempt_count = db.Column(db.Integer, default=0)

    def mark_complete(self, certificate_url=None):
        self.completed = True
        self.completion_date = datetime.now()
        if certificate_url:
            self.certificate_url = certificate_url
        db.session.commit()

    def get_grade_letter(self):
        if self.reattempt_count >= 26:
            return 'Z+'
        return chr(ord('A') + (self.reattempt_count or 0))

# --- Automatic prefixed number_series assignment ---
@event.listens_for(User, 'before_insert')
def assign_number_series(mapper, connection, target):
    """Assign SGYYYYNNNN for users. Uses per-year sequence user_number_series_{year}_seq."""
    existing = getattr(target, 'number_series', None)
    if existing:
        # Normalize: ensure starts with SG and correct length
        existing = existing.strip().upper()
        if existing.startswith('SG') and len(existing) == 10:
            return
        # Strip non-alphanumerics and regenerate below
    year = datetime.now(UTC).strftime('%Y')  # updated
    seq_name = f'user_number_series_{year}_seq'
    connection.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))
    seq_val = connection.execute(text(f"SELECT nextval('{seq_name}')")).scalar()
    target.number_series = f"SG{year}{seq_val:04d}"

@event.listens_for(Trainer, 'before_insert')
def assign_trainer_number_series(mapper, connection, target):
    """Assign TRYYYYNNNN for trainers. Uses per-year sequence trainer_number_series_{year}_seq."""
    existing = getattr(target, 'number_series', None)
    if existing:
        existing = existing.strip().upper()
        if existing.startswith('TR') and len(existing) == 10:
            return
    year = datetime.now(UTC).strftime('%Y')  # updated
    seq_name = f'trainer_number_series_{year}_seq'
    connection.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))
    seq_val = connection.execute(text(f"SELECT nextval('{seq_name}')")).scalar()
    target.number_series = f"TR{year}{seq_val:04d}"
