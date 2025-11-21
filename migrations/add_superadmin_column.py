"""
Database migration script to add is_superadmin column to admin table.

This script adds the is_superadmin boolean column to support superadmin role differentiation.
Run this migration after updating the Admin model in models.py.

Usage:
    python migrations/add_superadmin_column.py
"""

import sys
from pathlib import Path

# Add the parent directory to the path to import app modules
app_dir = Path(__file__).resolve().parent.parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from app import app, db
from sqlalchemy import text

def add_superadmin_column():
    """Add is_superadmin column to admin table."""
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='admin' AND column_name='is_superadmin'
            """))
            
            if result.fetchone():
                print("✓ Column 'is_superadmin' already exists in admin table.")
                return
            
            # Add the column
            print("Adding is_superadmin column to admin table...")
            db.session.execute(text("""
                ALTER TABLE admin 
                ADD COLUMN is_superadmin BOOLEAN NOT NULL DEFAULT FALSE
            """))
            db.session.commit()
            print("✓ Successfully added is_superadmin column to admin table.")
            print()
            print("Migration completed successfully!")
            print()
            print("Next steps:")
            print("1. Use create_admin.py to create a superadmin account")
            print("2. Or promote an existing admin to superadmin using:")
            print("   UPDATE admin SET is_superadmin = TRUE WHERE admin_id = <id>;")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Error during migration: {str(e)}")
            raise

if __name__ == '__main__':
    add_superadmin_column()
