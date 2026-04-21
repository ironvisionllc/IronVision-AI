# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC platform — "Compliance at Machine Speed" — with AI-powered policy generation, intelligent control mapping, SIEM integration, OSCAL support, DevSecOps pipeline, dynamic risk scoring, policy-as-code, drift detection, and automated evidence collection.

## Tagline
**"Compliance at Machine Speed"**

## Design System
- Brand: #2597B2 (primary), #1B839F (hover), #0a3540 (dark)
- Full dark mode support

## Architecture
```
Backend: FastAPI + Motor (async MongoDB) + Python 3.11
Frontend: React 18 + Tailwind + Shadcn/UI
Key Route Groups:
  /api/ingestion (STIG, CIS, PCI, Questionnaire, OSCAL upload & mapping)
  /api/oscal (import/export OSCAL v1.2.1)
  /api/pipeline (CI/CD webhook, gate, API keys, runs)
  /api/risk-scoring (org-score, framework-scores, trend, alerts)
  /api/policy-engine (rules, evaluate, drift/snapshot, drift/detect)
  /api/evidence-collection (collect, artifacts, coverage, stats, runs)
  /api/control-compliance, /api/policy-templates, /api/documents, etc.
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2)
```

## All Implemented Features
- [x] 14 frameworks, 962 controls, SIEM integration with 7 event categories
- [x] AI control mapping, policy suggestions, implementation guidance (GPT-5.2)
- [x] Policy Center: templates, version control, approval workflow, document library
- [x] Universal Compliance Ingestion (STIG/CIS/PCI/OSCAL/Questionnaires)
- [x] OSCAL v1.2.1 import/export (catalog, component-definition, assessment-results)
- [x] DevSecOps Pipeline (webhook, compliance gate, API keys, findings)
- [x] Dynamic Risk Scoring (5-factor model, framework scores, alerts, trends)
- [x] Policy-as-Code (8 rules, config evaluation, custom rules)
- [x] Compliance Drift Detection (baseline snapshots, drift comparison)
- [x] Automated Evidence Collection (5 sources, coverage tracking, freshness)
- [x] Documentation Suite (marketing, security architecture, UI walkthrough, pitch deck, brochure)

## Documentation (accessible at /docs/)
- Marketing page: /docs/marketing.html
- Security Architecture: /docs/security-architecture.html
- UI Walkthrough: /docs/ui-walkthrough.html
- Executive Pitch Deck: /docs/pitch-deck.html
- Product Brochure: /docs/brochure.html

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## Backlog
### P1
- Vendor Risk Assessments (TPRM with compliance tracking)
- Compliance Report Export (PDF/DOCX)
### P2
- Compliance Calendar
- Predictive Insights & Forecasting
- SIEM alerting rules, event correlation
- GitHub Actions / GitLab CI integration templates
