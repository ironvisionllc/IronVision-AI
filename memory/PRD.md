# IronVision AI - GRC Platform - PRD

## Overview
Enterprise GRC platform — "Compliance at Machine Speed" — with 10 core pillars, 6 AI engines, 14 frameworks, 962 controls.

## All Implemented Features (Complete)
- [x] 14 frameworks, 962 controls, SIEM integration, AI control mapping (GPT-5.2)
- [x] Policy Center (templates, version control, approval workflow, document library)
- [x] Universal Compliance Ingestion (STIG/CIS/PCI/OSCAL/Questionnaires)
- [x] OSCAL v1.2.1 import/export + **OSCAL SSP Export** (full workspace export)
- [x] DevSecOps Pipeline (webhook, compliance gate, API keys)
- [x] Dynamic Risk Scoring (5-factor model, alerts, trends)
- [x] Policy-as-Code (8 rules, config eval, drift detection)
- [x] Automated Evidence Collection (6 sources, coverage tracking)
- [x] Tenable VM Integration (sync, auto-assess, AI policy gen, POA&M)
- [x] **Auto-Remediation Code Generation** (Terraform/CloudFormation/K8s YAML templates + AI generation)
- [x] **Expanded RBAC** (Admin, Auditor, System Owner, Remediation Engineer, Viewer with granular permissions + UI)
- [x] **Natural Language Compliance Interrogation** (GPT-5.2 queries live platform data)
- [x] **Predictive Risk Forecasting** (trend analysis, pipeline failure patterns, POA&M deadlines, SIEM volume)
- [x] **Third-Party Risk Management (TPRM)** (vendor registry, 15-question questionnaire, weighted risk scoring, data access multiplier)
- [x] Documentation Suite (marketing, security architecture, UI walkthrough, pitch deck, brochure)

## Architecture
```
Routes: /api/ingestion, /api/oscal, /api/pipeline, /api/risk-scoring,
  /api/policy-engine, /api/evidence-collection, /api/tenable,
  /api/remediation, /api/rbac, /api/interrogate, /api/forecasting, /api/tprm
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2), Tenable.io
```

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## Backlog
- Compliance Report Export (PDF/DOCX)
- Compliance Calendar
- CrowdStrike/Qualys multi-scanner integration
- GitHub Actions / GitLab CI templates
