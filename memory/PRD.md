# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC (Governance, Risk & Compliance) platform with AI-powered policy generation, intelligent control mapping, LLM-powered compliance assistance, SIEM integration, Universal Compliance Ingestion, OSCAL support, DevSecOps Pipeline integration, Dynamic Risk Scoring, and Policy-as-Code engine.

## Design System
- Brand: #2597B2 (primary), #1B839F (hover), #0a3540 (dark)
- Full dark mode support

## App Structure

### Navigation
```
COMMAND CENTER - Dashboard (customizable widgets)
GOVERNANCE - Frameworks (workspace + Ingestion + Pipeline + Risk Scoring + Policy-as-Code + Organize) | Policies (5 tabs)
RISK - Risk Assessment | Vendors
SECURITY - SIEM
COMPLIANCE - Compliance (Audits + Evidence)
OPERATIONS - Tasks | Integrations | Settings
Global: Cmd+K Command Palette, Compliance Copilot (AI chat)
```

## Key Features

### Policy Center (5 Tabs)
- [x] Policy Templates with AI generation (GPT-5.2), Version Control, Approval Workflow
- [x] Upload & Map (3 modes), Create Document (built-in text editor)
- [x] Document Library (unified view, filters, click-to-view, approval workflow)
- [x] Control Mappings + Cross-Framework

### Frameworks & AI Control Mapping
- [x] 14 frameworks, 962 controls, Framework Workspace
- [x] AI Policy Suggestions, Coverage Analysis, Link/Unlink Documents

### Universal Compliance Ingestion Layer
- [x] Parse STIG XML, CIS YAML/CSV, PCI JSON, Questionnaires, OSCAL
- [x] AI Auto-Map to 14 frameworks (GPT-5.2), cross-framework overlaps
- [x] SIEM tie-in for real-time compliance status

### OSCAL Support (Phase A)
- [x] Import: OSCAL catalog, component-definition, assessment-results
- [x] Export: Framework as OSCAL catalog, compliance as OSCAL assessment-results
- [x] OSCAL v1.2.1 compatible, unified with ingestion pipeline

### DevSecOps Pipeline (Phase A)
- [x] Webhook API for SAST/DAST/SCA/Container/IaC scan results
- [x] Compliance gate evaluation (pass/fail/warn) with 3 policies (strict/default/permissive)
- [x] Pipeline API key management (create, list, revoke)
- [x] Risk scoring: critical*10 + high*5 + medium*2 + low*1
- [x] Pipeline dashboard with stats, runs list, findings detail

### Dynamic Risk Scoring (Phase B)
- [x] 5 weighted factors: SIEM (25%), Compliance (25%), Pipeline (20%), Ingestion (15%), Policy (15%)
- [x] Risk levels: critical (80+), high (60+), elevated (40+), moderate (20+), low (0+)
- [x] Per-framework risk scores with compliance + policy coverage stats
- [x] Risk trend tracking with history snapshots
- [x] Active alerts: SIEM events, pipeline failures, non-compliant controls, unmapped checklists, stale assessments

### Policy-as-Code Engine (Phase C)
- [x] 8 built-in rules: encryption, MFA, public access, logging, TLS, backups, secrets, tagging
- [x] Config evaluation against rules with violations mapped to framework controls
- [x] Custom rule creation
- [x] Evaluation history

### Compliance Drift Detection (Phase C)
- [x] Baseline snapshot creation (captures all framework compliance, pipeline, ingestion state)
- [x] Drift detection: compares current vs baseline, tracks improved/degraded changes
- [x] Snapshot history

## Architecture
```
Backend: FastAPI + Motor (async MongoDB)
Frontend: React 18 + Tailwind + Shadcn
Key Routes:
  /api/policy-templates, /api/documents, /api/control-compliance
  /api/ingestion (upload, checklists, auto-map, overlap, siem-status)
  /api/oscal (import, export/catalog, export/assessment)
  /api/pipeline (webhook, gate, runs, stats, api-keys)
  /api/risk-scoring (org-score, framework-scores, trend, alerts)
  /api/policy-engine (rules, evaluate, evaluations, drift/snapshot, drift/detect)
  /api/copilot, /api/siem, /api/frameworks, etc.
DB Collections: frameworks, controls, ingested_checklists, ingested_controls,
                pipeline_runs, pipeline_findings, pipeline_api_keys,
                risk_score_history, policy_rules, policy_evaluations,
                compliance_snapshots, and existing collections
External: AWS S3/Lambda/SES, Emergent LLM Key (GPT-5.2)
```

## Test Credentials
- Demo Admin: demo-admin@grc.com / DemoAdmin123!
- Demo User: demo-user@grc.com / DemoUser123!

## Backlog
### P1
- Vendor Risk Assessments (TPRM with compliance tracking)
- Compliance Report Export (PDF/DOCX)
### P2
- Automated Evidence Collection
- Compliance Calendar
- Predictive Insights
- SIEM alerting rules, event correlation
- Coverage Gap Report
