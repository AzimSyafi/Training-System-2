from flask import Blueprint, request, jsonify, render_template, session
from flask_login import login_required, current_user
from sqlalchemy import update, select
from datetime import datetime, UTC
import logging

from models import db, Certificate, User, Module, Course

authority_bp = Blueprint('authority', __name__, url_prefix='/authority')

BULK_LIMIT = 100

def _get_csrf_token() -> str:
    tok = session.get('csrf_token')
    if not tok:
        # Lazy-generate a token if missing
        import secrets
        tok = secrets.token_urlsafe(32)
        session['csrf_token'] = tok
    return tok

@authority_bp.route('', methods=['GET'])
@login_required
def authority_portal():
    # Only allow Users with role 'authority'
    role = getattr(current_user, 'role', None)
    if role != 'authority':
        return render_template('index.html'), 403
    # Filters
    status = (request.args.get('status') or 'pending').lower()
    if status not in ('pending', 'approved', 'all'):
        status = 'pending'
    q = (request.args.get('q') or '').strip()

    try:
        from sqlalchemy import and_, or_, func
        query = (
            db.session.query(Certificate)
            .join(User, User.User_id == Certificate.user_id)
            .join(Module, Module.module_id == Certificate.module_id)
            .outerjoin(Course, Course.course_id == Module.course_id)
        )
        conditions = []
        if status != 'all':
            conditions.append(Certificate.status == status)
        if q:
            like = f"%{q}%"
            # Search by user name, SG number, course name/code, module name, module type, certificate id text
            conditions.append(or_(
                User.full_name.ilike(like),
                func.coalesce(User.number_series, '').ilike(like),
                func.coalesce(Course.name, '').ilike(like),
                func.coalesce(Course.code, '').ilike(like),
                Module.module_name.ilike(like),
                Certificate.module_type.ilike(like),
                func.cast(Certificate.certificate_id, db.String).ilike(like)
            ))
        if conditions:
            query = query.filter(and_(*conditions))
        rows = (
            query.order_by(Certificate.certificate_id.desc())
            .limit(500)
            .all()
        )
    except Exception:
        logging.exception('[AUTHORITY] Failed to load certificates')
        rows = []
    # Ensure CSRF token exists for the page
    token = _get_csrf_token()
    return render_template('authority_portal.html', rows=rows, csrf_token=token, selected_status=status, search_query=q)

@authority_bp.route('/bulk_approve', methods=['POST'])
@login_required
def bulk_approve():
    # Security: only allow User role authority
    role = getattr(current_user, 'role', None)
    if role != 'authority' or not hasattr(current_user, 'User_id'):
        return jsonify({'error': 'forbidden'}), 403
    # CSRF: expect header X-CSRFToken matching session
    header_token = request.headers.get('X-CSRFToken') or request.headers.get('X-CSRF-Token')
    if not header_token or header_token != session.get('csrf_token'):
        return jsonify({'error': 'csrf_failed'}), 400
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}
    ids = payload.get('ids')
    if not isinstance(ids, list):
        return jsonify({'error': 'invalid_ids'}), 400
    try:
        ids = [int(i) for i in ids]
    except Exception:
        return jsonify({'error': 'invalid_ids'}), 400
    # Normalize and validate
    ids = [i for i in ids if i > 0]
    if not ids:
        return jsonify({'error': 'empty_ids'}), 400
    # Enforce maximum batch size
    if len(ids) > BULK_LIMIT:
        return jsonify({'error': 'batch_too_large', 'limit': BULK_LIMIT}), 400

    # Unique the list to avoid duplicate updates inflating counts
    unique_ids = list(dict.fromkeys(ids))

    now = datetime.now(UTC)

    # Perform a single bulk UPDATE with idempotency (status='pending')
    try:
        from sqlalchemy import and_
        conditions = and_(
            Certificate.certificate_id.in_(unique_ids),
            Certificate.status == 'pending'
        )
        stmt = (
            update(Certificate)
            .where(conditions)
            .values(status='approved', approved_by_id=current_user.User_id, approved_at=now)
        )
        result = db.session.execute(stmt)
        approved_count = result.rowcount or 0
        db.session.commit()
        requested = len(unique_ids)
        skipped = requested - approved_count
        logging.info('[AUTHORITY] user_id=%s bulk_approve requested=%d approved=%d skipped=%d', current_user.User_id, requested, approved_count, skipped)
        return jsonify({'success': True, 'requested': requested, 'approved': approved_count, 'skipped': skipped}), 200
    except Exception as e:
        logging.exception('[AUTHORITY] bulk_approve failed for user_id=%s: %s', getattr(current_user, 'User_id', None), e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'server_error'}), 500
