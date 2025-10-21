"""
Migration script to add visibility columns to certificate_template table
Run this to update your database schema
"""
import os
import sys

# Set DATABASE_URL if not already set (use your actual connection string)
if not os.environ.get('DATABASE_URL'):
    # Default to the PostgreSQL connection from smoke_test.py
    os.environ['DATABASE_URL'] = 'postgresql://postgres:0789@localhost:5432/Training_system'

from flask import Flask
from models import db
from sqlalchemy import text

app = Flask(__name__)
app.config['SECRET_KEY'] = 'migration-secret-key'

# Use same database configuration as flask_app.py
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///security_training.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

db.init_app(app)

with app.app_context():
    print(f"📊 Connected to database: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")

    try:
        # Add visibility columns for each field
        fields = ['name', 'ic', 'course_type', 'percentage', 'grade', 'text', 'date']

        print("\n🔄 Starting migration...")

        for field in fields:
            column_name = f'{field}_visible'
            try:
                # Try to select the column to check if it exists
                result = db.session.execute(text(f"SELECT {column_name} FROM certificate_template LIMIT 1"))
                result.close()
                print(f"✓ Column {column_name} already exists")
            except Exception as check_error:
                # Column doesn't exist, add it
                print(f"  Adding column {column_name}...")
                try:
                    # PostgreSQL syntax
                    db.session.execute(text(f"ALTER TABLE certificate_template ADD COLUMN {column_name} BOOLEAN DEFAULT TRUE"))
                    db.session.commit()
                    print(f"✅ Successfully added column {column_name}")
                except Exception as e:
                    db.session.rollback()
                    print(f"❌ Failed to add column {column_name}: {str(e)}")

                    # Try to continue with other columns
                    continue

        print("\n" + "="*50)
        print("✅ Migration completed!")
        print("="*50)
        print("\nYou can now use the Certificate Template Editor with field visibility controls.")

    except Exception as e:
        db.session.rollback()
        print(f"\n❌ Migration failed with error:")
        print(f"   {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
