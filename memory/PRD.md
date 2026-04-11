# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC (Governance, Risk & Compliance) platform with AI-powered policy generation, intelligent control mapping, LLM-powered compliance assistance, and SIEM integration.

## Design System
- Brand: #2597B2 (primary), #1B839F (hover), #0a3540 (dark)
- Fonts: Plus Jakarta Sans (headings), Inter (body)
- Full dark mode support

## App Structure

### Navigation
```
COMMAND CENTER - Dashboard (customizable widgets)
GOVERNANCE - Frameworks (organize + workspace) | Policies (5 tabs)
RISK - Risk Assessment | Vendors
SECURITY - SIEM
COMPLIANCE - Compliance (Audits + Evidence)
OPERATIONS - Tasks | Integrations | Settings
Global: Cmd+K Command Palette, Compliance Copilot (AI chat)
```

## Features (All Implemented)

### Dashboard (Customizable)
- [x] 5 widget sections: Posture, AI Insight, Framework/Risk, Trend/Health, Actions
- [x] Widget customization panel: toggle visibility + reorder with up/down arrows
- [x] Preferences saved to localStorage
- [x] Reset to default option

### Frameworks & AI Control Mapping
- [x] Framework grid with **Organize panel**: show/hide + reorder frameworks
- [x] Framework Workspace: per-control compliance status, SIEM evidence, AI assessment
- [x] **Expand All / Collapse All** button for all controls
- [x] 5 detail tabs per control: Overview, **Implementation & Guidelines**, SIEM Evidence, Policies, Notes
- [x] Implementation & Guidelines tab: AI-generated implementation steps, technical guidelines, assessment criteria, common pitfalls (cached)
- [x] Enhanced AI Policy Suggestion: shows **WHERE requirements are satisfied** (green) and **Gaps** (red)
- [x] AI bulk assessment using GPT-5.2
- [x] Editable compliance status per control (user override)
- [x] Editable notes per control
- [x] **SIEM maps to ALL frameworks**: NIST 800-53, NIST CSF (27 technical controls), GDPR (7 technical controls)
- [x] Status, category, and search filters

### Policies Hub (5 tabs)
- [x] Policy Builder, Policy Library, Document Analysis, Control Mappings, Cross-Framework

### Command Palette (Cmd+K)
- [x] Global search across pages and frameworks with keyboard navigation

### Other Features
- [x] 12 compliance frameworks (869 controls)
- [x] Compliance Copilot (GPT-5.2 AI chat)
- [x] Slack webhook integration
- [x] Control Effectiveness Scores
- [x] SIEM Integration with live simulator
- [x] Full dark mode

## Architecture
```
Backend: FastAPI + Motor (async MongoDB)
Frontend: React 18 + Tailwind + Shadcn
Key Routes: /api/control-compliance (6+ endpoints), /api/copilot, /api/siem, /api/frameworks, etc.
Databases: Local MongoDB (ironvision_grc) + Atlas MongoDB
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2)
```

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## Backlog

### P1 - Upcoming
- Dynamic Risk Scoring (SIEM events → real-time risk score adjustments)
- Vendor Risk Assessments (expand TPRM module with compliance tracking)

### P2 - Future
- Automated Evidence Collection
- Compliance Calendar
- Predictive Insights & Automated Recommendations
- Compliance report generation (PDF/DOCX export)
- SIEM alerting rules
- SIEM event correlation
