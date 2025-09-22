import os
# Avoid DB bootstrap work and heavy external connections
os.environ['DISABLE_SCHEMA_GUARD'] = '1'
# Default to PostgreSQL if DATABASE_URL is not set
os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:0789@localhost:5432/Training_system')

from app import app
from models import db, User, Course, Module, Agency
import json


def seed_minimal_data():
    with app.app_context():
        db.create_all()
        # Ensure an agency exists for FK
        if not Agency.query.get(1):
            a = Agency(agency_id=1, agency_name='Default Agency', contact_number='0000000000', address='', Reg_of_Company='', PIC='', email='')
            db.session.add(a)
            db.session.flush()
        # Create a course TNG and a module with quiz
        c = Course(name='NEPAL SECURITY GUARD TRAINING (TNG)', code='TNG', allowed_category='foreigner')
        db.session.add(c)
        db.session.flush()
        quiz = [
            { 'text': '2 + 2 = ?', 'answers': [ {'text':'3','isCorrect':False}, {'text':'4','isCorrect':True} ] }
        ]
        m1 = Module(module_name='Intro', module_type='TNG', series_number='TNG001', content='Welcome', course_id=c.course_id, quiz_json=json.dumps(quiz))
        db.session.add(m1)
        # Create a foreigner user
        u = User(full_name='Test User', email='test@example.com', user_category='foreigner', agency_id=1, is_finalized=True)
        u.set_password('pass1234')
        db.session.add(u)
        db.session.commit()


def get_first_module_id():
    with app.app_context():
        m = Module.query.first()
        return m.module_id if m else None


if __name__ == '__main__':
    seed_minimal_data()
    mod_id = get_first_module_id()
    with app.test_client() as c:
        r = c.get('/'); print('GET / =>', r.status)
        r = c.get('/login'); print('GET /login =>', r.status)
        # Login as user
        r = c.post('/login', data={'email':'test@example.com', 'password':'pass1234'}, follow_redirects=True)
        print('POST /login =>', r.status)
        # Access courses page
        r = c.get('/courses'); print('GET /courses =>', r.status)
        # Access modules for TNG
        r = c.get('/modules/TNG'); print('GET /modules/TNG =>', r.status)
        assert r.status_code == 200, '/modules/TNG should return 200 after login'
        # Load quiz via API
        if mod_id:
            r = c.get(f'/api/load_quiz/{mod_id}')
            print('GET /api/load_quiz/<id> =>', r.status, r.get_data(as_text=True))
            data = r.get_json(silent=True) or []
            assert isinstance(data, list) and len(data) > 0, 'Quiz should not be empty'
            # Open quiz page
            r = c.get(f'/quiz/{mod_id}')
            print('GET /quiz/<id> =>', r.status)
            assert r.status_code == 200, '/quiz/<id> should return 200'
