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
- [x] Organization Questionnaire for personalized policies
- [x] SIEM Threshold Suggestions for technical controls
- [x] AI policy generation via GPT-5.2
- [x] Fully editable sections with inline save
- [x] Generated policies listed with version, status, date

**Policy Version Control (Apr 12, 2026)**
- [x] **Version Snapshots**: Save current policy state as immutable version with change summary
- [x] **Auto Version 1**: Auto-created on policy generation
- [x] **Version History Dialog**: Full list with version numbers, summaries, creator, timestamps, LATEST/INITIAL tags
- [x] **Version Diff**: Section-by-section unified diff between any two versions (additions in green, deletions in red)
- [x] **Version Restore**: Restore any previous version (creates new version automatically)
- [x] **Approval Workflow**: Draft -> Under Review -> Approved with validated transitions
- [x] **Status Badge**: Color-coded (Draft=amber, Under Review=blue, Approved=green)
- [x] **Read-Only Mode**: Edit buttons hidden when policy is approved or under review
- [x] **Status Transitions**: Submit for Review, Approve, Return to Draft, Reopen as Draft buttons

**Tab 2: Upload & Map**
- [x] Upload PDF/DOCX policy documents
- [x] Multi-framework selector
- [x] Drag & drop + browse upload UI

**Tab 3: Document Library**
- [x] Central repository with document tagging to controls
- [x] Tag dialog: select document, framework, control IDs, notes

**Tab 4-5: Control Mappings + Cross-Framework**

### Frameworks & AI Control Mapping
- [x] Framework grid with Organize panel (show/hide, reorder)
- [x] Framework Workspace with AI assessment
- [x] Implementation & Guidelines tab (AI-generated, cached)
- [x] Enhanced AI Policy Suggestion (WHERE met + Gaps)

### Dashboard (Customizable)
- [x] 5 widget sections, toggle visibility + reorder

### Other Features
- [x] 12 frameworks, 869 controls, Command Palette (Cmd+K)
- [x] Compliance Copilot (GPT-5.2), Slack Integration
- [x] SIEM with live simulator, Full dark mode, JWT auth

## Architecture
```
Backend: FastAPI + Motor (async MongoDB)
Frontend: React 18 + Tailwind + Shadcn
Key Routes: /api/policy-templates (templates, versions, status, diff, restore, document-tags)
            /api/control-compliance, /api/copilot, /api/siem, etc.
DB Collections: org_profiles, generated_templates, policy_versions, document_tags, 
                control_compliance, siem_events, users, frameworks, controls
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2)
```

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## Backlog
### P1
- Dynamic Risk Scoring (SIEM -> real-time risk scores)
- Vendor Risk Assessments (TPRM with compliance tracking)
### P2
- Automated Evidence Collection, Compliance Calendar
- Predictive Insights, Compliance Report Export (PDF/DOCX)
- SIEM alerting rules, event correlation
