"""
Migration: Add dark_mode_enabled column to all user tables
This fixes the bug where dark mode affects all users on the same browser
"""
import os
import sys

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from sqlalchemy import text

def add_dark_mode_column():
    """Add dark_mode_enabled column to all user tables"""
    
    with app.app_context():
        from models import db
        
        tables = ['admin', 'user', 'trainer', 'agency_account']
        
        for table in tables:
            try:
                # Check if column already exists
                result = db.session.execute(text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='{table}' AND column_name='dark_mode_enabled';
                """))
                
                if result.fetchone() is None:
                    # Add column with default FALSE
                    print(f"Adding dark_mode_enabled column to {table}...")
                    db.session.execute(text(f"""
                        ALTER TABLE "{table}"
                        ADD COLUMN dark_mode_enabled BOOLEAN DEFAULT FALSE NOT NULL;
                    """))
                    db.session.commit()
                    print(f"✓ Successfully added dark_mode_enabled to {table}")
                else:
                    print(f"⊙ Column dark_mode_enabled already exists in {table}")
                    
            except Exception as e:
                print(f"✗ Error adding column to {table}: {e}")
                db.session.rollback()
        
        print("\n✓ Migration completed!")

if __name__ == '__main__':
    add_dark_mode_column()
