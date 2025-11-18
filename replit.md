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

### 2025-11-18 (Latest)
**Trainer Progress Monitoring Complete Redesign to Match Admin Page**:
- **Complete UI Overhaul**: Redesigned trainer progress monitoring section to match admin's monitor_progress.html page design
- **Five Working Filters**: Added fully functional 5-filter layout matching admin page:
  - Search input (filters by User, Agency, Course name) - col-md-3
  - Agency dropdown (filters by agency_id) - col-md-2  
  - Course dropdown (filters by course_id) - col-md-2
  - Status dropdown (All/In Progress/Completed) - col-md-2
  - Progress % range (Min-Max number inputs) - col-md-3
  - Apply & Reset buttons
- **Backend Filtering Logic**: trainer_portal route now applies all filters to progress_rows data:
  - Search query (q) filters by user name, email, agency name, and course name
  - Agency filter applies User.agency_id filter to database query
  - Course filter skips courses not matching course_id
  - Status filter separates 'Completed' (100% progress) from 'In Progress'
  - Progress range filter applies min_progress and max_progress bounds
  - All filters work together and preserve selected state via request.args
- **Bootstrap Components**: Replaced custom components with Bootstrap:
  - Bootstrap card (card shadow-sm) for filter section
  - Bootstrap table (table table-striped align-middle) for data display
  - Bootstrap modal (modal fade, modal-dialog modal-lg) for user progress details
  - Proper responsive table attributes (data-label, data-primary, data-secondary)
- **Custom CSS Cleanup**: Removed all custom modal CSS that conflicted with Bootstrap (.modal, .modal-content, .modal-close, etc.)
- **Bootstrap Modal Functionality**: Clicking a user name shows ALL their courses in a Bootstrap modal with:
  - User info (name, agency)
  - Table of all courses showing progress bars, scores, and status badges
  - Proper XSS protection with HTML escaping
- **Backend Data Provision**: Added agencies and courses queries to trainer_portal route (matching admin approach)
- **Responsive Design**: Table transforms to mobile-friendly cards on screens ≤768px
- **Full Parity**: Trainer progress monitoring now has complete functional and visual parity with admin monitor_progress page

**Trainer Content Management Enhancement**:
- **Admin-Style Upload Interface**: Trainers can now use the same content management system as admins
- **Unified manage_module_content Route**: Both Admin and Trainer roles can upload slides, videos, and manage quizzes
- **Improved Back Navigation**: Back button in upload_content page now includes icon and navigates to correct section
- **Role-Based Redirects**: After uploading content, trainers redirect to trainer_portal, admins to admin_course_management
- **Enhanced Upload Workflow**: Trainers have full access to slide uploads (PDF/PPTX), YouTube video URLs, and quiz management

### 2025-11-17
**Trainer Role Assignment and Course Management**:
- **Auto-Create Trainer Records**: When admin changes a user's role to 'trainer', system automatically creates a Trainer table record
- **Number Series Generation**: New trainers get assigned a unique TR{YEAR}{NNNN} series number
- **Password Sync**: User passwords are automatically synced to trainer accounts for seamless login
- **Smart Login Redirect**: Users with trainer role are automatically redirected to trainer portal upon login
- **Course Assignment UI**: Admins can assign specific courses to trainers via dropdown in admin users page
- **Flexible Access Control**: Trainers can be assigned to specific courses or given access to all courses
- **Backend Route**: New /assign_trainer_course endpoint handles course assignments with validation
- **Course List Integration**: Admin users page now includes full course list for assignment dropdown
- **Duplicate Prevention**: Admin users page now filters out duplicate entries when users are converted to trainers (shows Trainer record only, not both User and Trainer)

**Profile Action Buttons Mobile Fix**:
- **Enhanced Mobile Display**: Profile page Export and Settings buttons now properly sized for mobile (44x44px touch targets)
- **Better Spacing**: Added 12px gap between buttons on mobile for easier tapping
- **Touch-Friendly**: Minimum sizes ensure buttons meet accessibility standards
- **Interactive Feedback**: Added smooth transitions and scale animation on press
- **Consistent Icons**: Font Awesome icons properly sized at 18px on mobile
- **Cross-Device Support**: Buttons remain properly sized and spaced on all screen sizes
- **Fixed Dropdown Positioning**: Export and Settings dropdown menus now open from left on mobile to prevent cutoff
- **High Z-Index**: Dropdowns appear above all content with z-index: 9999 for proper visibility

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