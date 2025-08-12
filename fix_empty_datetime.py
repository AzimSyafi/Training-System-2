"""
Simple database fix for datetime issue.
Run this script to fix empty string values in completion_date field.
"""

import sqlite3
import os

def fix_empty_datetime_strings():
    db_path = os.path.join('instance', 'security_training.db')
    
    if not os.path.exists(db_path):
        print(f"Database file not found at {db_path}")
        return
    
    try:
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("Checking for empty completion_date strings...")
        
        # Find rows with empty strings in completion_date
        cursor.execute("SELECT COUNT(*) FROM user_module WHERE completion_date = ''")
        count = cursor.fetchone()[0]
        print(f"Found {count} rows with empty completion_date strings")
        
        if count > 0:
            # Update empty strings to NULL
            cursor.execute("UPDATE user_module SET completion_date = NULL WHERE completion_date = ''")
            conn.commit()
            print(f"Fixed {count} rows by setting empty completion_date to NULL")
        else:
            print("No empty completion_date strings found")
        
        # Also check for whitespace-only strings
        cursor.execute("SELECT COUNT(*) FROM user_module WHERE completion_date IS NOT NULL AND TRIM(completion_date) = ''")
        whitespace_count = cursor.fetchone()[0]
        
        if whitespace_count > 0:
            cursor.execute("UPDATE user_module SET completion_date = NULL WHERE completion_date IS NOT NULL AND TRIM(completion_date) = ''")
            conn.commit()
            print(f"Fixed {whitespace_count} rows with whitespace-only completion_date")
        
        conn.close()
        print("Database fix completed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    fix_empty_datetime_strings()
