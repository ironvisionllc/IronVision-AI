# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC platform — "Compliance at Machine Speed" — with AI-powered compliance, SIEM integration, OSCAL support, DevSecOps pipeline, dynamic risk scoring, policy-as-code, drift detection, automated evidence collection, and Tenable VM integration.

## Tagline: "Compliance at Machine Speed"

## Architecture
```
Backend: FastAPI + Motor (async MongoDB) + Python 3.11 + pyTenable
Frontend: React 18 + Tailwind + Shadcn/UI
Key Route Groups:
  /api/ingestion, /api/oscal, /api/pipeline, /api/risk-scoring
  /api/policy-engine, /api/evidence-collection, /api/tenable
  /api/control-compliance, /api/policy-templates, /api/documents, etc.
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2), Tenable.io
```

## All Implemented Features
- [x] 14 frameworks, 962 controls, SIEM integration (7 event categories)
- [x] AI control mapping, policy suggestions, implementation guidance (GPT-5.2)
- [x] Policy Center: templates, version control, approval workflow, document library
- [x] Universal Compliance Ingestion (STIG/CIS/PCI/OSCAL/Questionnaires)
- [x] OSCAL v1.2.1 import/export (catalog, component-definition, assessment-results)
- [x] DevSecOps Pipeline (webhook, compliance gate, API keys, findings)
- [x] Dynamic Risk Scoring (5-factor model, framework scores, alerts, trends)
- [x] Policy-as-Code (8 rules, config evaluation, custom rules)
- [x] Compliance Drift Detection (baseline snapshots, drift comparison)
- [x] Automated Evidence Collection (5 sources, coverage tracking, freshness)
- [x] **Tenable VM Integration** (vulnerability + compliance exports, NIST 800-53 mapping, demo + live modes)
- [x] Documentation Suite (marketing, security architecture, UI walkthrough, pitch deck, brochure)

## Tenable VM Integration Details
- **Phase 1**: pyTenable SDK, async export methodology, delta pulls with timestamp tracking
- **Phase 2**: Vulnerability exports (severity filter, state tracking) + Compliance exports (PASSED/FAILED, expected/actual)
- **Phase 3**: Mapping engine — vulns map to SI-2, RA-5, CM-6; compliance checks map via keyword matching to 34+ NIST controls
- **Demo mode**: 10 realistic vulnerabilities + 12 compliance checks with real CVE references
- **Live mode**: Connects to Tenable.io via access_key/secret_key

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## Backlog
### P1
- Vendor Risk Assessments (TPRM with compliance tracking)
- Compliance Report Export (PDF/DOCX)
### P2
- Compliance Calendar, Predictive Insights
- GitHub Actions / GitLab CI integration templates
- SIEM alerting rules, event correlation
