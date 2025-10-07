"""
Certificate-related logic for Training System app.
Extracted from app.py for modularity.
"""


def generate_certificate(user_id):
    """Generate or locate a certificate for the given user. Returns a file path or URL."""
    import os
    out_dir = os.path.join('static', 'certificates')
    os.makedirs(out_dir, exist_ok=True)
    filename = f'certificate_{user_id}.pdf'
    path = os.path.join(out_dir, filename)
    if not os.path.exists(path):
        with open(path, 'wb') as fh:
            fh.write(b'%PDF-1.4\n% Dummy certificate for user_id=%d\n' % user_id)
    return path


def validate_certificate(user_id, token):
    """Validate certificate authenticity. Returns True if valid, False otherwise."""
    if not token:
        return False
    expected = f'valid-{user_id}'
    return token == expected
