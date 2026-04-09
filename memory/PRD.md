# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC (Governance, Risk & Compliance) platform with AI-powered policy generation, intelligent control mapping, LLM-powered compliance assistance, and SIEM integration.

## Design System
- Brand: #2597B2 (primary), #1B839F (hover), #0a3540 (dark)
- Fonts: Plus Jakarta Sans (headings), Inter (body)
- Component system: .iv-card, .iv-stat-card, .iv-badge, .iv-btn-*, .iv-table
- Full dark mode support

## App Structure (Phase 1 Restructure - Apr 9, 2026)

### Navigation Architecture (8 Core Pillars)
```
COMMAND CENTER
  - Dashboard (/dashboard) - Unified command center with compliance posture, risk heatmap, trends, control health

GOVERNANCE
  - Frameworks (/frameworks) - Hub with 3 tabs:
    - Frameworks: Manage compliance frameworks (12 built-in)
    - Control Mappings: Manual + AI-powered policy-control mapping
    - Cross-Framework: Framework relationship heatmap & mapping matrix
  - Policies (/policies) - Hub with 3 tabs:
    - Policy Builder: Guided questionnaire-based policy generation
    - Policy Library: Generated & local policies with export
    - Document Analysis: Upload docs for AI-powered compliance analysis

RISK
  - Risk Assessment (/risks) - Risk register with severity/likelihood scoring
  - Vendors (/vendors) - Third-party vendor management

SECURITY
  - SIEM (/siem) - Security event monitoring, live simulator, source management

COMPLIANCE
  - Compliance (/compliance) - Hub with 2 tabs:
    - Audit Management: Schedule and track audits
    - Evidence Library: Central evidence repository with file uploads

OPERATIONS
  - Tasks (/tasks) - Task management with Kanban view
  - Integrations (/integrations) - Slack webhooks, SIEM connectors
  - Settings (/settings) - App configuration
```

### Route Redirects (Backward Compatibility)
- /policy-library → /policies?tab=library
- /documents → /policies?tab=documents
- /mappings → /frameworks?tab=mappings
- /cross-framework → /frameworks?tab=cross-framework
- /audits → /compliance?tab=audits
- /evidence → /compliance?tab=evidence

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

### Dashboard (Redesigned Apr 8, 2026)
- [x] Command Bar — "Needs Your Attention" with actionable alerts
- [x] 5 Key Metrics: Compliance Score, Control Health, Open Risks, Threat Level, Tasks
- [x] Framework Compliance horizontal bar chart
- [x] Risk Heatmap (likelihood vs impact)
- [x] Compliance Trend area chart
- [x] Control Effectiveness circular gauge + per-framework bars
- [x] Overdue Tasks + Upcoming sections
- [x] Quick Actions grid (4 shortcuts)
- [x] AI Analysis + Export Report buttons

### Compliance Copilot (Apr 8, 2026)
- [x] Floating Intercom-style chat widget (GPT-5.2 via Emergent LLM Key)
- [x] Session-based multi-turn conversations with history
- [x] Context-aware with org data

### Slack Integration (Apr 8, 2026)
- [x] Webhook-based GRC notifications
- [x] Per-event toggles, test message, notification history

### Control Effectiveness Score (Apr 8, 2026)
- [x] Auto-calculated 0-100 scoring (5 factors)
- [x] Manual override with reason tracking
- [x] Dashboard widget + inline scores

### SIEM Integration (Apr 8-9, 2026)
- [x] Security event collection and monitoring
- [x] 7 event categories with auto-mapping to NIST controls
- [x] Live Simulator for demos
- [x] Source management with webhook URLs + API keys
- [x] Export: JSON, CSV, syslog formats

### Phase 1 Structural Overhaul (Apr 9, 2026)
- [x] Consolidated sidebar navigation (15+ items → 10 items in 6 sections)
- [x] PolicyHub: Tabbed view merging Policy Builder + Library + Documents
- [x] FrameworkHub: Tabbed view merging Frameworks + Mappings + Cross-Framework
- [x] ComplianceHub: Tabbed view merging Audits + Evidence
- [x] Old route redirects for backward compatibility
- [x] All sub-pages support `embedded` prop for reuse without Layout wrapper

### Dark Mode (Apr 8, 2026)
- [x] Full CSS dark mode for all components

## Architecture
```
Backend: FastAPI + Motor (async MongoDB)
Frontend: React 18 + Tailwind + Shadcn
Routes: /api/auth, /api/frameworks, /api/controls, /api/policies, /api/policy-builder,
        /api/documents, /api/ironvision, /api/copilot, /api/slack,
        /api/control-effectiveness, /api/siem, /api/risks, /api/tasks, etc.
Databases: Local MongoDB (ironvision_grc) + Atlas MongoDB (IronVision Lambda data)
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2)
```

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## Next Steps / Backlog (Prioritized)

### P1 - Upcoming
- AI-Automated Control Mapping (LLM-based suggestions from policies + SIEM data)
- Dynamic Risk Scoring (SIEM events → real-time risk score adjustments)
- Vendor Risk Assessments (expand TPRM module with compliance tracking)

### P2 - Future
- Automated Evidence Collection (auto-gather logs/docs for audits)
- Compliance Calendar
- Predictive Insights & Automated Recommendations (ML/LLM forecasting)
- Mobile responsive improvements
- PDF export for policies
- Slack bot token integration (full bidirectional)
- SIEM alerting rules (auto-trigger Slack/email on critical events)
- SIEM event correlation (link related events across sources)
