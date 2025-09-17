import os
# Avoid DB bootstrap work and heavy external connections
os.environ['DISABLE_SCHEMA_GUARD'] = '1'
os.environ['DATABASE_URL'] = 'sqlite://'

from app import app

if __name__ == '__main__':
    with app.test_client() as c:
        r = c.get('/'); print('GET / =>', r.status)
        r = c.get('/login'); print('GET /login =>', r.status)

