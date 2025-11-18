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
**Admin User Creation - User & Authority Role Support**:
- **Fixed "Invalid role selected" Error**: Backend now properly handles 'user' and 'authority' roles in create account modal
- **User Creation**: Creates regular user accounts with default 'citizen' category and finalized status
- **Authority Creation**: Creates authority accounts with 'authority' role and finalized status
- **Improved Modal UX**: Changed modal from scrollable to centered positioning to fix dropdown appearing too far down on mobile
- **All Four Roles Supported**: Admin can now create Admin, Trainer, User, and Authority accounts from the modal

**Trainer Course Management - Admin-Style Interface**:
- **New Dedicated Page**: Created `/trainer_course_management` route with full admin-style course management UI
- **Course Cards Grid**: Beautiful card layout matching admin interface, showing assigned courses with module counts
- **Module Management**: Module cards with status badges (Slides, Video, Quiz) that turn green when content exists
- **Tabbed Content Modal**: Click "Manage Content" on any module to access Slides/Video/Quiz tabs
- **Read-Only Course Info**: Trainers can view course details but cannot edit course name, code, or category
- **Read-Only Module Info**: Trainers can view module details but cannot edit module name or series number
- **Content Management Only**: Trainers can upload slides (PDF/PPTX), add YouTube videos, and build quizzes
- **No Create/Delete**: Removed all course and module creation/deletion buttons for trainers
- **Course Filtering**: Trainers only see courses they're assigned to via `current_user.course` field
- **Security Enforcement**: Server-side authorization prevents trainers from accessing modules outside their assigned courses
- **Navigation Cleanup**: Added "Course Management" link and removed redundant "My Courses" navigation item
- **Proper Redirects**: All content upload endpoints redirect trainers to `trainer_course_management` after saving
- **Defensive Checks**: Validates module-course relationships and logs security warnings for unauthorized access attempts

**Trainer Progress Monitoring Mobile View Fix**:
- **Responsive Table System**: Applied responsive table system to "Trainee Performance" table in trainer portal
- **Mobile Card View**: Tables now transform into mobile-friendly cards on screens ≤768px
- **Data Labels**: Added data-label, data-primary, and data-secondary attributes for proper mobile display
- **Trainee Name Display**: User names now display prominently on mobile devices, just like in admin pages
- **Course Details Table**: Also updated the course details user table with responsive attributes
- **Dynamic Content**: JavaScript-generated table rows now include responsive attributes for consistency

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