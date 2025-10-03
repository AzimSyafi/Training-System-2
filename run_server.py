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
    PORT         - Server port (default: 5050)
    FLASK_DEBUG  - Enable debug mode (default: False)
    FLASK_ENV    - Flask environment (development/production)
"""

import os
import sys
import argparse
from pathlib import Path
import importlib.util

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

def _load_flask_app_from_file():
    """Load the Flask app object from the top-level app.py explicitly by file path.
    This avoids confusion with the 'app/' directory being treated as a namespace package.
    Returns the Flask app object.
    """
    root = Path(__file__).parent
    app_py = root / 'app.py'
    if not app_py.exists():
        raise ImportError(f"app.py not found at {app_py}")
    spec = importlib.util.spec_from_file_location('app_module', str(app_py))
    if spec is None or spec.loader is None:
        raise ImportError('Could not load specification for app.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['app_module'] = module
    spec.loader.exec_module(module)
    if not hasattr(module, 'app'):
        raise ImportError('The module app.py does not define a Flask `app` variable')
    return module.app

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
        # Import the Flask app explicitly from app.py to avoid name collision with app/ directory
        app = _load_flask_app_from_file()

        # Configuration: default to port 5050 unless overridden
        port = args.port or int(os.environ.get('PORT', 5050))
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

        # Print a quick route map to help diagnose 404s
        try:
            rules = sorted([f"{r.rule} -> {','.join(sorted(r.methods))}" for r in app.url_map.iter_rules()], key=lambda s: s)
            print("🔎 Registered routes (sample):")
            for line in rules[:25]:  # don't spam; show first 25
                print("  •", line)
            print(f"… total routes: {len(rules)}")
        except Exception as e:
            print(f"(Could not enumerate routes: {e})")

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
