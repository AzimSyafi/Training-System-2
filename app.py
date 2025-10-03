from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, UTC  # removed unused date
import os
from models import db, Admin, User, Agency, Module, Certificate, Trainer, UserModule, Management, Registration, Course, WorkHistory, UserCourseProgress, AgencyAccount
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, inspect as sa_inspect, or_  # added or_
import re
import urllib.parse
import logging
from werkzeug.routing import BuildError  # added
import json
import math  # Added for ceiling function
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

# Safe date parsing helper used for form date fields
def safe_parse_date(value, fmt='%Y-%m-%d'):
    """Parse a date string into a datetime.date safely.
    Returns a date object on success, None for empty/invalid values.
    Accepts already-date/datetime objects and returns date.
    """
    if value is None:
        return None
    # Accept actual date/datetime objects
    try:
        import datetime as _dt
        if isinstance(value, _dt.date) and not isinstance(value, _dt.datetime):
            return value
        if isinstance(value, _dt.datetime):
            return value.date()
    except Exception:
        pass
    # Normalize empty strings
    try:
        v = str(value).strip()
    except Exception:
        return None
    if v == '':
        return None
    # Try parsing
    try:
        return datetime.strptime(v, fmt).date()
    except Exception:
        return None

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

# For API endpoints, return JSON 401 instead of redirecting HTML login page
@login_manager.unauthorized_handler
def _unauthorized_handler():
    try:
        path = request.path or ''
        if path.startswith('/api/'):
            return jsonify(success=False, message='Unauthorized'), 401
    except Exception:
        pass
    # Fallback to normal redirect for non-API routes
    try:
        return redirect(url_for('login'))
    except Exception:
        # Very defensive: return minimal JSON if even redirect fails
        return jsonify(success=False, message='Unauthorized'), 401

# Register blueprints
try:
    from authority_routes import authority_bp
    app.register_blueprint(authority_bp)
except Exception as _e:
    # Log but don't crash app if import fails during certain offline scripts
    logging.debug(f"[INIT] Skipping authority blueprint registration: {_e}")

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

        # Ensure module.scoring_float exists
        try:
            if inspector.has_table('module'):
                mod_columns = {c['name'] for c in inspector.get_columns('module')}
                if 'scoring_float' not in mod_columns:
                    dialect = (getattr(db.engine, 'dialect', None).name or '').lower()
                    if dialect == 'postgresql':
                        db.session.execute(text('ALTER TABLE module ADD COLUMN IF NOT EXISTS scoring_float DOUBLE PRECISION DEFAULT 0.0'))
                        # Initialize existing rows to 0.0 where NULL
                        db.session.execute(text('UPDATE module SET scoring_float = 0.0 WHERE scoring_float IS NULL'))
                        db.session.commit()
                        print('[SCHEMA GUARD] Added scoring_float to module')
                    else:
                        # Generic fallback (e.g., SQLite)
                        try:
                            db.session.execute(text('ALTER TABLE module ADD COLUMN scoring_float FLOAT'))
                            db.session.execute(text('UPDATE module SET scoring_float = 0.0 WHERE scoring_float IS NULL'))
                            db.session.commit()
                            print('[SCHEMA GUARD] Added scoring_float to module (generic)')
                        except Exception as e:
                            db.session.rollback()
                            print(f'[SCHEMA GUARD] Could not add scoring_float to module: {e}')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Error ensuring module.scoring_float: {e}')

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
                # Ensure user.role column exists (for authority approvals and scoping)
                if 'role' not in user_columns:
                    dialect = (getattr(db.engine, 'dialect', None).name or '').lower()
                    with db.engine.begin() as conn:
                        if dialect == 'postgresql':
                            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'agency'"))
                            conn.execute(text("UPDATE \"user\" SET role = 'agency' WHERE role IS NULL"))
                            try:
                                conn.execute(text('ALTER TABLE "user" ALTER COLUMN role SET NOT NULL'))
                            except Exception:
                                pass
                        else:
                            # SQLite & others: no IF NOT EXISTS for ADD COLUMN in older versions
                            try:
                                conn.execute(text('ALTER TABLE user ADD COLUMN role VARCHAR(50)'))
                            except Exception:
                                # Column may already exist or SQL unsupported; ignore
                                pass
                            try:
                                conn.execute(text("UPDATE user SET role = 'agency' WHERE role IS NULL"))
                            except Exception:
                                pass
                    logging.info('[BOOT] Ensured user.role column exists')
                # Ensure user.remarks exists before any queries using User model
                if 'remarks' not in user_columns:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS remarks TEXT'))
                    db.session.commit()
                    print('[SCHEMA GUARD] Added remarks to user')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not ensure user.is_finalized: {e}')

        # Ensure certificate approval-related columns exist
        try:
            if inspector.has_table('certificate'):
                cert_columns = {c['name'] for c in inspector.get_columns('certificate')}
                # status column
                if 'status' not in cert_columns:
                    try:
                        db.session.execute(text("ALTER TABLE certificate ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending'"))
                        db.session.execute(text("UPDATE certificate SET status = 'pending' WHERE status IS NULL"))
                        db.session.execute(text('ALTER TABLE certificate ALTER COLUMN status SET NOT NULL'))
                        db.session.commit()
                        print('[SCHEMA GUARD] Added status to certificate')
                    except Exception as e:
                        db.session.rollback()
                        print(f'[SCHEMA GUARD] Could not ensure certificate.status: {e}')
                # approved_by_id column
                if 'approved_by_id' not in cert_columns:
                    try:
                        db.session.execute(text('ALTER TABLE certificate ADD COLUMN IF NOT EXISTS approved_by_id INTEGER NULL'))
                        db.session.commit()
                        print('[SCHEMA GUARD] Added approved_by_id to certificate')
                    except Exception as e:
                        db.session.rollback()
                        print(f'[SCHEMA GUARD] Could not ensure certificate.approved_by_id: {e}')
                # approved_at column
                if 'approved_at' not in cert_columns:
                    try:
                        db.session.execute(text('ALTER TABLE certificate ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP NULL'))
                        db.session.commit()
                        print('[SCHEMA GUARD] Added approved_at to certificate')
                    except Exception as e:
                        db.session.rollback()
                        print(f'[SCHEMA GUARD] Could not ensure certificate.approved_at: {e}')
                # star_rating column for user ratings
                if 'star_rating' not in cert_columns:
                    try:
                        db.session.execute(text('ALTER TABLE certificate ADD COLUMN IF NOT EXISTS star_rating INTEGER NULL'))
                        db.session.commit()
                        print('[SCHEMA GUARD] Added star_rating to certificate')
                    except Exception as e:
                        db.session.rollback()
                        print(f'[SCHEMA GUARD] Could not ensure certificate.star_rating: {e}')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not ensure certificate columns: {e}')

        # Ensure user.module_disclaimer_agreements column exists
        try:
            if inspector.has_table('user'):
                user_cols = {c['name'] for c in inspector.get_columns('user')}
                if 'module_disclaimer_agreements' not in user_cols:
                    try:
                        db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS module_disclaimer_agreements TEXT'))
                        # Optional: initialize to '{}' for existing rows
                        db.session.execute(text("UPDATE \"user\" SET module_disclaimer_agreements = '{}' WHERE module_disclaimer_agreements IS NULL"))
                        db.session.commit()
                        print('[SCHEMA GUARD] Added module_disclaimer_agreements to user')
                    except Exception as e:
                        db.session.rollback()
                        print(f'[SCHEMA GUARD] Could not ensure user.module_disclaimer_agreements: {e}')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Error inspecting user table: {e}')

        # Ensure approval_audit table exists even if essentials already present
        try:
            if not inspector.has_table('approval_audit'):
                db.create_all()
                db.session.commit()
                print('[SCHEMA GUARD] Ensured approval_audit table exists via create_all')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not ensure approval_audit table: {e}')
    except Exception as e:
        db.session.rollback()
        print(f"[SCHEMA GUARD] Could not complete schema initialization: {e}")
# -------------------------------------------------------------------------------
# Run schema initialization once at startup (safe + idempotent)
try:
    if os.environ.get('DISABLE_SCHEMA_GUARD', '0') not in ('1', 'true', 'True'):
        # Ensure an application context is active for db.engine access
        with app.app_context():
            _bootstrap_schema_with_advisory_lock(_initialize_schema)
except Exception as e:
    print(f"[SCHEMA GUARD] Initialization skipped due to error: {e}")

# Minimal self-healing initializer compatible with Flask >=3 (no before_first_request)
_minimal_schema_done = False
try:
    from threading import Lock as _Lock
    _minimal_schema_lock = _Lock()
except Exception:
    _minimal_schema_lock = None

def _ensure_minimal_columns_once():
    global _minimal_schema_done
    if _minimal_schema_done:
        return
    # lock to avoid duplicate execution under concurrency
    lock = _minimal_schema_lock
    if lock is not None:
        try:
            lock.acquire()
        except Exception:
            lock = None
    try:
        if _minimal_schema_done:
            return
        try:
            insp = sa_inspect(db.engine)
            if insp.has_table('user'):
                cols = {c['name'] for c in insp.get_columns('user')}
                if 'role' not in cols:
                    dialect = (getattr(db.engine, 'dialect', None).name or '').lower()
                    with db.engine.begin() as conn:
                        if dialect == 'postgresql':
                            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'agency'"))
                            conn.execute(text("UPDATE \"user\" SET role = 'agency' WHERE role IS NULL"))
                            try:
                                conn.execute(text('ALTER TABLE "user" ALTER COLUMN role SET NOT NULL'))
                            except Exception:
                                pass
                        else:
                            # SQLite & others: no IF NOT EXISTS for ADD COLUMN in older versions
                            try:
                                conn.execute(text('ALTER TABLE user ADD COLUMN role VARCHAR(50)'))
                            except Exception:
                                # Column may already exist or SQL unsupported; ignore
                                pass
                            try:
                                conn.execute(text("UPDATE user SET role = 'agency' WHERE role IS NULL"))
                            except Exception:
                                pass
                    logging.info('[BOOT] Ensured user.role column exists')
                # Ensure user.remarks exists before any queries using User model
                if 'remarks' not in cols:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS remarks TEXT'))
                    db.session.commit()
                    print('[SCHEMA GUARD] Added remarks to user')
        except Exception as e:
            db.session.rollback()
            print(f'[SCHEMA GUARD] Could not ensure user.role and remarks: {e}')
    finally:
        _minimal_schema_done = True
        if lock is not None:
            try:
                lock.release()
            except Exception:
                pass

@app.before_request
def _minimal_schema_guard_middleware():
    # Run the minimal schema check exactly once per process
    _ensure_minimal_columns_once()

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
            try:
                u = User.query.filter_by(number_series=user_id).first()
            except Exception as e:
                # Self-heal if missing user.role column
                msg = str(e)
                if 'column user.role does not exist' in msg or 'UndefinedColumn' in msg:
                    try:
                        dialect = (getattr(db.engine, 'dialect', None).name or '').lower()
                        with db.engine.begin() as conn:
                            if dialect == 'postgresql':
                                conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'agency'"))
                                conn.execute(text("UPDATE \"user\" SET role = 'agency' WHERE role IS NULL"))
                                try:
                                    conn.execute(text('ALTER TABLE "user" ALTER COLUMN role SET NOT NULL'))
                                except Exception:
                                    pass
                            else:
                                try:
                                    conn.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(50)"))
                                except Exception:
                                    pass
                                try:
                                    conn.execute(text("UPDATE user SET role = 'agency' WHERE role IS NULL"))
                                except Exception:
                                    pass
                        # Retry once
                        u = User.query.filter_by(number_series=user_id).first()
                    except Exception:
                        u = None
                else:
                    u = None
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
    profile_dir = app.config.get('UPLOAD_FOLDER', 'static_profile_pics')
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

# --- NEW: User signup route (previously missing causing BuildError) ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    # Prevent logged-in users from accessing signup again
    if current_user.is_authenticated:
        if isinstance(current_user, Admin):
            return redirect(url_for('admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        if isinstance(current_user, User):
            return redirect(url_for('user_dashboard'))
        return redirect(url_for('index'))
    agencies = []
    try:
        agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
    except Exception:
        logging.exception('[SIGNUP] Failed loading agencies')
        agencies = []
    if request.method == 'POST':
        form = request.form
        full_name = form.get('full_name','').strip()
        email = form.get('email','').strip().lower()
        password = form.get('password','')
        user_category = form.get('user_category','citizen').strip().lower()
        agency_id = form.get('agency_id')
        ic_number = form.get('ic_number','').strip() or None
        passport_number = form.get('passport_number','').strip() or None
        country = form.get('country','').strip() or None
        # Basic validation
        if not full_name or not email or not password or not agency_id:
            flash('All required fields must be filled: name, email, password, agency.', 'danger')
            return render_template('signup.html', agencies=agencies)
        try:
            agency_id_int = int(agency_id)
        except (ValueError, TypeError):
            flash('Invalid agency selected.', 'danger')
            return render_template('signup.html', agencies=agencies)
        try:
            # Ensure agency exists
            agency_obj = db.session.get(Agency, agency_id_int)
            if not agency_obj:
                flash('Selected agency does not exist.', 'danger')
                return render_template('signup.html', agencies=agencies)
        except Exception:
            flash('Database error checking agency.', 'danger')
            return render_template('signup.html', agencies=agencies)
        data = {
            'full_name': full_name,
            'email': email,
            'password': password,
            'user_category': 'foreigner' if user_category == 'foreigner' else 'citizen',
            'agency_id': agency_id_int
        }
        # Optional IDs (collected lightly; can be completed later during onboarding/profile editing)
        if ic_number:
            data['ic_number'] = ic_number
        if passport_number:
            data['passport_number'] = passport_number
        if country and user_category == 'foreigner':
            data['country'] = country
        try:
            new_user = Registration.registerUser(data)
            # Auto-login new user
            login_user(new_user)
            session['user_type'] = 'user'
            session['user_id'] = new_user.get_id()
            flash('Account created successfully! Complete your profile to finalize registration.', 'success')
            return redirect(url_for('onboarding', id=new_user.User_id))
        except ValueError as ve:
            flash(str(ve), 'danger')
        except Exception as e:
            logging.exception('[SIGNUP] Registration failed')
            flash('Registration failed due to server error. Please try again later.', 'danger')
        # On error re-render with agencies
        return render_template('signup.html', agencies=agencies)
    return render_template('signup.html', agencies=agencies)

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

# --- NEW: User dashboard (missing earlier; templates and redirects reference this) ---
@app.route('/user_dashboard')
@login_required
def user_dashboard():
    if not isinstance(current_user, User):
        # Redirect non-user roles to their respective dashboards
        if isinstance(current_user, Admin):
            return redirect(url_for('admin_dashboard'))
        if isinstance(current_user, Trainer):
            return redirect(url_for('trainer_portal'))
        from models import AgencyAccount as _AA
        if isinstance(current_user, _AA):
            return redirect(url_for('agency_portal'))
        return redirect(url_for('login'))
    try:
        # Use robust normalization (falls back via IDs if needed)
        cat = normalized_user_category(current_user)
        courses_q = Course.query.filter(or_(Course.allowed_category == cat, Course.allowed_category == 'both'))
        courses = courses_q.order_by(Course.name.asc()).all()
        # Fallback: if no courses found for the specific category, show all courses (graceful degradation)
        if not courses:
            courses = Course.query.order_by(Course.name.asc()).all()
    except Exception:
        logging.exception('[USER DASHBOARD] Failed loading courses')
        courses = []
    courses_progress = []
    course_completed_count = 0
    for c in courses:
        try:
            mods = c.modules
            total_modules = len(mods)
            if total_modules == 0:
                completed_modules = 0
                progress_pct = 0.0
            else:
                module_ids = [m.module_id for m in mods]
                completed_modules = UserModule.query.filter(
                    UserModule.user_id == current_user.User_id,
                    UserModule.module_id.in_(module_ids),
                    UserModule.is_completed.is_(True)
                ).count()
                progress_pct = round((completed_modules / total_modules) * 100.0, 1) if total_modules else 0.0
            if total_modules > 0 and completed_modules == total_modules:
                course_completed_count += 1
            courses_progress.append({
                'course_id': c.course_id,
                'name': c.name,
                'code': c.code,
                'total_modules': total_modules,
                'completed_modules': completed_modules,
                'progress': progress_pct
            })
        except Exception:
            logging.exception('[USER DASHBOARD] Error computing progress for course %s', getattr(c, 'code', '?'))
    course_enrolled_count = len([c for c in courses if len(c.modules) > 0])
    return render_template(
        'user_dashboard.html',
        user=current_user,
        courses=courses,
        courses_progress=courses_progress,
        course_enrolled_count=course_enrolled_count,
        course_completed_count=course_completed_count
    )

# --- OPTIONAL: minimal stubs for routes referenced by quick actions if they are not already defined ---
try:
    app.view_functions['courses']
except KeyError:
    @app.route('/courses')
    @login_required
    def courses():
        try:
            # DB-level filtering for the common allowed_category rule improves performance.
            # Admins/trainers/authority accounts should see all courses.
            if isinstance(current_user, Admin) or isinstance(current_user, Trainer) or getattr(current_user, 'role', None) == 'authority' or isinstance(current_user, AgencyAccount):
                courses_q = Course.query
            else:
                cat = normalized_user_category(current_user)
                courses_q = Course.query.filter(or_(Course.allowed_category == cat, Course.allowed_category == 'both'))
            all_courses = courses_q.order_by(Course.name.asc()).all()
        except Exception:
            logging.exception('[COURSES] Failed loading courses')
            all_courses = []

        # Final Python-level guard for complex rules that can't be expressed in SQL
        visible_courses = [c for c in all_courses if getattr(c, 'is_visible_to', lambda u: True)(current_user)]

        course_progress = []
        for c in visible_courses:
            try:
                allowed = c.allowed_category or 'both'
                modules = list(c.modules)
                module_ids = [m.module_id for m in modules]
                total_modules = len(modules)
                if total_modules == 0:
                    percent = 0
                    overall_percentage = 0
                else:
                    completed_q = UserModule.query.filter(
                        UserModule.user_id == current_user.User_id,
                        UserModule.module_id.in_(module_ids),
                        UserModule.is_completed.is_(True)
                    )
                    completed_count = completed_q.count()
                    percent = round((completed_count / total_modules) * 100) if total_modules else 0
                    # Average score across completed modules (ignore None)
                    scores = [um.score for um in completed_q.all() if um.score is not None]
                    overall_percentage = round(sum(scores)/len(scores),1) if scores else 0
                course_progress.append({
                    'name': c.name,
                    'code': c.code,
                    'allowed_category': allowed,
                    'locked': False,
                    'percent': percent,
                    'overall_percentage': overall_percentage
                })
            except Exception:
                logging.exception('[COURSES] Error computing progress for course %s', getattr(c,'code','?'))
        # If no courses at all (unlikely after defaults), page will show empty message
        return render_template('courses.html', course_progress=course_progress) if os.path.exists(os.path.join(app.template_folder or 'templates','courses.html')) else jsonify(course_progress)

try:
    app.view_functions['profile']
except KeyError:
    @app.route('/profile')
    @login_required
    def profile():
        return render_template('profile.html', user=current_user) if os.path.exists(os.path.join(app.template_folder or 'templates','profile.html')) else jsonify({'user': current_user.displayed_id})

try:
    app.view_functions['my_certificates']
except KeyError:
    @app.route('/my_certificates')
    @login_required
    def my_certificates():
        certs = []
        try:
            certs = Certificate.query.filter_by(user_id=current_user.User_id).order_by(Certificate.issue_date.desc()).all()
        except Exception:
            logging.exception('[MY CERTIFICATES] Failed loading certificates')
        return render_template('my_certificates.html', certificates=certs) if os.path.exists(os.path.join(app.template_folder or 'templates','my_certificates.html')) else jsonify({'count': len(certs)})

try:
    app.view_functions['agency']
except KeyError:
    @app.route('/agency')
    @login_required
    def agency():
        try:
            ag = db.session.get(Agency, getattr(current_user, 'agency_id', None)) if hasattr(current_user, 'agency_id') else None
        except Exception:
            ag = None
        return render_template('agency.html', agency=ag) if os.path.exists(os.path.join(app.template_folder or 'templates','agency.html')) else jsonify({'agency': getattr(ag,'agency_name', None)})

# New: unified logout route used by templates (supports POST and GET)
@app.route('/logout', methods=['POST', 'GET'])
@login_required
def logout():
    try:
        logout_user()
    except Exception:
        pass
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

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not isinstance(current_user, Admin):
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

from types import SimpleNamespace
from sqlalchemy.orm import joinedload


def _require_admin():
    if not current_user.is_authenticated or not isinstance(current_user, Admin):
        return False
    return True

@app.route('/admin_users')
@login_required
def admin_users():
    if not _require_admin():
        return redirect(url_for('login'))
    try:
        q = request.args.get('q', '').strip().lower()
        role_filter = request.args.get('role', 'all').lower()
        agency_id = request.args.get('agency_id')
        agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
        merged_accounts = []
        users_q = User.query
        if agency_id:
            try:
                users_q = users_q.filter(User.agency_id == int(agency_id))
            except ValueError:
                pass
        users = users_q.all()
        for u in users:
            if q and (q not in (u.full_name or '').lower() and q not in (u.email or '').lower() and q not in (u.number_series or '').lower()):
                continue
            # Determine user type based on role field
            user_role = getattr(u, 'role', 'agency')
            if user_role == 'authority':
                # Authority users
                if role_filter not in ('all', 'authority'):
                    continue
                merged_accounts.append({
                    'type': 'authority',
                    'id': u.User_id,
                    'number_series': u.number_series,
                    'name': u.full_name,
                    'email': u.email,
                    'agency': getattr(getattr(u, 'agency', None), 'agency_name', ''),
                    'active_status': True,
                })
            else:
                # Regular users
                if role_filter not in ('all','user'):
                    continue
                merged_accounts.append({
                    'type': 'user',
                    'id': u.User_id,
                    'number_series': u.number_series,
                    'name': u.full_name,
                    'email': u.email,
                    'agency': getattr(getattr(u, 'agency', None), 'agency_name', ''),
                    'active_status': True,
                })
        trainers = Trainer.query.all()
        for t in trainers:
            if q and (q not in (t.name or '').lower() and q not in (t.email or '').lower() and q not in (t.number_series or '').lower()):
                continue
            if role_filter not in ('all','trainer'):
                continue
            merged_accounts.append({
                'type': 'trainer',
                'id': t.trainer_id,
                'number_series': t.number_series,
                'name': t.name,
                'email': t.email,
                'agency': '',
                'active_status': t.active_status,
            })
        admins = Admin.query.all()
        for a in admins:
            if q and (q not in (a.username or '').lower() and q not in (a.email or '').lower()):
                continue
            if role_filter not in ('all','admin'):
                continue
            merged_accounts.append({
                'type': 'admin',
                'id': a.admin_id,
                'number_series': None,
                'name': a.username,
                'email': a.email,
                'agency': '',
                'active_status': True,
            })
        filters = SimpleNamespace(q=q, role=role_filter, agency_id=agency_id, status=request.args.get('status','all'))
    except Exception:
        logging.exception('[ADMIN USERS] Failed building context')
        merged_accounts = []
        agencies = []
        filters = SimpleNamespace(q='', role='all', agency_id=None, status='all')
    return render_template('admin_users.html', merged_accounts=merged_accounts, agencies=agencies, filters=filters)

@app.route('/admin_course_management')
@login_required
def admin_course_management():
    if not _require_admin():
        return redirect(url_for('login'))
    try:
        courses = Course.query.order_by(Course.name.asc()).all()
        course_modules = {}
        for c in courses:
            mods = Module.query.filter_by(course_id=c.course_id).order_by(Module.series_number.asc()).all()
            course_modules[c.course_id] = mods
    except Exception:
        logging.exception('[ADMIN COURSE MGMT] Error loading courses')
        courses = []
        course_modules = {}
    return render_template('admin_course_management.html', courses=courses, course_modules=course_modules)

@app.route('/admin_certificates')
@login_required
def admin_certificates():
    if not _require_admin():
        return redirect(url_for('login'))
    try:
        q = request.args.get('q','').strip().lower()
        agency_id = request.args.get('agency_id')
        course_id = request.args.get('course_id')
        cert_q = Certificate.query.options(joinedload(Certificate.user)).order_by(Certificate.issue_date.desc())
        if agency_id:
            try:
                cert_q = cert_q.join(User).filter(User.agency_id == int(agency_id))
            except ValueError:
                pass
        certificates = cert_q.limit(500).all()
        if q:
            filtered = []
            for c in certificates:
                hay = ' '.join([
                    str(c.certificate_id),
                    c.user.full_name if c.user else '',
                    c.module_type or ''
                ]).lower()
                if q in hay:
                    filtered.append(c)
            certificates = filtered
        agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
        courses = Course.query.order_by(Course.name.asc()).all()
        cert_template_url = None
        try:
            base = os.path.join(app.static_folder or 'static', 'cert_templates')
            if os.path.isdir(base):
                for fname in os.listdir(base):
                    if fname.lower().endswith(('.pdf','.png','.jpg','.jpeg','.svg')):
                        from flask import url_for as _uf
                        cert_template_url = _uf('static', filename=f'cert_templates/{fname}')
                        break
        except Exception:
            pass
        filters = SimpleNamespace(q=q, agency_id=agency_id, course_id=course_id)
    except Exception:
        logging.exception('[ADMIN CERTIFICATES] Error building context')
        certificates = []
        agencies = []
        courses = []
        cert_template_url = None
        filters = SimpleNamespace(q='', agency_id=None, course_id=None)
    return render_template('admin_certificates.html', certificates=certificates, agencies=agencies, courses=courses, cert_template_url=cert_template_url, filters=filters)

@app.route('/admin_agencies')
@login_required
def admin_agencies():
    if not _require_admin():
        return redirect(url_for('login'))
    try:
        agencies = Agency.query.options(joinedload(Agency.users)).order_by(Agency.agency_name.asc()).all()
    except Exception:
        logging.exception('[ADMIN AGENCIES] Failed loading agencies')
        agencies = []
    return render_template('admin_agencies.html', agencies=agencies)

@app.route('/add_agency', methods=['POST'])
@login_required
def add_agency():
    if not _require_admin():
        return redirect(url_for('login'))
    try:
        a = Agency(
            agency_name=request.form.get('agency_name','').strip(),
            PIC=request.form.get('PIC','').strip(),
            contact_number=request.form.get('contact_number','').strip(),
            email=request.form.get('email','').strip(),
            address=request.form.get('address','').strip(),
            Reg_of_Company=request.form.get('Reg_of_Company','').strip(),
        )
        db.session.add(a)
        db.session.commit()
        flash('Agency added','success')
    except Exception:
        db.session.rollback()
        logging.exception('[ADD AGENCY] Failed')
        flash('Failed to add agency','danger')
    return redirect(safe_url_for('admin_agencies'))

@app.route('/edit_agency/<int:agency_id>', methods=['POST'])
@login_required
def edit_agency(agency_id):
    if not _require_admin():
        return redirect(url_for('login'))
    ag = db.session.get(Agency, agency_id)
    if not ag:
        from flask import abort
        return abort(404)
    try:
        for field in ['agency_name','PIC','contact_number','email','address','Reg_of_Company']:
            if field in request.form:
                setattr(ag, field, request.form.get(field).strip())
        db.session.commit()
        flash('Agency updated','success')
    except Exception:
        db.session.rollback()
        logging.exception('[EDIT AGENCY] Failed')
        flash('Failed to update agency','danger')
    return redirect(safe_url_for('admin_agencies'))

@app.route('/admin_create_agency_account/<int:agency_id>', methods=['POST'])
@login_required
def admin_create_agency_account(agency_id):
    if not _require_admin():
        return redirect(url_for('login'))
    ag = db.session.get(Agency, agency_id)
    if not ag:
        from flask import abort
        return abort(404)
    if ag.account:
        flash('Agency already has an account','warning')
        return redirect(safe_url_for('admin_agencies'))
    try:
        acc = AgencyAccount(agency_id=ag.agency_id, email=ag.email)
        acc.set_password('ChangeMe123!')
        db.session.add(acc)
        db.session.commit()
        flash('Agency login created (temporary password: ChangeMe123!)','success')
    except Exception:
        db.session.rollback()
        logging.exception('[CREATE AGENCY ACCOUNT] Failed')
        flash('Failed to create agency login','danger')
    return redirect(safe_url_for('admin_agencies'))

@app.route('/create_user', methods=['POST'])
@login_required
def create_user():
    if not _require_admin():
        return redirect(url_for('login'))
    full_name = request.form.get('full_name','').strip()
    email = request.form.get('email','').strip().lower()
    role = request.form.get('role','').strip().lower()
    password = request.form.get('password','password123')
    try:
        if role == 'trainer':
            t = Trainer(name=full_name, email=email)
            t.set_password(password)
            db.session.add(t)
        elif role == 'admin':
            a = Admin(username=full_name, email=email)
            a.set_password(password)
            db.session.add(a)
        else:
            ag = Agency.query.first()
            if not ag:
                flash('Create an agency first before adding users','warning')
                return redirect(safe_url_for('admin_users'))
            u = User(full_name=full_name, email=email, agency_id=ag.agency_id, user_category='citizen')
            u.set_password(password)
            db.session.add(u)
        db.session.commit()
        flash('Account created','success')
    except Exception:
        db.session.rollback()
        logging.exception('[CREATE USER] Failed')
        flash('Failed to create account','danger')
    return redirect(safe_url_for('admin_users'))

@app.route('/delete_user', methods=['POST'])
@login_required
def delete_user():
    if not _require_admin():
        return jsonify(success=False, message='Forbidden')
    user_id = request.form.get('user_id')
    try:
        u = db.session.get(User, int(user_id)) if user_id else None
        if not u:
            return jsonify(success=False, message='User not found')
        db.session.delete(u)
        db.session.commit()
        return jsonify(success=True, message='User deleted')
    except Exception:
        db.session.rollback()
        logging.exception('[DELETE USER] Failed')
        return jsonify(success=False, message='Delete failed')

@app.route('/delete_trainer', methods=['POST'])
@login_required
def delete_trainer():
    if not _require_admin():
        return jsonify(success=False, message='Forbidden')
    trainer_id = request.form.get('trainer_id')
    try:
        t = db.session.get(Trainer, int(trainer_id)) if trainer_id else None
        if not t:
            return jsonify(success=False, message='Trainer not found')
        db.session.delete(t)
        db.session.commit()
        return jsonify(success=True, message='Trainer deleted')
    except Exception:
        db.session.rollback()
        logging.exception('[DELETE TRAINER] Failed')
        return jsonify(success=False, message='Delete failed')

@app.route('/reset_user_progress', methods=['POST'])
@login_required
def reset_user_progress():
    if not _require_admin():
        return jsonify(success=False, message='Forbidden')
    user_id = request.form.get('user_id')
    try:
        if not user_id:
            return jsonify(success=False, message='Missing user_id')
        UserModule.query.filter_by(user_id=int(user_id)).delete()
        db.session.commit()
        return jsonify(success=True, message='Progress reset')
    except Exception:
        db.session.rollback()
        logging.exception('[RESET PROGRESS] Failed')
        return jsonify(success=False, message='Reset failed')

@app.route('/change_role', methods=['POST'])
@login_required
def change_role():
    if not _require_admin():
        return jsonify(success=False, message='Forbidden')
    return jsonify(success=True, message='Role change stub (not fully implemented).')

@app.route('/create_course', methods=['POST'])
@login_required
def create_course():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    name = request.form.get('name','').strip()
    code = request.form.get('code','').strip().upper()
    allowed_category = request.form.get('allowed_category','both')
    if not name or not code:
        flash('Course name and code required','danger')
        return redirect(safe_url_for('admin_course_management'))
    try:
        existing = Course.query.filter(db.func.lower(db.func.trim(Course.code)) == code.lower()).first()
        if existing:
            flash('Course code already exists','warning')
        else:
            c = Course(name=name, code=code, allowed_category=allowed_category)
            db.session.add(c)
            db.session.commit()
            flash('Course created','success')
    except Exception:
        db.session.rollback()
        logging.exception('[CREATE COURSE] Failed')
        flash('Failed to create course','danger')
    return redirect(safe_url_for('admin_course_management'))

@app.route('/update_course/<int:course_id>', methods=['POST'])
@login_required
def update_course(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    course = db.session.get(Course, course_id)
    if not course:
        from flask import abort
        return abort(404)
    try:
        course.name = request.form.get('name', course.name).strip()
        course.allowed_category = request.form.get('allowed_category', course.allowed_category)
        db.session.commit()
        flash('Course updated','success')
    except Exception:
        db.session.rollback()
        logging.exception('[UPDATE COURSE] Failed')
        flash('Failed to update course','danger')
    return redirect(safe_url_for('admin_course_management'))

@app.route('/delete_course/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    c = db.session.get(Course, course_id)
    if not c:
        from flask import abort
        return abort(404)
    try:
        Module.query.filter_by(course_id=c.course_id).delete()
        db.session.delete(c)
        db.session.commit()
        flash('Course deleted','success')
    except Exception:
        db.session.rollback()
        logging.exception('[DELETE COURSE] Failed')
        flash('Failed to delete course','danger')
    return redirect(safe_url_for('admin_course_management'))

@app.route('/add_course_module/<int:course_id>', methods=['POST'])
@login_required
def add_course_module(course_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    course = db.session.get(Course, course_id)
    if not course:
        from flask import abort
        return abort(404)
    module_name = request.form.get('module_name','').strip()
    series_number = request.form.get('series_number','').strip() or None
    if not module_name:
        flash('Module name required','danger')
        return redirect(safe_url_for('admin_course_management'))
    try:
        m = Module(module_name=module_name, module_type=course.code, series_number=series_number, course_id=course.course_id)
        db.session.add(m)
        db.session.commit()
        flash('Module added','success')
    except Exception:
        db.session.rollback()
        logging.exception('[ADD MODULE] Failed')
        flash('Failed to add module','danger')
    return redirect(safe_url_for('admin_course_management'))

@app.route('/delete_course_module/<int:module_id>', methods=['POST'])
@login_required
def delete_course_module(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    m = db.session.get(Module, module_id)
    if not m:
        from flask import abort
        return abort(404)
    try:
        db.session.delete(m)
        db.session.commit()
        flash('Module deleted','success')
    except Exception:
        db.session.rollback()
        logging.exception('[DELETE MODULE] Failed')
        flash('Failed to delete module','danger')
    return redirect(safe_url_for('admin_course_management'))

@app.route('/update_course_module/<int:module_id>', methods=['POST'])
@login_required
def update_course_module(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    m = db.session.get(Module, module_id)
    if not m:
        from flask import abort
        return abort(404)
    try:
        m.module_name = request.form.get('module_name', m.module_name).strip()
        m.series_number = request.form.get('series_number', m.series_number)
        db.session.commit()
        flash('Module updated','success')
    except Exception:
        db.session.rollback()
        logging.exception('[UPDATE MODULE] Failed')
        flash('Failed to update module','danger')
    return redirect(safe_url_for('admin_course_management'))

@app.route('/manage_module_content/<int:module_id>', methods=['POST'])
@login_required
def manage_module_content(module_id):
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    m = db.session.get(Module, module_id)
    if not m:
        from flask import abort
        return abort(404)
    ctype = request.form.get('content_type')
    try:
        if ctype == 'slide':
            slide_file = request.files.get('slide_file')
            slide_text = request.form.get('slide_text','')
            if slide_file and slide_file.filename:
                fname = secure_filename(slide_file.filename)
                # Save into the configured uploads folder under the app root to match serving logic
                dest_dir = os.path.join(app.root_path, UPLOAD_CONTENT_FOLDER)
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, fname)
                slide_file.save(dest)
                m.slide_url = fname
        elif ctype == 'video':
            m.youtube_url = request.form.get('youtube_url','').strip()
        elif ctype == 'quiz':
            quiz_payload = {}
            for k, v in request.form.items():
                if k.startswith('q'):
                    quiz_payload[k] = v
            m.quiz_json = json.dumps(quiz_payload) if quiz_payload else m.quiz_json
        db.session.commit()
        flash('Content saved','success')
    except Exception:
        db.session.rollback()
        logging.exception('[MANAGE MODULE CONTENT] Failed')
        flash('Failed to save content','danger')
    return redirect(safe_url_for('admin_course_management'))

@app.route('/upload_cert_template', methods=['POST'])
@login_required
def upload_cert_template():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    f = request.files.get('cert_template')
    if not f or not f.filename:
        flash('No file selected','warning')
        return redirect(safe_url_for('admin_certificates'))
    try:
        folder = os.path.join(app.static_folder or 'static', 'cert_templates')
        os.makedirs(folder, exist_ok=True)
        fname = secure_filename(f.filename)
        f.save(os.path.join(folder, fname))
        flash('Template uploaded','success')
    except Exception:
        logging.exception('[UPLOAD CERT TEMPLATE] Failed')
        flash('Failed to upload template','danger')
    return redirect(safe_url_for('admin_certificates'))

@app.route('/delete_certificates_bulk', methods=['POST'])
@login_required
def delete_certificates_bulk():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    ids = request.form.getlist('cert_ids')
    if not ids:
        flash('No certificates selected','warning')
        return redirect(safe_url_for('admin_certificates'))
    try:
        Certificate.query.filter(Certificate.certificate_id.in_([int(i) for i in ids])).delete(synchronize_session=False)
        db.session.commit()
        flash(f'Deleted {len(ids)} certificates','success')
    except Exception:
        db.session.rollback()
        logging.exception('[DELETE CERTS BULK] Failed')
        flash('Failed to delete certificates','danger')
    return redirect(safe_url_for('admin_certificates'))

@app.route('/recalculate_ratings')
@login_required
def recalculate_ratings():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    updated = 0
    try:
        modules = Module.query.all()
        for m in modules:
            scores = [um.score for um in m.user_modules if um.score is not None]
            if scores:
                try:
                    m.scoring_float = sum(scores) / len(scores)
                    updated += 1
                except Exception:
                    pass
        if updated:
            db.session.commit()
        flash(f'Recalculated and saved average scores for {updated} module(s).', 'success')
    except Exception:
        db.session.rollback()
        logging.exception('[RECALCULATE RATINGS] Failed')
        flash('Failed to recalculate ratings.', 'danger')
    return redirect(safe_url_for('admin_dashboard'))

@app.route('/monitor_progress')
@login_required
def monitor_progress():
    if not isinstance(current_user, Admin):
        return redirect(url_for('login'))
    from types import SimpleNamespace as _SN
    q = (request.args.get('q') or '').strip().lower()
    agency_id = request.args.get('agency_id')
    course_id = request.args.get('course_id')
    status_filter = (request.args.get('status') or '').strip().lower()
    try:
        min_progress = float(request.args.get('min_progress')) if request.args.get('min_progress') not in (None, '',) else None
    except ValueError:
        min_progress = None
    try:
        max_progress = float(request.args.get('max_progress')) if request.args.get('max_progress') not in (None, '',) else None
    except ValueError:
        max_progress = None
    try:
        agencies = Agency.query.order_by(Agency.agency_name.asc()).all()
    except Exception:
        agencies = []
    try:
        courses_q = Course.query
        if course_id:
            try:
                courses_q = courses_q.filter(Course.course_id == int(course_id))
            except ValueError:
                pass
        courses = courses_q.order_by(Course.name.asc()).all()
    except Exception:
        courses = []
    try:
        users_q = User.query
        if agency_id:
            try:
                users_q = users_q.filter(User.agency_id == int(agency_id))
            except ValueError:
                pass
        users = users_q.all()
    except Exception:
        users = []
    rows = []
    try:
        for u in users:
            agency_name = getattr(getattr(u, 'agency', None), 'agency_name', '')
            for c in courses:
                mods = c.modules
                total_modules = len(mods)
                if total_modules == 0:
                    progress_pct = 0.0
                    completed_modules = 0
                    avg_score = None
                else:
                    module_ids = [m.module_id for m in mods]
                    user_module_q = UserModule.query.filter(
                        UserModule.user_id == u.User_id,
                        UserModule.module_id.in_(module_ids)
                    )
                    completed_modules = user_module_q.filter(UserModule.is_completed.is_(True)).count()
                    scores = [um.score for um in user_module_q.filter(UserModule.is_completed.is_(True)).all() if um.score is not None]
                    avg_score = round(sum(scores)/len(scores), 1) if scores else None
                    progress_pct = round((completed_modules / total_modules) * 100.0, 1) if total_modules else 0.0
                status = 'Completed' if total_modules and progress_pct >= 100.0 else 'In Progress'
                if q:
                    hay = ' '.join([
                        (u.full_name or '').lower(),
                        (u.email or '').lower(),
                        agency_name.lower(),
                        c.name.lower(),
                        c.code.lower()
                    ])
                    if q not in hay:
                        continue
                if status_filter in ('in_progress', 'completed') and status.lower().replace(' ', '_') != status_filter:
                    continue
                if min_progress is not None and progress_pct < min_progress:
                    continue
                if max_progress is not None and progress_pct > max_progress:
                    continue
                rows.append({
                    'user_name': u.full_name,
                    'course_name': c.name,
                    'course_code': c.code,
                    'agency_name': agency_name,
                    'completed_modules': completed_modules,
                    'total_modules': total_modules,
                    'progress_pct': progress_pct,
                    'avg_score': avg_score,
                    'status': status,
                })
    except Exception:
        logging.exception('[MONITOR PROGRESS] Failed building rows')
        rows = []
    try:
        rows.sort(key=lambda r: (-r['progress_pct'], r['user_name'].lower()))
    except Exception:
        pass
    filters = _SN(q=q, agency_id=(int(agency_id) if agency_id and agency_id.isdigit() else None), course_id=(int(course_id) if course_id and course_id.isdigit() else None), status=status_filter, min_progress=min_progress, max_progress=max_progress)
    return render_template('monitor_progress.html', course_progress_rows=rows, agencies=agencies, courses=courses, filters=filters)

@app.route('/modules/<course_code>')
@login_required
def course_modules(course_code):
    """Render modules for a given course code.
    Supports two data models:
      1. New model where modules are linked via course_id
      2. Legacy model where module.module_type stores the course code
    Also provides synthetic course when Course row missing but legacy modules exist.
    """
    code = (course_code or '').strip().upper()
    if not code:
        from flask import abort
        return abort(404)
    try:
        course = Course.query.filter(db.func.lower(db.func.trim(Course.code)) == code.lower()).first()
    except Exception:
        course = None
    try:
        if course:
            modules_q = Module.query.filter(or_(Module.course_id == course.course_id, db.func.lower(db.func.trim(Module.module_type)) == course.code.lower()))
        else:
            # Legacy-only fallback: no course row yet
            modules_q = Module.query.filter(db.func.lower(db.func.trim(Module.module_type)) == code.lower())
        modules = modules_q.all()
    except Exception:
        logging.exception('[COURSE MODULES] DB error loading modules for %s', code)
        modules = []
    if not modules and not course:
        from flask import abort
        return abort(404)
    # Build user progress map
    user_progress_rows = []
    if isinstance(current_user, User):
        try:
            mod_ids = [m.module_id for m in modules]
            if mod_ids:
                user_progress_rows = UserModule.query.filter(UserModule.user_id == current_user.User_id, UserModule.module_id.in_(mod_ids)).all()
        except Exception:
            logging.exception('[COURSE MODULES] Failed loading user progress')
            user_progress_rows = []
    user_progress = {um.module_id: um for um in user_progress_rows}
    # Sort modules (uses helper that handles natural series ordering)
    try:
        modules_sorted = _series_sort(modules)
    except Exception:
        modules_sorted = modules
    # Unlock logic: first always unlocked; subsequent unlocked if previous completed
    prev_completed = True  # first module unlocked even if no previous
    for idx, m in enumerate(modules_sorted):
        um = user_progress.get(m.module_id)
        unlocked = (idx == 0) or prev_completed
        # Attach transient attribute for template
        try:
            setattr(m, 'unlocked', bool(unlocked))
        except Exception:
            pass
        prev_completed = bool(um and um.is_completed)
    # Compute overall percentage (average of completed module scores)
    overall_percentage = None
    try:
        completed_scores = [ (user_progress.get(m.module_id).score) for m in modules_sorted if user_progress.get(m.module_id) and user_progress.get(m.module_id).is_completed and user_progress.get(m.module_id).score is not None ]
        if completed_scores:
            overall_percentage = round(sum(completed_scores)/len(completed_scores), 1)
    except Exception:
        overall_percentage = None
    course_name = course.name if course else f"{code} Course"
    return render_template('course_modules.html', course_name=course_name, modules=modules_sorted, overall_percentage=overall_percentage, user_progress=user_progress)

@app.route('/api/check_module_disclaimer/<int:module_id>')
@login_required
def api_check_module_disclaimer(module_id):
    try:
        # Use session.get to avoid deprecated Query.get
        m = db.session.get(Module, module_id)
        if not m:
            return jsonify(success=False, message='Module not found'), 404
        # Non-user roles bypass disclaimer gating (treat as agreed)
        if not isinstance(current_user, User):
            return jsonify(success=True, has_agreed=True)
        agreed = current_user.has_agreed_to_module_disclaimer(module_id)
        return jsonify(success=True, has_agreed=agreed)
    except Exception as e:
        logging.exception('[DISCLAIMER CHECK] Failed')
        return jsonify(success=False, message='Server error'), 500

@app.route('/api/agree_module_disclaimer/<int:module_id>', methods=['POST'])
@login_required
def api_agree_module_disclaimer(module_id):
    try:
        # Use session.get for consistency
        m = db.session.get(Module, module_id)
        if not m:
            return jsonify(success=False, message='Module not found'), 404
        if not isinstance(current_user, User):
            return jsonify(success=False, message='Only users can agree to disclaimers'), 403
        if current_user.has_agreed_to_module_disclaimer(module_id):
            return jsonify(success=True, already=True)
        current_user.agree_to_module_disclaimer(module_id)
        return jsonify(success=True, agreed=True)
    except Exception:
        logging.exception('[DISCLAIMER AGREE] Failed')
        return jsonify(success=False, message='Server error'), 500

@app.route('/module/<int:module_id>/quiz')
@login_required
def module_quiz(module_id):
    """Render the quiz player for a module."""
    m = db.session.get(Module, module_id)
    if not m:
        from flask import abort
        return abort(404)
    # Optional course context (new model) or infer from module_type
    course = None
    try:
        if m.course_id:
            course = db.session.get(Course, m.course_id)
        if not course and m.module_type:
            course = Course.query.filter(Course.code.ilike(m.module_type)).first()
    except Exception:
        course = None
    # Fetch/create user progress row (do not mark completed here)
    user_module = None
    try:
        if isinstance(current_user, User):
            user_module = UserModule.query.filter_by(user_id=current_user.User_id, module_id=m.module_id).first()
    except Exception:
        user_module = None
    return render_template('quiz_take.html', module=m, course=course, user_module=user_module)

# --- QUIZ API HELPERS ---
import json as _json


def _parse_quiz_json(raw):
    """Robustly parse/normalize stored quiz JSON.
    Accepts:
      - JSON string (list or dict)
      - Python list or dict (if DB column is JSON type)
      - bytes/bytearray
    Normalized output: list[ { 'text': str, 'answers': [ {'text':str, 'isCorrect':bool}, ... ] } ]
    """
    # Empty/None => no quiz
    if raw is None or raw == '':
        return []

    data = raw
    # Decode bytes and try JSON
    if isinstance(raw, (bytes, bytearray)):
        try:
            data = _json.loads(raw.decode('utf-8'))
        except Exception:
            return []
    elif isinstance(raw, str):
        # If it's a string, try to parse JSON; if it fails, consider no quiz
        try:
            data = _json.loads(raw)
        except Exception:
            return []

    normalized = []

    # Helper to normalize an answer entry to dict
    def norm_answer(a):
        if isinstance(a, dict):
            text = str(a.get('text', '')).strip()
            is_correct = bool(a.get('isCorrect') or a.get('correct') or a.get('is_correct') or False)
            return {'text': text, 'isCorrect': is_correct}
        # if answer is a string or other primitive, assume incorrect
        return {'text': str(a).strip(), 'isCorrect': False}

    # If it's already a list of questions
    if isinstance(data, list):
        for item in data:
            if not item:
                continue
            q_text = ''
            answers = []
            if isinstance(item, dict):
                q_text = str(item.get('text') or item.get('question') or '').strip()
                raw_answers = item.get('answers') or item.get('choices') or item.get('options') or []
                if isinstance(raw_answers, list):
                    answers = [norm_answer(a) for a in raw_answers if str(a).strip() != '']
            elif isinstance(item, str):
                q_text = item.strip()
                answers = []
            if q_text and answers:
                normalized.append({'text': q_text, 'answers': answers})
        return normalized

    # Legacy flat dict parser (e.g., keys q1, q1_a1, q1_a1_correct)
    if isinstance(data, dict):
        # Newer nested structure: { "questions": [ { question, answers, correct }, ... ] }
        try:
            questions_list = None
            if isinstance(data.get('questions'), list):
                questions_list = data.get('questions')
            elif isinstance(data.get('quiz'), list):
                questions_list = data.get('quiz')
            elif isinstance(data.get('items'), list):
                questions_list = data.get('items')
            if questions_list is not None:
                for q in questions_list:
                    if not isinstance(q, dict):
                        # Allow simple strings as questions (no answers)
                        if isinstance(q, str) and q.strip():
                            # skip since no answers provided
                            continue
                        else:
                            continue
                    q_text = str(q.get('text') or q.get('question') or '').strip()
                    raw_answers = q.get('answers') or q.get('choices') or q.get('options') or []
                    # Normalize answers, which may be strings
                    ans = []
                    if isinstance(raw_answers, list):
                        ans = [norm_answer(a) for a in raw_answers if str(a).strip() != '']
                    # Mark correct answer by index if provided
                    correct_val = q.get('correct')
                    if correct_val is None:
                        correct_val = q.get('correctIndex') if q.get('correctIndex') is not None else q.get('correct_index')
                    cidx = None
                    # Accept ints or numeric strings; support 1-based and 0-based
                    try:
                        if isinstance(correct_val, str) and correct_val.strip().isdigit():
                            correct_val = int(correct_val.strip())
                        if isinstance(correct_val, (int, float)):
                            ci = int(correct_val)
                            if ans:
                                if 1 <= ci <= len(ans):
                                    cidx = ci - 1
                                elif 0 <= ci < len(ans):
                                    cidx = ci
                    except Exception:
                        cidx = None
                    if ans and cidx is not None and 0 <= cidx < len(ans):
                        # Reset all flags then set the correct one
                        for i in range(len(ans)):
                            ans[i]['isCorrect'] = (i == cidx)
                    if q_text and ans:
                        normalized.append({'text': q_text, 'answers': ans})
                return normalized
        except Exception:
            # Fall through to legacy flat dict parser below
            pass

        grouped = {}
        for k, v in data.items():
            kstr = str(k)
            # q1 -> question text
            m = re.match(r'^\s*q(\d+)\s*$', kstr, re.I)
            if m:
                idx = int(m.group(1))
                grouped.setdefault(idx, {})['text'] = str(v).strip() if v is not None else ''
                continue
            # q1_a1 or q1_answer1 -> answer text
            m = re.match(r'^\s*q(\d+)[\._-]*a(?:nswer)?(\d+)\s*$', kstr, re.I)
            if m:
                qi = int(m.group(1)); ai = int(m.group(2))
                grp = grouped.setdefault(qi, {})
                ans_list = grp.setdefault('answers', {})
                ans_list[ai] = {'text': str(v).strip() if v is not None else '', 'isCorrect': ans_list.get(ai, {}).get('isCorrect', False)}
                continue
            # q1_a1_correct or q1_a1_isCorrect
            m = re.match(r'^\s*q(\d+)[\._-]*a(\d+)[\._-]*(correct|iscorrect|is_correct|true)\s*$', kstr, re.I)
            if m:
                qi = int(m.group(1)); ai = int(m.group(2))
                grp = grouped.setdefault(qi, {})
                ans_list = grp.setdefault('answers', {})
                entry = ans_list.setdefault(ai, {})
                try:
                    sval = str(v).strip().lower() if v is not None else 'true'
                except Exception:
                    sval = 'true'
                entry['isCorrect'] = sval in ('1', 'true', 'yes', 'y', 'on')
                continue

        for qk in sorted(grouped.keys()):
            g = grouped[qk]
            q_text = str(g.get('text', '')).strip()
            answers_map = g.get('answers', {})
            answers = []
            for aidx in sorted(answers_map.keys()):
                a = answers_map[aidx]
                text = str(a.get('text', '')).strip()
                is_correct = bool(a.get('isCorrect', False))
                if text:
                    answers.append({'text': text, 'isCorrect': is_correct})
            if q_text and answers:
                normalized.append({'text': q_text, 'answers': answers})
        return normalized

    # Unknown structure
    return []

@app.route('/api/load_quiz/<int:module_id>')
@login_required
def api_load_quiz(module_id):
    m = db.session.get(Module, module_id)
    if not m:
        return jsonify({'success': False, 'message': 'Module not found'}), 404

    raw = getattr(m, 'quiz_json', None)
    # Log raw DB value and its type to help debugging
    try:
        preview = raw if isinstance(raw, (str, int, float, bool, list, dict, type(None))) else '[non-primitive]'
    except Exception:
        preview = '[unserializable]'
    logging.debug('[API LOAD QUIZ] module_id=%s raw_type=%s raw_value=%s', module_id, type(raw).__name__, preview)

    quiz = _parse_quiz_json(raw)
    logging.debug('[API LOAD QUIZ] parsed_count=%d', len(quiz))

    payload = {'success': True, 'quiz': quiz}
    if app.debug:
        # include raw only in debug mode
        payload['raw'] = preview
    return jsonify(payload)

@app.route('/api/save_quiz_answers/<int:module_id>', methods=['POST'])
@login_required
def api_save_quiz_answers(module_id):
    try:
        # Only regular users persist quiz answers
        if not isinstance(current_user, User):
            return jsonify(success=False, message='Only users can save answers'), 403
        m = db.session.get(Module, module_id)
        if not m:
            return jsonify(success=False, message='Module not found'), 404
        payload = request.get_json(silent=True) or {}
        answers = payload.get('answers')
        if not isinstance(answers, list):
            return jsonify(success=False, message='Invalid answers payload'), 400
        # Ensure a UserModule row exists
        um = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module_id).first()
        if not um:
            um = UserModule(user_id=current_user.User_id, module_id=module_id, is_completed=False)
            db.session.add(um)
        # Persist as JSON text
        try:
            um.quiz_answers = json.dumps(answers)
        except Exception:
            return jsonify(success=False, message='Failed to serialize answers'), 400
        db.session.commit()
        return jsonify(success=True)
    except Exception:
        logging.exception('[API SAVE QUIZ ANSWERS] Failed')
        db.session.rollback()
        return jsonify(success=False, message='Server error'), 500


@app.route('/api/user_quiz_answers/<int:module_id>')
@login_required
def api_get_user_quiz_answers(module_id):
    try:
        if not isinstance(current_user, User):
            return jsonify([])
        um = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module_id).first()
        if not um or not um.quiz_answers:
            return jsonify([])
        try:
            data = json.loads(um.quiz_answers)
            if isinstance(data, list):
                return jsonify(data)
        except Exception:
            pass
        return jsonify([])
    except Exception:
        logging.exception('[API GET QUIZ ANSWERS] Failed')
        return jsonify([])


@app.route('/api/submit_quiz/<int:module_id>', methods=['POST'])
@login_required
def api_submit_quiz(module_id):
    try:
        if not isinstance(current_user, User):
            return jsonify(success=False, message='Only users can submit quizzes'), 403
        m = db.session.get(Module, module_id)
        if not m:
            return jsonify(success=False, message='Module not found'), 404
        quiz = _parse_quiz_json(getattr(m, 'quiz_json', None))
        if not quiz:
            return jsonify(success=False, message='No quiz available for this module'), 404
        payload = request.get_json(silent=True) or {}
        answers = payload.get('answers') or []
        is_reattempt = bool(payload.get('is_reattempt'))
        # Compute correct indices for each question
        correct_indices = []
        for q in quiz:
            idx = None
            ans_list = q.get('answers') or []
            for i, a in enumerate(ans_list):
                if isinstance(a, dict) and a.get('isCorrect'):
                    idx = i
                    break
            correct_indices.append(idx)
        total = len(correct_indices)
        # Compare up to min length
        correct = 0
        for i in range(min(len(answers), total)):
            try:
                sel = answers[i]
                if isinstance(sel, str) and sel.isdigit():
                    sel = int(sel)
                if isinstance(sel, (int, float)):
                    if correct_indices[i] is not None and int(sel) == int(correct_indices[i]):
                        correct += 1
            except Exception:
                continue
        score_pct = int(round((correct / total) * 100)) if total else 0
        # Upsert UserModule row and persist
        um = UserModule.query.filter_by(user_id=current_user.User_id, module_id=module_id).first()
        if not um:
            um = UserModule(user_id=current_user.User_id, module_id=module_id)
            db.session.add(um)
        # Increment reattempt count if explicitly flagged
        if is_reattempt:
            try:
                um.reattempt_count = (um.reattempt_count or 0) + 1
            except Exception:
                um.reattempt_count = 1
        # Save answers, completion, score (keep best score)
        try:
            um.quiz_answers = json.dumps(answers)
        except Exception:
            pass
        um.is_completed = True
        um.completion_date = datetime.now(UTC)
        if um.score is None or score_pct > int(um.score):
            um.score = score_pct
        db.session.commit()
        # Grade letter derived from per-module reattempt_count
        grade_letter = um.get_grade_letter() if hasattr(um, 'get_grade_letter') else 'A'
        return jsonify(success=True, score=score_pct, total=total, correct=correct, grade_letter=grade_letter, reattempt_count=(um.reattempt_count or 0))
    except Exception:
        logging.exception('[API SUBMIT QUIZ] Failed')
        db.session.rollback()
        return jsonify(success=False, message='Server error'), 500

# --- User profile update API (supports remarks) ---
@app.route('/api/user/update', methods=['PATCH'])
@login_required
def api_user_update():
    try:
        if not isinstance(current_user, User):
            return jsonify(success=False, error='Only users can update their profile'), 403
        payload = request.get_json(silent=True) or {}
        allowed = ('full_name','email','visa_number','visa_expiry_date','state','postcode','remarks','address')
        changes = {}
        for k in allowed:
            if k in payload:
                changes[k] = payload.get(k)
        # Basic validation
        if 'email' in changes:
            email = (changes.get('email') or '').strip().lower()
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
                return jsonify(success=False, error='Invalid email format'), 400
            # Ensure uniqueness for other accounts
            exists = User.query.filter(User.email == email, User.User_id != current_user.User_id).first()
            if exists:
                return jsonify(success=False, error='Email is already in use'), 400
            current_user.email = email
        if 'full_name' in changes and changes.get('full_name') is not None:
            current_user.full_name = str(changes.get('full_name')).strip()
        if 'visa_number' in changes:
            current_user.visa_number = (changes.get('visa_number') or '').strip()
        if 'visa_expiry_date' in changes:
            # Accept YYYY-MM-DD or empty
            dt = safe_parse_date(changes.get('visa_expiry_date'))
            current_user.visa_expiry_date = dt
        if 'state' in changes:
            current_user.state = (changes.get('state') or '').strip()
        if 'postcode' in changes:
            current_user.postcode = (changes.get('postcode') or '').strip()
        if 'address' in changes:
            current_user.address = (changes.get('address') or '').strip()
        if 'remarks' in changes:
            # Free text; store as-is (trim length lightly)
            txt = changes.get('remarks')
            if isinstance(txt, str) and len(txt) > 5000:
                txt = txt[:5000]
            current_user.remarks = txt
        db.session.commit()
        return jsonify(success=True)
    except Exception:
        logging.exception('[API USER UPDATE] Failed')
        db.session.rollback()
        return jsonify(success=False, error='Server error'), 500

# --- Certificate star rating API ---
@app.route('/api/certificate/<int:certificate_id>/rate', methods=['POST'])
@login_required
def api_rate_certificate(certificate_id):
    try:
        cert = db.session.get(Certificate, certificate_id)
        if not cert:
            return jsonify(success=False, error='Certificate not found'), 404
        # Only the owner user can rate their certificate
        if not isinstance(current_user, User) or cert.user_id != current_user.User_id:
            return jsonify(success=False, error='Forbidden'), 403
        data = request.get_json(silent=True) or {}
        rating = data.get('rating')
        try:
            rating = int(rating)
        except Exception:
            return jsonify(success=False, error='Invalid rating'), 400
        if rating < 1 or rating > 5:
            return jsonify(success=False, error='Rating must be between 1 and 5'), 400
        cert.star_rating = rating
        db.session.commit()
        return jsonify(success=True, rating=rating)
    except Exception:
        logging.exception('[API RATE CERTIFICATE] Failed')
        db.session.rollback()
        return jsonify(success=False, error='Server error'), 500

@app.route('/upload_content', methods=['GET', 'POST'])
@login_required
def upload_content():
    """Trainer-facing content upload endpoint. Renders a form to upload slides, add YouTube URL, or save a quiz.
    POST will handle basic validation and persist files to UPLOAD_CONTENT_FOLDER and update Module fields.
    """
    # Only trainers (or admins) should access this; existing project uses 'Trainer' role check elsewhere
    try:
        # Gather modules available to the trainer (simple approach: show all modules)
        modules = Module.query.order_by(Module.module_name).all()
    except Exception:
        modules = []

    if request.method == 'GET':
        # Render upload form
        return render_template('upload_content.html', modules=[m.to_dict() for m in modules])

    # POST - process submitted content
    module_id = request.form.get('module_id') or request.form.get('module')
    content_type = request.form.get('content_type')
    if not module_id:
        flash('Please select a module.', 'danger')
        return redirect(url_for('upload_content'))

    module = db.session.get(Module, module_id)
    if not module:
        flash('Selected module not found.', 'danger')
        return redirect(url_for('upload_content'))

    # Handle slide upload
    if content_type == 'slide' or 'slide_file' in request.files:
        slide = request.files.get('slide_file')
        if slide and slide.filename:
            filename = secure_filename(slide.filename)
            # Ensure extension allowed
            if not is_slide_file(filename):
                flash('Slide must be a PDF or PPTX file.', 'danger')
                return redirect(url_for('upload_content'))
            # Avoid collisions by prefixing timestamp
            name, ext = os.path.splitext(filename)
            safe_name = f"{int(datetime.utcnow().timestamp())}_{name}{ext}"
            # Save into the configured uploads folder under the app root to match serving logic
            dest_dir = os.path.join(app.root_path, UPLOAD_CONTENT_FOLDER)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, safe_name)
            try:
                slide.save(dest)
                # Save relative path/filename to module.slide_url
                module.slide_url = safe_name
                db.session.commit()
                flash('Slide uploaded successfully.', 'success')
            except Exception as e:
                db.session.rollback()
                logging.exception('Failed to save slide file')
                flash('Failed to save slide file.', 'danger')
                return redirect(url_for('upload_content'))
        else:
            flash('No slide file selected.', 'warning')

    # Handle YouTube URL
    if content_type == 'video' or request.form.get('youtube_url'):
        youtube_url = request.form.get('youtube_url')
        if youtube_url:
            # Basic extract/validation
            vid = extract_youtube_id(youtube_url)
            if not vid:
                flash('Invalid YouTube URL provided.', 'danger')
                return redirect(url_for('upload_content'))
            module.youtube_url = youtube_url.strip()
            try:
                db.session.commit()
                flash('YouTube URL saved.', 'success')
            except Exception:
                db.session.rollback()
                flash('Failed to save YouTube URL.', 'danger')
                return redirect(url_for('upload_content'))

    # Handle Quiz content
    if content_type == 'quiz' or any(k.startswith('quiz_question_') for k in request.form.keys()):
        # Build quiz JSON from form fields
        quiz = {'questions': []}
        try:
            # Determine how many questions were supplied (max 5)
            for qn in range(1, 6):
                qtext = request.form.get(f'quiz_question_{qn}')
                if not qtext:
                    continue
                answers = []
                for an in range(1, 6):
                    a = request.form.get(f'answer_{qn}_{an}')
                    if a:
                        answers.append(a)
                correct = request.form.get(f'correct_answer_{qn}')
                try:
                    correct_idx = int(correct) - 1 if correct else None
                except Exception:
                    correct_idx = None
                quiz['questions'].append({
                    'question': qtext,
                    'answers': answers,
                    'correct_index': correct_idx
                })
            module.quiz_json = json.dumps(quiz)
            db.session.commit()
            flash('Quiz saved to module.', 'success')
        except Exception:
            db.session.rollback()
            logging.exception('Failed to save quiz')
            flash('Failed to save quiz content.', 'danger')
            return redirect(url_for('upload_content'))

    # After processing, redirect back to trainer portal
    return redirect(url_for('trainer_portal'))

@app.route('/onboarding/<int:id>', methods=['GET', 'POST'])
def onboarding(id):
    step = request.args.get('step', 1, type=int)
    total_steps = 4
    # Load onboarding user record via session.get
    user = db.session.get(User, id)
    if not user:
        from flask import abort
        return abort(404)
    malaysian_states = [
        "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang", "Penang", "Perak", "Perlis", "Sabah", "Sarawak", "Selangor", "Terengganu", "Kuala Lumpur", "Labuan", "Putrajaya"
    ]
    if request.method == 'POST':
        # Step 1: Personal Details
        if step == 1:
            user.full_name = request.form.get('full_name', user.full_name)
            user.user_category = request.form.get('user_category', user.user_category)
            user.ic_number = request.form.get('ic_number', user.ic_number)
            user.passport_number = request.form.get('passport_number', user.passport_number)
            user.state = request.form.get('state', user.state)
        # Step 2: Contact Details
        elif step == 2:
            user.emergency_contact_phone = request.form.get('emergency_contact_phone', user.emergency_contact_phone)
            user.postcode = request.form.get('postcode', user.postcode)
            user.address = request.form.get('address', user.address)
            user.state = request.form.get('state', user.state)
        # Step 3: Work Details
        elif step == 3:
            user.current_workplace = request.form.get('current_workplace', user.current_workplace)
            # Parse recruitment_date safely using helper
            recruitment_val = request.form.get('recruitment_date')
            user.recruitment_date = safe_parse_date(recruitment_val)
            # Work histories handled separately if needed
        # Step 4: Emergency Contact
        elif step == 4:
            user.emergency_contact_name = request.form.get('emergency_contact_name', user.emergency_contact_name)
            user.emergency_contact_relationship = request.form.get('emergency_contact_relationship', user.emergency_contact_relationship)
            user.emergency_contact_phone = request.form.get('emergency_contact_phone', user.emergency_contact_phone)
        # Use the module-level `db` imported at top of file
        db.session.commit()
        if 'skip' in request.form:
            return redirect(url_for('user_dashboard'))
        next_step = step + 1 if step < total_steps else total_steps
        return redirect(url_for('onboarding', id=id, step=next_step))
    return render_template('onboarding.html', id=id, step=step, total_steps=total_steps, user=user, malaysian_states=malaysian_states)

# --- Debug/health endpoints to diagnose routing in dev ---
@app.route('/__health')
def __health():
    try:
        return jsonify(ok=True, app='training-system', time=datetime.utcnow().isoformat(), routes_count=len(list(app.url_map.iter_rules())))
    except Exception:
        return jsonify(ok=False), 500

@app.route('/__routes')
def __routes():
    try:
        rules = []
        for r in app.url_map.iter_rules():
            rules.append({
                'rule': r.rule,
                'methods': sorted(list(r.methods or [])),
                'endpoint': r.endpoint,
            })
        # Sort for stable output
        rules.sort(key=lambda x: x['rule'])
        return jsonify(routes=rules, count=len(rules))
    except Exception:
        return jsonify(routes=[], count=0), 500

@app.route('/__whoami')
def __whoami():
    try:
        return jsonify(
            server='training-system-2',
            host=request.host,
            path=request.path,
            remote_addr=request.remote_addr,
            time=datetime.utcnow().isoformat()
        )
    except Exception:
        return jsonify(server='training-system-2'), 200

@app.route('/index')
def index_redirect():
    return redirect(url_for('index'))

@app.route('/index.html')
def index_html_redirect():
    return redirect(url_for('index'))

@app.route('/home')
def home_redirect():
    return redirect(url_for('index'))

@app.route('/favicon.ico')
def favicon():
    try:
        # Prefer favicon in static/ if present
        static_dir = app.static_folder or 'static'
        for name in ('favicon.ico', 'favicon.png'):
            candidate = os.path.join(static_dir, name)
            if os.path.exists(candidate):
                return send_from_directory(static_dir, name)
        # No favicon available; return empty
        return ('', 204)
    except Exception:
        return ('', 204)

@app.errorhandler(404)
def _handle_404(e):
    try:
        p = (request.path or '').strip()
    except Exception:
        p = ''
    # API requests keep JSON 404
    if p.startswith('/api/'):
        return jsonify(success=False, error='Not found', path=p), 404
    # For common root-like paths, render the home page directly
    if p in ('', '/', '/index', '/index.html', '/home'):
        try:
            return render_template('index.html'), 200
        except Exception:
            # Fallback minimal text in case template missing
            return 'Home', 200
    # For other paths, show a simple not found page with a link home
    return render_template('404.html') if os.path.exists(os.path.join(app.template_folder or 'templates','404.html')) else ("Not Found. Go to /", 404)

# Final catch-all for non-API GETs to improve SPA-like navigation and avoid confusing 404s on root
@app.route('/<path:any_path>', methods=['GET'])
def _fallback_spa(any_path):
    # Allow static and uploads to proceed to their own handlers
    if any_path.startswith(('static/', 'uploads/', 'slides/')):
        from flask import abort
        return abort(404)
    # APIs should not be handled here
    if any_path.startswith('api/'):
        from flask import abort
        return abort(404)
    # Render index for other GETs (acts like basic SPA fallback)
    try:
        return render_template('index.html'), 200
    except Exception:
        return 'Home', 200

# Optional request logging for diagnostics (enable with LOG_REQUESTS=1)
ENABLE_REQUEST_LOG = os.environ.get('LOG_REQUESTS', '0') in ('1', 'true', 'True', 'yes', 'on')

@app.before_request
def _log_request_line():
    if ENABLE_REQUEST_LOG:
        try:
            print(f"[REQ] {request.method} {request.host}{request.full_path} from {request.remote_addr}")
        except Exception:
            pass

if __name__ == '__main__':
    # Allow direct execution: python app.py
    try:
        host = os.environ.get('HOST', '0.0.0.0')
        try:
            port = int(os.environ.get('PORT', '5050'))
        except Exception:
            port = 5050
        debug = os.environ.get('FLASK_DEBUG', '0') in ('1', 'true', 'True', 'yes', 'on')
        print('=' * 60)
        print('TRAINING SYSTEM - Flask server (app.py)')
        print('=' * 60)
        print(f'Listening on http://{host}:{port}  (debug={debug})')
        print('Press Ctrl+C to stop')
        print('=' * 60)
        app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=debug)
    except KeyboardInterrupt:
        pass

