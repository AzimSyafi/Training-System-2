from flask import Flask
import os
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models import db, User, Agency, Registration

app = Flask(__name__)

# Configure DB: prefer env DATABASE_URL; fallback to local Postgres
DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://postgres:0789@localhost:5432/Training_system'
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
app.app_context().push()


def ensure_user_role_column():
    """Ensure the user.role column exists across dialects (best-effort)."""
    try:
        dialect = (getattr(db.engine, 'dialect', None).name or '').lower()
    except Exception:
        dialect = ''
    try:
        with db.engine.begin() as conn:
            if dialect == 'postgresql':
                conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'agency'"))
                conn.execute(text("UPDATE \"user\" SET role = 'agency' WHERE role IS NULL"))
                try:
                    conn.execute(text('ALTER TABLE "user" ALTER COLUMN role SET NOT NULL'))
                except Exception:
                    pass
            else:
                # SQLite and others
                try:
                    conn.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(50)"))
                except Exception:
                    pass
                try:
                    conn.execute(text("UPDATE user SET role = 'agency' WHERE role IS NULL"))
                except Exception:
                    pass
    except Exception as e:
        print(f"[WARN] Could not ensure user.role column: {e}")


def ensure_default_agency(agency_id: int = 1) -> Agency:
    ag = db.session.get(Agency, agency_id)
    if ag:
        return ag
    try:
        ag = Agency(
            agency_id=agency_id,
            agency_name=f"Default Agency {agency_id}",
            contact_number="0000000000",
            address="",
            Reg_of_Company="",
            PIC="",
            email=f"agency{agency_id}@example.com",
        )
        db.session.add(ag)
        db.session.commit()
        print(f"[INFO] Created default agency with ID {agency_id}")
    except IntegrityError:
        db.session.rollback()
        ag = db.session.get(Agency, agency_id)
    return ag


def create_or_update_authority(email: str, full_name: str, password: str, agency_id: int = 1) -> User:
    ensure_user_role_column()
    ensure_default_agency(agency_id)

    existing = User.query.filter_by(email=email).first()
    if existing:
        existing.role = 'authority'
        try:
            existing.set_password(password)
        except Exception:
            pass
        # Mark as finalized so onboarding isn’t forced
        try:
            existing.is_finalized = True
        except Exception:
            pass
        db.session.commit()
        print(f"[INFO] Updated existing user to authority: {email}")
        return existing

    # Create via Registration helper to get number_series generated
    user_data = {
        'full_name': full_name,
        'email': email,
        'password': password,
        'user_category': 'citizen',
        'agency_id': agency_id,
    }
    u = Registration.registerUser(user_data)
    # Elevate to authority
    u.role = 'authority'
    try:
        u.is_finalized = True
    except Exception:
        pass
    db.session.commit()
    print(f"[INFO] Created authority user: {email}")
    return u


if __name__ == '__main__':
    # Default mock credentials; override via env if desired
    email = os.environ.get('AUTHORITY_EMAIL', 'authority@example.com')
    full_name = os.environ.get('AUTHORITY_NAME', 'Mock Authority')
    password = os.environ.get('AUTHORITY_PASSWORD', 'Authority@123')
    try:
        agency_id = int(os.environ.get('AUTHORITY_AGENCY_ID', '1'))
    except Exception:
        agency_id = 1

    u = create_or_update_authority(email=email, full_name=full_name, password=password, agency_id=agency_id)
    print('\nLogin details:')
    print(f"  Email:    {email}")
    print(f"  Password: {password}")
    try:
        print(f"  Series:   {u.number_series}")
    except Exception:
        pass
    print("\nAfter login, open /authority to access the portal.")
