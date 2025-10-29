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
            # Search by user name, course name/code, module name, module type, certificate id text
            conditions.append(or_(
                User.full_name.ilike(like),
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
    # Create users list with pending counts
    from collections import defaultdict
    users_dict = defaultdict(lambda: {'user': None, 'count': 0})
    for c in rows:
        if c.status == 'pending':
            users_dict[c.user_id]['user'] = c.user
            users_dict[c.user_id]['count'] += 1
    users_list = [{'user': v['user'], 'count': v['count']} for v in users_dict.values() if v['user'] and v['count'] > 0]
    # Ensure CSRF token exists for the page
    token = _get_csrf_token()
    return render_template('authority_portal.html', rows=rows, csrf_token=token, selected_status=status, search_query=q, users_list=users_list, id=token)

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
    scope = payload.get('scope')

    # Handle different approval scopes
    if scope == 'selected':
        # Approve specific selected certificates
        cert_ids = payload.get('cert_ids')
        if not cert_ids or not isinstance(cert_ids, list) or len(cert_ids) == 0:
            return jsonify({'error': 'no_certificates_selected'}), 400
        # Validate all IDs are integers
        try:
            cert_ids = [int(cid) for cid in cert_ids]
        except (ValueError, TypeError):
            return jsonify({'error': 'invalid_certificate_ids'}), 400
        from sqlalchemy import and_
        conditions = and_(
            Certificate.status == 'pending',
            Certificate.certificate_id.in_(cert_ids)
        )
    elif scope == 'all':
        # Approve all pending certificates
        conditions = Certificate.status == 'pending'
    elif scope == 'user':
        user_id = payload.get('user_id')
        if not user_id or not isinstance(user_id, int):
            return jsonify({'error': 'invalid_user_id'}), 400
        from sqlalchemy import and_
        conditions = and_(Certificate.status == 'pending', Certificate.user_id == user_id)
    else:
        return jsonify({'error': 'invalid_scope'}), 400

    now = datetime.now(UTC)

    # Perform a single bulk UPDATE with idempotency (status='pending')
    try:
        from sqlalchemy import and_
        stmt = (
            update(Certificate)
            .where(conditions)
            .values(status='approved', approved_by_id=current_user.User_id, approved_at=now)
        )
        result = db.session.execute(stmt)
        approved_count = result.rowcount or 0
        db.session.commit()
        logging.info('[AUTHORITY] user_id=%s bulk_approve scope=%s approved=%d', current_user.User_id, scope, approved_count)
        return jsonify({'success': True, 'approved': approved_count}), 200
    except Exception as e:
        logging.exception('[AUTHORITY] bulk_approve failed for user_id=%s: %s', getattr(current_user, 'User_id', None), e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'server_error'}), 500
