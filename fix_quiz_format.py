"""
Fix quiz data format - convert {"questions": [...]} to [...] format
This script normalizes all quiz data to use the array format expected by the quiz builder
"""
from flask import Flask
from models import db, Module
import json
import os

def fix_quiz_format():
    """Convert all quiz data from object format to array format"""
    app = Flask(__name__)

    # Use PostgreSQL database from environment variable or default
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://postgres:0789@localhost:5432/Training_system'
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        print("=" * 80)
        print("FIXING QUIZ DATA FORMAT")
        print("=" * 80)
        print(f"Database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}\n")

        modules = Module.query.all()
        print(f"Total modules: {len(modules)}")

        fixed_count = 0
        skipped_count = 0
        error_count = 0

        for module in modules:
            if not module.quiz_json:
                continue

            try:
                quiz_data = json.loads(module.quiz_json)

                # Check if it's already in array format
                if isinstance(quiz_data, list):
                    print(f"✓ Module {module.module_id} ({module.module_name}): Already in array format")
                    skipped_count += 1
                    continue

                # Check if it has 'questions' key
                if isinstance(quiz_data, dict) and 'questions' in quiz_data:
                    questions = quiz_data['questions']

                    if not isinstance(questions, list):
                        print(f"✗ Module {module.module_id} ({module.module_name}): 'questions' is not an array")
                        error_count += 1
                        continue

                    # Convert to array format
                    normalized_questions = []
                    for q in questions:
                        if not isinstance(q, dict):
                            continue

                        # Handle both old and new answer formats
                        normalized_q = {
                            'text': q.get('text') or q.get('question') or '',
                            'answers': []
                        }

                        raw_answers = q.get('answers', [])

                        # If answers are already objects with text/isCorrect
                        if raw_answers and isinstance(raw_answers[0], dict) and 'isCorrect' in raw_answers[0]:
                            normalized_q['answers'] = [
                                {
                                    'text': ans.get('text', ''),
                                    'isCorrect': bool(ans.get('isCorrect', False))
                                }
                                for ans in raw_answers
                            ]
                        else:
                            # Old format with string array and correct index
                            correct_idx = int(q.get('correct', 1)) - 1
                            normalized_q['answers'] = [
                                {
                                    'text': ans if isinstance(ans, str) else str(ans),
                                    'isCorrect': (idx == correct_idx)
                                }
                                for idx, ans in enumerate(raw_answers)
                            ]

                        normalized_questions.append(normalized_q)

                    # Save the normalized format
                    module.quiz_json = json.dumps(normalized_questions)
                    print(f"✓ Module {module.module_id} ({module.module_name}): Fixed ({len(normalized_questions)} questions)")
                    fixed_count += 1
                else:
                    print(f"⚠ Module {module.module_id} ({module.module_name}): Unknown format - {type(quiz_data).__name__}")
                    error_count += 1

            except json.JSONDecodeError as e:
                print(f"✗ Module {module.module_id} ({module.module_name}): Invalid JSON - {e}")
                error_count += 1
            except Exception as e:
                print(f"✗ Module {module.module_id} ({module.module_name}): Error - {e}")
                error_count += 1

        # Commit all changes
        if fixed_count > 0:
            try:
                db.session.commit()
                print(f"\n{'='*80}")
                print("✓ Changes committed to database")
            except Exception as e:
                db.session.rollback()
                print(f"\n{'='*80}")
                print(f"✗ Failed to commit changes: {e}")

        print(f"\n{'='*80}")
        print("SUMMARY:")
        print(f"  Fixed: {fixed_count}")
        print(f"  Skipped (already correct): {skipped_count}")
        print(f"  Errors: {error_count}")
        print(f"{'='*80}")

if __name__ == '__main__':
    fix_quiz_format()

