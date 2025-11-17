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

## Recent Changes

### 2025-11-17 (Latest)
**Profile Action Buttons Mobile Fix**:
- **Enhanced Mobile Display**: Profile page Export and Settings buttons now properly sized for mobile (44x44px touch targets)
- **Better Spacing**: Added 12px gap between buttons on mobile for easier tapping
- **Touch-Friendly**: Minimum sizes ensure buttons meet accessibility standards
- **Interactive Feedback**: Added smooth transitions and scale animation on press
- **Consistent Icons**: Font Awesome icons properly sized at 18px on mobile
- **Cross-Device Support**: Buttons remain properly sized and spaced on all screen sizes

**Password Toggle Button Styling**:
- **Enhanced Button Design**: Password visibility toggle button now has polished, modern styling
- **Interactive States**: Added smooth hover (light gray background) and active (pressed effect) states
- **Visual Improvements**: White background, proper spacing, and smooth transitions
- **Better UX**: Clear visual feedback on interaction with scale animation on click
- **Consistent Design**: Seamlessly integrates with password input field

**Agency Portal Mobile View Fix**:
- **Responsive "Your Users" Table**: Applied responsive table system to the "Your Users" section in agency portal
- **Mobile Card View**: Table now transforms into mobile-friendly cards on screens ≤768px
- **Data Labels**: Added data-label, data-primary, and data-secondary attributes for proper mobile display
- **Table ID**: Added unique table ID (agencyUsersTable) for responsive functionality
- **Fixed Display Issue**: Users are now properly displayed on mobile devices in the agency portal

**Scrollable Pages with Hidden Scrollbars**:
- **Scrollable Pages**: Login, signup, and landing pages are now fully scrollable when content overflows
- **Hidden Scrollbars**: Scrollbars are hidden for a clean, modern appearance
- **Cross-Browser Support**: Implemented scrollbar hiding for Chrome/Safari (webkit), Firefox (scrollbar-width), and IE/Edge (ms-overflow-style)
- **Best of Both Worlds**: Pages scroll smoothly without visible scrollbars
- **Applied to**: index.html (landing page), login.html, and signup.html pages

**Dark Mode Text Visibility Fix**:
- **Fixed Hardcoded Black Text**: Changed all `color: #000000 !important` instances to use `var(--text-color)` for proper dark mode support
- **Signup Page Labels**: All form labels, radio button labels, and check labels now respect dark/light theme
- **Onboarding Page Header**: Removed hardcoded black color from "Complete your profile" heading
- **Theme-Aware Colors**: All text now uses CSS variables that automatically adjust based on the active theme