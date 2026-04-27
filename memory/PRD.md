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
- [x] **UX Navigation Restructure** (Feb 2026) — Sidebar grouped into 5 sections: COMMAND CENTER, GOVERNANCE, SECURITY, RISK & COMPLIANCE, OPERATIONS. Extracted 6 features out of FrameworksPage into standalone routes: `/ingestion`, `/pipeline`, `/tenable`, `/risk-scoring`, `/evidence`, `/policy-engine`. Validated via testing_agent_v3_fork (iteration_21: 24/24 frontend checks PASS, 0 issues).
- [x] **Asset Inventory + Asset-Centric Vulnerability Tracking** (Feb 2026) — First-class `assets` collection (hardware: OS, IPs, MAC, ports; software: installed apps with versions; metadata: criticality, environment, owner, tags). Tenable sync now upserts asset records with hardware/software inventory. New routes `/assets` (list with filters) and `/assets/:id` (detail with all open + fixed vulns, CVEs, compliance checks, POA&M). Risk Scoring engine extended with 6th factor (`asset` weight 0.25) using **criticality multipliers** (critical=2.0×, high=1.5×, medium=1.0×, low=0.5×) — Crown Jewel assets carry 4× the risk weight of dev boxes. Tenable findings hostnames now Link to asset detail (option 3a). Validated via iteration_22 (backend 14/14 + frontend 100% after 1-line useState fix).

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
- Coverage Gap Report (aggregate low/no-coverage controls + recommend policies)
- **Asset enrichment**: AWS/Azure/GCP cloud asset discovery + Active Directory / CrowdStrike / Qualys multi-source ingest
- **SBOM-aware vuln tracking**: detect installed package versions and auto-flag when new CVE drops
- **Asset risk normalization**: divide weighted risk by total assets (not just risky ones) for fleet-wide density score
- Pagination on `/api/assets` for >2000-asset orgs
- CrowdStrike/Qualys multi-scanner integration
- GitHub Actions / GitLab CI templates
- 404 catch-all route in App.js (per code-review note)
- App.js route registration is growing — consider grouped route config / lazy imports
- React Error Boundary around major route components
