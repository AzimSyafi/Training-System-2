from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, UTC  # removed unused date
import os
from models import db, Admin, User, Agency, Module, Certificate, Trainer, UserModule, Management, Registration, Course, WorkHistory, UserCourseProgress, AgencyAccount
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, inspect as sa_inspect
import re
import urllib.parse
import logging
from werkzeug.routing import BuildError  # added
import json
# Load .env for local development only
try:
    # Treat presence of any hosted env signal or an existing DB URL as production
    hosted_signals = (
        os.environ.get('RENDER'),
        os.environ.get('RENDER_EXTERNAL_HOSTNAME'),
        os.environ.get('RENDER_SERVICE_ID'),
        os.environ.get('DYNO'),  # Heroku
    )
    existing_db = (
        os.environ.get('DATABASE_URL')
        or os.environ.get('DATABASE_INTERNAL_URL')
        or os.environ.get('DATABASE_URL_INTERNAL')
        or os.environ.get('POSTGRES_URL')
        or os.environ.get('POSTGRESQL_URL')
    )
    if not any(hosted_signals) and not existing_db:
        from dotenv import load_dotenv
        load_dotenv()
except Exception:
    pass

app = Flask(__name__, static_url_path='/static')

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Decide which PostgreSQL driver is installed and normalize DB URL accordingly
def _normalize_pg_url_for_sqlalchemy(url: str) -> str:
    if not isinstance(url, str) or not url:
        return url
    # normalize postgres:// -> postgresql://
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    # Detect installed driver
    driver = None
    try:
        import psycopg  # type: ignore
        driver = 'psycopg'
    except Exception:
        try:
            import psycopg2  # type: ignore
            driver = 'psycopg2'
        except Exception:
            driver = None
    # If already has a dialect prefix, leave it; otherwise add best driver
    if url.startswith('postgresql+'):  # already explicit
        return url
    if driver:
        return url.replace('postgresql://', f'postgresql+{driver}://', 1)
    # No driver detected: return generic and let SQLAlchemy error with clear message
    return url

# Database configuration - Prefer PostgreSQL, fallback to SQLite if unreachable
# Prefer hosted env vars first (Render, etc.), then fall back to local
_db_candidates = [
    ('DATABASE_INTERNAL_URL', os.environ.get('DATABASE_INTERNAL_URL')),  # Render internal URL
    ('DATABASE_URL_INTERNAL', os.environ.get('DATABASE_URL_INTERNAL')),  # common typo/alt
    ('DATABASE_URL', os.environ.get('DATABASE_URL')),
    ('POSTGRES_URL', os.environ.get('POSTGRES_URL')),
    ('POSTGRESQL_URL', os.environ.get('POSTGRESQL_URL')),
]
_used_name = None
_db_url = None
for name, val in _db_candidates:
    if val:
        _used_name = name
        _db_url = val
        break
if _db_url:
    database_url = _normalize_pg_url_for_sqlalchemy(_db_url)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print(f"[DB] Using env database URL from { _used_name }")
else:
    # Local PostgreSQL defaults (adjust via env vars if needed)
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '0789')  # align with .env example
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_NAME = os.environ.get('DB_NAME', 'Training_system')
    raw_url = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    app.config['SQLALCHEMY_DATABASE_URI'] = _normalize_pg_url_for_sqlalchemy(raw_url)
    print('[DB] Using local fallback PostgreSQL connection (adjust via env vars)')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Proactively ping pooled connections to avoid stale sockets on cold starts
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True
}

# Attempt a quick connectivity test; keep PostgreSQL and DO NOT fall back to SQLite
try:
    from sqlalchemy import create_engine  # local import to avoid hard dependency if unused
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if uri.startswith('postgresql'):
        tmp_engine = create_engine(uri, pool_pre_ping=True)
        try:
            with tmp_engine.connect() as conn:
                conn.execute(text('SELECT 1'))
                print('[DB] PostgreSQL connectivity check: OK')
        except Exception as e:
            # Do not change DB to SQLite; surface connectivity issues at runtime
            print(f"[DB] PostgreSQL connectivity check failed; staying on PostgreSQL URI. Error: {e}")
except Exception as e:
    # If test fails unexpectedly, keep current URI; subsequent operations may handle it
    print(f"[DB] Connectivity pre-check failed: {e}")

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

# Inject Tailwind flag into all templates: set USE_TAILWIND_CDN=1 in dev; unset in prod
@app.context_processor
def inject_tailwind_flag():
    # Prefer the locally compiled Tailwind CSS if it exists in static/css/tailwind.css.
    # This ensures the app uses the exact utilities the project was built with and
    # prevents visual drift from the runtime CDN injecting a different set.
    compiled_path = os.path.join(app.static_folder or 'static', 'css', 'tailwind.css')
    try:
        compiled_exists = os.path.exists(compiled_path)
    except Exception:
        compiled_exists = False
    # If compiled file exists, prefer local CSS regardless of env var.
    if compiled_exists:
        use_cdn = False
    else:
        use_cdn = os.environ.get('USE_TAILWIND_CDN', '0') in ('1', 'true', 'True')
    return {'USE_TAILWIND_CDN': use_cdn}

# --- DB readiness helper ---
def _wait_for_db(engine, seconds: int = 20) -> bool:
    """Try to connect to the DB for up to `seconds`. Returns True if reachable, False otherwise."""
    import time
    start = time.time()
    last_err = None
    while time.time() - start < seconds:
        try:
            with engine.connect() as conn:
                conn.execute(text('SELECT 1'))
                return True
        except Exception as e:
            last_err = e
            time.sleep(1.0)
    if last_err:
        logging.warning(f"[DB WAIT] DB not reachable after {seconds}s: {last_err}")
    return False

# --- Helpers ---
def normalized_user_category(user: User) -> str:
    """Return 'citizen' or 'foreigner' robustly.
    Falls back using passport/ic when user_category missing/invalid."""
    try:
        raw = (getattr(user, 'user_category', None) or '').strip().lower()
    except Exception:
        raw = ''
    if raw in ('citizen', 'foreigner'):
        return raw
    # Fallback by IDs
    passport = getattr(user, 'passport_number', None)
    ic = getattr(user, 'ic_number', None)
    if passport and not ic:
        return 'foreigner'
    return 'citizen'

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

# Prevent browser from caching authenticated pages so Back button doesn’t show them after logout
@app.after_request
def add_no_cache_headers(response):
    try:
        # Skip static and uploaded file endpoints to allow normal caching there
        skip_endpoints = {'static', 'serve_upload', 'serve_uploaded_slide'}
        ep = request.endpoint or ''
        if ep not in skip_endpoints:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
    except Exception:
        # Don’t break the response pipeline if anything goes wrong
        pass
    return response

# --- One-time schema safeguard: ensure trainer.number_series exists & populated ---
DISABLE_SCHEMA_GUARD = os.environ.get('DISABLE_SCHEMA_GUARD', '0') in ('1', 'true', 'True')

# Check PostgreSQL version to determine lock function availability
def _get_pg_version(engine):
    """Get PostgreSQL version to determine available functions"""
    try:
        with engine.connect() as conn:
            version_str = conn.execute(text("SHOW server_version")).scalar()
            # Extract major version number
            return int(version_str.split('.')[0])
    except Exception:
        # Default to assuming newer version
        return 10

# Function to safely bootstrap schema with advisory lock
def _bootstrap_schema_with_advisory_lock(initializer):
    """Runs schema initialization safely with only one worker performing the work.
    Other workers will wait until initialization is complete."""
    # If not PostgreSQL, just run initializer directly (SQLite/MySQL don't support pg advisory locks)
    try:
        if db.engine.dialect.name != 'postgresql':
            initializer()
            return
    except Exception:
        # If engine unavailable, try to run initializer anyway
        try:
            initializer()
            return
        except Exception:
            pass

    if not _wait_for_db(db.engine, seconds=20):
        print('[SCHEMA GUARD] Skipping schema guard: database not reachable yet.')
        return

    # Do not return early simply because some tables exist; we still need to run
    # initializer to create newly added tables/columns (idempotent logic inside).

    # Use a stable lock key derived from app name
    lock_key = 922337203685477571  # 64-bit key

    with db.engine.connect() as conn:
        # Try to become the leader (non-blocking)
        got_leader = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": lock_key}).scalar()

        if got_leader:
            print(f'[SCHEMA GUARD] Worker (PID {os.getpid()}) acquired lock and will initialize schema')
            try:
                # Run the initialization (idempotent)
                initializer()
                print(f'[SCHEMA GUARD] Schema initialization completed by worker {os.getpid()}')
            finally:
                # Release the lock so waiting workers can continue
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key})
        else:
            # Another worker is initializing; wait until it finishes
            print(f'[SCHEMA GUARD] Worker (PID {os.getpid()}) waiting for schema initialization to complete')

            # Check PostgreSQL version for lock_timeout support
            pg_version = _get_pg_version(db.engine)

            if pg_version >= 9.3:  # lock_timeout was added in PostgreSQL 9.3
                try:
                    # Set a statement timeout to prevent indefinite waiting
                    conn.execute(text("SET LOCAL lock_timeout = '30s'"))
                    conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": lock_key})
                    print(f'[SCHEMA GUARD] Worker (PID {os.getpid()}) proceeding after schema initialization')
                except Exception as e:
                    print(f'[SCHEMA GUARD] Lock acquisition timed out: {e}, proceeding anyway')
                finally:
                    # Try to unlock if we got the lock
                    try:
                        conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key})
                    except Exception:
                        pass
            else:
                # Fallback for older PostgreSQL versions
                import time
                max_wait = 30  # seconds
                start_time = time.time()

                while time.time() - start_time < max_wait:
                    # Try non-blocking lock acquisition
                    got_lock = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": lock_key}).scalar()
                    if got_lock:
                        try:
                            print(f'[SCHEMA GUARD] Worker (PID {os.getpid()}) acquired lock after waiting')
                            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key})
                        except Exception:
                            pass
                        break
                    time.sleep(1)

                print(f'[SCHEMA GUARD] Worker (PID {os.getpid()}) proceeding after wait period')

# Define the initialization function
def _initialize_schema():
    inspector = sa_inspect(db.engine)
    try:
        # Auto-create missing tables
        essential = ['course', 'user', 'module', 'trainer', 'user_module', 'user_course_progress', 'certificate', 'agency', 'work_history', 'admin', 'management', 'agency_account']
        missing = [t for t in essential if not inspector.has_table(t)]
        if missing:
            db.create_all()
            db.session.commit()
            print(f"[SCHEMA GUARD] Created missing tables: {', '.join(missing)}")

        # Check agency table schema if it exists
        if inspector.has_table('agency'):
            agency_columns = {c['name']: c for c in inspector.get_columns('agency')}
            # If contact_number exists and is not nullable, add ALTER TABLE to make it nullable
            if 'contact_number' in agency_columns and agency_columns['contact_number'].get('nullable') is False:
                try:
                    db.session.execute(text('ALTER TABLE agency ALTER COLUMN contact_number DROP NOT NULL'))
                    db.session.commit()
                    print('[SCHEMA GUARD] Modified agency.contact_number to be nullable')
                except Exception as e:
                    db.session.rollback()
                    print(f'[SCHEMA GUARD] Could not alter agency.contact_number: {e}')
        # Safely handle trainer table
        if inspector.has_table('trainer'):
            trainer_columns = {c['name'] for c in inspector.get_columns('trainer')}
        else:
            trainer_columns = set()
        # Ensure user_module.reattempt_count column exists (only if table exists)
        try:
            if inspector.has_table('user_module'):
                um_columns = {c['name'] for c in inspector.get_columns('user_module')}
                if 'reattempt_count' not in um_columns:
                    db.session.execute(text('ALTER TABLE user_module ADD COLUMN IF NOT EXISTS reattempt_count INTEGER DEFAULT 0'))
                    db.session.commit()
                    print('[SCHEMA GUARD] Added reattempt_count to user_module')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not ensure reattempt_count on user_module: {e}')
        # Ensure user_course_progress.reattempt_count column exists (only if table exists)
        try:
            if inspector.has_table('user_course_progress'):
                ucp_columns = {c['name'] for c in inspector.get_columns('user_course_progress')}
                if 'reattempt_count' not in ucp_columns:
                    db.session.execute(text('ALTER TABLE user_course_progress ADD COLUMN IF NOT EXISTS reattempt_count INTEGER DEFAULT 0'))
                    db.session.commit()
                    print('[SCHEMA GUARD] Added reattempt_count to user_course_progress')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not add reattempt_count to user_course_progress: {e}')
        # Ensure work_history has extended columns for detailed experiences
        try:
            if inspector.has_table('work_history'):
                wh_columns = {c['name'] for c in inspector.get_columns('work_history')}
                # Ensure surrogate id column exists and is populated (for ORM compatibility)
                try:
                    if 'id' not in wh_columns:
                        if db.engine.dialect.name == 'postgresql':
                            # Create sequence and add id column with defaults
                            db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS work_history_id_seq"))
                            db.session.execute(text("ALTER TABLE work_history ADD COLUMN IF NOT EXISTS id INTEGER"))
                            db.session.execute(text("ALTER TABLE work_history ALTER COLUMN id SET DEFAULT nextval('work_history_id_seq')"))
                            # Backfill existing rows
                            db.session.execute(text("UPDATE work_history SET id = nextval('work_history_id_seq') WHERE id IS NULL"))
                            db.session.execute(text("ALTER TABLE work_history ALTER COLUMN id SET NOT NULL"))
                            # Add primary key if table has none
                            pk = inspector.get_pk_constraint('work_history') or {}
                            constrained = pk.get('constrained_columns') or []
                            if not constrained:
                                try:
                                    db.session.execute(text("ALTER TABLE work_history ADD CONSTRAINT work_history_pkey PRIMARY KEY (id)"))
                                except Exception:
                                    # If constraint exists or cannot add, ignore; column is still usable
                                    pass
                            db.session.commit()
                        else:
                            # Generic fallback (e.g., SQLite): just add the column
                            try:
                                db.session.execute(text("ALTER TABLE work_history ADD COLUMN id INTEGER"))
                            except Exception:
                                # Column might already exist in some form; ignore
                                pass
                            db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    print(f"[SCHEMA GUARD] Could not ensure work_history.id: {e}")

                # Existing extended columns
                if 'recruitment_date' not in wh_columns:
                    db.session.execute(text('ALTER TABLE work_history ADD COLUMN IF NOT EXISTS recruitment_date DATE'))
                if 'visa_number' not in wh_columns:
                    db.session.execute(text('ALTER TABLE work_history ADD COLUMN IF NOT EXISTS visa_number VARCHAR(50)'))
                if 'visa_expiry_date' not in wh_columns:
                    db.session.execute(text('ALTER TABLE work_history ADD COLUMN IF NOT EXISTS visa_expiry_date DATE'))
                db.session.commit()
                print('[SCHEMA GUARD] Ensured extended columns on work_history')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not ensure extended columns on work_history: {e}')
        # Trainer number_series backfill (only Postgres supports the sequence logic)
        try:
            if inspector.has_table('trainer') and db.engine.dialect.name == 'postgresql':
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
            elif inspector.has_table('trainer') and db.engine.dialect.name != 'postgresql':
                # Ensure the column exists on SQLite without sequence backfill
                try:
                    if 'number_series' not in trainer_columns:
                        db.session.execute(text("ALTER TABLE trainer ADD COLUMN number_series VARCHAR(10)"))
                        db.session.commit()
                except Exception:
                    db.session.rollback()
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Trainer backfill skipped/failed: {e}')
        # Ensure default courses exist without relying on unique constraint
        try:
            if inspector.has_table('course'):
                defaults = [
                    {'name': 'NEPAL SECURITY GUARD TRAINING (TNG)', 'code': 'TNG', 'allowed_category': 'foreigner'},
                    {'name': 'CERTIFIED SECURITY GUARD (CSG)', 'code': 'CSG', 'allowed_category': 'citizen'}
                ]
                # Use ORM upserts: check existence by code (case-insensitive) and create missing ones.
                for d in defaults:
                    existing = Course.query.filter(db.func.lower(db.func.trim(Course.code)) == d['code'].lower()).first()
                    if not existing:
                        c = Course(name=d['name'], code=d['code'], allowed_category=d['allowed_category'])
                        db.session.add(c)
                db.session.commit()
            else:
                print('[SCHEMA GUARD] Skipping course defaults: course table not found.')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not ensure default courses: {e}')

        # Ensure user.is_finalized column exists
        try:
            if inspector.has_table('user'):
                user_columns = {c['name'] for c in inspector.get_columns('user')}
                if 'is_finalized' not in user_columns:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_finalized BOOLEAN DEFAULT FALSE'))
                    db.session.commit()
                    print('[SCHEMA GUARD] Added is_finalized to user')
                # Ensure user.country column exists
                if 'country' not in user_columns:
                    try:
                        db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS country VARCHAR(100) NULL'))
                        db.session.commit()
                        print('[SCHEMA GUARD] Added country to user')
                    except Exception as e:
                        db.session.rollback()
                        print(f'[SCHEMA GUARD] Could not ensure user.country: {e}')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not ensure user.is_finalized: {e}')

        # Ensure default agency exists
        try:
            if inspector.has_table('agency'):
                if db.engine.dialect.name != 'postgresql':
                    # SQLite-safe ORM approach
                    ag = db.session.get(Agency, 1)
                    if not ag:
                        ag = Agency(
                            agency_id=1,
                            agency_name='Default Agency',
                            contact_number='0000000000',
                            address='',
                            Reg_of_Company='',
                            PIC='',
                            email=''
                        )
                        db.session.add(ag)
                        db.session.commit()
                        print('[SCHEMA GUARD] Ensured default agency exists (SQLite path)')
                else:
                    # PostgreSQL dynamic insert based on current schema
                    agency_columns = {c['name']: c for c in inspector.get_columns('agency')}
                    required_values = {'agency_id': 1, 'agency_name': 'Default Agency'}
                    for actual_name, col_info in agency_columns.items():
                        if actual_name in required_values:
                            continue
                        if col_info.get('nullable') is False:
                            lname = actual_name.lower()
                            if lname == 'contact_number':
                                required_values[actual_name] = '0000000000'
                            elif lname in ('address', 'reg_of_company', 'pic', 'email'):
                                required_values[actual_name] = ''
                            else:
                                col_type = col_info.get('type')
                                try:
                                    tstr = str(col_type).lower() if col_type is not None else ''
                                except Exception:
                                    tstr = ''
                                if 'char' in tstr or 'text' in tstr or 'varchar' in tstr:
                                    required_values[actual_name] = ''
                                elif 'int' in tstr or 'numeric' in tstr:
                                    required_values[actual_name] = 0
                                else:
                                    required_values[actual_name] = ''
                    cols_quoted = ', '.join(f'"{c}"' for c in required_values.keys())
                    placeholders = ', '.join(f':{k}' for k in required_values.keys())
                    insert_sql = f"INSERT INTO agency ({cols_quoted}) VALUES ({placeholders}) ON CONFLICT (agency_id) DO NOTHING"
                    try:
                        db.session.execute(text(insert_sql), required_values)
                        db.session.commit()
                        print('[SCHEMA GUARD] Ensured default agency exists with ID 1 with required fields')
                    except Exception as e:
                        db.session.rollback()
                        print(f'[SCHEMA GUARD] Could not create default agency: {e}')
            else:
                print('[SCHEMA GUARD] Skipping agency default: agency table not found.')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Default agency ensure failed: {e}')

        # Optionally: create an agency account for default agency if email present and none exists
        try:
            if inspector.has_table('agency') and inspector.has_table('agency_account'):
                ag = db.session.get(Agency, 1)
                if ag and ag.email and not AgencyAccount.query.filter_by(agency_id=ag.agency_id).first():
                    acct = AgencyAccount(agency_id=ag.agency_id, email=ag.email)
                    acct.set_password('Agency#' + str(ag.agency_id))
                    db.session.add(acct)
                    db.session.commit()
                    print('[SCHEMA GUARD] Created default agency login account for agency 1')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not create default agency account: {e}')

        # Ensure a default admin exists so login works initially
        try:
            if inspector.has_table('admin'):
                has_admin = Admin.query.first()
                if not has_admin:
                    default_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
                    default_username = os.environ.get('ADMIN_USERNAME', 'admin')
                    default_password = os.environ.get('ADMIN_PASSWORD', 'Admin#12345')
                    new_admin = Admin(username=default_username, email=default_email)
                    new_admin.set_password(default_password)
                    db.session.add(new_admin)
                    db.session.commit()
                    print(f"[SCHEMA GUARD] Created default admin account {default_email} (change the password!)")
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not ensure default admin: {e}')
    except Exception as e:
        db.session.rollback()
        print(f"[SCHEMA GUARD] Could not ensure default entities: {e}")

# Execute schema initialization with the advisory lock pattern at import time
with app.app_context():
    if not DISABLE_SCHEMA_GUARD:
        _bootstrap_schema_with_advisory_lock(_initialize_schema)
# -------------------------------------------------------------------------------

@login_manager.user_loader
def load_user(user_id):
    user_type = session.get('user_type')
    # Admins keep numeric IDs
    if user_type == 'admin':
        try:
            return db.session.get(Admin, int(user_id))
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
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None
    # Trainers use TRYYYYNNNN number_series
    if user_type == 'trainer':
        if isinstance(user_id, str) and user_id.startswith('TR'):
            t = Trainer.query.filter_by(number_series=user_id).first()
            if t:
                return t
        try:
            return db.session.get(Trainer, int(user_id))
        except (TypeError, ValueError):
            return None
    # Agency accounts use numeric account IDs
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
        # Try numeric admin then user then agency account
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

@app.route('/uploads/<path:filename>')  # unified route; path allows subdirectories if needed
def serve_upload(filename):
    """Serve uploaded profile pictures or module slide files from their respective directories.
    Tries profile pictures folder first, then static/uploads. Returns 404 if not found.
    If the requested file is a module slide, enforce disclaimer acceptance for regular users."""
    profile_dir = app.config.get('UPLOAD_FOLDER', 'static/profile_pics')
    slides_dir = os.path.join(app.root_path, 'static', 'uploads')

    # If this filename corresponds to a module slide, enforce disclaimer for regular users
    try:
        m = Module.query.filter_by(slide_url=filename).first()
        if m is not None:
            # If unauthenticated or a regular user who hasn't agreed, block
            if not current_user.is_authenticated:
                from flask import abort
                return abort(403)
            # Allow admins/trainers to bypass; enforce for regular users
            if isinstance(current_user, User):
                if not current_user.has_agreed_to_module_disclaimer(m.module_id):
                    from flask import abort
                    return abort(403)
    except Exception:
        # On error, fall through to normal serving to avoid breaking avatars
        pass

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
@login_required
def serve_uploaded_slide(filename):
    """Serve module slide files from static/uploads with mandatory disclaimer enforcement.
    Resolves the filename to a Module to check per-user agreement before serving."""
    slides_dir = os.path.join(app.root_path, 'static', 'uploads')

    # Check if the file belongs to a module and enforce acceptance for regular users
    m = Module.query.filter_by(slide_url=filename).first()
    if m is not None and isinstance(current_user, User):
        if not current_user.has_agreed_to_module_disclaimer(m.module_id):
            from flask import abort
            return abort(403)
    # Non-user roles (admin/trainer/agency) can view for QA/review
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
        # Agency account
        from models import AgencyAccount as _AA
        if isinstance(current_user, _AA):
            return redirect(url_for('agency_portal'))
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
        from models import AgencyAccount as _AA
        if isinstance(current_user, _AA):
            return redirect(url_for('agency_portal'))
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
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
            # If not trainer, try Agency accounts
            acct = AgencyAccount.query.filter_by(email=email).first()
            if acct and acct.check_password(password):
                login_user(acct)
                session['user_type'] = 'agency'
                session['user_id'] = acct.get_id()
                print(f"[DEBUG] Logged in as agency: {acct.email}, session['user_type']: {session.get('user_type')}")
                return redirect(url_for('agency_portal'))
            flash('Invalid email or password')
        except Exception as e:
            logging.exception('[LOGIN] Database error during authentication')
            flash('Database error. Please check server database connection.')

    return render_template('login.html')

# New: unified logout route used by templates (supports POST and GET)
@app.route('/logout', methods=['POST', 'GET'])
@login_required
def logout():
    try:
        logout_user()
    except Exception:
        pass
    # Clear entire session to remove user_type and other flags
    try:
        session.clear()
    except Exception:
        pass
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

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
            # Normalize user_category at query time to avoid mismatches
            if course.allowed_category == 'citizen':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'citizen')
            elif course.allowed_category == 'foreigner':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'foreigner')
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
        # Module star ratings removed; keep avg_rating_pct for template compatibility
        avg_rating_pct = 0.0
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
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'citizen')
            elif course_obj.allowed_category == 'foreigner':
                trainees_q = trainees_q.filter(db.func.lower(db.func.trim(User.user_category)) == 'foreigner')
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

# --- Admin dashboard ---
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    # Only admins can access
    if not isinstance(current_user, Admin):
        # Redirect other roles to their dashboards
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        return redirect(url_for('login'))
    try:
        mgr = Management()
        dashboard = mgr.getDashboard()
    except Exception:
        logging.exception('[ADMIN DASHBOARD] Failed to build dashboard context')
        dashboard = {
            'total_users': 0,
            'total_modules': 0,
            'total_certificates': 0,
            'active_trainers': 0,
            'completion_stats': [],
            'performance_metrics': None,
        }
    return render_template('admin_dashboard.html', dashboard=dashboard)

# Progress monitoring for admins
@app.route('/monitor_progress')
@login_required
def monitor_progress():
    # Only admins can access
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))

    # Load filter options
    try:
        agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
    except Exception:
        agencies = []
    try:
        courses = Course.query.order_by(Course.name.asc()).all()
    except Exception:
        courses = []

    # Parse filters safely
    q = (request.args.get('q') or '').strip()
    try:
        agency_id = int(request.args.get('agency_id')) if request.args.get('agency_id') else None
    except Exception:
        agency_id = None
    try:
        course_id = int(request.args.get('course_id')) if request.args.get('course_id') else None
    except Exception:
        course_id = None
    status = (request.args.get('status') or '').strip().lower()  # '', in_progress, completed
    try:
        min_progress = int(request.args.get('min_progress')) if request.args.get('min_progress') not in (None, '') else None
    except Exception:
        min_progress = None
    try:
        max_progress = int(request.args.get('max_progress')) if request.args.get('max_progress') not in (None, '') else None
    except Exception:
        max_progress = None

    # Build users list constrained by agency filter
    users_q = User.query
    if agency_id:
        users_q = users_q.filter(User.agency_id == agency_id)
    # Preload agency to reduce lazy loads in template
    try:
        users = users_q.all()
    except Exception:
        users = []

    # If there is a text query, we'll apply it after row-build (match name/email/agency)

    # Determine courses to include
    selected_courses = []
    if course_id:
        c = db.session.get(Course, course_id)
        if c:
            selected_courses = [c]
    else:
        selected_courses = courses

    course_progress_rows = []
    try:
        from sqlalchemy import func, case
        # Build lookup maps
        users_by_id = {u.User_id: u for u in users}
        agency_by_id = {a.agency_id: a for a in agencies}
        user_ids = list(users_by_id.keys())
        for c in selected_courses:
            module_ids = [m.module_id for m in getattr(c, 'modules', [])]
            total_modules = len(module_ids)
            if total_modules == 0:
                continue
            if not user_ids:
                break
            # Aggregate per user for this course's modules
            agg = (
                db.session.query(
                    UserModule.user_id.label('uid'),
                    func.count(UserModule.id).label('total_rows'),
                    func.sum(case((UserModule.is_completed == True, 1), else_=0)).label('completed_cnt'),
                    func.avg(case((UserModule.is_completed == True, UserModule.score), else_=None)).label('avg_score')
                )
                .filter(UserModule.module_id.in_(module_ids), UserModule.user_id.in_(user_ids))
                .group_by(UserModule.user_id)
                .all()
            )
            stats = {row.uid: row for row in agg}
            for uid in user_ids:
                u = users_by_id.get(uid)
                if not u:
                    continue
                st = stats.get(uid)
                completed = int(getattr(st, 'completed_cnt', 0) or 0)
                avg_score = float(getattr(st, 'avg_score', 0.0) or 0.0)
                progress_pct = int(round((completed / total_modules * 100.0), 0)) if total_modules else 0
                ag = agency_by_id.get(getattr(u, 'agency_id', None))
                row = {
                    'user_name': getattr(u, 'full_name', ''),
                    'user_email': getattr(u, 'email', ''),
                    'course_name': getattr(c, 'name', ''),
                    'course_code': getattr(c, 'code', ''),
                    'agency_name': getattr(ag, 'agency_name', '') if ag else '',
                    'completed_modules': completed,
                    'total_modules': total_modules,
                    'progress_pct': progress_pct,
                    'avg_score': round(avg_score, 1) if avg_score else None,
                    'status': 'Completed' if progress_pct >= 100 else 'In Progress' if progress_pct > 0 else 'Not Started'
                }
                course_progress_rows.append(row)
    except Exception:
        logging.exception('[MONITOR PROGRESS] Failed to build rows')
        course_progress_rows = []

    # Apply post-filters
    if status in ('completed', 'in_progress'):
        want_completed = (status == 'completed')
        if want_completed:
            course_progress_rows = [r for r in course_progress_rows if r['progress_pct'] >= 100]
        else:
            course_progress_rows = [r for r in course_progress_rows if 0 < r['progress_pct'] < 100]
    if min_progress is not None:
        course_progress_rows = [r for r in course_progress_rows if r['progress_pct'] >= min_progress]
    if max_progress is not None:
        course_progress_rows = [r for r in course_progress_rows if r['progress_pct'] <= max_progress]
    if q:
        ql = q.lower()
        def match(r):
            return (
                ql in (r['user_name'] or '').lower() or
                ql in (r['user_email'] or '').lower() or
                ql in (r['agency_name'] or '').lower() or
                ql in (r['course_name'] or '').lower() or
                ql in (r['course_code'] or '').lower()
            )
        course_progress_rows = [r for r in course_progress_rows if match(r)]

    # Sort by progress desc, then user name
    course_progress_rows.sort(key=lambda r: (-r['progress_pct'], (r['user_name'] or '').lower()))

    filters = {
        'q': q,
        'agency_id': agency_id,
        'course_id': course_id,
        'status': status,
        'min_progress': min_progress,
        'max_progress': max_progress,
    }
    return render_template('monitor_progress.html', course_progress_rows=course_progress_rows, agencies=agencies, courses=courses, filters=filters)

# Quick action referenced by admin dashboard (noop-safe)
@app.route('/recalculate_ratings')
@login_required
def recalculate_ratings():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        # Ratings columns were removed; keep endpoint for UX and show a friendly message
        flash('Recalculated ratings.', 'success')
    except Exception:
        logging.exception('[ADMIN] Recalculate ratings failed')
        flash('Failed to recalculate ratings.', 'danger')
    return redirect(url_for('admin_dashboard'))

MALAYSIAN_STATES = [
    'Johor', 'Kedah', 'Kelantan', 'Melaka', 'Negeri Sembilan', 'Pahang', 'Perak', 'Perlis',
    'Penang', 'Sabah', 'Sarawak', 'Selangor', 'Terengganu', 'Kuala Lumpur', 'Labuan', 'Putrajaya'
]

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # Get form data
        user_category = request.form.get('user_category', 'citizen')
        email = (request.form.get('email') or '').strip().lower()

        # Get agency_id from form or use default if not provided
        try:
            agency_id = int(request.form.get('agency_id', 1))
        except (ValueError, TypeError):
            agency_id = 1

        # Validate agency existence
        agency = Agency.query.get(agency_id)
        if not agency:
            # Create default agency if it doesn't exist
            try:
                agency = Agency(
                    agency_id=agency_id,
                    agency_name=f"Default Agency {agency_id}",
                    contact_number="0000000000",
                    address="",
                    Reg_of_Company="",
                    PIC="",
                    email=""
                )
                db.session.add(agency)
                db.session.commit()
                print(f"[SIGNUP] Created default agency with ID {agency_id}")
            except IntegrityError:
                db.session.rollback()
                # Another process might have created it; try to fetch again
                agency = Agency.query.get(agency_id)
                if not agency:
                    flash('Invalid agency selected. Please try again.')
                    return render_template('signup.html', agencies=Agency.query.all())

        # If an existing unf inalized user has this email, hard-delete them and dependents to free the email
        try:
            to_purge = User.query.filter(db.func.lower(db.func.trim(User.email)) == email, User.is_finalized.is_(False)).all()
            for existing_user in to_purge:
                WorkHistory.query.filter_by(user_id=existing_user.User_id).delete(synchronize_session=False)
                UserModule.query.filter_by(user_id=existing_user.User_id).delete(synchronize_session=False)
                UserCourseProgress.query.filter_by(user_id=existing_user.User_id).delete(synchronize_session=False)
                Certificate.query.filter_by(user_id=existing_user.User_id).delete(synchronize_session=False)
                db.session.delete(existing_user)
            if to_purge:
                db.session.commit()
        except Exception:
            db.session.rollback()

        user_data = {
            'full_name': request.form['full_name'],
            'email': email,
            'password': request.form['password'],
            'user_category': user_category,
            'agency_id': agency_id
        }

        # Optionally add IC or Passport number and country (collect fully during onboarding)
        if user_category == 'citizen':
            ic_number = request.form.get('ic_number')
            if ic_number:
                user_data['ic_number'] = ic_number
        else:
            passport_number = request.form.get('passport_number')
            if passport_number:
                user_data['passport_number'] = passport_number
            country = (request.form.get('country') or '').strip()
            if country:
                user_data['country'] = country

        # Check if user already exists and is finalized (only finalized users should block signup)
        existing_finalized = User.query.filter(db.func.lower(db.func.trim(User.email)) == email, User.is_finalized.is_(True)).first()
        if existing_finalized:
            flash('Email already registered')
            return render_template('signup.html', agencies=Agency.query.all())

        # Register user
        try:
            user = Registration.registerUser(user_data)
            # Mark as pending until onboarding is completed or skipped at the last step
            login_user(user)
            session['user_type'] = 'user'
            session['user_id'] = user.get_id()
            session['pending_signup'] = True
            session['sign_up_finalized'] = False
            return redirect(url_for('onboarding', step=1))
        except ValueError as e:
            # Handle duplicate email and other validation errors with user-friendly messages
            flash(str(e), 'error')
            return render_template('signup.html', agencies=Agency.query.all())
        except Exception as e:
            # Handle other unexpected errors
            flash(f'An unexpected error occurred during registration: {str(e)}', 'error')
            return render_template('signup.html', agencies=Agency.query.all())

    agencies = Agency.query.all()
    return render_template('signup.html', agencies=agencies)

@app.route('/cancel_onboarding')
@login_required
def cancel_onboarding():
    """Cancel onboarding: if current user is not finalized, delete user and related rows; then logout and go to signup."""
    try:
        if isinstance(current_user, User):
            u = db.session.get(User, current_user.User_id)
            if u and not getattr(u, 'is_finalized', False):
                WorkHistory.query.filter_by(user_id=u.User_id).delete(synchronize_session=False)
                UserModule.query.filter_by(user_id=u.User_id).delete(synchronize_session=False)
                UserCourseProgress.query.filter_by(user_id=u.User_id).delete(synchronize_session=False)
                Certificate.query.filter_by(user_id=u.User_id).delete(synchronize_session=False)
                db.session.delete(u)
                db.session.commit()
    except Exception:
        db.session.rollback()
        # Fall through to logout and redirect
    # Always logout and clear session before leaving onboarding
    try:
        logout_user()
    except Exception:
        pass
    session.clear()
    return redirect(url_for('signup'))

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

    # Determine dynamic steps based on user category (trim + lower)
    user_cat = normalized_user_category(current_user)
    total_steps = 5 if user_cat == 'foreigner' else 4

    # Current step from query or form
    try:
        step = int(request.values.get('step', 1))
    except Exception:
        step = 1
    step = max(1, min(step, total_steps))

    if request.method == 'POST':
        # Determine last step now so we can handle Skip correctly
        last_step = 5 if user_cat == 'foreigner' else 4
        if 'skip' in request.form:
            # Finalize only if skipping at the last step; otherwise just go to dashboard without finalizing
            if step == last_step:
                try:
                    current_user.is_finalized = True
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                session['sign_up_finalized'] = True
                session['pending_signup'] = False
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
                # Profile picture upload (optional)
                if 'profile_pic' in request.files:
                    f = request.files['profile_pic']
                    if f and getattr(f, 'filename', ''):
                        import time
                        filename_raw = secure_filename(f.filename)
                        _, ext = os.path.splitext(filename_raw)
                        ext = (ext or '').lower()
                        allowed_ext = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
                        if ext in allowed_ext:
                            save_dir = app.config.get('UPLOAD_FOLDER', os.path.join('static', 'profile_pics'))
                            os.makedirs(save_dir, exist_ok=True)
                            unique_name = f"u{current_user.User_id}_{int(time.time())}{ext}"
                            save_path = os.path.join(save_dir, unique_name)
                            f.save(save_path)
                            current_user.Profile_picture = unique_name
                        elif ext:
                            flash('Unsupported image type. Please upload PNG, JPG, JPEG, GIF, or WEBP.')
            elif step == 2:
                # Contact details
                current_user.emergency_contact_phone = request.form.get('phone') or request.form.get('emergency_contact_phone')
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
                    exp_visas = request.form.getlist('exp_visa_number')
                    exp_visa_exps = request.form.getlist('exp_visa_expiry')
                    exp_recs = request.form.getlist('exp_recruitment')
                    # Remove existing entries for this user
                    WorkHistory.query.filter_by(user_id=current_user.User_id).delete(synchronize_session=False)
                    # Add new ones
                    for i in range(max(len(companies), len(positions), len(starts), len(ends), len(exp_visas), len(exp_visa_exps), len(exp_recs))):
                        company = (companies[i].strip() if i < len(companies) and companies[i] else '')
                        position = (positions[i].strip() if i < len(positions) and positions[i] else None)
                        start_s = (starts[i].strip() if i < len(starts) and starts[i] else '')
                        end_s = (ends[i].strip() if i < len(ends) and ends[i] else '')
                        visa_no = (exp_visas[i].strip() if i < len(exp_visas) and exp_visas[i] else None)
                        visa_exp_s = (exp_visa_exps[i].strip() if i < len(exp_visa_exps) and exp_visa_exps[i] else None)
                        rec_s = (exp_recs[i].strip() if i < len(exp_recs) and exp_recs[i] else '')
                        # Skip completely empty row
                        if not company and not start_s and not end_s and not rec_s:
                            continue
                        # Require at minimum a company and a start-like date (start or recruitment)
                        if not company:
                            continue
                        # Parse dates with fallbacks
                        start_d = None
                        end_d = None
                        rec_d = None
                        if rec_s:
                            try:
                                rec_d = datetime.strptime(rec_s, '%Y-%m-%d').date()
                            except Exception:
                                rec_d = None
                        if start_s:
                            try:
                                start_d = datetime.strptime(start_s, '%Y-%m-%d').date()
                            except Exception:
                                start_d = None
                        # Fallback: if start missing, use recruitment as start
                        if start_d is None and rec_d is not None:
                            start_d = rec_d
                        # If still missing start, skip (model requires start_date)
                        if start_d is None:
                            continue
                        if end_s:
                            try:
                                end_d = datetime.strptime(end_s, '%Y-%m-%d').date()
                            except Exception:
                                end_d = None
                        # Default end to start if missing/invalid to satisfy NOT NULL
                        if end_d is None:
                            end_d = start_d
                        # Ignore if end before start
                        if end_d < start_d:
                            continue
                        visa_exp_d = None
                        if visa_exp_s:
                            try:
                                visa_exp_d = datetime.strptime(visa_exp_s, '%Y-%m-%d').date()
                            except Exception:
                                visa_exp_d = None
                        wh = WorkHistory(
                            user_id=current_user.User_id,
                            company_name=company,
                            position_title=position,
                            start_date=start_d,
                            end_date=end_d,
                            recruitment_date=rec_d or start_d,
                            visa_number=visa_no,
                            visa_expiry_date=visa_exp_d
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
                current_user.emergency_contact_relationship = request.form.get('emergency_contact_relationship')
                current_user.emergency_contact_name = request.form.get('emergency_contact_name')
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash('Could not save your progress. Please try again.')
            return render_template('onboarding.html', step=step, total_steps=total_steps, user=current_user, malaysian_states=MALAYSIAN_STATES)

        # Advance to next step or finish
        next_step = step + 1
        if next_step > total_steps:
            # Finalize signup upon completion
            try:
                current_user.is_finalized = True
                db.session.commit()
            except Exception:
                db.session.rollback()
            session['sign_up_finalized'] = True
            session['pending_signup'] = False
            return redirect(url_for('user_dashboard'))
        return redirect(url_for('onboarding', step=next_step))

    return render_template('onboarding.html', step=step, total_steps=total_steps, user=current_user, malaysian_states=MALAYSIAN_STATES)

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
        user_cat = normalized_user_category(current_user)
        preferred_code = 'TNG' if user_cat == 'foreigner' else 'CSG'
        main_course = Course.query.filter(Course.code.ilike(preferred_code)).first()

        # Build list of visible courses: always include 'both' courses in addition to main (if any)
        courses = []
        if main_course:
            courses.append(main_course)
        # Add all courses allowed for both categories (case-insensitive)
        both_courses = Course.query.filter(db.func.lower(db.func.trim(Course.allowed_category)) == 'both').all()
        for c in both_courses:
            if not any(getattr(x, 'course_id', None) == getattr(c, 'course_id', None) for x in courses):
                courses.append(c)
        # If no main course exists, also include courses explicitly allowed for the user's category (case-insensitive)
        if not main_course:
            extra_allowed = Course.query.filter(db.func.lower(db.func.trim(Course.allowed_category)) == user_cat).all()
            for c in extra_allowed:
                if not any(getattr(x, 'course_id', None) == getattr(c, 'course_id', None) for x in courses):
                    courses.append(c)

        # Compute per-course progress
        courses_progress = []
        total_user_modules = []
        # Added: course-level stats
        course_enrolled_count = 0
        course_completed_count = 0
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
            # Added: derive course-level enrolled/completed
            enrolled = (len(user_um) > 0)
            ucp = UserCourseProgress.query.filter_by(user_id=current_user.User_id, course_id=course.course_id).first()
            if ucp:
                enrolled = True
                completed_course = bool(ucp.completed)
            else:
                completed_course = (total > 0 and completed == total)
            if enrolled:
                course_enrolled_count += 1
            if completed_course:
                course_completed_count += 1
            courses_progress.append({
                'code': course.code,
                'name': course.name,
                'progress': progress_pct,
                'completed_modules': completed,
                'total_modules': total,
                'enrolled': enrolled,
                'completed': completed_course
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
        # user_modules for dashboard stats: show enrolled modules for all visible courses
        user_modules = total_user_modules
    except Exception:
        logging.exception('[USER DASHBOARD] Failed to build dashboard context')
        courses_progress = []
        user_modules = []
        rating_unlocked = False
        preferred_code = 'CSG'
        # Added: default course stats on error
        course_enrolled_count = 0
        course_completed_count = 0

    return render_template(
        'user_dashboard.html',
        user=current_user,
        user_modules=user_modules,
        rating_unlocked=rating_unlocked,
        courses_progress=courses_progress,
        grade_course_code=preferred_code,
        # Added: pass course-level stats
        course_enrolled_count=course_enrolled_count,
        course_completed_count=course_completed_count
    )

@app.route('/enroll', methods=['GET'])
@login_required
def enroll_course():
    # Enroll user into modules for their primary course (TNG for foreigner, CSG for citizen)
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    user_cat = normalized_user_category(current_user)
    preferred_code = 'TNG' if user_cat == 'foreigner' else 'CSG'
    course = Course.query.filter(Course.code.ilike(preferred_code)).first()
    if course is None:
        # Fallback: take first course allowed for the category (case-insensitive)
        course = Course.query.filter(
            (db.func.lower(db.func.trim(Course.allowed_category)) == user_cat) |
            (db.func.lower(db.func.trim(Course.allowed_category)) == 'both')
        ).first()
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
            # New: country field
            current_user.country = request.form.get('country') or current_user.country
            # Deprecated single working_experience field retained for compat
            current_user.working_experience = request.form.get('working_experience') or current_user.working_experience
            # Dates and numbers (user-level)
            rec = request.form.get('recruitment_date')
            if rec:
                try:
                    current_user.recruitment_date = datetime.strptime(rec, '%Y-%m-%d').date()
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
            current_user.emergency_contact_phone = request.form.get('emergency_contact_phone') or current_user.emergency_contact_phone
            current_user.emergency_contact_name = request.form.get('emergency_contact_name') or current_user.emergency_contact_name
            current_user.emergency_contact_relationship = request.form.get('emergency_contact_relationship') or current_user.emergency_contact_relationship

            # Handle profile picture upload
            if 'profile_pic' in request.files:
                f = request.files['profile_pic']
                if f and f.filename:
                    filename = secure_filename(f.filename)
                    save_dir = app.config.get('UPLOAD_FOLDER', os.path.join('static', 'profile_pics'))
                    os.makedirs(save_dir, exist_ok=True)
                    f.save(os.path.join(save_dir, filename))
                    current_user.Profile_picture = filename

            # Handle multiple working experiences from modal (optional)
            try:
                companies = request.form.getlist('exp_company')
                positions = request.form.getlist('exp_position')
                starts = request.form.getlist('exp_start')
                ends = request.form.getlist('exp_end')
                visas = request.form.getlist('exp_visa_number')
                visa_exps = request.form.getlist('exp_visa_expiry')
                recs = request.form.getlist('exp_recruitment')
                any_exp_fields = any([companies, positions, starts, ends, visas, visa_exps, recs]) and (
                    (len(companies) + len(positions) + len(starts) + len(ends) + len(visas) + len(visa_exps) + len(recs)) > 0
                )
                if any_exp_fields:
                    # Replace existing experiences for this user
                    WorkHistory.query.filter_by(user_id=current_user.User_id).delete(synchronize_session=False)
                    for i in range(max(len(companies), len(positions), len(starts), len(ends), len(visas), len(visa_exps), len(recs))):
                        company = (companies[i].strip() if i < len(companies) and companies[i] else '')
                        position = (positions[i].strip() if i < len(positions) and positions[i] else None)
                        start_s = (starts[i].strip() if i < len(starts) and starts[i] else '')
                        end_s = (ends[i].strip() if i < len(ends) and ends[i] else '')
                        visa_no = (visas[i].strip() if i < len(visas) and visas[i] else None)
                        visa_exp_s = (visa_exps[i].strip() if i < len(visa_exps) and visa_exps[i] else None)
                        rec_s = (recs[i].strip() if i < len(recs) and recs[i] else '')
                        # Skip empty rows
                        if not company and not start_s and not end_s and not rec_s:
                            continue
                        # Require company and at least a start-like date
                        if not company:
                            continue
                        # Parse
                        rec_d = None
                        start_d = None
                        end_d = None
                        if rec_s:
                            try:
                                rec_d = datetime.strptime(rec_s, '%Y-%m-%d').date()
                            except Exception:
                                rec_d = None
                        if start_s:
                            try:
                                start_d = datetime.strptime(start_s, '%Y-%m-%d').date()
                            except Exception:
                                start_d = None
                        if start_d is None and rec_d is not None:
                            start_d = rec_d
                        if start_d is None:
                            continue
                        if end_s:
                            try:
                                end_d = datetime.strptime(end_s, '%Y-%m-%d').date()
                            except Exception:
                                end_d = None
                        if end_d is None:
                            end_d = start_d
                        if end_d < start_d:
                            continue
                        visa_exp_d = None
                        if visa_exp_s:
                            try:
                                visa_exp_d = datetime.strptime(visa_exp_s, '%Y-%m-%d').date()
                            except Exception:
                                visa_exp_d = None
                        wh = WorkHistory(
                            user_id=current_user.User_id,
                            company_name=company,
                            position_title=position,
                            start_date=start_d,
                            end_date=end_d,
                            recruitment_date=rec_d or start_d,
                            visa_number=visa_no,
                            visa_expiry_date=visa_exp_d
                        )
                        db.session.add(wh)
            except Exception:
                # Do not block profile update if experience parsing fails
                pass
            db.session.commit()
            flash('Profile updated successfully.')
        except Exception:
            db.session.rollback()
            logging.exception('[PROFILE] Update failed')
            flash('Could not update profile. Please try again.')
        return redirect(url_for('profile'))
    # GET
    # Fetch experiences sorted by start_date (recruitment date) desc
    try:
        experiences = WorkHistory.query.filter_by(user_id=current_user.User_id).order_by(db.func.coalesce(WorkHistory.recruitment_date, WorkHistory.start_date).desc()).all()
    except Exception:
        experiences = []
    return render_template('profile.html', user=current_user, malaysian_states=MALAYSIAN_STATES, experiences=experiences)

@app.route('/courses')
@login_required
def courses():
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    user_cat = normalized_user_category(current_user)
    preferred_code = 'TNG' if user_cat == 'foreigner' else 'CSG'
    # Prefer the primary course for the user by code; also include any courses allowed for both
    main_course = Course.query.filter(Course.code.ilike(preferred_code)).first()

    courses = []
    if main_course:
        courses.append(main_course)
    # Add courses with allowed_category='both' (case-insensitive)
    both_courses = Course.query.filter(db.func.lower(db.func.trim(Course.allowed_category)) == 'both').all()
    for c in both_courses:
        if not any(getattr(x, 'course_id', None) == getattr(c, 'course_id', None) for x in courses):
            courses.append(c)
    # If no main course exists, include courses explicitly allowed for the user's category (case-insensitive)
    if not main_course:
        extra_allowed = Course.query.filter(db.func.lower(db.func.trim(Course.allowed_category)) == user_cat).all()
        for c in extra_allowed:
            if not any(getattr(x, 'course_id', None) == getattr(c, 'course_id', None) for x in courses):
                courses.append(c)

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
    # Show only the current user's agency for regular users/agency accounts; admins see all
    try:
        if isinstance(current_user, Admin):
            ags = Agency.query.order_by(Agency.agency_name.asc()).all()
        elif isinstance(current_user, AgencyAccount):
            ag = db.session.get(Agency, getattr(current_user, 'agency_id', None))
            ags = [ag] if ag else []
        elif isinstance(current_user, User):
            ag = db.session.get(Agency, getattr(current_user, 'agency_id', None))
            ags = [ag] if ag else []
        else:
            ags = []
    except Exception:
        logging.exception('[AGENCY] Failed to load agency list')
        ags = []
    return render_template('agency.html', agencies=ags)

# --- Agency portal routes ---
@app.route('/agency_portal')
@login_required
def agency_portal():
    # Only agency accounts can access
    if not isinstance(current_user, AgencyAccount):
        return redirect(url_for('login'))
    ag = db.session.get(Agency, current_user.agency_id)
    if not ag:
        flash('Agency not found for this account.')
        return render_template('agency_portal.html', agency=None, users=[], module_counts={})
    try:
        users = User.query.filter_by(agency_id=ag.agency_id).order_by(User.full_name.asc()).all()
    except Exception:
        logging.exception('[AGENCY PORTAL] Failed to load users list')
        users = []
    # Aggregate module completion count and average score per user
    module_counts = {}
    try:
        if users:
            user_ids = [u.User_id for u in users]
            rows = (
                db.session.query(
                    UserModule.user_id,
                    db.func.count(UserModule.id).label('completed'),
                    db.func.avg(UserModule.score).label('avg_score')
                )
                .filter(
                    UserModule.user_id.in_(user_ids),
                    UserModule.is_completed.is_(True)
                )
                .group_by(UserModule.user_id)
                .all()
            )
            stats_map = {uid: {'completed': int(comp or 0), 'avg_score': float(avg or 0.0)} for uid, comp, avg in rows}
            for u in users:
                module_counts[u.User_id] = stats_map.get(u.User_id, {'completed': 0, 'avg_score': 0.0})
    except Exception:
        logging.exception('[AGENCY PORTAL] Failed to compute module stats')
        module_counts = {u.User_id: {'completed': 0, 'avg_score': 0.0} for u in users}
    return render_template('agency_portal.html', agency=ag, users=users, module_counts=module_counts)

@app.route('/agency/create_user', methods=['POST'])
@login_required
def agency_create_user():
    # Only agency accounts can create users
    if not isinstance(current_user, AgencyAccount):
        return redirect(url_for('login'))
    ag = db.session.get(Agency, current_user.agency_id)
    if not ag:
        flash('Agency not found.')
        return redirect(url_for('agency_portal'))
    full_name = (request.form.get('full_name') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    password = request.form.get('password') or ''
    user_category = (request.form.get('user_category') or 'citizen').strip().lower()
    if not full_name or not email or not password:
        flash('All fields are required.')
        return redirect(url_for('agency_portal'))
    if user_category not in ('citizen', 'foreigner'):
        user_category = 'citizen'
    # Prevent duplicate emails across users
    if User.query.filter_by(email=email).first():
        flash('Email already registered.')
        return redirect(url_for('agency_portal'))
    u = User(full_name=full_name, email=email, user_category=user_category, agency_id=ag.agency_id)
    u.set_password(password)
    try:
        db.session.add(u)
        db.session.commit()
        flash('User created successfully.')
    except Exception:
        db.session.rollback()
        logging.exception('[AGENCY PORTAL] Create user failed')
        flash('Could not create user. Please try again later.')
    return redirect(url_for('agency_portal'))

@app.route('/admin/agency/<int:agency_id>/create_account', methods=['POST'])
@login_required
def admin_create_agency_account(agency_id: int):
    # Only admin can create agency accounts
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    ag = db.session.get(Agency, agency_id)
    if not ag:
        flash('Agency not found.', 'warning')
        return redirect(url_for('admin_agencies'))
    if not ag.email:
        flash('Agency email is required to create a login.', 'warning')
        return redirect(url_for('admin_agencies'))
    # Ensure uniqueness of email
    if AgencyAccount.query.filter_by(email=ag.email).first():
        flash('An account with this email already exists.', 'info')
        return redirect(url_for('admin_agencies'))
    acct = AgencyAccount(agency_id=ag.agency_id, email=ag.email)
    acct.set_password('Agency#' + str(ag.agency_id))
    db.session.add(acct)
    db.session.commit()
    flash('Agency login created. Temporary password set.', 'success')
    return redirect(url_for('admin_agencies'))

@app.route('/admin_course_management')
@login_required
def admin_course_management():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        courses = Course.query.order_by(Course.code.asc()).all()
        course_modules = {}
        for c in courses:
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
    q = (request.args.get('q') or '').strip()
    role = (request.args.get('role') or 'all').strip().lower()  # all|user|trainer|admin
    status = (request.args.get('status') or 'all').strip().lower()  # for trainers
    try:
        agency_id = int(request.args.get('agency_id')) if request.args.get('agency_id') else None
    except Exception:
        agency_id = None

    users = []; trainers = []; admins = []
    try:
        if role in ('all', 'user'):
            uq = User.query
            if agency_id:
                uq = uq.filter(User.agency_id == agency_id)
            if q:
                like = f"%{q}%"; from sqlalchemy import or_
                uq = uq.filter(or_(User.full_name.ilike(like), User.email.ilike(like), db.func.coalesce(User.number_series, '').ilike(like)))
            users = uq.order_by(User.full_name.asc()).all()
    except Exception:
        logging.exception('[ADMIN USERS] Users load failed')
        users = []
    try:
        if role in ('all', 'trainer'):
            tq = Trainer.query
            if status in ('active', 'inactive'):
                want = (status == 'active')
                tq = tq.filter(Trainer.active_status.is_(want))
            if q:
                like = f"%{q}%"; from sqlalchemy import or_
                tq = tq.filter(or_(Trainer.name.ilike(like), Trainer.email.ilike(like), db.func.coalesce(Trainer.number_series, '').ilike(like), db.func.coalesce(Trainer.contact_number, '').ilike(like), db.func.coalesce(Trainer.course, '').ilike(like)))
            trainers = tq.order_by(Trainer.name.asc()).all()
    except Exception:
        logging.exception('[ADMIN USERS] Trainers load failed')
        trainers = []
    try:
        if role in ('all', 'admin'):
            aq = Admin.query
            if q:
                like = f"%{q}%"; from sqlalchemy import or_
                aq = aq.filter(or_(Admin.username.ilike(like), Admin.email.ilike(like)))
            admins = aq.order_by(Admin.username.asc()).all()
    except Exception:
        logging.exception('[ADMIN USERS] Admins load failed')
        admins = []

    merged_accounts = []
    for u in users:
        merged_accounts.append({'type': 'user','id': u.User_id,'number_series': u.number_series,'name': u.full_name,'email': u.email,'agency': getattr(u.agency, 'agency_name', None),'recruitment_date': u.recruitment_date,'active_status': True,'contact_number': None,'course': None})
    for t in trainers:
        merged_accounts.append({'type': 'trainer','id': t.trainer_id,'number_series': t.number_series,'name': t.name,'email': t.email,'agency': None,'recruitment_date': None,'active_status': t.active_status,'contact_number': t.contact_number,'course': t.course,'availability': getattr(t, 'availability', None)})
    for a in admins:
        merged_accounts.append({'type': 'admin','id': a.admin_id,'number_series': None,'name': a.username,'email': a.email,'agency': None,'recruitment_date': None,'active_status': True,'contact_number': None,'course': None,'availability': None})
    merged_accounts.sort(key=lambda x: (x['name'] or '').lower())

    try:
        agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
    except Exception:
        agencies = []

    filters = {'q': q, 'role': role, 'status': status, 'agency_id': agency_id}
    return render_template('admin_users.html', merged_accounts=merged_accounts, agencies=agencies, filters=filters)

@app.route('/admin_certificates')
@login_required
def admin_certificates():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        certs = Certificate.query.order_by(Certificate.issue_date.desc()).all()
    except Exception:
        logging.exception('[ADMIN CERTIFICATES] Load failed')
        certs = []
    try:
        template_path = os.path.join(app.root_path, 'static', 'cert_templates', 'Training_cert.pdf')
        cert_template_url = url_for('static', filename='cert_templates/Training_cert.pdf') if os.path.exists(template_path) else None
    except Exception:
        cert_template_url = None
    return render_template('admin_certificates.html', certificates=certs, cert_template_url=cert_template_url)

@app.route('/admin/certificates/upload_template', methods=['POST'])
@login_required
def upload_cert_template():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        f = request.files.get('cert_template')
        if not f or not getattr(f, 'filename', ''):
            flash('No file selected.', 'warning')
            return redirect(url_for('admin_certificates'))
        target_dir = os.path.join(app.root_path, 'static', 'cert_templates')
        os.makedirs(target_dir, exist_ok=True)
        filename = 'Training_cert.pdf' if f.filename.lower().endswith('.pdf') else secure_filename(f.filename)
        f.save(os.path.join(target_dir, filename))
        flash('Certificate template uploaded.', 'success')
    except Exception:
        logging.exception('[ADMIN CERTIFICATES] Upload failed')
        flash('Failed to upload template.', 'danger')
    return redirect(url_for('admin_certificates'))

@app.route('/admin/certificates/delete_bulk', methods=['POST'])
@login_required
def delete_certificates_bulk():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        ids = request.form.getlist('cert_ids')
        ids_int = [int(x) for x in ids if str(x).strip().isdigit()]
        if ids_int:
            Certificate.query.filter(Certificate.certificate_id.in_(ids_int)).delete(synchronize_session=False)
            db.session.commit()
            flash(f'Deleted {len(ids_int)} certificate(s).', 'success')
        else:
            flash('No certificates selected.', 'info')
    except Exception:
        db.session.rollback()
        logging.exception('[ADMIN CERTIFICATES] Bulk delete failed')
        flash('Failed to delete selected certificates.', 'danger')
    return redirect(url_for('admin_certificates'))

@app.route('/admin_agencies')
@login_required
def admin_agencies():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        ags = Agency.query.order_by(Agency.agency_name.asc()).all()
    except Exception:
        logging.exception('[ADMIN AGENCIES] Load failed')
        ags = []
    return render_template('admin_agencies.html', agencies=ags)

@app.route('/admin/agency/add', methods=['POST'])
@login_required
def add_agency():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        a = Agency(
            agency_name=(request.form.get('agency_name') or '').strip(),
            PIC=(request.form.get('PIC') or '').strip(),
            contact_number=(request.form.get('contact_number') or '').strip(),
            email=(request.form.get('email') or '').strip(),
            address=(request.form.get('address') or '').strip(),
            Reg_of_Company=(request.form.get('Reg_of_Company') or '').strip(),
        )
        if not a.agency_name:
            flash('Agency name is required.', 'warning')
            return redirect(url_for('admin_agencies'))
        db.session.add(a)
        db.session.commit()
        flash('Agency added.', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[ADMIN AGENCIES] Add failed')
        flash('Failed to add agency.', 'danger')
    return redirect(url_for('admin_agencies'))

@app.route('/admin/agency/<int:agency_id>/edit', methods=['POST'])
@login_required
def edit_agency(agency_id: int):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    try:
        ag = db.session.get(Agency, agency_id)
        if not ag:
            flash('Agency not found.', 'warning')
            return redirect(url_for('admin_agencies'))
        ag.agency_name = (request.form.get('agency_name') or ag.agency_name).strip()
        ag.PIC = (request.form.get('PIC') or ag.PIC).strip()
        ag.contact_number = (request.form.get('contact_number') or ag.contact_number).strip()
        ag.email = (request.form.get('email') or ag.email).strip()
        ag.address = (request.form.get('address') or ag.address).strip()
        ag.Reg_of_Company = (request.form.get('Reg_of_Company') or ag.Reg_of_Company).strip()
        db.session.commit()
        flash('Agency updated.', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[ADMIN AGENCIES] Edit failed')
        flash('Failed to update agency.', 'danger')
    return redirect(url_for('admin_agencies'))

@app.route('/modules/<string:course_code>')
@login_required
def course_modules(course_code: str):
    """Show modules for a given course code (e.g., /modules/TNG).
    Renders course_modules.html with modules, user progress, and unlock flags.
    """
    # Only regular users access this page
    if not isinstance(current_user, User):
        return redirect(url_for('login'))

    # Normalize input
    code = (course_code or '').strip()
    if not code:
        flash('Invalid course code.', 'warning')
        return redirect(url_for('courses'))

    # Find course by code (case-insensitive)
    course = Course.query.filter(Course.code.ilike(code)).first()
    if not course:
        flash(f'Course {code} not found.', 'warning')
        return redirect(url_for('courses'))

    # Enforce category access policy
    user_cat = normalized_user_category(current_user)
    allowed = (str(course.allowed_category or '').strip().lower())
    if allowed not in ('citizen', 'foreigner', 'both'):
        allowed = 'both'
    if allowed != 'both' and allowed != user_cat:
        flash('You do not have access to this course.', 'warning')
        return redirect(url_for('courses'))

    # Load and sort modules
    modules = list(getattr(course, 'modules', []) or [])
    modules = _series_sort(modules)

    # Build user progress map for current user (module_id -> UserModule row)
    try:
        module_ids = [m.module_id for m in modules]
        progress_rows = []
        if module_ids:
            progress_rows = (
                UserModule.query
                .filter(UserModule.user_id == current_user.User_id, UserModule.module_id.in_(module_ids))
                .all()
            )
        user_progress = {um.module_id: um for um in progress_rows}
    except Exception:
        logging.exception('[COURSE MODULES] Failed to load user progress')
        user_progress = {}

    # Determine unlock flags: first module unlocked, others unlocked if previous completed
    prev_completed = True
    for idx, m in enumerate(modules):
        unlocked = False
        if idx == 0:
            unlocked = True
        else:
            prev = modules[idx - 1]
            prev_um = user_progress.get(getattr(prev, 'module_id', None))
            unlocked = bool(prev_um and getattr(prev_um, 'is_completed', False))
        # attach transient attribute for template
        try:
            setattr(m, 'unlocked', unlocked)
        except Exception:
            pass

    # Compute overall average score across completed modules for this course
    overall_percentage = None
    try:
        if module_ids:
            avg_score_val = (
                db.session.query(db.func.avg(UserModule.score))
                .filter(
                    UserModule.user_id == current_user.User_id,
                    UserModule.module_id.in_(module_ids),
                    UserModule.is_completed.is_(True)
                )
                .scalar()
            )
            if avg_score_val is not None:
                overall_percentage = int(round(float(avg_score_val or 0.0), 0))
    except Exception:
        overall_percentage = None

    return render_template(
        'course_modules.html',
        course_name=getattr(course, 'name', code),
        modules=modules,
        user_progress=user_progress,
        overall_percentage=overall_percentage
    )


@app.route('/quiz/<int:module_id>')
@login_required
def module_quiz(module_id: int):
    """Open the Quiz Player for the given module."""
    if not isinstance(current_user, User):
        return redirect(url_for('login'))
    module = db.session.get(Module, module_id)
    if not module:
        flash('Module not found.', 'warning')
        return redirect(url_for('courses'))
    course = db.session.get(Course, getattr(module, 'course_id', None)) if getattr(module, 'course_id', None) else None
    user_module = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module.module_id).first()
    return render_template('quiz_take.html', module=module, course=course, user_module=user_module)


# Minimal APIs to support slide disclaimer gating on modules page
@app.route('/api/check_module_disclaimer/<int:module_id>')
@login_required
def api_check_module_disclaimer(module_id: int):
    try:
        if not isinstance(current_user, User):
            return jsonify(success=False, has_agreed=False)
        has = current_user.has_agreed_to_module_disclaimer(module_id)
        return jsonify(success=True, has_agreed=has)
    except Exception as e:
        logging.exception('[API] check_module_disclaimer failed')
        return jsonify(success=False, message=str(e)), 500


@app.route('/api/agree_module_disclaimer/<int:module_id>', methods=['POST'])
@login_required
def api_agree_module_disclaimer(module_id: int):
    try:
        if not isinstance(current_user, User):
            return jsonify(success=False, message='Unauthorized'), 403
        ok = current_user.agree_to_module_disclaimer(module_id)
        return jsonify(success=bool(ok))
    except Exception as e:
        logging.exception('[API] agree_module_disclaimer failed')
        return jsonify(success=False, message=str(e)), 500


@app.route('/api/reattempt_course/<string:course_code>', methods=['POST'])
@login_required
def api_reattempt_course(course_code: str):
    if not isinstance(current_user, User):
        return jsonify(success=False, message='Unauthorized'), 403
    code = (course_code or '').strip()
    if not code:
        return jsonify(success=False, message='Invalid course code'), 400
    course = Course.query.filter(Course.code.ilike(code)).first()
    if not course:
        return jsonify(success=False, message='Course not found'), 404
    try:
        # Get modules for this course
        module_ids = [m.module_id for m in getattr(course, 'modules', [])]
        if module_ids:
            rows = UserModule.query.filter(
                UserModule.user_id == current_user.User_id,
                UserModule.module_id.in_(module_ids)
            ).all()
            for um in rows:
                um.is_completed = False
                um.score = None
                um.quiz_answers = None
                # Do not reset reattempt_count per-module here; leave as is
            db.session.flush()
        # Increment course-level reattempt counter (create row if missing)
        ucp = UserCourseProgress.query.filter_by(user_id=current_user.User_id, course_id=course.course_id).first()
        if not ucp:
            ucp = UserCourseProgress(user_id=current_user.User_id, course_id=course.course_id, completed=False, reattempt_count=1)
            db.session.add(ucp)
        else:
            ucp.reattempt_count = int(ucp.reattempt_count or 0) + 1
            ucp.completed = False
        db.session.commit()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        logging.exception('[API] reattempt_course failed')
        return jsonify(success=False, message=str(e)), 500


@app.route('/api/complete_course', methods=['POST'])
@login_required
def api_complete_course():
    if not isinstance(current_user, User):
        return jsonify(success=False, message='Unauthorized'), 403
    try:
        payload = request.get_json(silent=True) or {}
        code = (payload.get('course_code') or '').strip()
        if not code:
            return jsonify(success=False, message='Missing course_code'), 400
        course = Course.query.filter(Course.code.ilike(code)).first()
        if not course:
            return jsonify(success=False, message='Course not found'), 404
        # Mark as completed (does not issue certificate here; keep minimal)
        ucp = UserCourseProgress.query.filter_by(user_id=current_user.User_id, course_id=course.course_id).first()
        if not ucp:
            ucp = UserCourseProgress(user_id=current_user.User_id, course_id=course.course_id, completed=True)
            db.session.add(ucp)
        else:
            ucp.completed = True
        db.session.commit()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        logging.exception('[API] complete_course failed')
        return jsonify(success=False, message=str(e)), 500

@app.route('/api/load_quiz/<int:module_id>')
@login_required
def api_load_quiz(module_id: int):
    try:
        m = db.session.get(Module, module_id)
        if not m:
            return jsonify([])
        try:
            raw = m.quiz_json or '[]'
            data = json.loads(raw)
            # Handle double-encoded JSON values (string containing JSON)
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    pass
        except Exception:
            data = []
        # Coerce root to a list if it's a dict with common keys or a single question object
        def _coerce_to_list(payload):
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                for k in ('quiz', 'questions', 'items', 'data'):
                    v = payload.get(k)
                    if isinstance(v, list):
                        return v
                # Single-question object: treat as one-item list
                if any(k in payload for k in ('answers', 'options', 'optionA', 'question', 'text')):
                    return [payload]
            return []
        data = _coerce_to_list(data)
        # Normalize to expected shape: list of {text, answers:[{text,isCorrect}]}
        def _norm_answers(ans_val):
            out = []
            # list of dicts/strings
            if isinstance(ans_val, list):
                for opt in ans_val:
                    if isinstance(opt, dict):
                        txt = (str(opt.get('text') or opt.get('label') or opt.get('option') or '')).strip()
                        is_corr = bool(opt.get('isCorrect') or opt.get('correct') or opt.get('is_correct'))
                        if txt:
                            out.append({'text': txt, 'isCorrect': is_corr})
                    elif isinstance(opt, str):
                        txt = opt.strip()
                        if txt:
                            out.append({'text': txt, 'isCorrect': False})
            # dict of key->dict/string
            elif isinstance(ans_val, dict):
                for _, opt in ans_val.items():
                    if isinstance(opt, dict):
                        txt = (str(opt.get('text') or opt.get('label') or opt.get('option') or '')).strip()
                        is_corr = bool(opt.get('isCorrect') or opt.get('correct') or opt.get('is_correct'))
                        if txt:
                            out.append({'text': txt, 'isCorrect': is_corr})
                    elif isinstance(opt, str):
                        txt = opt.strip()
                        if txt:
                            out.append({'text': txt, 'isCorrect': False})
            return out
        def _normalize_item(item):
            if not isinstance(item, dict):
                return None
            text = (str(item.get('text') or item.get('question') or '')).strip()
            answers = []
            # common fields
            if 'answers' in item:
                answers = _norm_answers(item.get('answers'))
            elif 'options' in item:
                answers = _norm_answers(item.get('options'))
            else:
                # Some shapes: optionA/optionB..., choices, etc.
                tmp = []
                for key in ('optionA','optionB','optionC','optionD','optionE'):
                    val = item.get(key)
                    if isinstance(val, str) and val.strip():
                        tmp.append(val.strip())
                if tmp:
                    answers = _norm_answers(tmp)
            # correct index/marker
            correct_index = None
            try:
                if correct_index is None and isinstance(item.get('correctIndex'), (int, float)):
                    ci = int(item.get('correctIndex'))
                    correct_index = ci if ci >= 0 else None
            except Exception:
                pass
            # If answers present as strings and correct_index provided
            if correct_index is not None and isinstance(answers, list) and answers:
                for i in range(len(answers)):
                    answers[i]['isCorrect'] = (i == correct_index)
            # Ensure at least two answers and exactly one correct
            answers = [a for a in answers if isinstance(a, dict) and str(a.get('text') or '').strip()]
            if not answers:
                return None
            # If no correct marked, mark first; if multiple, keep the first as true and others false
            marked = [i for i,a in enumerate(answers) if a.get('isCorrect') is True]
            if not marked:
                answers[0]['isCorrect'] = True
                for i in range(1, len(answers)):
                    answers[i]['isCorrect'] = False
            # Fallback question text if missing
            if not text:
                text = 'Select the correct answer'
            return {'text': text, 'answers': answers}
        normalized = []
        if isinstance(data, list):
            for it in data:
                norm = _normalize_item(it)
                if norm is not None:
                    normalized.append(norm)
        # Limit to a reasonable maximum to avoid flooding UI
        if len(normalized) > 100:
            normalized = normalized[:100]
        return jsonify(normalized)
    except Exception:
        logging.exception('[API] load_quiz failed')
        return jsonify([])


@app.route('/api/submit_quiz/<int:module_id>', methods=['POST'])
@login_required
def api_submit_quiz(module_id: int):
    try:
        if not isinstance(current_user, User):
            return jsonify(success=False, message='Unauthorized'), 403
        m = db.session.get(Module, module_id)
        if not m:
            return jsonify(success=False, message='Module not found'), 404
        try:
            raw = m.quiz_json or '[]'
            quiz_raw = json.loads(raw)
            # Handle double-encoded JSON
            if isinstance(quiz_raw, str):
                try:
                    quiz_raw = json.loads(quiz_raw)
                except Exception:
                    pass
        except Exception:
            quiz_raw = []
        # Coerce root to a list when dict with common keys or a single-question dict
        def _coerce_to_list(payload):
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                for k in ('quiz', 'questions', 'items', 'data'):
                    v = payload.get(k)
                    if isinstance(v, list):
                        return v
                if any(k in payload for k in ('answers', 'options', 'optionA', 'question', 'text')):
                    return [payload]
            return []
        quiz_raw = _coerce_to_list(quiz_raw)
        # Normalize quiz to expected shape for grading
        def _norm_answers(ans_val):
            out = []
            if isinstance(ans_val, list):
                for opt in ans_val:
                    if isinstance(opt, dict):
                        txt = (str(opt.get('text') or opt.get('label') or opt.get('option') or '')).strip()
                        is_corr = bool(opt.get('isCorrect') or opt.get('correct') or opt.get('is_correct'))
                        if txt:
                            out.append({'text': txt, 'isCorrect': is_corr})
                    elif isinstance(opt, str):
                        txt = opt.strip()
                        if txt:
                            out.append({'text': txt, 'isCorrect': False})
            elif isinstance(ans_val, dict):
                for _, opt in ans_val.items():
                    if isinstance(opt, dict):
                        txt = (str(opt.get('text') or opt.get('label') or opt.get('option') or '')).strip()
                        is_corr = bool(opt.get('isCorrect') or opt.get('correct') or opt.get('is_correct'))
                        if txt:
                            out.append({'text': txt, 'isCorrect': is_corr})
                    elif isinstance(opt, str):
                        txt = opt.strip()
                        if txt:
                            out.append({'text': txt, 'isCorrect': False})
            return out
        def _normalize_item(item):
            if not isinstance(item, dict):
                return None
            text = (str(item.get('text') or item.get('question') or '')).strip()
            answers = []
            if 'answers' in item:
                answers = _norm_answers(item.get('answers'))
            elif 'options' in item:
                answers = _norm_answers(item.get('options'))
            else:
                tmp = []
                for key in ('optionA','optionB','optionC','optionD','optionE'):
                    val = item.get(key)
                    if isinstance(val, str) and val.strip():
                        tmp.append(val.strip())
                if tmp:
                    answers = _norm_answers(tmp)
            # Set correct by index if provided
            correct_index = None
            try:
                if isinstance(item.get('correctIndex'), (int, float)):
                    ci = int(item.get('correctIndex'))
                    correct_index = ci if ci >= 0 else None
            except Exception:
                correct_index = None
            if correct_index is not None and answers:
                for i in range(len(answers)):
                    answers[i]['isCorrect'] = (i == correct_index)
            # Clean answers
            answers = [a for a in answers if isinstance(a, dict) and str(a.get('text') or '').strip()]
            if not answers:
                return None
            # Ensure single correct
            marked = [i for i,a in enumerate(answers) if a.get('isCorrect') is True]
            first = marked[0] if marked else 0
            for i in range(len(answers)):
                answers[i]['isCorrect'] = (i == first)
            if not text:
                text = 'Select the correct answer'
            return {'text': text, 'answers': answers}
        quiz = []
        if isinstance(quiz_raw, list):
            for it in quiz_raw:
                norm = _normalize_item(it)
                if norm is not None:
                    quiz.append(norm)
        if not isinstance(quiz, list) or not quiz:
            return jsonify(success=False, message='No quiz available for this module'), 400
        payload = request.get_json(silent=True) or {}
        answers = payload.get('answers')
        is_reattempt = bool(payload.get('is_reattempt'))
        if not isinstance(answers, list):
            return jsonify(success=False, message='Invalid answers'), 400
        # Grade
        total = len(quiz)
        correct = 0
        for idx, q in enumerate(quiz):
            try:
                chosen = answers[idx] if idx < len(answers) else None
                opts = q.get('answers') if isinstance(q, dict) else None
                if not isinstance(opts, list):
                    continue
                correct_idx = None
                for ai, opt in enumerate(opts):
                    if isinstance(opt, dict) and opt.get('isCorrect') is True:
                        correct_idx = ai
                        break
                if correct_idx is not None and isinstance(chosen, int) and chosen == correct_idx:
                    correct += 1
            except Exception:
                continue
        score_pct = int(round((correct / total) * 100.0, 0)) if total else 0

        # Upsert user progress for this module
        um = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module_id).first()
        if not um:
            um = UserModule(user_id=current_user.User_id, module_id=module_id)
            db.session.add(um)
            db.session.flush()
        # Increment reattempt count if flagged
        if is_reattempt:
            try:
                um.reattempt_count = int(um.reattempt_count or 0) + 1
            except Exception:
                um.reattempt_count = 1
        # Save final answers and score
        um.quiz_answers = json.dumps(answers)
        if um.score is None or score_pct > (um.score or 0):
            um.score = float(score_pct)
        um.is_completed = True
        um.completion_date = datetime.now(UTC)
        db.session.commit()
        grade_letter = um.get_grade_letter()
        return jsonify(success=True, score=score_pct, grade_letter=grade_letter, reattempt_count=int(um.reattempt_count or 0))
    except Exception as e:
        db.session.rollback()
        logging.exception('[API] submit_quiz failed')
        return jsonify(success=False, message=str(e)), 500

@app.route('/upload_content', methods=['GET', 'POST'])
@login_required
def upload_content():
    # Limit to trainers/admins to manage content
    if not (isinstance(current_user, Trainer) or isinstance(current_user, Admin)):
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Parse basics
        try:
            module_id = int(request.form.get('module_id') or 0)
        except Exception:
            module_id = 0
        content_type = (request.form.get('content_type') or '').strip().lower()
        m = db.session.get(Module, module_id) if module_id else None
        if not m:
            flash('Invalid module selection.', 'warning')
            return redirect(url_for('upload_content'))
        try:
            if content_type == 'slide':
                f = request.files.get('slide_file')
                if not f or not getattr(f, 'filename', ''):
                    flash('Please choose a PDF or PPTX file.', 'warning')
                    return redirect(url_for('upload_content'))
                filename = secure_filename(f.filename)
                name, ext = os.path.splitext(filename)
                ext = (ext or '').lower()
                if ext not in ('.pdf', '.pptx', '.ppt'):
                    flash('Unsupported slide type. Please upload PDF or PPTX.', 'warning')
                    return redirect(url_for('upload_content'))
                # Save to static/uploads with a unique filename
                target_dir = os.path.join(app.root_path, 'static', 'uploads')
                os.makedirs(target_dir, exist_ok=True)
                unique = filename
                i = 1
                while os.path.exists(os.path.join(target_dir, unique)):
                    unique = f"{name}_{i}{ext}"
                    i += 1
                f.save(os.path.join(target_dir, unique))
                m.slide_url = unique
                db.session.commit()
                flash('Slide uploaded to module.', 'success')
            elif content_type == 'video':
                url = (request.form.get('youtube_url') or '').strip()
                if not url:
                    flash('Please provide a YouTube URL.', 'warning')
                    return redirect(url_for('upload_content'))
                m.youtube_url = url
                db.session.commit()
                flash('Video URL saved.', 'success')
            elif content_type == 'quiz':
                # Build quiz from up to 5 question slots
                quiz = []
                # Allow up to 50 for future-proofing; forms usually send up to 5
                for qn in range(1, 51):
                    qtext = (request.form.get(f'quiz_question_{qn}') or '').strip()
                    if not qtext:
                        # Stop if we hit a gap and no further fields exist beyond 5
                        if qn > 5:
                            continue
                        # For 1..5, allow blank to be skipped
                        continue
                    answers = []
                    # Collect up to 5 answers from forms used in templates
                    for an in range(1, 6):
                        atext = (request.form.get(f'answer_{qn}_{an}') or '').strip()
                        if atext:
                            answers.append({'text': atext, 'isCorrect': False})
                    # Default at least two empty answers if none
                    if not answers:
                        continue
                    # Mark correct
                    try:
                        correct_sel = int(request.form.get(f'correct_answer_{qn}') or 0)
                    except Exception:
                        correct_sel = 0
                    if 1 <= correct_sel <= len(answers):
                        answers[correct_sel - 1]['isCorrect'] = True
                    else:
                        # If invalid, make first one correct by default
                        answers[0]['isCorrect'] = True
                    quiz.append({'text': qtext, 'answers': answers})
                if not quiz:
                    flash('Please provide at least one question and answers.', 'warning')
                    return redirect(url_for('upload_content'))
                m.quiz_json = json.dumps(quiz)
                db.session.commit()
                flash('Quiz saved to module.', 'success')
            else:
                flash('Unsupported content type.', 'warning')
            return redirect(url_for('upload_content'))
        except Exception:
            db.session.rollback()
            logging.exception('[UPLOAD CONTENT] Failed to save content')
            flash('Failed to save content. Please try again later.', 'danger')
            return redirect(url_for('upload_content'))

    # GET: render content management page with modules list
    try:
        modules = Module.query.order_by(Module.module_type.asc(), Module.series_number.asc()).all()
    except Exception:
        modules = []
    return render_template('upload_content.html', modules=modules)

@app.route('/api/debug/modules')
@login_required
def api_debug_modules():
    try:
        rows = []
        mods = Module.query.all()
        for m in mods:
            try:
                q = json.loads(m.quiz_json or '[]')
            except Exception:
                q = []
            course = db.session.get(Course, getattr(m, 'course_id', None)) if getattr(m, 'course_id', None) else None
            rows.append({
                'module_id': m.module_id,
                'module_name': m.module_name,
                'course_code': getattr(course, 'code', None),
                'course_name': getattr(course, 'name', None),
                'has_quiz': bool(q),
                'quiz_len': len(q) if isinstance(q, list) else 0,
            })
        return jsonify(rows)
    except Exception as e:
        logging.exception('[DEBUG] list modules failed')
        return jsonify([]), 500


@app.route('/api/debug/my_experiences')
@login_required
def api_debug_my_experiences():
    try:
        if not isinstance(current_user, User):
            return jsonify(success=False, message='Unauthorized'), 403
        rows = (
            WorkHistory.query
            .filter_by(user_id=current_user.User_id)
            .order_by(db.func.coalesce(WorkHistory.recruitment_date, WorkHistory.start_date).desc())
            .all()
        )
        return jsonify(success=True, count=len(rows), items=[r.to_dict() for r in rows])
    except Exception as e:
        logging.exception('[DEBUG] my_experiences failed')
        return jsonify(success=False, message=str(e)), 500


@app.route('/healthz')
def healthz():
    try:
        # Quick DB ping
        with db.engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        # Mask DB URI to avoid secrets disclosure
        uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
        dialect = db.engine.dialect.name if hasattr(db, 'engine') else 'unknown'
        return jsonify(ok=True, db=dialect)
    except Exception as e:
        logging.exception('[HEALTHZ] Failed')
        return jsonify(ok=False, error=str(e)), 500

# -------------------------------------------------------------------------------
# Allow running this file directly: `python app.py`
if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 5000))
    except Exception:
        port = 5000
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes', 'on')
    host = os.environ.get('HOST', '0.0.0.0')
    print(f"[SERVER] Starting Flask development server on http://{host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug, threaded=True)
