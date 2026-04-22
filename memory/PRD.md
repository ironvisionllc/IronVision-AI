# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC platform — "Compliance at Machine Speed" — with Tenable VM integration driving automated NIST control assessment, AI policy generation, and POA&M tracking.

## Architecture
```
Backend: FastAPI + Motor (async MongoDB) + Python 3.11 + pyTenable
Frontend: React 18 + Tailwind + Shadcn/UI
Key Routes: /api/ingestion, /api/oscal, /api/pipeline, /api/risk-scoring,
  /api/policy-engine, /api/evidence-collection, /api/tenable,
  /api/control-compliance, /api/policy-templates, /api/documents, etc.
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2), Tenable.io
```

## All Implemented Features
- [x] 14 frameworks, 962 controls, SIEM integration, AI control mapping (GPT-5.2)
- [x] Policy Center (templates, version control, approval workflow, document library)
- [x] Universal Compliance Ingestion (STIG/CIS/PCI/OSCAL/Questionnaires)
- [x] OSCAL v1.2.1 import/export
- [x] DevSecOps Pipeline (webhook, compliance gate, API keys)
- [x] Dynamic Risk Scoring (5-factor model, alerts, trends)
- [x] Policy-as-Code (8 rules, config eval, drift detection)
- [x] Automated Evidence Collection (5 sources, coverage tracking)
- [x] **Tenable VM Integration** — Full loop:
  - Sync vulns + compliance checks (live Tenable.io or demo mode)
  - **Auto-Assess NIST Controls** — 26 controls auto-assessed from scan data
  - **AI Policy Generation** — GPT-5.2 generates remediation policies from critical findings
  - **POA&M Generation** — Severity-based timelines (critical=15d, high=30d, medium=90d)
  - POA&M tracking with status management (open→in_progress→completed→delayed)
- [x] Documentation Suite (marketing, security arch, UI walkthrough, pitch deck, brochure)

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## Backlog
### P1
- Vendor Risk Assessments (TPRM)
- Compliance Report Export (PDF/DOCX)
### P2
- Compliance Calendar, Predictive Insights
- GitHub Actions / GitLab CI integration templates
- CrowdStrike/Qualys integration
