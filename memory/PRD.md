# IronVision AI - GRC Platform - Product Requirements Document

## Problem Statement
Import and deploy IronVision Framework AI Tool - an enterprise GRC (Governance, Risk & Compliance) platform with AI-powered control mapping, policy builder, document analysis pipelines, and cross-framework mapping capabilities.

## Architecture
```
Frontend: React 18 + Shadcn/UI + Tailwind CSS (Port 3000)
Backend: FastAPI + Python (Port 8001)
Database: MongoDB (Local) + IronVision MongoDB Atlas (Production)
AI: OpenAI GPT-5.2 via Emergent LLM Key
AWS: S3 (kevin-policy-bucket) + Lambda (IronVision-Analyze, ironvision-preprocess-lambda, IronVision-Generate-Policy) + SES
```

## What's Been Implemented (Apr 3, 2026)

### Core Platform
- [x] IronVision AI branding (logo, colors, dark mode)
- [x] JWT Authentication with demo accounts
- [x] 12 compliance frameworks (NIST CSF, NIST 800-53, ISO 27001, SOC 2, HIPAA, GDPR, etc.)
- [x] 869 controls across all frameworks
- [x] 710 pre-seeded control mappings (81% compliance score)

### Dashboard
- [x] Executive dashboard with compliance score (Grade B: 81%)
- [x] Framework compliance bar chart
- [x] Risk heatmap (Likelihood vs Impact)
- [x] Compliance trend timeline chart
- [x] Overdue tasks, upcoming deadlines, recent activity

### Policy Builder
- [x] 20 NIST 800-53 control families
- [x] 982 questionnaire questions
- [x] Draft save/resume functionality
- [x] Lambda integration for policy generation

### Document Analysis (AWS S3 + Lambda)
- [x] S3 upload to kevin-policy-bucket
- [x] Preprocessing Lambda: ironvision-preprocess-lambda
- [x] Analysis Lambda: IronVision-Analyze
- [x] Policy Generation Lambda: IronVision-Generate-Policy
- [x] PDF and DOCX file support

### Risk & Compliance
- [x] 7 pre-seeded demo risks
- [x] Risk CRUD operations
- [x] Vendor management (4 vendors)
- [x] Audit management
- [x] Cross-framework mapping with heatmap

### Operations
- [x] Task management with Kanban view (6 tasks)
- [x] Evidence library
- [x] Activity audit trail
- [x] Training modules with quizzes
- [x] In-app notifications with polling

### AI Features
- [x] AI-powered policy-to-control mapping (GPT-5.2)
- [x] Cross-framework AI mapping suggestions
- [x] Emergent LLM Key integrated

### Integrations Configured ✓
- [x] MongoDB (local) - primary database
- [x] IronVision MongoDB Atlas - production Policy Builder data
- [x] AWS S3 - kevin-policy-bucket for document storage
- [x] AWS Lambda - preprocessing, analysis, policy generation
- [x] AWS SES - email notifications (sender verification pending)
- [x] Emergent LLM Key - AI features
- [x] OpenAI API Key - backup AI access

## User Personas
1. **GRC Admin**: Full access, manages policies, risks, compliance
2. **Compliance Analyst**: Manages mappings, evidence, frameworks
3. **Risk Manager**: Focuses on risks, vendors, audits
4. **Auditor**: Read-only access to compliance reports

## Backlog (Prioritized)

### P1 (High)
- Verify SES sender domain (noreply@ironvision.ai)
- Test end-to-end document analysis flow

### P2 (Medium)
- Advanced workflow rules for tasks
- Integration hub persistence (Slack, Jira)
- Enhanced PDF reports with charts

### P3 (Low)
- Pinecone vector embeddings integration
- SIEM integration
- Custom framework builder

## Next Tasks
1. Verify AWS SES domain in AWS console
2. Test document upload → S3 → Lambda → Analysis flow
3. Test policy generation from questionnaire
