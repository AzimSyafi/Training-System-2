#!/usr/bin/env python3
"""
Create PostgreSQL schema from SQLAlchemy models
Run this before migrating data to ensure all tables exist
"""

import os
from app import app, db

def create_postgresql_schema():
    """Create all tables in PostgreSQL database"""

    # Set PostgreSQL as the database URL
    if not os.environ.get('DATABASE_URL'):
        print("❌ Please set DATABASE_URL environment variable")
        print("Example: postgresql://training_user:password@localhost:5432/security_training")
        return

    with app.app_context():
        try:
            print("🔗 Connecting to PostgreSQL...")

            # Create all tables
            db.create_all()
            print("✅ All tables created successfully in PostgreSQL!")

            # List created tables
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()

            print(f"\n📋 Created {len(tables)} tables:")
            for table in sorted(tables):
                print(f"  - {table}")

        except Exception as e:
            print(f"❌ Error creating schema: {e}")

if __name__ == "__main__":
    create_postgresql_schema()
