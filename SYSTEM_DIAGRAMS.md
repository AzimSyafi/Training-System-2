# SHAPADU Security Training System - Technical Diagrams

## Table of Contents
1. [System Architecture Diagram](#system-architecture-diagram)
2. [Entity Relationship Diagram (ERD)](#entity-relationship-diagram-erd)
3. [System Flowcharts](#system-flowcharts)

---

## System Architecture Diagram

```mermaid
graph TB
    subgraph "Client Layer"
        Browser[Web Browser]
        Mobile[Mobile Browser]
    end

    subgraph "Frontend Layer"
        Jinja[Jinja2 Templates]
        Tailwind[Tailwind CSS]
        Bootstrap[Bootstrap 5.3]
        ChartJS[Chart.js]
        PDFJS[PDF.js]
    end

    subgraph "Application Layer - Flask"
        Routes[Routes Handler]
        Auth[Flask-Login Auth]
        
        subgraph "Core Modules"
            UserMgmt[User Management]
            CourseMgmt[Course Management]
            QuizEngine[Quiz Engine]
            CertGen[Certificate Generator]
            AuthorityApproval[Authority Approval]
        end
    end

    subgraph "Business Logic"
        UserModule[User Progress Tracker]
        GradeCalc[Grade Calculator]
        BulkImport[Excel Bulk Import]
        TemplateEditor[Certificate Template Editor]
    end

    subgraph "Data Layer"
        SQLAlchemy[SQLAlchemy ORM]
        PostgreSQL[(PostgreSQL Database<br/>Neon-backed)]
    end

    subgraph "External Libraries"
        ReportLab[ReportLab - PDF Generation]
        PyPDF2[PyPDF2 - PDF Manipulation]
        Werkzeug[Werkzeug - Security]
        OpenPyXL[OpenPyXL - Excel Processing]
        FlaskMail[Flask-Mail - Email]
    end

    subgraph "Storage"
        StaticFiles[Static Files Storage]
        Uploads[User Uploads<br/>Profile Pics, Templates]
        Certificates[Generated Certificates]
    end

    Browser --> Jinja
    Mobile --> Jinja
    Jinja --> Routes
    Tailwind --> Browser
    Bootstrap --> Browser
    ChartJS --> Browser
    PDFJS --> Browser

    Routes --> Auth
    Auth --> UserMgmt
    Auth --> CourseMgmt
    Auth --> QuizEngine
    Auth --> CertGen
    Auth --> AuthorityApproval

    UserMgmt --> UserModule
    CourseMgmt --> UserModule
    QuizEngine --> GradeCalc
    CertGen --> TemplateEditor
    AuthorityApproval --> CertGen

    UserModule --> SQLAlchemy
    GradeCalc --> SQLAlchemy
    BulkImport --> SQLAlchemy
    TemplateEditor --> SQLAlchemy

    SQLAlchemy --> PostgreSQL

    CertGen --> ReportLab
    CertGen --> PyPDF2
    Auth --> Werkzeug
    BulkImport --> OpenPyXL
    Routes --> FlaskMail

    CertGen --> Certificates
    UserMgmt --> Uploads
    Routes --> StaticFiles
```

---

## Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    ADMIN ||--o{ APPROVAL_AUDIT : "approves"
    ADMIN {
        int admin_id PK
        string username
        string email
        string password_hash
        boolean is_superadmin
        boolean dark_mode_enabled
        datetime created_at
    }

    AGENCY ||--o{ USER : "employs"
    AGENCY ||--o{ AGENCY_ACCOUNT : "has"
    AGENCY {
        int agency_id PK
        string agency_name
        string contact_person
        string email
        string phone
        datetime created_at
    }

    AGENCY_ACCOUNT {
        int account_id PK
        int agency_id FK
        string username
        string email
        string password_hash
        boolean dark_mode_enabled
        datetime created_at
    }

    USER ||--o{ USER_MODULE : "completes"
    USER ||--o{ USER_COURSE_PROGRESS : "tracks"
    USER ||--o{ CERTIFICATE : "earns"
    USER ||--o{ WORK_HISTORY : "has"
    USER {
        int User_id PK
        string number_series "SG2025NNNN"
        string full_name
        string email
        string password_hash
        string user_category "citizen/foreigner"
        string ic_number
        string passport_number
        int agency_id FK
        string role "agency/trainer/authority"
        boolean is_finalized
        boolean dark_mode_enabled
        datetime created_at
    }

    TRAINER {
        int trainer_id PK
        string username
        string email
        string password_hash
        boolean dark_mode_enabled
        datetime created_at
    }

    COURSE ||--o{ MODULE : "contains"
    COURSE {
        int course_id PK
        string course_code
        string course_name
        string description
        string user_category "citizen/foreigner/both"
        datetime created_at
    }

    MODULE ||--o{ USER_MODULE : "attempted_by"
    MODULE ||--o{ CERTIFICATE : "certifies"
    MODULE {
        int module_id PK
        int course_id FK
        string module_name
        string series_number
        string module_type "TNG/CSG"
        string youtube_url
        string slide_url
        json quiz_json
        text content
        datetime created_at
    }

    USER_MODULE {
        int user_id FK
        int module_id FK
        boolean is_completed
        float score
        date completion_date
        int reattempt_count
        string grade "A-Z+"
    }

    USER_COURSE_PROGRESS {
        int progress_id PK
        int user_id FK
        string course_code
        float overall_percentage
        datetime last_updated
    }

    CERTIFICATE ||--o{ APPROVAL_AUDIT : "audited"
    CERTIFICATE {
        int certificate_id PK
        int user_id FK
        int module_id FK
        string module_type "TNG/CSG"
        date issue_date
        float score
        string status "pending/approved"
        string certificate_url
        int approved_by_id FK
        datetime approved_at
    }

    CERTIFICATE_TEMPLATE {
        int id PK
        string name
        int name_x
        int name_y
        int name_font_size
        boolean name_visible
        int ic_x
        int ic_y
        int ic_font_size
        boolean ic_visible
        int course_type_x
        int course_type_y
        int course_type_font_size
        boolean course_type_visible
        int percentage_x
        int percentage_y
        int percentage_font_size
        boolean percentage_visible
        int grade_x
        int grade_y
        int grade_font_size
        boolean grade_visible
        int text_x
        int text_y
        int text_font_size
        boolean text_visible
        int date_x
        int date_y
        int date_font_size
        boolean date_visible
        boolean is_active
        datetime created_at
        datetime updated_at
    }

    WORK_HISTORY {
        int id PK
        int user_id FK
        string company_name
        string position
        date start_date
        date end_date
        text responsibilities
    }

    APPROVAL_AUDIT {
        int audit_id PK
        int certificate_id FK
        int approved_by_id FK
        datetime approved_at
        string approver_type "admin/user"
    }

    USER ||--o{ APPROVAL_AUDIT : "approver"
```

---

## System Flowcharts

### 1. User Registration & Onboarding Flow

```mermaid
flowchart TD
    Start([User Visits Landing Page]) --> SignupForm[Fill Signup Form]
    SignupForm --> CreateUser[Create User Account<br/>is_finalized = False]
    CreateUser --> Step1[Onboarding Step 1/4<br/>Address, State, Postcode]
    Step1 --> Step2[Onboarding Step 2/4<br/>Work Experience Entries]
    Step2 --> Step3[Onboarding Step 3/4<br/>Emergency Contact]
    Step3 --> Step4[Onboarding Step 4/4<br/>Visa/IC Details]
    Step4 --> Finalize[Set is_finalized = True]
    Finalize --> Dashboard([User Dashboard])
```

### 2. Course Completion & Certificate Flow

```mermaid
flowchart TD
    Start([User Dashboard]) --> SelectCourse[Select Course<br/>Filtered by citizen/foreigner]
    SelectCourse --> ViewModules[View Course Modules]
    ViewModules --> FirstModule{First Module?}
    FirstModule -->|Yes| Unlocked[Module Unlocked]
    FirstModule -->|No| CheckPrevious{Previous Module<br/>Completed?}
    CheckPrevious -->|No| Locked[Module Locked]
    CheckPrevious -->|Yes| Unlocked
    
    Unlocked --> WatchContent[Watch Video/View Slides]
    WatchContent --> TakeQuiz[Take Quiz]
    TakeQuiz --> SubmitQuiz[Submit Answers]
    SubmitQuiz --> ServerScore[Server Scores Quiz]
    ServerScore --> CheckScore{Score >= 50%?}
    
    CheckScore -->|No| Failed[Quiz Failed<br/>Increment reattempt_count]
    Failed --> Retry{Retry Quiz?}
    Retry -->|Yes| TakeQuiz
    Retry -->|No| ViewModules
    
    CheckScore -->|Yes| Passed[Quiz Passed<br/>Set is_completed = True]
    Passed --> UnlockNext[Unlock Next Module]
    UnlockNext --> MoreModules{More Modules?}
    MoreModules -->|Yes| ViewModules
    MoreModules -->|No| AllComplete[All Modules Complete]
    
    AllComplete --> CalcAverage[Calculate Average Score]
    CalcAverage --> AutoGenCert[Auto-generate Certificate<br/>status = 'pending'<br/>score = average]
    AutoGenCert --> UserSees[User Sees Pending Certificate]
    UserSees --> WaitApproval[Wait for Authority Approval]
    
    WaitApproval --> AuthApprove[Authority Approves]
    AuthApprove --> UpdateStatus[Update status = 'approved'<br/>Create ApprovalAudit]
    UpdateStatus --> DownloadCert([User Downloads PDF Certificate])
```

### 3. Certificate Approval Workflow

```mermaid
flowchart TD
    Start([Authority Login]) --> Dashboard[Authority Dashboard]
    Dashboard --> ViewPending[View Pending Certificates]
    ViewPending --> FilterSearch[Filter/Search Certificates]
    FilterSearch --> SelectCerts{Selection Type?}
    
    SelectCerts -->|Individual| SelectOne[Select Specific Certificates]
    SelectCerts -->|All Pending| SelectAll[Select All Pending]
    SelectCerts -->|By User| SelectUser[Select All by User ID]
    
    SelectOne --> ApproveAction[Click Approve Selected]
    SelectAll --> ApproveAction
    SelectUser --> ApproveAction
    
    ApproveAction --> BulkUpdate[Bulk UPDATE certificate<br/>SET status = 'approved']
    BulkUpdate --> CreateAudit[Create ApprovalAudit Records<br/>approved_by_id = authority<br/>approved_at = NOW]
    CreateAudit --> Success[Show Success Message]
    Success --> Notify[User Notified]
    Notify --> UserDownload([User Can Download Certificate])
```

### 4. Quiz Taking & Grading Flow

```mermaid
flowchart TD
    Start([User Opens Module]) --> LoadQuiz[Load Quiz via API<br/>/api/load_quiz/module_id]
    LoadQuiz --> DisplayQuiz[Display Quiz Questions]
    DisplayQuiz --> UserAnswers[User Selects Answers]
    UserAnswers --> AutoSave{Auto-save Enabled?}
    AutoSave -->|Yes| SaveProgress[POST /api/save_quiz_answers<br/>Save in-progress answers]
    AutoSave -->|No| Continue
    SaveProgress --> Continue[Continue Answering]
    Continue --> Submit[Click Submit Quiz]
    
    Submit --> PostAnswers[POST /api/submit_quiz/module_id<br/>Send all answers]
    PostAnswers --> ServerValidate[Server Validates Answers]
    ServerValidate --> CalcScore[Calculate Score<br/>correct/total * 100]
    CalcScore --> CheckPassing{Score >= 50%?}
    
    CheckPassing -->|Yes| Pass[Quiz Passed]
    CheckPassing -->|No| Fail[Quiz Failed]
    
    Pass --> SaveComplete[Save UserModule<br/>is_completed = True<br/>score = calculated_score<br/>reattempt_count++]
    Fail --> SaveIncomplete[Save UserModule<br/>is_completed = False<br/>score = calculated_score<br/>reattempt_count++]
    
    SaveComplete --> CalcGrade[Calculate Grade<br/>A + reattempt_count<br/>0=A, 1=B, 2=C...]
    SaveIncomplete --> CalcGrade
    
    CalcGrade --> ReturnResult[Return JSON Response<br/>score, passed, grade, correct, total]
    ReturnResult --> DisplayResult([Display Results to User])
```

### 5. Certificate Template Editor Flow

```mermaid
flowchart TD
    Start([Admin Opens Editor]) --> LoadPDF[Load PDF Template via API<br/>/api/get_active_certificate_template]
    LoadPDF --> RenderCanvas[Render PDF on Canvas<br/>A4 size: 595x842 points]
    RenderCanvas --> CreateMarkers[Create Draggable Field Markers<br/>7 fields: name, ic, course_type,<br/>percentage, grade, text, date]
    CreateMarkers --> LoadPositions[Load Saved Positions<br/>from CertificateTemplate]
    LoadPositions --> DisplayEditor([Editor Ready])
    
    DisplayEditor --> UserDrags[User Drags Markers]
    UserDrags --> UpdateInputs[Update X/Y Input Fields]
    UpdateInputs --> AdjustSettings{Adjust Settings?}
    
    AdjustSettings -->|Font Size| ChangeFontSize[Change Font Size 8-72]
    AdjustSettings -->|Visibility| ToggleVisible[Toggle Field Visibility]
    AdjustSettings -->|Continue| UserDrags
    
    ChangeFontSize --> Preview{Preview?}
    ToggleVisible --> Preview
    
    Preview -->|Yes| OpenPreview[Open /preview_certificate_template<br/>New tab with mock data]
    Preview -->|No| SaveCheck{Save?}
    
    OpenPreview --> ViewPDF[View Generated PDF<br/>with current positions]
    ViewPDF --> SaveCheck
    
    SaveCheck -->|Yes| ClickSave[Click Save Template]
    SaveCheck -->|No| UserDrags
    
    ClickSave --> CollectData[Collect All Field Data<br/>x, y, font_size, visible<br/>for all 7 fields]
    CollectData --> PostUpdate[POST /update_certificate_template<br/>Send JSON data]
    PostUpdate --> ServerUpdate[Update CertificateTemplate<br/>Deactivate other templates<br/>Set is_active = True]
    ServerUpdate --> Commit[db.session.commit]
    Commit --> ShowSuccess[Show Success Message<br/>Stay on Editor Page]
    ShowSuccess --> DisplayEditor
```

### 6. Admin Dashboard Analytics Flow

```mermaid
flowchart TD
    Start([Admin Login]) --> LoadDashboard[Load Admin Dashboard]
    LoadDashboard --> FetchData[Fetch Dashboard Data]
    
    FetchData --> GetStats[Get Statistics<br/>Total Users, Courses,<br/>Modules, Certificates]
    GetStats --> GetPerf[Get Performance Metrics<br/>Average Score,<br/>Max Score, Min Score]
    GetPerf --> GetCompletion[Get Completion Stats<br/>Per Course: completed,<br/>total attempts, avg score]
    
    GetCompletion --> PrepareChartData[Prepare Chart.js Data<br/>Labels: course names<br/>Datasets: completion rate,<br/>avg scores, total attempts]
    PrepareChartData --> RenderHTML[Render Dashboard HTML]
    RenderHTML --> LoadChartJS[Load Chart.js v4.4.0<br/>from CDN]
    LoadChartJS --> CreateChart[Create Mixed Chart<br/>Dual Y-axis<br/>Responsive config]
    CreateChart --> CheckMobile{Mobile Device?}
    
    CheckMobile -->|Yes| MobileConfig[Apply Mobile Settings<br/>Legend: bottom<br/>Smaller fonts<br/>Rotated labels]
    CheckMobile -->|No| DesktopConfig[Apply Desktop Settings<br/>Legend: top<br/>Standard fonts<br/>Horizontal labels]
    
    MobileConfig --> DisplayChart([Display Interactive Chart])
    DesktopConfig --> DisplayChart
    
    DisplayChart --> UserInteract{User Interaction?}
    UserInteract -->|Hover| ShowTooltip[Show Tooltip<br/>Formatted data with %]
    UserInteract -->|Resize| ResponsiveUpdate[Update Chart Layout<br/>Responsive resize]
    UserInteract -->|Navigate| End([Navigate to Other Pages])
    
    ShowTooltip --> DisplayChart
    ResponsiveUpdate --> DisplayChart
```

---

## System Components Summary

### Frontend Stack
- **Templates**: Jinja2 with Flask
- **CSS Frameworks**: Tailwind CSS 3.4.18 + Bootstrap 5.3.0
- **JavaScript Libraries**: Chart.js 4.4.0, PDF.js 3.11.174
- **Icons**: Font Awesome

### Backend Stack
- **Framework**: Flask 3.x
- **Authentication**: Flask-Login
- **ORM**: Flask-SQLAlchemy
- **Database**: PostgreSQL (Neon-backed)
- **PDF Processing**: ReportLab, PyPDF2
- **Excel Processing**: openpyxl
- **Email**: Flask-Mail

### Key Features
1. **Multi-role Access Control**: Superadmin, Admin, Trainer, Agency, User, Authority
2. **Sequential Learning**: Module unlocking based on completion
3. **Grading System**: Attempt-based grades (A→B→C with retakes)
4. **Certificate Workflow**: Auto-generation → Pending → Authority Approval → Download
5. **Visual Template Editor**: Drag-and-drop certificate field positioning
6. **Analytics Dashboard**: Chart.js visualizations for admin insights
7. **Bulk Operations**: Excel-based user import, bulk certificate approval
8. **Mobile Responsive**: Full mobile support across all pages

---

**Generated**: November 26, 2025
**Version**: 1.0
**System**: SHAPADU Security Personnel Training Platform
