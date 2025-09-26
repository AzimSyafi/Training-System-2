#!/usr/bin/env python3
"""Basic validation tests for the /modules/<course_code> route and disclaimer APIs.
Run manually: python tests/test_modules_route.py
This does not use pytest so it can be executed directly in environments without pytest installed.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models import User, Course, Module, UserModule  # noqa: E402

TEST_EMAIL = 'modules_test_user@example.com'
TEST_PASSWORD = 'TestPass123!'


def ensure_test_user():
    with app.app_context():
        user = User.query.filter_by(email=TEST_EMAIL).first()
        if user:
            return user
        # Ensure at least one agency exists (fallback id=1 from bootstrap logic)
        from models import Agency
        ag = Agency.query.first()
        if not ag:
            ag = Agency(agency_name='Test Agency', contact_number='0', address='', Reg_of_Company='', PIC='', email='agency@example.com')
            db.session.add(ag)
            db.session.commit()
        user = User(full_name='Modules Test User', email=TEST_EMAIL, user_category='citizen', agency_id=ag.agency_id)
        user.set_password(TEST_PASSWORD)
        db.session.add(user)
        db.session.commit()
        return user

def ensure_course_and_module():
    with app.app_context():
        course = Course.query.filter_by(code='TEST').first()
        if not course:
            course = Course(name='Test Course', code='TEST', allowed_category='both')
            db.session.add(course)
            db.session.commit()
        module = Module.query.filter_by(module_type='TEST').first()
        if not module:
            module = Module(module_name='Intro TEST Module', module_type='TEST', series_number='TEST001', content='Sample content for test module', course_id=course.course_id)
            db.session.add(module)
            db.session.commit()
        return course, module

def run():
    user = ensure_test_user()
    course, module = ensure_course_and_module()

    print(f"Using user id={user.User_id}, course={course.code}, module_id={module.module_id}")
    client = app.test_client()

    # Login
    resp = client.post('/login', data={'email': TEST_EMAIL, 'password': TEST_PASSWORD}, follow_redirects=False)
    assert resp.status_code in (302, 303), f"Login failed: {resp.status_code} body={resp.data[:200]}"
    print('Login redirect OK')

    # Access modules page
    resp = client.get(f'/modules/{course.code}')
    assert resp.status_code == 200, f"/modules/{course.code} returned {resp.status_code}"
    assert b'Intro TEST Module' in resp.data, 'Module name not present in response'
    print(f"/modules/{course.code} page OK")

    # Check disclaimer status (should be false initially)
    resp = client.get(f'/api/check_module_disclaimer/{module.module_id}')
    assert resp.status_code == 200, 'Disclaimer check endpoint failed'
    data = resp.get_json()
    assert data['success'] is True
    has_agreed_initial = data.get('has_agreed')
    print('Initial disclaimer agreed:', has_agreed_initial)

    # Agree to disclaimer
    resp = client.post(f'/api/agree_module_disclaimer/{module.module_id}')
    assert resp.status_code == 200, 'Disclaimer agree endpoint failed'
    data = resp.get_json()
    assert data['success'] is True, 'Disclaimer agree did not return success'
    print('Disclaimer agreement recorded')

    # Check again should now be agreed
    resp = client.get(f'/api/check_module_disclaimer/{module.module_id}')
    data = resp.get_json()
    assert data['has_agreed'] is True, 'Disclaimer state not persisted'
    print('Disclaimer persistence verified')

    # Simulate completing the module for unlock chain logic (if we add another later)
    with app.app_context():
        um = UserModule.query.filter_by(user_id=user.User_id, module_id=module.module_id).first()
        if not um:
            um = UserModule(user_id=user.User_id, module_id=module.module_id, is_completed=True, score=85, completion_date=datetime.utcnow())
            db.session.add(um)
        else:
            um.is_completed = True
            um.score = 85
        db.session.commit()
    print('Module progress recorded (completed)')

    print('ALL TESTS PASSED')

if __name__ == '__main__':
    run()

