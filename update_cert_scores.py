from app import app
from models import db, Certificate, UserModule

def update_cert_scores():
    with app.app_context():
        certs = Certificate.query.all()
        updated = 0
        for cert in certs:
            user_module = UserModule.query.filter_by(user_id=cert.user_id, module_id=cert.module_id).first()
                    cert.star_rating = stars
        print(f"Updated {updated} certificates with correct score and star_rating.")

