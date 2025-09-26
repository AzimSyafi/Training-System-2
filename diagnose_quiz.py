#!/usr/bin/env python3
"""
Comprehensive quiz diagnostic script
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Module, Course, User, UserModule
import json

def diagnose_quiz_issue():
    """Diagnose why uploaded quizzes aren't showing for users"""
    with app.app_context():
        try:
            print("=== QUIZ DIAGNOSTIC REPORT ===\n")

            # 1. Check modules with quiz data
            print("1. MODULES WITH QUIZ DATA:")
            modules_with_quiz = Module.query.filter(Module.quiz_json.isnot(None)).all()
            print(f"Found {len(modules_with_quiz)} modules with quiz_json data")

            for module in modules_with_quiz:
                print(f"\nModule ID {module.module_id}: {module.module_name}")
                print(f"  - Module type: {module.module_type}")
                print(f"  - Series number: {module.series_number}")

                # Parse quiz JSON
                try:
                    quiz_data = json.loads(module.quiz_json)
                    print(f"  - Quiz has {len(quiz_data)} questions")
                    if quiz_data:
                        first_q = quiz_data[0]
                        print(f"  - First question: {first_q.get('text', 'No text')[:50]}...")
                except Exception as e:
                    print(f"  - Quiz JSON parse error: {e}")

                # Check course relationship
                course = Course.query.join(Course.modules).filter(Module.module_id == module.module_id).first()
                if course:
                    print(f"  - Belongs to course: {course.code} - {course.name}")
                    print(f"  - Course allowed category: {course.allowed_category}")
                else:
                    print(f"  - ⚠️ WARNING: Module not linked to any course!")

            # 2. Check users and their categories
            print(f"\n2. USER CATEGORIES:")
            users = User.query.all()
            print(f"Found {len(users)} total users")

            user_categories = {}
            for user in users:
                cat = (user.user_category or 'unknown').lower().strip()
                user_categories[cat] = user_categories.get(cat, 0) + 1

            for cat, count in user_categories.items():
                print(f"  - {cat}: {count} users")

            # 3. Check courses and their allowed categories
            print(f"\n3. COURSES AND ACCESS:")
            courses = Course.query.all()
            for course in courses:
                print(f"\nCourse: {course.code} - {course.name}")
                print(f"  - Allowed category: {course.allowed_category}")
                print(f"  - Modules: {len(course.modules)}")

                # Count modules with quizzes in this course
                quiz_modules = [m for m in course.modules if m.quiz_json]
                print(f"  - Modules with quizzes: {len(quiz_modules)}")

                if quiz_modules:
                    for qm in quiz_modules:
                        print(f"    * {qm.module_name} (ID: {qm.module_id})")

            # 4. Test API access for each user type
            print(f"\n4. API ACCESS TEST:")

            # Get a sample user for each category
            citizen_user = User.query.filter(db.func.lower(db.func.trim(User.user_category)) == 'citizen').first()
            foreigner_user = User.query.filter(db.func.lower(db.func.trim(User.user_category)) == 'foreigner').first()

            test_users = []
            if citizen_user:
                test_users.append(('citizen', citizen_user))
            if foreigner_user:
                test_users.append(('foreigner', foreigner_user))

            for user_type, user in test_users:
                print(f"\nTesting access for {user_type} user: {user.full_name}")

                # Test access to modules with quizzes
                for module in modules_with_quiz:
                    course = Course.query.join(Course.modules).filter(Module.module_id == module.module_id).first()
                    if course:
                        course_allowed_cat = (course.allowed_category or '').lower().strip()
                        user_cat = (user.user_category or '').lower().strip()

                        has_access = course_allowed_cat in ('both', user_cat)
                        access_status = "✅ HAS ACCESS" if has_access else "❌ NO ACCESS"

                        print(f"  Module {module.module_id} ({module.module_name}): {access_status}")
                        print(f"    Course: {course.code} (allows: {course_allowed_cat}, user is: {user_cat})")

            # 5. Check for common issues
            print(f"\n5. POTENTIAL ISSUES:")
            issues = []

            # Check if modules with quizzes are not linked to courses
            orphan_modules = []
            for module in modules_with_quiz:
                course = Course.query.join(Course.modules).filter(Module.module_id == module.module_id).first()
                if not course:
                    orphan_modules.append(module)

            if orphan_modules:
                issues.append(f"Found {len(orphan_modules)} modules with quizzes not linked to any course")
                for om in orphan_modules:
                    print(f"  - Module {om.module_id}: {om.module_name}")

            # Check if course categories don't match user categories
            mismatched_access = []
            for course in courses:
                allowed_cat = (course.allowed_category or '').lower().strip()
                if allowed_cat not in ('citizen', 'foreigner', 'both'):
                    mismatched_access.append(course)

            if mismatched_access:
                issues.append(f"Found {len(mismatched_access)} courses with invalid allowed_category")
                for ma in mismatched_access:
                    print(f"  - Course {ma.code}: allowed_category = '{ma.allowed_category}'")

            if not issues:
                print("  No obvious issues detected. The problem might be in the frontend or session handling.")

            print(f"\n=== END DIAGNOSTIC REPORT ===")

        except Exception as e:
            print(f"Diagnostic failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    diagnose_quiz_issue()
