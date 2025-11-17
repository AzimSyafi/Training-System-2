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
**Course Completion Graph Visualization**:
- **Replaced Table with Chart**: Admin dashboard course completion statistics now uses Chart.js interactive graph instead of static table
- **Graph Features**:
  - Mixed bar/line chart showing Completion Rate (%), Average Score (%), and Total Attempts
  - Dual Y-axes: percentages (left), attempt counts (right)
  - Green bars for completion rates, blue bars for average scores, orange line for attempts
  - Hover tooltips showing formatted data
- **Mobile-Responsive Design**:
  - Dynamic responsive configuration using isMobile() function
  - Smaller fonts on mobile (10-13px vs 12-14px desktop)
  - Legend positioned at bottom on mobile, top on desktop
  - 45-degree rotated X-axis labels on mobile for readability
  - Axis titles hidden on mobile to save space
  - Debounced (150ms) resize handler for smooth transitions without page reload
- **Graceful Handling**:
  - Empty data shows friendly "No course completion data available yet" message
  - Numeric data preserved throughout (formatted only in tooltips)
  - Fallback defaults for missing fields (course_name, scores, attempts)
- **Backend Fix**: Converted SQLAlchemy Row objects to dictionaries for JSON serialization in models.py getDashboard()

**Responsive Table System - Full-Width and Mobile Cards**:
- **Full-Width Tables**: All tables now fill the entire width of their container boxes on desktop (removed padding restrictions)
- **Mobile Card Layout (≤768px)**: Tables automatically transform into card-based layouts on mobile devices
  - Each table row becomes a tappable card showing primary information (Name + Email/Course)
  - Clicking/tapping any card opens a detail modal displaying ALL row data (Type, ID, Agency, Status, Actions, etc.)
  - Clean card design without arrows - simple, tap-friendly interface
  - Pagination works seamlessly with card view - showing "X-Y of Z" with navigation arrows
- **Architecture**:
  - Created `static/css/responsive-tables.css` for styling (full-width enforcement + mobile card styles)
  - Created `static/responsiveTable.js` for mobile transformation logic (integrates with existing TablePagination)
  - Uses `data-responsive-table="true"` attribute on tables to enable responsive behavior
  - Uses `data-label`, `data-primary`, `data-secondary` attributes on headers for card rendering
- **Coverage**: Applied to admin_users.html, monitor_progress.html, agency_progress_monitor.html, admin_certificates.html tables

**UI/UX Improvements - November 17 PM**:
- **User Management Table Full Width**: Removed padding from table-responsive div to allow table to fill the full card width for better data visibility
- **Hidden Table Scrollbars on Mobile**: Tables maintain horizontal scroll functionality but scrollbar is now hidden on mobile for cleaner UI (using scrollbar-width: none and ::-webkit-scrollbar)
- **Small Square Trash Icon Buttons**: All trash/delete icon buttons now render as small squares (32px standard, 28px for btn-sm) using aspect-ratio: 1/1 with proper centering
- **Progress Monitoring Modal System**: 
  - User names in progress monitoring pages are now clickable links
  - Clicking a user name opens a Bootstrap modal showing detailed course progress for that specific user
  - Modal displays progress bars, completion status, average scores, and completion counts per course
  - Implemented secure event handling using data attributes instead of inline onclick to prevent JavaScript injection
  - Added HTML escaping to prevent XSS attacks
  - Works correctly with special characters in names (apostrophes, quotes, etc.)
  - Available on both admin progress monitor and agency progress monitor pages
  - Fixed agency_progress_monitor route to use correct template (agency_progress_monitor.html) and pass all required data fields
  - Enhanced modal with better visibility: larger user name header (h5 bold), course count display, console debugging, and improved table styling with max-height scrolling

**Mobile-Responsive Design System**:
- **Comprehensive Mobile Support**: Implemented full mobile-responsive design system supporting screens from 320px to desktop
- **Touch-Friendly Interface**: All interactive elements (buttons, links, form inputs) now have 44px minimum touch targets for mobile usability
- **Mobile-First CSS**: Enhanced Tailwind CSS and responsive.css with mobile-first breakpoints (≤768px mobile, 769-1024px tablet, >1024px desktop)
- **Form Optimization**: All form inputs now use 16px font size on mobile to prevent iOS zoom, with improved spacing and touch targets
- **Modal Full-Screen**: Modals now take full-screen on mobile devices with sticky headers/footers for better usability
- **Table Scrolling**: Tables are horizontally scrollable on mobile with proper touch gestures
- **Certificate Editor Mobile**: Certificate template editor optimized for mobile with larger drag targets and stackable layout
- **Responsive Navigation**: Hamburger menu works seamlessly on all screen sizes with smooth slide-out animation
- **Dashboard Cards**: Statistics and dashboard cards stack vertically on mobile for better readability
- **Module Cards**: Course and module cards fully responsive with adjusted padding, font sizes, and button layouts

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
