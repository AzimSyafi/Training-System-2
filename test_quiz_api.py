#!/usr/bin/env python3
"""
Quick test script to verify quiz API functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Module, Course, User
from flask_login import login_user
import json

def test_quiz_api():
    """Test the quiz loading API endpoint"""
    with app.test_client() as client:
        with app.app_context():
            try:
                # Check if we have any modules
                modules = Module.query.limit(5).all()
                print(f"Found {len(modules)} modules in database")

                for module in modules:
                    print(f"Module {module.module_id}: {module.module_name}")
                    print(f"  - Module type: {module.module_type}")
                    print(f"  - Has quiz_json: {bool(module.quiz_json)}")
                    if module.quiz_json:
                        try:
                            quiz_data = json.loads(module.quiz_json)
                            print(f"  - Raw quiz_json type: {type(quiz_data).__name__}")
                            if isinstance(quiz_data, list):
                                print(f"  - Quiz JSON has {len(quiz_data)} questions")
                            elif isinstance(quiz_data, dict):
                                # Helpful for your current format with a 'questions' array
                                keys = list(quiz_data.keys())
                                print(f"  - Quiz JSON is a dict with keys: {keys}")
                        except Exception as e:
                            print(f"  - Quiz JSON parse error: {e}")

                    # Test the API endpoints with a mock user session
                    try:
                        test_user = User.query.first()
                        if test_user:
                            with client.session_transaction() as sess:
                                sess['user_type'] = 'user'
                                sess['user_id'] = str(test_user.User_id)

                            # Load quiz
                            response = client.get(f'/api/load_quiz/{module.module_id}')
                            print(f"  - API /api/load_quiz status: {response.status_code}")
                            if response.status_code == 200:
                                payload = response.get_json() or []
                                data = payload if isinstance(payload, list) else (payload.get('quiz') or [])
                                qcount = len(data) if isinstance(data, list) else 0
                                print(f"  - API returned {qcount} questions")
                                # Try save answers (all zeros) if we have any questions
                                if qcount > 0:
                                    answers = [0] * qcount
                                    save_res = client.post(
                                        f'/api/save_quiz_answers/{module.module_id}',
                                        data=json.dumps({'answers': answers}),
                                        content_type='application/json'
                                    )
                                    print(f"  - API /api/save_quiz_answers status: {save_res.status_code}")
                                    try:
                                        print(f"    Save payload: {save_res.get_json()}")
                                    except Exception:
                                        print(f"    Save payload (raw): {save_res.get_data(as_text=True)[:120]}")
                                    # Submit quiz
                                    submit_res = client.post(
                                        f'/api/submit_quiz/{module.module_id}',
                                        data=json.dumps({'answers': answers, 'is_reattempt': True}),
                                        content_type='application/json'
                                    )
                                    print(f"  - API /api/submit_quiz status: {submit_res.status_code}")
                                    try:
                                        print(f"    Submit payload: {submit_res.get_json()}")
                                    except Exception:
                                        print(f"    Submit payload (raw): {submit_res.get_data(as_text=True)[:120]}")
                            else:
                                print(f"  - API error: {response.get_data(as_text=True)}")
                        else:
                            print("  - No test user found")
                    except Exception as e:
                        print(f"  - API test failed: {e}")

                    print()

                # Check if we have any users
                users = User.query.limit(3).all()
                print(f"Found {len(users)} users in database")
                for user in users:
                    print(f"  - User: {user.full_name} ({user.email}) - Category: {user.user_category}")

                # Check if we have any courses
                courses = Course.query.all()
                print(f"Found {len(courses)} courses in database")
                for course in courses:
                    print(f"Course: {course.code} - {course.name}")
                    print(f"  - Allowed category: {course.allowed_category}")
                    print(f"  - Module count: {len(course.modules)}")

            except Exception as e:
                print(f"Test failed: {e}")
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    test_quiz_api()
