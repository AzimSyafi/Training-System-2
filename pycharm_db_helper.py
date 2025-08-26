"""
PyCharm-friendly PostgreSQL connection script
Run this in PyCharm's Python Console for interactive database access
"""

import psycopg
import os

# Local PostgreSQL connection settings
DB_USER = 'postgres'  # Change if you created a different user
DB_PASSWORD = 'your_password'  # Replace with your PostgreSQL password
DB_HOST = 'localhost'
DB_PORT = '5432'
DB_NAME = 'training_system_local'  # The database you created

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def quick_connect():
    """Quick connection function for PyCharm console"""
    try:
        conn = psycopg.connect(DATABASE_URL)
        print("✅ Connected to local PostgreSQL!")
        return conn
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("📋 Make sure:")
        print("  1. PostgreSQL is running")
        print("  2. Database 'training_system_local' exists")
        print(f"  3. User '{DB_USER}' has access")
        print("  4. Password is correct")
        return None

def show_tables(conn):
    """Show all tables in database"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT table_name, 
               (SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name = t.table_name) as column_count
        FROM information_schema.tables t
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)

    tables = cursor.fetchall()
    print(f"\n📋 Found {len(tables)} tables:")
    for table_name, col_count in tables:
        print(f"  • {table_name} ({col_count} columns)")

def quick_query(conn, query):
    """Execute a quick query"""
    cursor = conn.cursor()
    cursor.execute(query)
    return cursor.fetchall()

# Example usage:
if __name__ == "__main__":
    print("🐘 PyCharm PostgreSQL Helper")
    print("=" * 40)
    print("1. Update DATABASE_URL variable above")
    print("2. Run: conn = quick_connect()")
    print("3. Run: show_tables(conn)")
    print("4. Run: quick_query(conn, 'SELECT * FROM admin LIMIT 5')")
    print("=" * 40)
