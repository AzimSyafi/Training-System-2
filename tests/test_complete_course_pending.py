import os
import json
from datetime import datetime, UTC
import pytest


def _login(client, email, password):
    return client.post('/login', data={
        'email': email,
        'password': password
    }, follow_redirects=False)


@pytest.fixture()
def app_client(monkeypatch):
    # In-memory DB and disable schema guard to speed test
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('DISABLE_SCHEMA_GUARD', '1')
    import importlib
    flask_app_module = importlib.import_module('app')
    app = flask_app_module.app
    app.config['TESTING'] = True
    with app.app_context():
        flask_app_module.db.drop_all()
        flask_app_module.db.create_all()
        # Seed minimal data
        a1 = flask_app_module.Agency(agency_name='A', contact_number='0', address='', Reg_of_Company='', PIC='', email='a@example.com')
        flask_app_module.db.session.add(a1)
        flask_app_module.db.session.flush()
        u = flask_app_module.User(full_name='U1', email='u1@example.com', user_category='citizen', agency_id=a1.agency_id)
        u.set_password('pass123')
        flask_app_module.db.session.add(u)
        c = flask_app_module.Course(name='CERTIFIED SECURITY GUARD (CSG)', code='CSG', allowed_category='citizen')
        flask_app_module.db.session.add(c)
        flask_app_module.db.session.flush()
        m1 = flask_app_module.Module(module_name='M1', module_type='CSG', series_number='CSG001', course_id=c.course_id)
        m2 = flask_app_module.Module(module_name='M2', module_type='CSG', series_number='CSG002', course_id=c.course_id)
        flask_app_module.db.session.add_all([m1, m2])
        flask_app_module.db.session.commit()
    client = app.test_client()
    yield client


def test_complete_requires_full_completion(app_client):
    # login
    resp = _login(app_client, 'u1@example.com', 'pass123')
    assert resp.status_code in (302, 303)
    # mark only one module completed
    import app as appmod
    with appmod.app.app_context():
        u = appmod.User.query.filter_by(email='u1@example.com').first()
        c = appmod.Course.query.filter(appmod.Course.code.ilike('CSG')).first()
        mods = list(c.modules)
        assert len(mods) == 2
        um = appmod.UserModule(user_id=u.User_id, module_id=mods[0].module_id, is_completed=True, score=80.0, completion_date=datetime.now(UTC))
        appmod.db.session.add(um)
        appmod.db.session.commit()
    # press complete
    r = app_client.post('/api/complete_course', data=json.dumps({'course_code':'CSG'}), headers={'Content-Type':'application/json'})
    assert r.status_code == 400
    data = r.get_json()
    assert data.get('success') is False
    # no certificate created
    with appmod.app.app_context():
        certs = appmod.Certificate.query.all()
        assert len(certs) == 0


def test_complete_creates_pending_certificate(app_client):
    resp = _login(app_client, 'u1@example.com', 'pass123')
    assert resp.status_code in (302, 303)
    import app as appmod
    with appmod.app.app_context():
        u = appmod.User.query.filter_by(email='u1@example.com').first()
        c = appmod.Course.query.filter(appmod.Course.code.ilike('CSG')).first()
        mods = list(c.modules)
        for m in mods:
            um = appmod.UserModule(user_id=u.User_id, module_id=m.module_id, is_completed=True, score=70.0, completion_date=datetime.now(UTC))
            appmod.db.session.add(um)
        appmod.db.session.commit()
    # press complete
    r = app_client.post('/api/complete_course', data=json.dumps({'course_code':'CSG'}), headers={'Content-Type':'application/json'})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get('success') is True
    # verify pending cert
    with appmod.app.app_context():
        certs = appmod.Certificate.query.all()
        assert len(certs) == 1
        cert = certs[0]
        assert cert.status == 'pending'
        # module_id should belong to the course
        c = appmod.Course.query.filter(appmod.Course.code.ilike('CSG')).first()
        m_ids = {m.module_id for m in c.modules}
        assert cert.module_id in m_ids


def test_idempotent_press(app_client):
    resp = _login(app_client, 'u1@example.com', 'pass123')
    assert resp.status_code in (302, 303)
    import app as appmod
    with appmod.app.app_context():
        u = appmod.User.query.filter_by(email='u1@example.com').first()
        c = appmod.Course.query.filter(appmod.Course.code.ilike('CSG')).first()
        mods = list(c.modules)
        for m in mods:
            um = appmod.UserModule(user_id=u.User_id, module_id=m.module_id, is_completed=True, score=85.0, completion_date=datetime.now(UTC))
            appmod.db.session.add(um)
        appmod.db.session.commit()
    # first press
    r1 = app_client.post('/api/complete_course', data=json.dumps({'course_code':'CSG'}), headers={'Content-Type':'application/json'})
    assert r1.status_code == 200
    # second press should not create duplicate
    r2 = app_client.post('/api/complete_course', data=json.dumps({'course_code':'CSG'}), headers={'Content-Type':'application/json'})
    assert r2.status_code == 200
    data2 = r2.get_json()
    assert data2.get('success') is True
    assert data2.get('already_submitted') is True
    with appmod.app.app_context():
        certs = appmod.Certificate.query.all()
        assert len(certs) == 1

