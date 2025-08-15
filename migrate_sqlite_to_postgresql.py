#!/usr/bin/env python3
"""
Migration script to transfer data from SQLite to PostgreSQL
Usage: python migrate_sqlite_to_postgresql.py
"""

import sqlite3
import psycopg2
import os
from datetime import datetime
import json

# Configuration
SQLITE_DB_PATH = 'instance/security_training.db'
POSTGRESQL_URL = os.environ.get('DATABASE_URL')  # Set this environment variable

def connect_sqlite():
    """Connect to SQLite database"""
    return sqlite3.connect(SQLITE_DB_PATH)

def connect_postgresql():
    """Connect to PostgreSQL database"""
    # Handle postgres:// vs postgresql:// URL scheme
    db_url = POSTGRESQL_URL
    if db_url and db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    return psycopg2.connect(db_url)

def export_table_data(sqlite_conn, table_name):
    """Export data from SQLite table"""
    cursor = sqlite_conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    return columns, rows

def import_table_data(pg_conn, table_name, columns, rows):
    """Import data to PostgreSQL table"""
    if not rows:
        print(f"No data to import for table: {table_name}")
        return

    cursor = pg_conn.cursor()

    # Create placeholders for INSERT statement
    placeholders = ', '.join(['%s'] * len(columns))
    columns_str = ', '.join(columns)

    insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

    try:
        cursor.executemany(insert_query, rows)
        pg_conn.commit()
        print(f"✅ Imported {len(rows)} rows to {table_name}")
    except Exception as e:
        print(f"❌ Error importing {table_name}: {e}")
        pg_conn.rollback()

def migrate_data():
    """Main migration function"""
    if not POSTGRESQL_URL:
        print("❌ Please set DATABASE_URL environment variable with your PostgreSQL connection string")
        return

    if not os.path.exists(SQLITE_DB_PATH):
        print(f"❌ SQLite database not found at: {SQLITE_DB_PATH}")
        return

    print("🚀 Starting migration from SQLite to PostgreSQL...")

    # Define tables in dependency order (tables with foreign keys last)
    tables_to_migrate = [
        'agency',
        'admin',
        'module',
        'trainer',
        'user',
        'management',
        'user_module',
        'certificate',
    ]

    try:
        # Connect to both databases
        sqlite_conn = connect_sqlite()
        pg_conn = connect_postgresql()

        print("✅ Connected to both databases")

        # Migrate each table
        for table in tables_to_migrate:
            print(f"\n📋 Migrating table: {table}")

            try:
                columns, rows = export_table_data(sqlite_conn, table)
                import_table_data(pg_conn, table, columns, rows)
            except Exception as e:
                print(f"⚠️  Skipping table {table}: {e}")

        print("\n🎉 Migration completed!")
        print("\n📊 Summary:")

        # Show row counts
        cursor = pg_conn.cursor()
        for table in tables_to_migrate:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {table}: {count} rows")
            except:
                print(f"  {table}: table not found")

    except Exception as e:
        print(f"❌ Migration failed: {e}")

    finally:
        sqlite_conn.close()
        pg_conn.close()
        print("\n🔌 Database connections closed")

if __name__ == "__main__":
    migrate_data()
