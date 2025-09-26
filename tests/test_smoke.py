import pytest
from app import app
from flask import url_for

def test_upload_content_endpoint_exists():
    # This only verifies the endpoint name is registered and url_for can build it.
    # It avoids making HTTP requests or touching the DB.
    with app.test_request_context():
        url = url_for('upload_content')
        assert url == '/upload_content'

