# IronVision AI - GRC Platform - Product Requirements Document

## Problem Statement
Merge IronVision AI's existing enterprise GRC platform with enhanced features from a new Emergent-built GRC app. IronVision AI is the source of truth — its branding, design system, integrations, and Policy Builder are preserved. New GRC features are integrated natively into IronVision's design language.

## Design System
- **Primary**: IronVision Blue Munsell (#2597B2)
- **Secondary**: Blue Munsell Dark (#1B839F)
- **Accent**: Gold (#FFB700 for success/completed states)
- **Text**: Onyx (#454548)
- **Background**: Off-white (#FDFDFD), Cards: white with 2xl rounded corners
- **Font**: Inter (400-800 weights)
- **Dark Mode**: Supported via CSS class toggle
- **Component Library**: Shadcn/UI with IronVision color overrides

## Architecture
```
/app/backend/
├── server.py                 (Entry point, router registration)
├── database.py               (Local MongoDB connection)
├── ironvision_db.py          (IronVision Atlas MongoDB connection)
├── models.py, utils.py       (Pydantic models, auth, logging)
├── seed.py                   (Demo data seeding incl. notifications)
├── framework_controls_data.py (12 frameworks, NIST 800-53)
├── cci_data.py               (243 CCIs)
├── nist_questionnaire_data.json (982 questions, 20 families)
├── routes/
│   ├── auth.py, admin.py
│   ├── frameworks.py, policies.py, mappings.py
│   ├── risks.py, vendors.py (+ PUT/DELETE), audits.py
│   ├── tasks.py, evidence.py, training.py
│   ├── analytics.py, compliance.py, reports.py
│   ├── activity.py, notifications.py
│   ├── controls.py, exports.py
│   ├── ironvision.py         (IronVision Atlas proxy)
│   ├── policy_builder.py     (Questionnaire-based policy builder)
│   ├── documents.py          (S3 document upload + Lambda preprocessing)
│   ├── compliance_trends.py  (Historical compliance trend snapshots)
│   └── email_notifications.py (AWS SES email notifications)
/app/frontend/
├── src/
│   ├── App.js
│   ├── index.css             (IronVision brand palette)
│   ├── components/Layout.js  (IronVision sidebar with dark mode, notifications)
│   └── pages/
│       ├── PolicyBuilderPage.js  (Questionnaire flow)
│       ├── DocumentsPage.js      (S3 upload + Lambda analysis)
│       ├── Dashboard.js          (Exec dashboard + compliance trends chart)
│       ├── LoginPage.js, RegisterPage.js
│       ├── PoliciesPage.js (Policy Library)
│       ├── FrameworksPage.js, ControlDetailPage.js
│       ├── CrossFrameworkPage.js (collapsible heatmap)
│       ├── RisksPage.js, VendorsPage.js (edit/delete)
│       ├── AuditsPage.js, TasksPage.js, EvidencePage.js
│       ├── ActivityPage.js, TrainingPage.js
│       └── MappingsPage.js, IntegrationsPage.js, SettingsPage.js
```

## Implemented Features (as of Apr 3, 2026)

### Core Platform
- [x] IronVision AI branding (logo, colors, dark mode, sidebar design)
- [x] JWT Auth with register/login + Demo accounts
- [x] IronVision Atlas MongoDB connection (Policy Builder data access)
- [x] 12 compliance frameworks (NIST 800-53 with 20 families, 190 controls, 243 CCIs)
- [x] AI-Powered Control Mapping (GPT-5.2)

### Policy Builder
- [x] Questionnaire-based policy creation (982 questions across 20 NIST 800-53 families)
- [x] Step-by-step flow: select family → answer questions → review → generate
- [x] Draft save/resume/delete with progress tracking
- [x] Quality score indicator (Incomplete → Minimal → Good → Excellent)
- [x] Lambda invocation for policy generation (configured, needs AWS permissions)

### Dashboard & Reporting
- [x] Executive Dashboard with compliance score, risk heatmap, deadlines, activity feed
- [x] **Compliance Trend Timeline** — area chart showing historical compliance snapshots
- [x] PDF Executive Report download
- [x] Quick Actions panel

### Risk & Compliance
- [x] Risk Management with create-from-risk remediation tasks
- [x] Vendor Management with edit/delete in admin mode
- [x] Audit Management
- [x] Cross-Framework Mapping with collapsible heatmap
- [x] CCI drill-down (Frameworks → Controls → CCIs)

### Operations
- [x] Task Management with Kanban view
- [x] Evidence Library with file upload
- [x] In-App Notifications (bell, dropdown, unread count)
- [x] **Real-time Notification Polling** — automatic refresh of notification feed
- [x] Audit Trail / Activity (timeline view with filters)
- [x] **Training & Awareness** — 12 comprehensive modules (7 GRC knowledge + 5 platform training) with lessons, quizzes, progress tracking, category filtering, and search

### Document Management & Analysis
- [x] **S3 Document Upload** — chunked file upload to AWS S3 bucket
- [x] **Lambda Preprocessing Pipeline** — invokes IronVision Lambda for document preprocessing
- [x] **Compliance Analysis Pipeline** — invokes Lambda for compliance analysis on uploaded docs

### Email Notifications
- [x] **AWS SES Integration** — email notification endpoints configured
- [x] SES status check endpoint (`/api/email-notifications/status`)
- [x] Note: SES sender `noreply@ironvision.ai` requires domain verification in AWS console (sandbox mode)

### Integrations Configured
- [x] OpenAI GPT-5.2 (via Emergent LLM Key)
- [x] IronVision MongoDB Atlas
- [x] AWS S3 + Lambda (credentials configured)
- [x] AWS SES (credentials configured, sender verification pending)
- [x] Pinecone (placeholder)

## Backlog (Prioritized)

### P3
- Advanced Workflow Rules for Task Management
- Integration Hub persistence (Slack, Jira, SIEM)
- Enhanced PDF reports with charts
