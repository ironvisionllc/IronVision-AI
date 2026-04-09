# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC (Governance, Risk & Compliance) platform with AI-powered policy generation, intelligent control mapping, LLM-powered compliance assistance, and SIEM integration.

## Design System
- Brand: #2597B2 (primary), #1B839F (hover), #0a3540 (dark)
- Fonts: Plus Jakarta Sans (headings), Inter (body)
- Component system: .iv-card, .iv-stat-card, .iv-badge, .iv-btn-*, .iv-table
- Full dark mode support

## App Structure (Phase A Restructure Complete - Apr 9, 2026)

### Navigation Architecture
```
COMMAND CENTER
  - Dashboard (/dashboard)

GOVERNANCE
  - Frameworks (/frameworks) — Framework grid → click into Framework Workspace
    - Workspace: per-control compliance status, SIEM evidence, AI assessment, editable notes, policy suggestions
  - Policies (/policies) — Hub with 5 tabs:
    - Policy Builder: Guided questionnaire-based policy generation
    - Policy Library: Generated & local policies with export
    - Document Analysis: Upload docs for AI-powered compliance analysis
    - Control Mappings: Manual + AI-powered policy-control mapping
    - Cross-Framework: Framework relationship heatmap & mapping matrix

RISK
  - Risk Assessment (/risks) - Risk register with severity/likelihood scoring
  - Vendors (/vendors) - Third-party vendor management

SECURITY
  - SIEM (/siem) - Security event monitoring, live simulator, source management

COMPLIANCE
  - Compliance (/compliance) — Hub with 2 tabs:
    - Audit Management: Schedule and track audits
    - Evidence Library: Central evidence repository with file uploads

OPERATIONS
  - Tasks (/tasks) - Task management with Kanban view
  - Integrations (/integrations) - Slack webhooks, SIEM connectors
  - Settings (/settings) - App configuration
```

### Global Features
- **Command Palette (Cmd+K)**: Global search across pages, frameworks, controls with keyboard navigation
- **Compliance Copilot**: Floating AI chat widget (GPT-5.2 via Emergent LLM Key)

## Features

### Core Platform
- [x] 12 compliance frameworks (869 controls)
- [x] AI-powered policy generation via Lambda
- [x] Document analysis with S3 + Lambda
- [x] Policy Library with export (HTML/MD/TXT)
- [x] Risk management with task creation
- [x] Task management with Kanban view
- [x] Cross-framework mapping
- [x] JWT Authentication with demo accounts

### AI-Automated Control Mapping / Framework Workspace (Apr 9, 2026) — NEW
- [x] Per-control compliance status (Compliant/Partial/Non-Compliant/Not Assessed)
- [x] AI bulk assessment using GPT-5.2 — analyzes SIEM data + policy coverage to suggest status
- [x] SIEM evidence per control — maps SIEM event categories to framework controls
- [x] Editable compliance status — user can override any AI suggestion
- [x] Editable notes per control — free-text for implementation details, exceptions
- [x] AI policy suggestions — suggests policy title, statements, and guidance per control
- [x] Compliance progress bar with color-coded segments
- [x] Summary cards (Total, Compliant, Partial, Non-Compliant, Not Assessed)
- [x] Filters: search, status filter, category filter
- [x] Technical control badges showing SIEM event counts
- [x] Policy mapping indicators
- [x] Backend: /api/control-compliance/ with 6 endpoints

### Command Palette (Apr 9, 2026) — NEW
- [x] Cmd+K / Ctrl+K shortcut to open
- [x] Quick navigation to all pages
- [x] Search frameworks by name
- [x] Keyboard navigation (arrow keys + enter)
- [x] Sidebar Search button with ⌘K hint

### Dashboard (Redesigned Apr 8, 2026)
- [x] Command Bar, 5 Key Metrics, Framework Compliance chart
- [x] Risk Heatmap, Compliance Trend, Control Effectiveness gauge
- [x] Overdue/Upcoming Tasks, Quick Actions, AI Analysis

### Previous Features
- [x] Compliance Copilot (LLM chat)
- [x] Slack Integration
- [x] Control Effectiveness Scores
- [x] SIEM Integration with live simulator
- [x] Phase 1 Structural Overhaul (consolidated navigation)
- [x] Full dark mode

## Architecture
```
Backend: FastAPI + Motor (async MongoDB)
Frontend: React 18 + Tailwind + Shadcn
Routes: /api/auth, /api/frameworks, /api/controls, /api/policies, /api/policy-builder,
        /api/documents, /api/ironvision, /api/copilot, /api/slack,
        /api/control-effectiveness, /api/siem, /api/risks, /api/tasks,
        /api/control-compliance (NEW)
Databases: Local MongoDB (ironvision_grc) + Atlas MongoDB (IronVision Lambda data)
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2)
```

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## Next Steps / Backlog (Prioritized)

### P1 - Upcoming
- Dynamic Risk Scoring (SIEM events → real-time risk score adjustments)
- Vendor Risk Assessments (expand TPRM module with compliance tracking)

### P2 - Future
- Automated Evidence Collection (auto-gather logs/docs for audits)
- Compliance Calendar
- Predictive Insights & Automated Recommendations (ML/LLM forecasting)
- Mobile responsive improvements
- PDF export for policies
- SIEM alerting rules (auto-trigger Slack/email on critical events)
- SIEM event correlation (link related events across sources)
