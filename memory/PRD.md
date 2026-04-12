# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC (Governance, Risk & Compliance) platform with AI-powered policy generation, intelligent control mapping, LLM-powered compliance assistance, and SIEM integration.

## Design System
- Brand: #2597B2 (primary), #1B839F (hover), #0a3540 (dark)
- Full dark mode support

## App Structure

### Navigation
```
COMMAND CENTER - Dashboard (customizable widgets)
GOVERNANCE - Frameworks (organize + workspace) | Policies (Policy Center - 5 tabs)
RISK - Risk Assessment | Vendors
SECURITY - SIEM
COMPLIANCE - Compliance (Audits + Evidence)
OPERATIONS - Tasks | Integrations | Settings
Global: Cmd+K Command Palette, Compliance Copilot (AI chat)
```

## Key Features

### Policy Center (Standout Feature)
**Tab 1: Policy Templates**
- [x] 10 pre-built GRC templates with framework mappings
- [x] Template Detail View: click template → see all sections, framework coverage with control IDs, SIEM thresholds, Generate button
- [x] Organization Questionnaire, AI policy generation via GPT-5.2
- [x] Policy Version Control: snapshots, diff, restore, approval workflow (Draft→Under Review→Approved)
- [x] Reviewer & Approver Assignment from org users
- [x] Approved Policy → Framework Linkage (auto-creates control mappings)

**Tab 2: Upload & Map (Redesigned Apr 12, 2026)**
- [x] Dual upload mode: "Map to Framework" (select frameworks) or "General Upload" (no framework required)
- [x] Document category selector: Policy, Procedure, Evidence, Contract, Training, Other
- [x] Custom labels/tags input (comma-separated) stored on upload
- [x] Expanded file support: PDF, DOCX, DOC, TXT, CSV, XLSX, PNG, JPG
- [x] Recent uploads with category + custom tag badges

**Tab 3: Document Library (Redesigned Apr 12, 2026)**
- [x] Unified view: generated policies + uploaded documents in one list
- [x] 4 filters: Search, Type (Policies/Uploads), Status (Draft/Under Review/Approved), Category
- [x] **Click-to-view**: Click generated policy → opens PolicyViewer with approval bar; Click uploaded doc → opens DocumentDetailPanel
- [x] DocumentDetailPanel: file info, category badge, Edit mode (change category, description)
- [x] **Custom Labels system**: Add/remove freeform tags with auto-suggest from previously used labels
- [x] **Framework Control Tags**: Add/remove framework+control ID tags per document
- [x] Status badges, type badges, framework tags, custom tag pills on each card

**Tab 4-5: Control Mappings + Cross-Framework**

### Frameworks & AI Control Mapping
- [x] Framework grid with Organize panel, Framework Workspace with AI assessment
- [x] Policies tab per control shows approved policy mappings

### Dashboard (Customizable)
- [x] 5 widget sections, toggle visibility + reorder

### Other Features
- [x] 12 frameworks, 869 controls, Command Palette (Cmd+K)
- [x] Compliance Copilot (GPT-5.2), Slack Integration, SIEM with live simulator
- [x] Full dark mode, JWT auth with demo accounts

## Architecture
```
Backend: FastAPI + Motor (async MongoDB)
Frontend: React 18 + Tailwind + Shadcn
Key Routes:
  /api/policy-templates (templates, versions, status, diff, restore, assignees, org-users, document-tags)
  /api/documents (upload, list, metadata, custom-tags, download-url)
  /api/control-compliance, /api/copilot, /api/siem, etc.
DB Collections: org_profiles, generated_templates, policy_versions, mappings,
                document_tags, document_uploads, control_compliance, siem_events, users, frameworks
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2)
```

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## Backlog
### P1
- Dynamic Risk Scoring (SIEM → real-time risk scores)
- Vendor Risk Assessments (TPRM with compliance tracking)
### P2
- Automated Evidence Collection, Compliance Calendar
- Predictive Insights, Compliance Report Export (PDF/DOCX)
- SIEM alerting rules, event correlation
