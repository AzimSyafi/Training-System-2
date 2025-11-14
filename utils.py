"""
Shared helpers and Jinja filter registration for the Training System app.
This module centralizes small utilities extracted from `app.py`.
"""
from typing import Optional, Any
import os
import re
import urllib.parse
from flask import url_for
from werkzeug.routing import BuildError


def safe_url_for(endpoint: str, **values) -> str:
    """Return a safe URL or '#' if the endpoint build fails."""
    try:
        return url_for(endpoint, **values)
    except BuildError:
        return '#'


def normalized_user_category(user: Any) -> str:
    """Return 'citizen' or 'foreigner' robustly.

    Falls back to inspecting passport/ic when user.user_category is missing or invalid.
    """
    try:
        raw = (getattr(user, 'user_category', None) or '').strip().lower()
    except Exception:
        raw = ''
    if raw in ('citizen', 'foreigner'):
        return raw
    passport = getattr(user, 'passport_number', None)
    ic = getattr(user, 'ic_number', None)
    if passport and not ic:
        return 'foreigner'
    return 'citizen'


def safe_parse_date(value, fmt: str = '%Y-%m-%d'):
    """Parse date-like values to a date object or return None for invalid/empty inputs."""
    if value is None:
        return None
    try:
        import datetime as _dt
        if isinstance(value, _dt.date) and not isinstance(value, _dt.datetime):
            return value
        if isinstance(value, _dt.datetime):
            return value.date()
    except Exception:
        pass
    try:
        v = str(value).strip()
    except Exception:
        return None
    if v == '':
        return None
    try:
        from datetime import datetime
        return datetime.strptime(v, fmt).date()
    except Exception:
        return None


def extract_youtube_id(url: str) -> Optional[str]:
    """Extract a YouTube video ID from various URL formats.

    Returns None when not found.
    """
    if not isinstance(url, str):
        return None
    regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    m = re.search(regex, url)
    return m.group(1) if m else None


def is_slide_file(filename: str) -> bool:
    """Return True for allowed slide file extensions (pdf, pptx)."""
    if not isinstance(filename, str):
        return False
    return filename.lower().endswith(('.pdf', '.pptx'))


def allowed_file(filename: str) -> bool:
    """Return True if filename extension allowed for profile pictures."""
    if not isinstance(filename, str):
        return False
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_slide_file(filename: str) -> bool:
    """Return True if filename extension allowed for slide uploads (PDF, PPTX)."""
    return is_slide_file(filename)


def register_jinja_filters(app) -> None:
    """Register common Jinja filters and globals on the provided Flask app.

    Adds: 'youtube_id', 'is_slide', 'url_encode' filters and `safe_url_for` global.
    Also injects a `USE_TAILWIND_CDN` context variable similar to the previous implementation.
    """
    app.jinja_env.filters['youtube_id'] = extract_youtube_id
    app.jinja_env.filters['is_slide'] = is_slide_file
    app.jinja_env.filters['url_encode'] = lambda s: urllib.parse.quote(str(s), safe='')
    app.jinja_env.globals['safe_url_for'] = safe_url_for

    @app.context_processor
    def _inject_tailwind_flag():
        compiled_path = os.path.join(app.static_folder or 'static', 'css', 'tailwind.css')
        try:
            compiled_exists = os.path.exists(compiled_path)
        except Exception:
            compiled_exists = False
        if compiled_exists:
            use_cdn = False
        else:
            use_cdn = os.environ.get('USE_TAILWIND_CDN', '0') in ('1', 'true', 'True')
        return {'USE_TAILWIND_CDN': use_cdn}
