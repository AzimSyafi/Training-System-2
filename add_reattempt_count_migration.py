"""
Migration to add reattempt_count column to user_module table
"""
from models import db
import sqlite3
import os

def add_reattempt_count_column():
    """Add reattempt_count column to user_module table"""
    try:
        # Get the correct database path
        db_path = os.path.join('instance', 'security_training.db')

        # Check if database file exists
        if not os.path.exists(db_path):
            print(f"Database file not found at: {db_path}")
            return False

        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(user_module)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'reattempt_count' not in columns:
            # Add the reattempt_count column with default value 0
            cursor.execute("ALTER TABLE user_module ADD COLUMN reattempt_count INTEGER DEFAULT 0")
            conn.commit()
            print("Successfully added reattempt_count column to user_module table")

            # Update existing records to have reattempt_count = 0
            cursor.execute("UPDATE user_module SET reattempt_count = 0 WHERE reattempt_count IS NULL")
            conn.commit()
            print("Updated existing records with default reattempt_count = 0")

        else:
            print("reattempt_count column already exists in user_module table")

        # Verify the column was added
        cursor.execute("PRAGMA table_info(user_module)")
        columns_after = [column[1] for column in cursor.fetchall()]
        print(f"Current columns in user_module table: {columns_after}")

        conn.close()
        return True

    except Exception as e:
        print(f"Error adding reattempt_count column: {e}")
        return False

if __name__ == "__main__":
    print("Starting migration to add reattempt_count column...")
    success = add_reattempt_count_column()
    if success:
        print("Migration completed successfully!")
    else:
        print("Migration failed!")
