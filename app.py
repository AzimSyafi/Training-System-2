from flask import Flask, session
from models import db
from flask_login import LoginManager
from utils import register_jinja_filters
from routes import main_bp
from authority_routes import authority_bp
from flask_mail import Mail
import os
import logging

app = Flask(__name__, static_url_path='/static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Database configuration
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:password@localhost:5432/Training_system'

logging.info(f"Using database: {app.config['SQLALCHEMY_DATABASE_URI']}")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

# Mail configuration for MailHog
app.config['MAIL_SERVER'] = 'localhost'
app.config['MAIL_PORT'] = 1025
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = False

# Initialize extensions
register_jinja_filters(app)
db.init_app(app)
mail = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'main.login'

# Create database tables if they don't exist
with app.app_context():
    db.create_all()

# Restore the user loader so flask-login can resolve current_user
@login_manager.user_loader
def load_user(user_id):
    """Load a user for Flask-Login from the session id and stored user_type.

    This mirrors the original app logic: supports Admin, User, Trainer, AgencyAccount
    and falls back to numeric/series lookups when needed.
    """
    from models import Admin, User, Trainer, AgencyAccount
    # Determine user_type from session, fall back to heuristics
    user_type = session.get('user_type')
    # Admins keep numeric IDs
    if user_type == 'admin':
        try:
            return db.session.get(Admin, int(user_id))
        except (TypeError, ValueError):
            return None
    # Users stored with SG... number_series or numeric legacy IDs
    if user_type == 'user':
        if isinstance(user_id, str) and user_id.startswith('SG'):
            try:
                u = User.query.filter_by(number_series=user_id).first()
            except Exception:
                u = None
            if u:
                return u
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None
    # Trainers
    if user_type == 'trainer':
        if isinstance(user_id, str) and user_id.startswith('TR'):
            t = Trainer.query.filter_by(number_series=user_id).first()
            if t:
                return t
        try:
            return db.session.get(Trainer, int(user_id))
        except (TypeError, ValueError):
            return None
    # Agency accounts
    if user_type == 'agency':
        try:
            return db.session.get(AgencyAccount, int(user_id))
        except (TypeError, ValueError):
            return None
    # Fallback detection if session user_type missing
    if isinstance(user_id, str):
        if user_id.startswith('SG'):
            return User.query.filter_by(number_series=user_id).first()
        if user_id.startswith('TR'):
            return Trainer.query.filter_by(number_series=user_id).first()
        try:
            num_id = int(user_id)
            admin = db.session.get(Admin, num_id)
            if admin:
                return admin
            u = db.session.get(User, num_id)
            if u:
                return u
            return db.session.get(AgencyAccount, num_id)
        except (TypeError, ValueError):
            return None
    return None

# Register main blueprint
app.register_blueprint(main_bp)
app.register_blueprint(authority_bp)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5050, debug=True)
