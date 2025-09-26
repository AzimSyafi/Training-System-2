import os
import json
from datetime import date
import pytest


def _login(client, email, password):
    return client.post('/login', data={
        'email': email,
        'password': password
    }, follow_redirects=False)


@pytest.fixture()
def app_client(monkeypatch):
    # Use in-memory SQLite and disable schema guard before importing app
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('DISABLE_SCHEMA_GUARD', '1')
    import importlib
    flask_app_module = importlib.import_module('app')
    app = flask_app_module.app
    app.config['TESTING'] = True
    with app.app_context():
        flask_app_module.db.drop_all()
        flask_app_module.db.create_all()
        # Seed agencies
        a1 = flask_app_module.Agency(agency_name='A1', contact_number='0', address='', Reg_of_Company='', PIC='', email='a1@example.com')
        a2 = flask_app_module.Agency(agency_name='A2', contact_number='0', address='', Reg_of_Company='', PIC='', email='a2@example.com')
        flask_app_module.db.session.add_all([a1, a2])
        flask_app_module.db.session.commit()
        # Seed users
        u_regular = flask_app_module.User(full_name='Regular', email='regular@example.com', user_category='citizen', agency_id=a1.agency_id)
        u_regular.set_password('pass123')
        u_auth = flask_app_module.User(full_name='Authority', email='authority@example.com', user_category='citizen', agency_id=a1.agency_id, role='authority')
        u_auth.set_password('pass123')
        u_other_agency = flask_app_module.User(full_name='OtherAg', email='other@example.com', user_category='citizen', agency_id=a2.agency_id)
        u_other_agency.set_password('pass123')
        flask_app_module.db.session.add_all([u_regular, u_auth, u_other_agency])
        flask_app_module.db.session.commit()
        # Seed a module
        m = flask_app_module.Module(module_name='Module1', module_type='CSG', series_number='CSG001')
        flask_app_module.db.session.add(m)
        flask_app_module.db.session.commit()
    client = app.test_client()
    yield client


def test_unauthorized_user_forbidden(app_client):
    # Login as regular user (not authority)
    resp = _login(app_client, 'regular@example.com', 'pass123')
    assert resp.status_code in (302, 303)  # redirect to dashboard
    # Attempt bulk approve without CSRF
    r = app_client.post('/authority/bulk_approve', json={'ids': [1, 2]})
    assert r.status_code == 403


def test_authority_bulk_approve_success(app_client):
    # Login as authority
    resp = _login(app_client, 'authority@example.com', 'pass123')
    assert resp.status_code in (302, 303)
    # Create pending certificates for users in same agency
    import app as appmod
    with appmod.app.app_context():
        u_reg = appmod.User.query.filter_by(email='regular@example.com').first()
        u_auth = appmod.User.query.filter_by(email='authority@example.com').first()
        m = appmod.Module.query.first()
        c1 = appmod.Certificate(user_id=u_reg.User_id, module_type='CSG', module_id=m.module_id, issue_date=date.today())
        c2 = appmod.Certificate(user_id=u_auth.User_id, module_type='CSG', module_id=m.module_id, issue_date=date.today())
        appmod.db.session.add_all([c1, c2])
        appmod.db.session.commit()
        ids = [c1.certificate_id, c2.certificate_id]
    # Fetch the authority portal to establish CSRF in session
    page = app_client.get('/authority')
    assert page.status_code in (200, 403)  # 200 expected if role matched
    # Read CSRF token from session
    with app_client.session_transaction() as sess:
        csrf = sess.get('csrf_token')
    assert csrf
    # Call bulk approve
    r = app_client.post('/authority/bulk_approve', data=json.dumps({'ids': ids}), headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf})
    assert r.status_code == 200
    data = r.get_json()
    assert data and data.get('success') is True
    assert data.get('requested') == len(ids)
    assert data.get('approved') == len(ids)
    assert data.get('skipped') == 0
    # Verify DB state
    import app as appmod
    with appmod.app.app_context():
        rows = appmod.Certificate.query.filter(appmod.Certificate.certificate_id.in_(ids)).all()
        assert all(c.status == 'approved' for c in rows)
        # approved_by_id should be authority user id
        auth_user = appmod.User.query.filter_by(email='authority@example.com').first()
        assert all(c.approved_by_id == auth_user.User_id for c in rows)
        assert all(c.approved_at is not None for c in rows)


def test_mixed_statuses_and_scope(app_client):
    # Login as authority
    resp = _login(app_client, 'authority@example.com', 'pass123')
    assert resp.status_code in (302, 303)
    import app as appmod
    with appmod.app.app_context():
        m = appmod.Module.query.first()
        auth = appmod.User.query.filter_by(email='authority@example.com').first()
        reg = appmod.User.query.filter_by(email='regular@example.com').first()
        other = appmod.User.query.filter_by(email='other@example.com').first()
        c_pending = appmod.Certificate(user_id=reg.User_id, module_type='CSG', module_id=m.module_id, issue_date=date.today())
        c_approved = appmod.Certificate(user_id=auth.User_id, module_type='CSG', module_id=m.module_id, issue_date=date.today(), status='approved')
        c_out_scope = appmod.Certificate(user_id=other.User_id, module_type='CSG', module_id=m.module_id, issue_date=date.today())
        appmod.db.session.add_all([c_pending, c_approved, c_out_scope])
        appmod.db.session.commit()
        ids = [c_pending.certificate_id, c_approved.certificate_id, c_out_scope.certificate_id]
    # CSRF
    page = app_client.get('/authority')
    with app_client.session_transaction() as sess:
        csrf = sess.get('csrf_token')
    # POST
    r = app_client.post('/authority/bulk_approve', data=json.dumps({'ids': ids}), headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf})
    assert r.status_code == 200
    data = r.get_json()
    # With cross-agency approval allowed, should approve two (both pending), skip one (already approved)
    assert data.get('approved') == 2
    assert data.get('requested') == 3
    assert data.get('skipped') == 1


def test_invalid_and_empty_ids(app_client):
    _login(app_client, 'authority@example.com', 'pass123')
    # establish csrf
    app_client.get('/authority')
    with app_client.session_transaction() as sess:
        csrf = sess.get('csrf_token')
    # Empty list
    r = app_client.post('/authority/bulk_approve', data=json.dumps({'ids': []}), headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf})
    assert r.status_code == 400
    # Invalid types
    r2 = app_client.post('/authority/bulk_approve', data=json.dumps({'ids': ['a', 1]}), headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf})
    assert r2.status_code == 400


def test_batch_size_limit(app_client):
    _login(app_client, 'authority@example.com', 'pass123')
    app_client.get('/authority')
    with app_client.session_transaction() as sess:
        csrf = sess.get('csrf_token')
    too_many = list(range(1, 102))
    r = app_client.post('/authority/bulk_approve', data=json.dumps({'ids': too_many}), headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf})
    assert r.status_code == 400


def test_idempotent_second_call_skips(app_client):
    _login(app_client, 'authority@example.com', 'pass123')
    import app as appmod
    with appmod.app.app_context():
        m = appmod.Module.query.first()
        auth = appmod.User.query.filter_by(email='authority@example.com').first()
        c = appmod.Certificate(user_id=auth.User_id, module_type='CSG', module_id=m.module_id, issue_date=date.today())
        appmod.db.session.add(c)
        appmod.db.session.commit()
        cid = c.certificate_id
    app_client.get('/authority')
    with app_client.session_transaction() as sess:
        csrf = sess.get('csrf_token')
    # First call approves 1
    r1 = app_client.post('/authority/bulk_approve', data=json.dumps({'ids': [cid]}), headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf})
    assert r1.status_code == 200
    data1 = r1.get_json()
    assert data1.get('approved') == 1
    # Second call approves 0, skipped 1
    r2 = app_client.post('/authority/bulk_approve', data=json.dumps({'ids': [cid]}), headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf})
    assert r2.status_code == 200
    data2 = r2.get_json()
    assert data2.get('approved') == 0
    assert data2.get('skipped') == 1

