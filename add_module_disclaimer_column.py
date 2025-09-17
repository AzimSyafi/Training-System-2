"""
Migration to add module_disclaimer_agreements column to user table
This column will store JSON data tracking which modules a user has agreed to disclaimers for
"""

import os
import sys

def add_module_disclaimer_column():
    """Add module_disclaimer_agreements column to user table"""

    # Add the project root to Python path to import models
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        # Import Flask app and database
        from app import app, db
        from sqlalchemy import text, inspect

        with app.app_context():
            # Check if column already exists
            inspector = inspect(db.engine)
            if inspector.has_table('user'):
                columns = [col['name'] for col in inspector.get_columns('user')]

                if 'module_disclaimer_agreements' in columns:
                    print("Column 'module_disclaimer_agreements' already exists in user table")
                    return True

                try:
                    # Add the new column using PostgreSQL syntax
                    db.session.execute(text("""
                        ALTER TABLE "user" 
                        ADD COLUMN module_disclaimer_agreements TEXT DEFAULT '{}'
                    """))

                    db.session.commit()
                    print("Successfully added module_disclaimer_agreements column to user table")

                    # Verify the column was added
                    inspector = inspect(db.engine)
                    columns = [col['name'] for col in inspector.get_columns('user')]

                    if 'module_disclaimer_agreements' in columns:
                        print("Column addition verified successfully")
                        return True
                    else:
                        print("Failed to verify column addition")
                        return False

                except Exception as e:
                    db.session.rollback()
                    print(f"Database error: {e}")
                    return False
            else:
                print("User table not found")
                return False

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = add_module_disclaimer_column()
    if success:
        print("Migration completed successfully")
    else:
        print("Migration failed")
