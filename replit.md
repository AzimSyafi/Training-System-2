# Security Personnel Training System

## Overview
This project is a Flask-based training platform for security professionals. It offers interactive training modules, quizzes, certificate generation, and career progression tracking. The system supports multiple user roles (Admin, User, Trainer, Agency, Authority) and includes an agency portal for progress oversight and bulk user import. The platform is designed to be mobile-responsive and provide a comprehensive learning and management experience.

## User Preferences
Not specified.

## System Architecture

### Technology Stack
- **Backend**: Flask (Python 3.12)
- **Database**: PostgreSQL (Replit-managed Neon database)
- **Frontend**: HTML templates with Tailwind CSS
- **Server**: Gunicorn for production, Flask development server for development

### UI/UX Decisions
- Comprehensive mobile-responsive design supporting various screen sizes and touch-friendly interactions.
- Enhanced UI/UX with improved form field visibility, interactive states, and streamlined certificate management.
- Responsive table system that transforms into card-based layouts on mobile devices with detailed modals.
- Clean, modern design with hidden scrollbars for core pages.
- Dark mode support with theme-aware colors.

### Core Features
- Interactive training modules and quiz system with progress tracking.
- PDF Certificate generation.
- Multi-role support: Admin, User, Trainer, Agency, Authority.
- Agency portal for monitoring employee progress.
- Bulk user import functionality.
- Dynamic work experience editor within user profiles.
- Redesigned certificate template editor with drag-and-drop functionality and live PDF preview.
- Course completion statistics visualized using Chart.js graphs on the Admin dashboard.
- Admin and Trainer interfaces for course and user management.

### Project Structure
- **Application Core**: `app.py`, `run_server.py`, `models.py`, `routes.py`, `authority_routes.py`, `database.py`, `utils.py`, `certificate.py`
- **Frontend Assets**: `templates/` (HTML), `static/` (CSS, JS, images, uploads, profile pictures)
- **Database Management**: `migrations/`
- **Testing**: `tests/`

### System Design
- Uses environment variables for sensitive configurations.
- Database tables are automatically created on the first run.
- Tailwind CSS is integrated with build and watch modes.
- Production deployment utilizes Gunicorn.
- Quiz system is embedded directly into module pages, featuring a vertical accordion layout and responsive design for mobile.
- Unified sidebar toggle functionality across all screen sizes.

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

## Recent Changes

### 2025-11-19 (Latest)
**Profile Edit Form - IC Number Field Protection**:
- **Greyed Out for Foreigners**: IC Number field is now disabled and greyed out for users with user_category = 'foreigner'
- **Visual Feedback**: Field displays with light grey background, reduced opacity (60%), and 'not-allowed' cursor
- **Prevents Editing**: Foreigner users cannot modify the IC Number field in their profile
- **Citizens Unaffected**: IC Number field remains fully editable for citizen users
- **Applied To**: templates/profile.html edit profile form