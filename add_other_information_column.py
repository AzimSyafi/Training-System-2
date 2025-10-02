from models import db
from sqlalchemy import text

def upgrade():
    # Remove the other_information column from user table if it exists
    db.session.execute(text('ALTER TABLE "user" DROP COLUMN IF EXISTS other_information'))
    db.session.commit()

def downgrade():
    # Recreate the column if downgrading
    db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS other_information TEXT'))
    db.session.commit()

if __name__ == "__main__":
    upgrade()
    print("Migration applied: other_information column removed from user table.")
