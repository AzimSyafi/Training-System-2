from models import db
from flask import Flask
import os

app = Flask(__name__)
# Prefer env DATABASE_URL; fallback to local PostgreSQL like the main app
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'postgresql://postgres:0789@localhost:5432/Training_system'
app.app_context().push()
db.init_app(app)

def upgrade():
    with app.app_context():
        # Add 'role' column to 'user' table (user is reserved; quote it)
        db.session.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS role VARCHAR(50) NOT NULL DEFAULT \'user\';')
        # Add 'role' column to 'trainer' table
        db.session.execute('ALTER TABLE trainer ADD COLUMN IF NOT EXISTS role VARCHAR(50) NOT NULL DEFAULT \'trainer\';')
        db.session.commit()


def downgrade():
    # Note: Dropping columns in PostgreSQL is supported, but we keep it noop-safe here.
    pass


if __name__ == "__main__":
    upgrade()
    print("Migration complete: 'role' column added to user and trainer tables.")
