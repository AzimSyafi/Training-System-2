"""
Migration script to add certificate_template table for customizable field positions.
Run this script to update your database with the new table.
Compatible with PostgreSQL.
"""

from flask_app import app
from models import db
from sqlalchemy import text

def migrate():
    with app.app_context():
        # Create the certificate_template table for PostgreSQL
        try:
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
            print("✓ Certificate template table created successfully!")
        except Exception as e:
            print(f"Error creating table: {e}")
            db.session.rollback()

        # Create default template if none exists
        from models import CertificateTemplate
        try:
            if not CertificateTemplate.query.first():
                default_template = CertificateTemplate(name='Default Template')
                db.session.add(default_template)
                db.session.commit()
                print("✓ Default certificate template created!")
            else:
                print("✓ Certificate template already exists!")
        except Exception as e:
            print(f"Error creating default template: {e}")
            db.session.rollback()

        print("\nMigration completed successfully!")

if __name__ == '__main__':
    migrate()
