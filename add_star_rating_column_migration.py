from flask import Flask
import os
from models import db

app = Flask(__name__)
# Prefer env DATABASE_URL; fallback to local PostgreSQL like the main app
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'postgresql://postgres:0789@localhost:5432/Training_system'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.app_context().push()
db.init_app(app)


def column_exists_sqlite(table: str, column: str) -> bool:
    rows = db.session.execute(f"PRAGMA table_info('{table}')").fetchall()
    for r in rows:
        # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
        if len(r) >= 2 and str(r[1]).lower() == column.lower():
            return True
    return False


def upgrade():
    with app.app_context():
        dialect = (getattr(db.engine, 'dialect', None).name or '').lower()
        if dialect == 'postgresql':
            db.session.execute("ALTER TABLE certificate ADD COLUMN IF NOT EXISTS star_rating INTEGER")
            db.session.commit()
        elif dialect == 'sqlite':
            if not column_exists_sqlite('certificate', 'star_rating'):
                db.session.execute("ALTER TABLE certificate ADD COLUMN star_rating INTEGER")
                db.session.commit()
        else:
            # Generic attempt with IF NOT EXISTS; may fail on unsupported dialects
            try:
                db.session.execute("ALTER TABLE certificate ADD COLUMN IF NOT EXISTS star_rating INTEGER")
                db.session.commit()
            except Exception:
                # Final fallback: try without IF NOT EXISTS and ignore if it already exists
                try:
                    db.session.execute("ALTER TABLE certificate ADD COLUMN star_rating INTEGER")
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise


def downgrade():
    # No-op: we are restoring a previously removed column
    pass


if __name__ == "__main__":
    upgrade()
    print("Migration complete: 'star_rating' column ensured on certificate table.")

