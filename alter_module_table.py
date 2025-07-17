from models import db, Module
from app import app
from sqlalchemy import text

with app.app_context():
    # Check if the column already exists
    result = db.session.execute(text("PRAGMA table_info(module);"))
    columns = [row[1] for row in result]
    if 'quiz_json' not in columns:
        db.session.execute(text('ALTER TABLE module ADD COLUMN quiz_json TEXT'))
        db.session.commit()
        print('Added quiz_json column to module table.')
    else:
        print('quiz_json column already exists.')

