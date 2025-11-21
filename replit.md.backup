# SHAPADU Security Personnel Training System - Compressed Documentation

## Overview
The SHAPADU Security Personnel Training System is a comprehensive web-based platform designed for training security professionals in Malaysia and international workers. Its primary purpose is to standardize training, track progress, ensure compliance through a certificate approval workflow, and support multi-agency management with multi-language and mobile accessibility. The system caters to security trainees, agency managers, trainers, administrators, superadministrators, and authorities, aiming to provide consistent, high-quality security training and robust progress monitoring.

## User Preferences
I prefer iterative development with clear communication at each stage. Ask before making major architectural changes or introducing new dependencies. Ensure code is well-commented and follows Flask/Python best practices. I prioritize security and maintainability.

## System Architecture

### UI/UX Decisions
- **Responsive Design**: Mobile-first approach with custom responsive table system for optimal viewing across devices.
- **Theme System**: Database-backed per-user dark mode preference, synchronized with local storage for instant feedback and persistence.
- **Templates**: Jinja2 for dynamic HTML rendering.
- **Styling**: Tailwind CSS 3.4.18 for utility-first styling, compiled via npm scripts.
- **Icons**: Font Awesome for a consistent icon set.
- **Visualizations**: Chart.js for dashboard analytics and statistics.

### Technical Implementations
- **Authentication**: Flask-Login with custom user loader supporting multiple user types (Admin, User, Trainer, Agency Account) and robust session management. Password hashing uses Werkzeug security.
- **Authorization**: Role-based access control implemented via decorators (`@login_required`, `@superadmin_required`) and explicit role checks.
- **Database**: PostgreSQL (Replit-managed Neon) with SQLAlchemy ORM. Custom Python migration scripts manage schema changes.
- **PDF Generation**: ReportLab and PyPDF2 for server-side certificate generation, with a visual template editor for drag-and-drop field positioning and customization.
- **Quiz System**: Client-side quiz builder (JavaScript) with server-side scoring, supporting unlimited reattempts and a dynamic grading system (A→B→C based on reattempts). Quiz data is JSON-formatted.
- **User Management**: Supports self-registration, agency bulk import via Excel (using `openpyxl`), and admin manual creation. Includes a multi-step onboarding process for new users.
- **Content Management**: Trainers/Admins can upload YouTube videos, PDF/PPTX slide presentations, and create interactive quizzes.
- **Certificate Workflow**: Automated certificate generation upon course completion (status 'pending'), followed by an authority approval workflow with bulk approval capabilities and audit logging.
- **File Storage**: Static assets, uploaded slides, profile pictures, and generated certificates are stored on the local filesystem within `static/` directory.

### Feature Specifications
- **Superadmin**: Exclusive admin management (create, edit, delete admins), full system control, and a gold UI badge.
- **Admin**: Comprehensive user, course, module, agency, and certificate management. Includes dashboard analytics.
- **User**: Course access filtered by category, sequential module unlocking, progress tracking, unlimited quiz reattempts, profile management, and certificate download.
- **Trainer**: Content upload to assigned modules, quiz creation, and student monitoring.
- **Agency**: Employee management (create, bulk import), progress monitoring for agency employees.
- **Authority**: Certificate approval workflow (pending, approved, bulk actions), approval audit.

### System Design Choices
- **Modular Flask Application**: Structured with dedicated files for models, routes, utilities, and specific user roles.
- **Environment Management**: Utilizes `python-dotenv` for configuration and Replit Secrets for sensitive information.
- **Development & Deployment**: Designed for seamless deployment on Replit using Gunicorn as the production server.

## External Dependencies
- **Backend Framework**: Flask 3.x
- **Database**: PostgreSQL (via Neon on Replit), psycopg 3.2.9, psycopg2-binary
- **ORM**: Flask-SQLAlchemy
- **Authentication**: Flask-Login
- **Password Hashing**: Werkzeug security
- **PDF Generation**: ReportLab, PyPDF2
- **Excel Processing**: openpyxl
- **Email**: Flask-Mail (SendGrid for production, MailHog for development)
- **Token Generation**: itsdangerous
- **HTTP Requests**: requests library
- **Production Server**: Gunicorn
- **Frontend Libraries**:
    - Jinja2 (templating)
    - Tailwind CSS 3.4.18 (CSS framework)
    - Chart.js (data visualization)
    - Bootstrap 5.3.0 (UI components)
    - html2pdf.bundle.min.js (client-side PDF generation)
    - Font Awesome (icons)
- **Development Tools**: pytest (testing), python-dotenv, npm (for Node.js dependencies like Tailwind)