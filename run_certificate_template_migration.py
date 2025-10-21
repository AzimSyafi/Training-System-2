"""
Run this script to apply the certificate_template migration to your database.
This will create the table and insert a default template.
"""

import sys
import os

# Add the parent directory to the path so we can import from the project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask_app import app
from models import db
from sqlalchemy import text

def run_migration():
    """Execute the certificate_template table migration"""
    with app.app_context():
        print("=" * 60)
        print("Starting certificate_template migration...")
        print("=" * 60)

        try:
            # Create the certificate_template table
            print("\n1. Creating certificate_template table...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS certificate_template (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL DEFAULT 'Default Template',
                    name_x INTEGER DEFAULT 425,
                    name_y INTEGER DEFAULT 290,
                    name_font_size INTEGER DEFAULT 28,
                    ic_x INTEGER DEFAULT 425,
                    ic_y INTEGER DEFAULT 260,
                    ic_font_size INTEGER DEFAULT 14,
                    course_type_x INTEGER DEFAULT 425,
                    course_type_y INTEGER DEFAULT 230,
                    course_type_font_size INTEGER DEFAULT 14,
                    percentage_x INTEGER DEFAULT 425,
                    percentage_y INTEGER DEFAULT 200,
                    percentage_font_size INTEGER DEFAULT 14,
                    grade_x INTEGER DEFAULT 425,
                    grade_y INTEGER DEFAULT 185,
                    grade_font_size INTEGER DEFAULT 14,
                    text_x INTEGER DEFAULT 425,
                    text_y INTEGER DEFAULT 170,
                    text_font_size INTEGER DEFAULT 12,
                    date_x INTEGER DEFAULT 425,
                    date_y INTEGER DEFAULT 150,
                    date_font_size INTEGER DEFAULT 12,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.session.commit()
            print("   ✓ Table created successfully!")

        except Exception as e:
            print(f"   ⚠ Table might already exist or error: {e}")
            db.session.rollback()

        try:
            # Insert default template
            print("\n2. Inserting default template...")
            result = db.session.execute(text("""
                INSERT INTO certificate_template (name, is_active) 
                VALUES ('Default Template', true)
                RETURNING id
            """))
            db.session.commit()

            # Check if a row was inserted
            row = result.fetchone()
            if row:
                print(f"   ✓ Default template created with ID: {row[0]}")
            else:
                print("   ✓ Default template already exists!")

        except Exception as e:
            # If the insert fails (e.g., duplicate), just check if a template exists
            db.session.rollback()
            print(f"   ⚠ Insert skipped (may already exist): {e}")
            try:
                result = db.session.execute(text("SELECT id FROM certificate_template WHERE name = 'Default Template' LIMIT 1"))
                existing = result.fetchone()
                if existing:
                    print(f"   ✓ Default template already exists with ID: {existing[0]}")
            except:
                pass

        # Verify the table and data
        try:
            print("\n3. Verifying migration...")
            result = db.session.execute(text("SELECT COUNT(*) FROM certificate_template"))
            count = result.scalar()
            print(f"   ✓ Table exists with {count} template(s)")

            result = db.session.execute(text("SELECT * FROM certificate_template LIMIT 1"))
            template = result.fetchone()
            if template:
                print(f"   ✓ Default template: ID={template[0]}, Name='{template[1]}'")
        except Exception as e:
            print(f"   ✗ Verification failed: {e}")
            return False

        print("\n" + "=" * 60)
        print("Migration completed successfully! ✓")
        print("=" * 60)
        print("\nYou can now:")
        print("1. Refresh your application")
        print("2. Access the certificate template editor")
        print("3. Start customizing field positions")
        return True

if __name__ == '__main__':
    try:
        success = run_migration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Migration failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
