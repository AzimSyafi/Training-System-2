#!/usr/bin/env python3
"""
Script to create an admin account
"""
import os
import sys
from pathlib import Path

app_dir = Path(__file__).parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from app import app, db
from models import Admin

def create_admin(username, email, password):
    """Create a new admin account"""
    with app.app_context():
        existing_admin = Admin.query.filter(
            (Admin.username == username) | (Admin.email == email)
        ).first()
        
        if existing_admin:
            print(f"❌ Admin with username '{username}' or email '{email}' already exists!")
            return False
        
        admin = Admin(
            username=username,
            email=email,
            role='admin'
        )
        admin.set_password(password)
        
        db.session.add(admin)
        db.session.commit()
        
        print(f"✅ Admin account created successfully!")
        print(f"   Username: {username}")
        print(f"   Email: {email}")
        print(f"   Admin ID: {admin.admin_id}")
        return True

if __name__ == '__main__':
    print("=" * 60)
    print("CREATE ADMIN ACCOUNT")
    print("=" * 60)
    
    username = input("Enter username (default: admin): ").strip() or "admin"
    email = input("Enter email (default: admin@example.com): ").strip() or "admin@example.com"
    password = input("Enter password (default: admin123): ").strip() or "admin123"
    
    print()
    create_admin(username, email, password)
