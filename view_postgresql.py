#!/usr/bin/env python3
"""
Quick PostgreSQL database viewer script
Shows tables and row counts from your database
"""

import psycopg
import os
from tabulate import tabulate

# Get DATABASE_URL from environment
DATABASE_URL = os.environ.get('DATABASE_URL')

def connect_postgresql():
    """Connect to PostgreSQL database"""
    if not DATABASE_URL:
        print("❌ Please set DATABASE_URL environment variable")
        print("Example:")
        print('set DATABASE_URL="postgresql://username:password@hostname:port/database"')
        return None

    # Handle postgres:// vs postgresql:// URL scheme
    db_url = DATABASE_URL
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    try:
        return psycopg.connect(db_url)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None

def show_database_info():
    """Display database information"""
    conn = connect_postgresql()
    if not conn:
        return

    print("🔗 Connected to PostgreSQL database!")
    print("=" * 50)

    cursor = conn.cursor()

    # Show all tables
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)

    tables = cursor.fetchall()

    if not tables:
        print("📋 No tables found in database")
        return

    print(f"📋 Found {len(tables)} tables:")
    print("-" * 30)

    table_info = []

    for (table_name,) in tables:
        try:
            # Get row count
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            row_count = cursor.fetchone()[0]

            # Get column info
            cursor.execute(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                ORDER BY ordinal_position
                LIMIT 5;
            """)
            columns = cursor.fetchall()
            column_names = [col[0] for col in columns]

            table_info.append([
                table_name,
                row_count,
                ', '.join(column_names[:3]) + ('...' if len(column_names) > 3 else '')
            ])

        except Exception as e:
            table_info.append([table_name, "Error", str(e)[:30]])

    # Display table information
    headers = ["Table", "Rows", "Sample Columns"]
    print(tabulate(table_info, headers=headers, tablefmt="grid"))

    print("\n" + "=" * 50)
    print("✅ Database overview complete!")
    print("\n💡 Tips:")
    print("1. Use pgAdmin for visual database management")
    print("2. Use 'psql' command line for SQL queries")
    print("3. Install PostgreSQL tools locally for better experience")

    conn.close()

def show_sample_data(table_name, limit=5):
    """Show sample data from a specific table"""
    conn = connect_postgresql()
    if not conn:
        return

    cursor = conn.cursor()

    try:
        cursor.execute(f'SELECT * FROM "{table_name}" LIMIT {limit}')
        rows = cursor.fetchall()

        # Get column names
        cursor.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' 
            ORDER BY ordinal_position;
        """)
        columns = [col[0] for col in cursor.fetchall()]

        print(f"\n📊 Sample data from '{table_name}' table:")
        print("-" * 50)

        if rows:
            print(tabulate(rows, headers=columns, tablefmt="grid"))
        else:
            print("No data found in table")

    except Exception as e:
        print(f"❌ Error reading table {table_name}: {e}")

    conn.close()

if __name__ == "__main__":
    print("🐘 PostgreSQL Database Viewer")
    print("=" * 50)

    # Show database overview
    show_database_info()

    # Show sample data from key tables
    key_tables = ['admin', 'user', 'agency', 'module']

    for table in key_tables:
        show_sample_data(table)

    print("\n🎉 Done! Use pgAdmin for detailed database exploration.")
