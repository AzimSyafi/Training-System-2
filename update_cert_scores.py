from app import app
from models import db, Certificate, UserModule

def update_cert_scores():
    with app.app_context():
        certs = Certificate.query.all()
        updated = 0
        for cert in certs:
            user_module = UserModule.query.filter_by(user_id=cert.user_id, module_id=cert.module_id).first()
            if user_module and user_module.score is not None:
                # Keep certificate.score in sync with user's module score
                if cert.score != user_module.score:
                    cert.score = user_module.score
                    updated += 1
        if updated:
            db.session.commit()
        print(f"Updated {updated} certificates with correct score.")

if __name__ == '__main__':
    update_cert_scores()
