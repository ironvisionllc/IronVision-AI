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
- [x] **Template Detail View**: Click any template → see all sections, framework coverage with individual control IDs, SIEM thresholds with best practices, Generate button
- [x] Organization Questionnaire for personalized policies
- [x] SIEM Threshold Suggestions for technical controls
- [x] AI policy generation via GPT-5.2
- [x] Fully editable sections with inline save
- [x] Generated policies listed with version, status, date

**Policy Version Control (Apr 12, 2026)**
- [x] Version Snapshots with change summaries, auto-version 1 on generation
- [x] Version History Dialog with LATEST/INITIAL tags, version diff (unified diff)
- [x] Version Restore creates new version automatically
- [x] Approval Workflow: Draft → Under Review → Approved with validated transitions
- [x] Read-Only Mode when policy is approved or under review

**Reviewer & Approver Assignment (Apr 12, 2026)**
- [x] Assign specific reviewers and approvers to each policy from org users
- [x] Assignee dialog with checkbox-based user selection (Reviewers/Approvers)
- [x] Assigned users displayed in the approval bar (blue for reviewers, green for approvers)

**Approved Policy → Framework Linkage (Apr 12, 2026)**
- [x] When policy approved, auto-creates mapping records in `mappings` collection
- [x] Maps policy to all addressed framework controls (fuzzy framework name matching)
- [x] Re-approval cleans old mappings and recreates fresh ones
- [x] Approved policies visible in Framework Workspace per-control "Policies" tab

**Tab 2: Upload & Map**
- [x] Upload PDF/DOCX policy documents, multi-framework selector, drag & drop

**Tab 3: Document Library (Unified, Apr 12, 2026)**
- [x] Unified view of generated policies AND uploaded documents
- [x] Type filter: All Types / Generated Policies / Uploaded Documents
- [x] Status filter: All / Draft / Under Review / Approved / Completed
- [x] Status badges + type badges (Policy/Upload) + framework tags
- [x] Search across both types, document tagging preserved

**Tab 4-5: Control Mappings + Cross-Framework**

### Frameworks & AI Control Mapping
- [x] Framework grid with Organize panel (show/hide, reorder)
- [x] Framework Workspace with AI assessment, policies tab per control
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
Key Routes: /api/policy-templates (templates, versions, status, diff, restore, 
            assignees, org-users, document-tags)
            /api/control-compliance, /api/copilot, /api/siem, etc.
DB Collections: org_profiles, generated_templates, policy_versions, mappings,
                document_tags, control_compliance, siem_events, users, frameworks
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
