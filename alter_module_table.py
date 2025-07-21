import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'security_training.db')

def add_slide_url_column():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Check if the column already exists
    cursor.execute("PRAGMA table_info(module)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'slide_url' not in columns:
        cursor.execute("ALTER TABLE module ADD COLUMN slide_url VARCHAR(255)")
        print("slide_url column added to module table.")
    else:
        print("slide_url column already exists.")
    conn.commit()
    conn.close()

if __name__ == '__main__':
    add_slide_url_column()

