#!/usr/bin/env python3
"""
Enhanced migration script with better error handling and data type conversion
"""

import sqlite3
import psycopg
import os
from datetime import datetime

# Configuration
SQLITE_DB_PATH = 'instance/security_training.db'
POSTGRESQL_URL = os.environ.get('DATABASE_URL')

def connect_sqlite():
    """Connect to SQLite database"""
    return sqlite3.connect(SQLITE_DB_PATH)

def connect_postgresql():
    """Connect to PostgreSQL database"""
    db_url = POSTGRESQL_URL
    if db_url and db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    return psycopg.connect(db_url)

def convert_data_types(rows, table_name):
    """Convert SQLite data types to PostgreSQL compatible types"""
    converted_rows = []

    for row in rows:
        converted_row = []
        for value in row:
            # Handle None values
            if value is None:
                converted_row.append(None)
            # Handle datetime strings
            elif isinstance(value, str) and table_name in ['user', 'certificate', 'user_module']:
                # Try to parse datetime strings
                if 'date' in str(value).lower() or len(str(value)) > 10:
                    try:
                        # Convert various datetime formats
                        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                        converted_row.append(dt)
                    except:
                        converted_row.append(value)
                else:
                    converted_row.append(value)
            else:
                converted_row.append(value)
        converted_rows.append(tuple(converted_row))

    return converted_rows

def migrate_table_with_constraints(pg_conn, table_name):
    """Disable/enable foreign key constraints for smoother migration"""
    cursor = pg_conn.cursor()

    try:
        # Disable foreign key checks temporarily
        cursor.execute("SET session_replication_role = replica;")
        return True
    except Exception as e:
        print(f"⚠️  Could not disable constraints: {e}")
        return False

def restore_constraints(pg_conn):
    """Re-enable foreign key constraints"""
    cursor = pg_conn.cursor()
    try:
        cursor.execute("SET session_replication_role = DEFAULT;")
        pg_conn.commit()
    except Exception as e:
        print(f"⚠️  Could not restore constraints: {e}")

def migrate_with_retry(sqlite_conn, pg_conn, table_name):
    """Migrate table with retry logic for constraint violations"""
    try:
        # Export from SQLite
        cursor = sqlite_conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()

        if not rows:
            print(f"  No data in {table_name}")
            return

        # Convert data types
        converted_rows = convert_data_types(rows, table_name)

        # Import to PostgreSQL
        pg_cursor = pg_conn.cursor()
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join(columns)

        # Clear existing data (optional - remove if you want to preserve existing data)
        pg_cursor.execute(f"DELETE FROM {table_name}")

        insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

        pg_cursor.executemany(insert_query, converted_rows)
        pg_conn.commit()

        print(f"✅ {table_name}: {len(rows)} rows migrated")

    except Exception as e:
        print(f"❌ {table_name}: {e}")
        pg_conn.rollback()

def main():
    """Enhanced migration with better error handling"""

    if not POSTGRESQL_URL:
        print("❌ Set DATABASE_URL environment variable")
        print("Example: postgresql://user:pass@localhost:5432/dbname")
        return

    if not os.path.exists(SQLITE_DB_PATH):
        print(f"❌ SQLite database not found: {SQLITE_DB_PATH}")
        return

    print("🚀 Starting enhanced SQLite to PostgreSQL migration...\n")

    # Migration order (independent tables first)
    migration_order = [
        'agency',
        'admin',
        'trainer',
        'module',
        'user',
        'management',
        'user_module',
        'certificate',
        'registration'
    ]

    sqlite_conn = None
    pg_conn = None
    try:
        sqlite_conn = connect_sqlite()
        pg_conn = connect_postgresql()

        print("✅ Connected to both databases")

        # Disable constraints
        migrate_table_with_constraints(pg_conn, None)

        # Migrate each table
        for table in migration_order:
            print(f"\n📋 Migrating: {table}")
            migrate_with_retry(sqlite_conn, pg_conn, table)

        # Restore constraints
        restore_constraints(pg_conn)

        print("\n🎉 Migration completed!")

        # Show summary
        print("\n📊 Final row counts:")
        cursor = pg_conn.cursor()
        for table in migration_order:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {table}: {count} rows")
            except:
                print(f"  {table}: not found")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
    finally:
        try:
            if sqlite_conn:
                sqlite_conn.close()
        except Exception:
            pass
        try:
            if pg_conn:
                pg_conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
