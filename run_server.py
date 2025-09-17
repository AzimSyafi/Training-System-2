#!/usr/bin/env python3
"""
Flask Application Runner
========================

This is the main entry point for running the Training System Flask application.
It provides multiple ways to start the server and includes proper error handling.

Usage:
    python run_server.py           # Run with default settings
    python run_server.py --debug   # Run in debug mode
    python run_server.py --port 8000  # Run on custom port

Environment Variables:
    PORT         - Server port (default: 5000)
    FLASK_DEBUG  - Enable debug mode (default: False)
    FLASK_ENV    - Flask environment (development/production)
"""

import os
import sys
import argparse
from pathlib import Path

def setup_environment():
    """Ensure the app directory is in the Python path"""
    app_dir = Path(__file__).parent
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

def check_requirements():
    """Check if required packages are installed"""
    required_packages = ['flask', 'flask_login', 'flask_sqlalchemy', 'werkzeug']
    missing = []

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"❌ Missing required packages: {', '.join(missing)}")
        print(f"💡 Install them with: pip install {' '.join(missing)}")
        return False
    return True

def main():
    """Main entry point for the Flask application"""
    parser = argparse.ArgumentParser(description='Run the Training System Flask App')
    parser.add_argument('--port', type=int, default=None, help='Port to run on')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')

    args = parser.parse_args()

    # Setup environment
    setup_environment()

    # Check requirements
    if not check_requirements():
        sys.exit(1)

    try:
        # Import the Flask app
        from app import app

        # Configuration
        port = args.port or int(os.environ.get('PORT', 5000))
        debug = args.debug or os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes', 'on')
        host = args.host

        # Display startup information
        print("=" * 60)
        print("🚀 TRAINING SYSTEM - FLASK APPLICATION")
        print("=" * 60)
        print(f"🌐 Server: http://{host}:{port}")
        print(f"🔧 Debug Mode: {debug}")
        print(f"📁 Working Directory: {os.getcwd()}")
        print(f"🐍 Python Version: {sys.version.split()[0]}")
        print("=" * 60)
        print("🎯 Application is starting...")
        print("💡 Press Ctrl+C to stop the server")
        print("=" * 60)

        # Start the Flask development server
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True,
            use_reloader=debug  # Only use reloader in debug mode
        )

    except ImportError as e:
        print(f"❌ Failed to import Flask app: {e}")
        print("💡 Make sure app.py exists and is properly configured")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
