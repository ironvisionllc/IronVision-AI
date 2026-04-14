# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC (Governance, Risk & Compliance) platform with AI-powered policy generation, intelligent control mapping, LLM-powered compliance assistance, SIEM integration, and Universal Compliance Ingestion Layer.

## Design System
- Brand: #2597B2 (primary), #1B839F (hover), #0a3540 (dark)
- Full dark mode support

## App Structure

### Navigation
```
COMMAND CENTER - Dashboard (customizable widgets)
GOVERNANCE - Frameworks (organize + workspace + Ingestion Layer) | Policies (Policy Center - 5 tabs)
RISK - Risk Assessment | Vendors
SECURITY - SIEM
COMPLIANCE - Compliance (Audits + Evidence)
OPERATIONS - Tasks | Integrations | Settings
Global: Cmd+K Command Palette, Compliance Copilot (AI chat)
```

## Key Features

### Policy Center
**Tab 1: Policy Templates**
- [x] 10 pre-built templates, Template Detail View, Org Questionnaire
- [x] AI policy generation (GPT-5.2), Policy Version Control (snapshots, diff, restore)
- [x] Approval Workflow (Draft→Under Review→Approved), Reviewer/Approver Assignment
- [x] Approved Policy → Framework Linkage (auto-creates control mappings)

**Tab 2: Upload & Map (3 Modes)**
- [x] **Map to Framework**: Select frameworks + upload docs for compliance mapping
- [x] **General Upload**: Upload any document (no framework required)
- [x] **Create Document**: Built-in text editor to write policies/procedures locally
- [x] Category selector: Policy/Procedure/Evidence/Contract/Training/Other
- [x] Custom labels input, expanded file support

**Tab 3: Document Library (Unified)**
- [x] Unified view: generated policies + uploaded docs + created docs
- [x] 4 filters: Search, Type, Status, Category
- [x] Click-to-view: opens PolicyViewer or DocumentDetailPanel
- [x] DocumentDetailPanel: file info, category, custom labels, framework tags
- [x] **Document Approval Workflow**: Draft→Under Review→Approved
- [x] **Content Editor**: Edit content inline for created documents
- [x] Read-only mode when approved/under review

**Tab 4-5: Control Mappings + Cross-Framework**

### Frameworks & AI Control Mapping
- [x] Framework grid with Organize panel, Framework Workspace
- [x] **Policy Coverage Summary**: Aggregate bar showing X/Y controls have linked policies
- [x] **Link Document to Control**: In Policies tab, pick any document to link
- [x] **AI Coverage Analysis**: Analyze how well a linked document covers a control's requirements
- [x] **Unlink Document**: Remove linked documents from controls
- [x] Implementation & Guidelines tab, AI Policy Suggestions

### Universal Compliance Ingestion Layer (NEW - Apr 14, 2026)
- [x] **Phase 1: Checklist Parser Engine** - Parses STIG (XML/XCCDF), CIS (YAML/CSV), PCI DSS (JSON), Questionnaires (CSV/JSON)
  - Normalizes all parsed items into unified `ingested_controls` schema
  - Handles namespace-agnostic XML parsing, nested sections, flexible field mapping
- [x] **Phase 2: Auto-Mapping Engine** - AI-powered cross-framework mapping using GPT-5.2
  - Maps ingested controls against 14 existing compliance frameworks
  - Batch processing (15 controls at a time) for token management
  - Returns confidence scores and mapping reasons
- [x] **Phase 3: SIEM Tie-In** - Links ingested controls to SIEM events
  - Derives SIEM categories from mapped framework controls
  - Shows monitored/attention/critical/no_events status
  - Correlates with last 30 days of SIEM event data
- [x] **Phase 4: Frontend UI** - Full ingestion management interface
  - Upload interface with source type selection (STIG/CIS/PCI/Questionnaire)
  - Checklist list view with status badges (Parsed/Mapped)
  - Detail view with 3 tabs: Control Graph, Framework Overlaps, SIEM Status
  - Stats cards (total/mapped/unmapped/severity), mapping progress bar
  - Search & filter (severity, mapping status)
  - Expandable control rows showing framework mappings and SIEM categories
  - Framework coverage distribution bars
  - Overlap pairs and multi-framework controls view
  - Sample files available for testing

### Dashboard (Customizable)
- [x] 5 widget sections, toggle visibility + reorder

### Other Features
- [x] 14 frameworks (incl. NERC CIP, NERC 693), 962 controls, Command Palette (Cmd+K)
- [x] Compliance Copilot (GPT-5.2), Slack Integration, SIEM with live simulator
- [x] Full dark mode, JWT auth with demo accounts

## Architecture
```
Backend: FastAPI + Motor (async MongoDB)
Frontend: React 18 + Tailwind + Shadcn
Key Routes:
  /api/policy-templates (templates, versions, status, diff, restore, assignees, org-users, document-tags)
  /api/documents (upload, create, list, metadata, content, status, custom-tags, download-url)
  /api/control-compliance (compliance, link-document, unlink-document, analyze-coverage, suggest-policy)
  /api/ingestion (upload, checklists, auto-map, overlap, siem-status, sample-files)
  /api/copilot, /api/siem, /api/frameworks, etc.
DB Collections: org_profiles, generated_templates, policy_versions, mappings,
                document_tags, document_uploads, control_compliance, siem_events, users, frameworks,
                ingested_checklists, ingested_controls
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2)
```

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## SIEM Mappings (Updated Apr 14, 2026)
All 14 frameworks mapped to 7 SIEM categories. Coverage: StateRAMP 99%, NIST 800-171 92%, NERC CIP 72%, CMMC 70%, NIS2 67%, HIPAA 62%, ISO 27001 52%, SOC 2 49%, FS AI 40%, NERC 693 38%, NIST AI RMF 33%, GDPR 28%, NIST CSF 25%, NIST 800-53 12%.

## Backlog
### P1
- Dynamic Risk Scoring (SIEM → real-time risk scores)
- Vendor Risk Assessments (TPRM with compliance tracking)
### P2
- Automated Evidence Collection, Compliance Calendar
- Predictive Insights, Compliance Report Export (PDF/DOCX)
- SIEM alerting rules, event correlation
- Coverage Gap Report (aggregate controls with low/no coverage)
