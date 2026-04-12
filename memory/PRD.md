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

### Policy Center (Standout Feature - Apr 12, 2026)
**Tab 1: Policy Templates**
- [x] 10 pre-built GRC templates: Access Control, Incident Response, Risk Management, Data Protection, System Integrity, Configuration Management, Audit & Accountability, Personnel Security, Contingency Planning, Physical Security
- [x] Each template maps to multiple frameworks (NIST 800-53, NIST CSF, GDPR) with specific controls
- [x] **Organization Questionnaire**: CISO, Data Owner, Policy Owner, Compliance Officer, Industry, Review Frequency — auto-populates generated policies
- [x] **SIEM Threshold Suggestions**: For technical controls (AC-2, AC-7, IR-4, SI-4, etc.) with specific best-practice thresholds
- [x] AI policy generation via GPT-5.2 produces full editable documents with proper sections
- [x] **Fully editable output**: Every section can be edited and saved inline
- [x] Generated policies listed with version, status, and date

**Tab 2: Upload & Map**
- [x] Upload PDF/DOCX policy documents
- [x] **Multi-framework selector**: Choose which frameworks to map against (12 frameworks)
- [x] Drag & drop + browse upload UI
- [x] Recent uploads list with status

**Tab 3: Document Library**
- [x] Central repository of all uploaded documents
- [x] **Document tagging**: Tag any document to specific framework controls
- [x] Tag dialog: select document, framework, control IDs, notes
- [x] Tags visible on each document card, removable

**Tab 4-5: Control Mappings + Cross-Framework** (secondary utilities)

### Frameworks & AI Control Mapping
- [x] Framework grid with Organize panel (show/hide, reorder)
- [x] Framework Workspace: per-control compliance, SIEM evidence, AI assessment
- [x] Expand All / Collapse All
- [x] Implementation & Guidelines tab (AI-generated, cached)
- [x] Enhanced AI Policy Suggestion (WHERE met + Gaps)
- [x] SIEM maps to all frameworks (NIST 800-53, NIST CSF, GDPR)

### Dashboard (Customizable)
- [x] 5 widget sections, toggle visibility + reorder
- [x] Posture metrics, Framework Coverage, Risk Heatmap, Compliance Trend, Control Effectiveness, Tasks

### Other Features
- [x] 12 frameworks, 869 controls, Command Palette (Cmd+K)
- [x] Compliance Copilot (GPT-5.2), Slack Integration
- [x] Control Effectiveness Scores, SIEM with live simulator
- [x] Full dark mode, JWT auth with demo accounts

## Architecture
```
Backend: FastAPI + Motor (async MongoDB)
Frontend: React 18 + Tailwind + Shadcn
Key Routes: /api/policy-templates (NEW), /api/control-compliance, /api/copilot, /api/siem, etc.
DB Collections: org_profiles, generated_templates, document_tags, control_compliance, siem_events, etc.
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
