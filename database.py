"""
Database helpers and schema guard logic for Training System app.
Extracted from app.py for modularity.
"""
import os
import logging
from sqlalchemy import text, inspect as sa_inspect, create_engine
from models import db, Course, Agency, Module, Trainer, User, UserModule, UserCourseProgress, Certificate, WorkHistory, Admin, Management, AgencyAccount
from datetime import datetime, UTC

def normalize_pg_url_for_sqlalchemy(url: str) -> str:
    """Normalize PostgreSQL URL for SQLAlchemy driver."""
    if not isinstance(url, str) or not url:
        return url
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    driver = None
    try:
        import psycopg
        driver = 'psycopg'
    except Exception:
        try:
            import psycopg2
            driver = 'psycopg2'
        except Exception:
            driver = None
    if url.startswith('postgresql+'):
        return url
    if driver:
        return url.replace('postgresql://', f'postgresql+{driver}://', 1)
    return url

def wait_for_db(engine, seconds: int = 20) -> bool:
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

# Schema guard and initialization logic
def bootstrap_schema_with_advisory_lock(initializer):
    """Runs schema initialization safely with only one worker performing the work."""
    from flask import current_app
    from sqlalchemy import text

    # Only one process should initialize the schema at a time.
    lock_id = f"schema_init_lock"
    with current_app.extensions['sqlalchemy'].db.engine.begin() as conn:
        # Attempt to acquire an advisory lock.
        result = conn.execute(text("SELECT pg_try_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
        if not result.scalar():
            logging.info(f"Schema initialization is already in progress by another worker.")
            return False

    try:
        # Perform the schema initialization.
        initializer()
    finally:
        # Release the advisory lock.
        with current_app.extensions['sqlalchemy'].db.engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_unlock(:lock_id)"), {"lock_id": lock_id})

    return True

def initialize_schema():
    """Idempotent schema initialization for all required tables and columns."""
    from flask import current_app
    from sqlalchemy import text

    # Example: Create tables if they don't exist
    with current_app.extensions['sqlalchemy'].db.engine.begin() as conn:
        # Check and create tables, indexes, etc.
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS example_table (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL
        )
        """))

        # Add more schema initialization logic as needed

    logging.info("Database schema initialized.")

def ensure_minimal_columns_once():
    """Ensure minimal columns exist in user table."""
    from flask import current_app
    from sqlalchemy import text, inspect as sa_inspect

    # Check if the table exists
    inspector = sa_inspect(current_app.extensions['sqlalchemy'].db.engine)
    if 'user' not in inspector.get_table_names():
        # Table doesn't exist, can't check columns, so we assume it's not initialized
        return False

    with current_app.extensions['sqlalchemy'].db.engine.begin() as conn:
        # Check and add columns if they don't exist
        result = conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'user' AND column_name IN ('first_name', 'last_name')
        """))

        existing_columns = {row['column_name'] for row in result}

        if 'first_name' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN first_name VARCHAR(255)"))
            logging.info("Added missing column 'first_name' to 'user' table.")
        if 'last_name' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN last_name VARCHAR(255)"))
            logging.info("Added missing column 'last_name' to 'user' table.")

    return True

# Minimal self-healing initializer compatible with Flask >=3
minimal_schema_done = False
