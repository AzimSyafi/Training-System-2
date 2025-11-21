# SHAPADU Security Personnel Training System - Complete Documentation

## Table of Contents
1. [Project Overview](#project-overview)
2. [Features by User Role](#features-by-user-role)
3. [Technology Stack](#technology-stack)
4. [Installation & Setup](#installation--setup)
5. [User Flows](#user-flows)
6. [API Documentation](#api-documentation)
7. [Database Schema](#database-schema)
8. [Recent Changes](#recent-changes)

---

## Project Overview

### Purpose
SHAPADU Security Personnel Training System is a comprehensive web-based training platform designed for security professionals in Malaysia and international workers. The system provides structured training courses, interactive quizzes, certificate management with approval workflows, and multi-agency oversight capabilities.

### Goals
- **Standardize Training**: Provide consistent, high-quality security training across multiple agencies
- **Track Progress**: Monitor individual and agency-wide learning progress in real-time
- **Ensure Compliance**: Certificate approval workflow ensures training quality and regulatory compliance
- **Support Multiple Languages**: Accommodate both local citizens and foreign workers
- **Mobile Accessibility**: Full mobile responsiveness for learning on-the-go
- **Multi-Agency Management**: Support multiple security agencies with independent user bases

### Target Users
1. **Security Trainees** (Citizens & Foreigners): Primary learners completing courses
2. **Agency Managers**: Oversee their agency's employee training progress
3. **Trainers**: Create and manage training content
4. **Admins**: System-wide management and reporting
5. **Superadmins**: Full system control including admin management
6. **Authorities**: Approve certificates and ensure compliance

---

## Features by User Role

### Superadmin Features
- **Exclusive Admin Management**: Create, edit, and delete admin accounts
- **Full System Control**: All admin capabilities plus elevated privileges
- **Password Management**: Change passwords for any user type
- **Gold "SUPERADMIN" Badge**: UI distinction
- **Self-Deletion Protection**: Cannot delete own account

### Admin Features
- **User Management**: View, create, edit users/trainers
- **Course & Module Management**: Full CRUD for courses and modules
- **Agency Management**: Add and manage security agencies
- **Certificate Management**: View all certificates, generate manually, bulk delete
- **Dashboard Analytics**: Chart.js visualizations of completion stats

### User Features
- **Course Access**: Browse courses filtered by citizen/foreigner status
- **Sequential Module Unlocking**: Complete previous module to unlock next
- **Interactive Learning**: YouTube videos, slide presentations, quizzes
- **Unlimited Quiz Reattempts**: Grade decreases with retakes (A→B→C...)
- **Profile Management**: Update info, upload picture, manage work history
- **Certificate Download**: View and download approved certificates

### Trainer Features
- **Content Upload**: Add videos, slides, quizzes to assigned modules
- **Quiz Builder**: Visual interface for creating interactive quizzes
- **Student Monitoring**: Track learner progress and performance

### Agency Features
- **Employee Management**: Create users, bulk import via Excel
- **Progress Dashboard**: Real-time tracking of all employees
- **Bulk Import**: Excel template-based mass user creation

### Authority Features
- **Certificate Approval**: View pending certificates, approve individually or in bulk
- **Approval Audit**: Automatic logging of all approval actions
- **Dashboard Stats**: Pending count, approved today, total approved

---

## Technology Stack

### Backend
- Flask 3.x, Flask-Login, Flask-SQLAlchemy, Flask-Mail
- PostgreSQL (Replit-managed Neon), psycopg 3.2.9
- Werkzeug (password hashing), ReportLab/PyPDF2 (PDFs)
- openpyxl (Excel), Gunicorn (production server)

### Frontend
- Jinja2 templates, Tailwind CSS 3.4.18, Bootstrap 5.3.0
- Chart.js (visualizations), Font Awesome (icons)
- Custom responsive table system, dark mode with per-user database storage

### Database
- PostgreSQL with SQLAlchemy ORM
- 13 tables: admin, agency, agency_account, user, course, module, user_module, user_course_progress, certificate, certificate_template, trainer, work_history, approval_audit

---

## Installation & Setup

### Local Development
```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Install Node.js dependencies
npm install

# 3. Build Tailwind CSS
npm run build:css

# 4. Set up database (use DATABASE_URL env variable)
# For PostgreSQL:
export DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"

# 5. Run migrations
python migrations/add_superadmin_column.py
python migrations/add_dark_mode_preference.py

# 6. Create admin account
python create_admin.py

# 7. Start server
python run_server.py
# Server runs on http://0.0.0.0:5000
```

### Replit Deployment
- DATABASE_URL provided automatically
- Set SECRET_KEY in Replit Secrets
- Workflow auto-configured: `PORT=5000 python run_server.py --host 0.0.0.0`
- Tables created automatically on first run

---

## User Flows

### User Registration Flow
```
Landing Page → Signup Form → Create User (is_finalized=False)
  → Onboarding Step 1/4 (Address, state, postcode)
  → Onboarding Step 2/4 (Work experience entries)
  → Onboarding Step 3/4 (Emergency contact)
  → Onboarding Step 4/4 (Visa/IC details)
  → is_finalized=True → User Dashboard
```

### Course Completion Flow
```
User Dashboard → Select Course → View Modules
  → First module always unlocked
  → Subsequent modules locked until previous is completed (UserModule.is_completed=True)
  → Click Module → Watch video/View slides
  → Expand Quiz Accordion → Take Quiz
  → Submit → Server Scores → Save to UserModule
    - Sets is_completed=True if score >= 50%
    - Increments reattempt_count on each attempt
    - Next module unlocks automatically
  → If all modules complete → Auto-generate Certificate (status='pending')
  → User sees "Pending" certificate
  → Authority approves → Certificate status='approved'
  → User downloads PDF
```

### Certificate Approval Flow
```
Authority Login → View Pending Certificates
  → Filter/Search → Select certificates
  → Approve Selected / Approve All / Approve by User
  → Bulk UPDATE certificate SET status='approved'
  → Create ApprovalAudit record
  → User can now download certificate
```

---

## API Documentation

**Note**: This section covers primary user-facing endpoints. The system has 40+ additional admin/trainer endpoints for course management, user CRUD, and system configuration. See routes.py for complete endpoint list.

### Authentication
- **POST /login**: Authenticate user, create session
- **POST /signup**: Create new user account
- **POST /logout**: Destroy session

### Courses & Modules
- **GET /courses**: List available courses (filtered by user_category)
- **GET /course/<id>**: View modules in course
- **GET /modules/<code>**: Alternative module view by course code

### Quiz API
- **GET /api/load_quiz/<module_id>**: Retrieve quiz questions (JSON)
- **POST /api/save_quiz_answers/<module_id>**: Auto-save in-progress answers
- **POST /api/submit_quiz/<module_id>**: Submit for scoring
  - Request: `{0: "answerA", 1: "answerC", ...}`
  - Response: `{score: 85.5, passed: true, grade: "A", correct: 17, total: 20}`

### Certificates
- **GET /my_certificates**: View user's certificates
- **GET /generate_and_download_certificate/<id>**: Download PDF

### Authority
- **GET /authority**: View certificate approval portal
- **POST /authority/bulk_approve**: Approve certificates
  - `{scope: "selected", cert_ids: [1,2,3]}` - Approve selected
  - `{scope: "all"}` - Approve all pending
  - `{scope: "user", user_id: 123}` - Approve all for user

### Admin Endpoints (Examples)
- **POST /create_course**: Create new course
- **POST /add_course_module/<course_id>**: Add module to course
- **POST /create_user**: Admin creates user
- **POST /admin_change_user_password**: Admin/superadmin changes password

### Theme
- **POST /api/save_theme_preference**: Save dark mode to database
  - Request: `{dark_mode: true}`
  - Updates: admin/user/trainer/agency_account.dark_mode_enabled

---

## Database Schema

### Key Tables

**user** (Main learner table):
- User_id (PK), number_series (SG2025NNNN), email, password_hash
- user_category ('citizen'|'foreigner'), ic_number, passport_number
- agency_id (FK), role ('agency'|'trainer'|'authority')
- dark_mode_enabled, is_finalized

**module**:
- module_id (PK), module_name, series_number, course_id (FK)
- youtube_url, slide_url, quiz_json (JSON), content

**user_module** (Progress tracking):
- user_id (FK), module_id (FK)
- is_completed, score, completion_date, reattempt_count
- Grade calculated as: chr(ord('A') + reattempt_count)
  - 0 attempts = A, 1 = B, 2 = C, ..., 26+ = Z+

**certificate**:
- certificate_id (PK), user_id (FK), module_id (FK)
- score, status ('pending'|'approved'), certificate_url
- approved_by_id (FK), approved_at

**admin**:
- admin_id (PK), username, email, password_hash
- is_superadmin, dark_mode_enabled

### Relationships
```
Agency 1:N User 1:N UserModule N:1 Module N:1 Course
User 1:N Certificate N:1 Module
User 1:N ApprovalAudit (as approver) N:1 Certificate
User 1:N WorkHistory
```

---

## Recent Changes

### 2025-11-21 (Latest)
**Fixed Dark Mode Cross-Account Bug**:
- Added `dark_mode_enabled` column to all user tables
- Theme preferences now stored per-user in database
- Prevents cross-account contamination from localStorage
- Files: models.py, routes.py, templates/base.html, migrations/add_dark_mode_preference.py

**Force Light Mode on Public Pages**:
- Login, signup, landing pages enforce light mode
- Inline scripts remove dark classes before rendering
- Prevents theme bleed after logout

**Enhanced Admin Password Change**:
- New `/admin_change_user_password` route
- Superadmins can change all user passwords
- Regular admins limited to users/trainers only
- Files: routes.py, templates/admin_users.html

**Superadmin Role Implementation**:
- Added `is_superadmin` column to admin table
- Exclusive admin management rights
- Gold "SUPERADMIN" UI badge
- Self-deletion protection
- Files: models.py, utils.py, routes.py, migrations/add_superadmin_column.py

---

**End of Documentation**

This documentation provides a comprehensive overview of the SHAPADU Security Personnel Training System. For specific feature details, see:
- `SUPERADMIN_IMPLEMENTATION.md` - Superadmin role details
- `BULK_IMPORT_GUIDE.md` - Agency bulk user import
- `CERTIFICATE_EDITOR_README.md` - Certificate template editor
