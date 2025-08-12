  #!/usr/bin/env python3

"""
Fix datetime issue in the database where empty strings are stored in datetime fields.
This script will identify and fix empty string values in the completion_date field of user_module table.
"""

from app import app, db
from models import UserModule
import sqlite3

def fix_datetime_issue():
    with app.app_context():
        try:
            # First, let's check the database directly using raw SQL
            print("Checking for problematic datetime values...")

            # Connect to the SQLite database directly
            db_path = 'instance/security_training.db'
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check for empty string values in completion_date
            cursor.execute("SELECT id, user_id, module_id, completion_date FROM user_module WHERE completion_date = ''")
            empty_date_rows = cursor.fetchall()

            print(f"Found {len(empty_date_rows)} rows with empty completion_date strings")
            for row in empty_date_rows:
                print(f"ID: {row[0]}, User ID: {row[1]}, Module ID: {row[2]}, Completion Date: '{row[3]}'")

            # Fix the empty strings by setting them to NULL
            if empty_date_rows:
                print("\nFixing empty completion_date values by setting them to NULL...")
                cursor.execute("UPDATE user_module SET completion_date = NULL WHERE completion_date = ''")
                conn.commit()
                print(f"Updated {cursor.rowcount} rows")

            # Also check for any other potential datetime format issues
            cursor.execute("SELECT id, completion_date FROM user_module WHERE completion_date IS NOT NULL AND completion_date != ''")
            all_dates = cursor.fetchall()

            problematic_dates = []
            for row in all_dates:
                date_str = row[1]
                # Check if it's a valid datetime format
                try:
                    from datetime import datetime
                    if date_str and not date_str.strip():  # whitespace only
                        problematic_dates.append(row)
                    elif date_str and len(date_str) < 10:  # too short to be a valid datetime
                        problematic_dates.append(row)
                except:
                    problematic_dates.append(row)

            if problematic_dates:
                print(f"\nFound {len(problematic_dates)} rows with potentially problematic date formats:")
                for row in problematic_dates:
                    print(f"ID: {row[0]}, Completion Date: '{row[1]}'")

                # Fix these by setting them to NULL as well
                for row in problematic_dates:
                    cursor.execute("UPDATE user_module SET completion_date = NULL WHERE id = ?", (row[0],))
                conn.commit()
                print(f"Fixed {len(problematic_dates)} problematic date entries")

            conn.close()
            print("\nDatabase fix completed successfully!")

        except Exception as e:
            print(f"Error occurred: {e}")
            if 'conn' in locals():
                conn.close()

if __name__ == "__main__":
    fix_datetime_issue()
