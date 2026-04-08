# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC (Governance, Risk & Compliance) platform with AI-powered policy generation, intelligent control mapping, LLM-powered compliance assistance, and SIEM integration.

## Design System
- Brand: #2597B2 (primary), #1B839F (hover), #0a3540 (dark)
- Fonts: Plus Jakarta Sans (headings), Inter (body)
- Component system: .iv-card, .iv-stat-card, .iv-badge, .iv-btn-*, .iv-table
- Full dark mode support

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
- [x] Command Bar — "Needs Your Attention" with actionable alerts (risks, tasks, control health)
- [x] 4 Key Metrics: Compliance Score, Open Risks, Active Tasks, Control Health
- [x] Framework Compliance horizontal bar chart
- [x] Risk Heatmap (likelihood vs impact)
- [x] Compliance Trend area chart
- [x] Control Effectiveness circular gauge + per-framework bars
- [x] Tabbed Activity Center (Overdue | Upcoming | Activity)
- [x] Quick Actions grid (5 shortcuts)
- [x] Export Report button

### Compliance Copilot (Apr 8, 2026)
- [x] Floating Intercom-style chat widget (GPT-5.2 via Emergent LLM Key)
- [x] Session-based multi-turn conversations with history
- [x] Context-aware with org data
- [x] Suggestion prompts for quick queries

### Slack Integration (Apr 8, 2026)
- [x] Webhook-based GRC notifications (requires user's Slack webhook URL)
- [x] Per-event toggles (risks, tasks, policies, audits)
- [x] Test message, notification history

### Control Effectiveness Score (Apr 8, 2026)
- [x] Auto-calculated 0-100 scoring (5 factors: Policy, Evidence, CCI, Risk, Recency)
- [x] Manual override with reason tracking
- [x] Dashboard widget with circular gauge
- [x] Inline scores on Framework cards and controls table
- [x] Framework-level summary endpoint

### SIEM Integration (Apr 8, 2026)
- [x] Security event collection and monitoring
- [x] 7 event categories: authentication, authorization, data_access, policy_change, risk_management, incident, system
- [x] Auto-mapping to NIST 800-53 and NIST 800-171 controls
- [x] Threat level scoring (weighted severity)
- [x] Severity distribution charts
- [x] Critical/High events monitoring
- [x] Event log with search, severity, and category filtering
- [x] Control mapping visualization
- [x] Export: JSON, CSV, syslog formats
- [x] Demo data seeding

### Dark Mode (Apr 8, 2026)
- [x] Full CSS dark mode for all components
- [x] Dark variants for cards, tables, badges, buttons, grades, empty states

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

## Next Steps / Backlog
- Micro-animations (framer-motion)
- Mobile responsive improvements
- PDF export for policies
- Slack bot token integration (full bidirectional)
- Real-time SIEM event ingestion from external sources
- User needs to provide Slack webhook URL to activate notifications
