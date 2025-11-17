# Security Personnel Training System

## Overview
A comprehensive Flask-based training platform for security professionals. The system allows users to complete training modules, take quizzes, earn certificates, and track their career progress.

## Project Architecture

### Technology Stack
- **Backend**: Flask (Python 3.12)
- **Database**: PostgreSQL (Replit-managed Neon database)
- **Frontend**: HTML templates with Tailwind CSS
- **Server**: Gunicorn for production, Flask dev server for development

### Key Features
- Interactive training modules
- Quiz system with progress tracking
- Certificate generation (PDF)
- Multi-role support (Admin, User, Trainer, Agency, Authority)
- Agency portal for progress monitoring
- Bulk user import functionality

### Project Structure
```
├── app.py                    # Main Flask application
├── run_server.py             # Development server entry point
├── models.py                 # SQLAlchemy database models
├── routes.py                 # Main application routes
├── authority_routes.py       # Authority-specific routes
├── database.py               # Database helpers and utilities
├── utils.py                  # Utility functions and Jinja filters
├── certificate.py            # Certificate generation logic
├── templates/                # HTML templates
├── static/                   # Static assets (CSS, JS, images)
│   ├── css/                  # Stylesheets including Tailwind
│   ├── uploads/              # User uploads (gitignored)
│   └── profile_pics/         # Profile pictures
├── migrations/               # Database migration scripts
└── tests/                    # Test files
```

## Development Setup

### Environment Variables
- `DATABASE_URL`: PostgreSQL connection string (provided by Replit)
- `SECRET_KEY`: Flask secret key for sessions (required)
- `PORT`: Server port (defaults to 5000)

### Database
- Uses Replit's built-in PostgreSQL database (Neon-backed)
- Connection string is automatically provided via DATABASE_URL
- Database tables are created automatically on first run via `db.create_all()`

### Running Locally
The application runs automatically via the configured workflow:
```bash
PORT=5000 python run_server.py --host 0.0.0.0
```

### Building CSS
Tailwind CSS must be built before deployment:
```bash
npm run build:css
```

For development with auto-rebuild:
```bash
npm run dev:css
```

## Deployment Configuration

### Production Deployment
The app is configured for autoscale deployment:
- **Build**: Compiles Tailwind CSS
- **Run**: Uses Gunicorn with 2 workers on port 5000
- Database migrations should be handled before deploying

### Key Notes
- The frontend binds to 0.0.0.0:5000 (required for Replit)
- Gunicorn is used for production with worker reuse
- Static files are served through Flask in development

## User Roles
1. **Admin**: Full system access, user management, course creation
2. **User**: Standard learners, complete courses and quizzes
3. **Trainer**: Manage training content and monitor learners
4. **Agency**: Monitor employee progress
5. **Authority**: Approve certificates and manage compliance

## Recent Changes

### 2025-11-17 (Latest)
**Certificate System Fixes**:
- **Certificate Template Upload Fixed**: Corrected field name from `template_name` to `name` to match CertificateTemplate model
- **Certificate Download Fixed**: Implemented missing `/generate_and_download_certificate` route allowing users to download approved certificates
- **PDF Upload Size Fixed**: Increased file upload limit to 50 MB to support large PDF certificate templates
- **Certificate Generation Fixed**: Updated to use admin-uploaded templates from `static/uploads/certificate_templates/` instead of hardcoded path
- **Module Lookup Fixed**: Added direct module_id lookup and case-insensitive fallback to prevent "No module found" errors
- **Certificate Template API Fixed**: Corrected API endpoint to use `template.name` instead of non-existent `template.template_file` field

**UI/UX Improvements**:
- **Form Field Visibility**: Added visible borders (2px gray) and shadow effects to all form inputs for better visibility
- **Interactive Form States**: Added hover effects (darker border + shadow) and focus states (blue ring glow) to form fields
- **Working Experience Form**: Added dynamic work experience editor to Edit Profile modal with add/remove functionality
  - Users can add multiple work experience entries (company name, position, start date, end date)
  - Each entry can be individually removed
  - Green "Add Experience" button to create new entries
  - Red remove icon (X) to delete specific entries
- **Certificate Template Editor**: Redesigned with drag-and-drop functionality:
  - Live PDF preview with accurate positioning
  - Drag field markers directly on the certificate preview
  - Real-time position updates as you drag
  - Click markers to activate and highlight corresponding field settings
  - Toggle field visibility with checkboxes
  - Clean UI without emojis
  - API endpoint to fetch active certificate template PDF

### 2025-11-14
**Critical Bug Fixes**:
- **Slide Upload Fixed**: Created `allowed_slide_file()` validation function to accept PDF and PPTX files for module slides (previously only images were allowed)
- **Multi-Step Onboarding Fixed**: Refactored onboarding flow to properly progress through all 4 steps instead of finalizing users on step 1
  - Step 1: Personal details + profile picture
  - Step 2: Contact details (phone, address, location)
  - Step 3: Work details + employment history
  - Step 4: Emergency contact (only this step finalizes the user)
  - Fixed profile picture upload crash by setting `Profile_picture` database field instead of read-only `profile_pic_url` property
- **Role Dropdown Fixed**: Added missing "User" and "Authority" roles to admin account creation dropdowns
- **Country Dropdown Fixed**: Added comprehensive list of all countries (excluding Israel) to onboarding contact details step
- **Course Completion Fixed**: Implemented missing `/api/complete_course` route to allow users to complete courses and send certificates for authority approval

**Previous Bug Fixes**:
- Fixed onboarding page crash by adding total_steps=4 variable to template rendering
- Fixed PDF slide upload by creating static/uploads/slides directory with makedirs safety check
- Implemented scroll position preservation for module uploads using course-aware hash navigation (#course-X-module-Y)
- Added automatic course panel expansion and smooth scroll-to-module with highlight effect

**Previous Setup**:
- Imported from GitHub to Replit environment
- Configured PostgreSQL database connection
- Set up Tailwind CSS build process
- Configured deployment with Gunicorn
- Updated .gitignore for Python and Node.js
- Created workflow for development server on port 5000

## Dependencies
See `requirements.txt` for Python dependencies and `package.json` for Node.js dependencies.

### Key Python Packages
- Flask, Flask-Login, Flask-SQLAlchemy, Flask-Mail
- psycopg (PostgreSQL adapter)
- ReportLab, PyPDF2 (PDF generation)
- openpyxl (Excel import)

### Key Node Packages
- Tailwind CSS (styling framework)
