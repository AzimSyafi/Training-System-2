"""
Development Configuration for Training System
============================================

This file contains development-specific settings and utilities
to ensure the Flask app always starts correctly.
"""

import os
from pathlib import Path

# Development server settings
DEV_CONFIG = {
    'host': '0.0.0.0',
    'port': 5000,
    'debug': True,
    'threaded': True,
    'use_reloader': True
}

def ensure_flask_app_runnable():
    """
    Ensures that app.py has the necessary code to run as a Flask server.
    This is a safety net to prevent the 'exit code 0' problem.
    """
    app_file = Path(__file__).parent / 'app.py'

    if not app_file.exists():
        raise FileNotFoundError("app.py not found!")

    # Read the current app.py content
    with open(app_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if it has the required startup code
    has_main_block = "if __name__ == '__main__':" in content
    has_app_run = "app.run(" in content

    if not (has_main_block and has_app_run):
        print("⚠️  WARNING: app.py is missing server startup code!")
        print("🔧 Adding required startup code to app.py...")

        # Add the missing startup code
        startup_code = '''

if __name__ == '__main__':
    # Development server configuration
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes', 'on')
    
    print(f"[SERVER] Starting Flask development server on port {port}")
    print(f"[SERVER] Debug mode: {debug}")
    print(f"[SERVER] Open your browser to: http://localhost:{port}")
    
    # Run the Flask development server
    app.run(
        host='0.0.0.0',  # Allow connections from any IP
        port=port,
        debug=debug,
        threaded=True  # Enable threading for better performance
    )
'''

        # Only add if it doesn't already exist
        if not has_main_block:
            with open(app_file, 'a', encoding='utf-8') as f:
                f.write(startup_code)
            print("✅ Added startup code to app.py")
        else:
            print("ℹ️  app.py has startup code but may need manual review")

    return True

def get_dev_config():
    """Returns development configuration with environment overrides"""
    config = DEV_CONFIG.copy()

    # Override with environment variables if present
    if 'PORT' in os.environ:
        config['port'] = int(os.environ['PORT'])

    if 'FLASK_DEBUG' in os.environ:
        config['debug'] = os.environ['FLASK_DEBUG'].lower() in ('true', '1', 'yes', 'on')

    if 'FLASK_HOST' in os.environ:
        config['host'] = os.environ['FLASK_HOST']

    return config

def print_startup_banner(config):
    """Print a helpful startup banner"""
    print("=" * 70)
    print("🎓 TRAINING SYSTEM - DEVELOPMENT SERVER")
    print("=" * 70)
    print(f"🌐 URL: http://{config['host']}:{config['port']}")
    print(f"🔧 Debug: {config['debug']}")
    print(f"🔄 Auto-reload: {config['use_reloader']}")
    print(f"📁 Directory: {os.getcwd()}")
    print("=" * 70)
    print("💡 Tips:")
    print("   • Press Ctrl+C to stop the server")
    print("   • Set FLASK_DEBUG=1 for debug mode")
    print("   • Set PORT=8000 for custom port")
    print("=" * 70)

if __name__ == '__main__':
    # This can be used as a standalone configuration checker
    ensure_flask_app_runnable()
    config = get_dev_config()
    print_startup_banner(config)
