from models import db
from flask import Flask

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/security_training.db'  # Adjust if using PostgreSQL
app.app_context().push()
db.init_app(app)

def upgrade():
    with app.app_context():
        # Add 'role' column to 'user' table
        db.session.execute('ALTER TABLE user ADD COLUMN role VARCHAR(50) NOT NULL DEFAULT "user";')
        # Add 'role' column to 'trainer' table
        db.session.execute('ALTER TABLE trainer ADD COLUMN role VARCHAR(50) NOT NULL DEFAULT "trainer";')
        db.session.commit()

def downgrade():
    # SQLite does not support DROP COLUMN directly; would require table recreation
    pass

if __name__ == "__main__":
    upgrade()
    print("Migration complete: 'role' column added to user and trainer tables.")

