# Security Personnel Training System

## Overview
This project is a Flask-based training platform designed for security professionals. It enables users to engage with interactive training modules, complete quizzes, earn certificates, and monitor their career progression. The system supports multiple user roles, including Admin, User, Trainer, Agency, and Authority, and features an agency portal for progress oversight and bulk user import capabilities.

## User Preferences
Not specified.

## System Architecture

### Technology Stack
- **Backend**: Flask (Python 3.12)
- **Database**: PostgreSQL (Replit-managed Neon database)
- **Frontend**: HTML templates with Tailwind CSS
- **Server**: Gunicorn for production, Flask development server for development

### Key Features
- Interactive training modules and quiz system with progress tracking.
- PDF Certificate generation.
- Multi-role support: Admin, User, Trainer, Agency, Authority.
- Agency portal for monitoring employee progress.
- Bulk user import functionality.
- Comprehensive mobile-responsive design supporting various screen sizes and touch-friendly interactions.
- Dynamic work experience editor within user profiles.
- Redesigned certificate template editor with drag-and-drop functionality and live PDF preview.
- Course completion statistics visualized using Chart.js graphs on the Admin dashboard.
- Responsive table system that transforms into card-based layouts on mobile devices with detailed modals.
- Enhanced UI/UX with improved form field visibility, interactive states, and streamlined certificate management.

### Project Structure
- **Application Core**: `app.py`, `run_server.py`, `models.py`, `routes.py`, `authority_routes.py`, `database.py`, `utils.py`, `certificate.py`
- **Frontend Assets**: `templates/` (HTML), `static/` (CSS, JS, images, uploads, profile pictures)
- **Database Management**: `migrations/`
- **Testing**: `tests/`

### Deployment and Development
- Uses environment variables for `DATABASE_URL`, `SECRET_KEY`, and `PORT`.
- Database tables are automatically created on the first run.
- Tailwind CSS requires building (`npm run build:css`) for deployment and has a development watch mode (`npm run dev:css`).
- Production deployment utilizes Gunicorn with worker reuse.

### User Roles
1.  **Admin**: Full system access, user and course management.
2.  **User**: Standard learners.
3.  **Trainer**: Manage content and monitor learners.
4.  **Agency**: Monitor employee progress.
5.  **Authority**: Approve certificates and manage compliance.

## External Dependencies

### Python Packages
-   Flask, Flask-Login, Flask-SQLAlchemy, Flask-Mail
-   psycopg (PostgreSQL adapter)
-   ReportLab, PyPDF2 (PDF generation)
-   openpyxl (Excel import)

### Node.js Packages
-   Tailwind CSS (styling framework)
-   Chart.js (for data visualization)