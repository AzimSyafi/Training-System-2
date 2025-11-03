"""
Diagnostic script to check quiz data in the database
"""
from flask import Flask
from models import db, Module
import json
import os

def check_quiz_data():
    """Check quiz data in the PostgreSQL database"""
    app = Flask(__name__)

    # Use PostgreSQL database from environment variable or default
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://postgres:0789@localhost:5432/Training_system'
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        print("=" * 80)
        print("CHECKING QUIZ DATA IN DATABASE")
        print("=" * 80)
        print(f"Database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")

        modules = Module.query.all()
        print(f"\nTotal modules: {len(modules)}")

        modules_with_quiz = []
        modules_without_quiz = []

        for m in modules:
            print(f"\n{'='*60}")
            print(f"Module ID: {m.module_id}")
            print(f"Module Name: {m.module_name}")
            print(f"Series Number: {m.series_number}")
            print(f"Course ID: {m.course_id}")

            if m.quiz_json:
                modules_with_quiz.append(m)
                print(f"HAS QUIZ DATA: Yes")
                print(f"Quiz JSON length: {len(m.quiz_json)} characters")

                # Try to parse it
                try:
                    quiz_data = json.loads(m.quiz_json)
                    print(f"Quiz JSON is valid")
                    print(f"Quiz data type: {type(quiz_data).__name__}")

                    if isinstance(quiz_data, list):
                        print(f"Number of questions: {len(quiz_data)}")
                        if len(quiz_data) > 0:
                            print(f"\nFirst question preview:")
                            first_q = quiz_data[0]
                            print(f"  Question text: {first_q.get('text', 'N/A')[:100]}")
                            if 'answers' in first_q:
                                print(f"  Number of answers: {len(first_q.get('answers', []))}")
                    elif isinstance(quiz_data, dict):
                        print(f"Quiz data is a dict with keys: {list(quiz_data.keys())}")
                        if 'questions' in quiz_data:
                            print(f"Number of questions: {len(quiz_data.get('questions', []))}")

                    # Show raw data (first 500 chars)
                    print(f"\nRaw quiz_json (first 500 chars):")
                    print(m.quiz_json[:500])
                except json.JSONDecodeError as e:
                    print(f"ERROR: Quiz JSON is INVALID - {e}")
                    print(f"Raw data (first 200 chars): {m.quiz_json[:200]}")
            else:
                modules_without_quiz.append(m)
                print(f"HAS QUIZ DATA: No")

        print(f"\n{'='*80}")
        print(f"SUMMARY:")
        print(f"  Modules with quiz: {len(modules_with_quiz)}")
        print(f"  Modules without quiz: {len(modules_without_quiz)}")
        print(f"{'='*80}")

if __name__ == '__main__':
    check_quiz_data()

