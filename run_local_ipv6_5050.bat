@echo off
REM Run Flask app bound to IPv6 loopback on port 5050 with request logging
set HOST=::1
set PORT=5050
set LOG_REQUESTS=1
set FLASK_DEBUG=1
python app.py

