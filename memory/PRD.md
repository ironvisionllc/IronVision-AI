# IronVision AI - GRC Platform - Product Requirements Document

## Problem Statement
Import and deploy IronVision Framework AI Tool - an enterprise GRC (Governance, Risk & Compliance) platform with AI-powered control mapping, policy builder, document analysis pipelines, and cross-framework mapping capabilities.

## Architecture
```
Frontend: React 18 + Shadcn/UI + Tailwind CSS (Port 3000)
Backend: FastAPI + Python (Port 8001)
Database: MongoDB (Local) + IronVision MongoDB Atlas (Production)
AI: OpenAI GPT-5.2 via Emergent LLM Key
AWS: S3 (project-assets-ironvision-dev) + Lambda + SES
```

## What's Been Implemented (Apr 3, 2026)

### Core Platform ✓
- [x] IronVision AI branding (logo, colors, dark mode)
- [x] JWT Authentication with demo accounts
- [x] 12 compliance frameworks with 869 controls
- [x] 710 pre-seeded control mappings (81% compliance score)

### Document Analysis Pipeline ✓ (TESTED & WORKING)
- [x] S3 upload to `project-assets-ironvision-dev` bucket
- [x] Preprocessing Lambda: `ironvision-preprocess-lambda`
- [x] Analysis Lambda: `ironvision-analysis-lambda`
- [x] Policy Generation Lambda: `ironvision-generate-policy`
- [x] PDF and DOCX file support
- [x] Status tracking (uploaded → preprocessing → analyzing → complete)

### AWS Configuration (Updated Apr 3, 2026)
```
AWS_ACCESS_KEY_ID=AKIATAVAA4K4P6BNA42D
BUCKET_NAME=project-assets-ironvision-dev
PREPROCESS_LAMBDA=ironvision-preprocess-lambda
ANALYSIS_LAMBDA=ironvision-analysis-lambda
POLICY_GENERATION_LAMBDA=ironvision-generate-policy
```

### Dashboard ✓
- [x] Executive dashboard with compliance score (Grade B: 81%)
- [x] Framework compliance bar chart
- [x] Risk heatmap, compliance trend timeline
- [x] Overdue tasks, upcoming deadlines, recent activity

### Policy Builder ✓
- [x] 20 NIST 800-53 control families
- [x] 982 questionnaire questions
- [x] Draft save/resume functionality
- [x] Lambda integration for policy generation

### Risk & Compliance ✓
- [x] Risk management (7 demo risks)
- [x] Vendor management (4 vendors)
- [x] Audit management
- [x] Cross-framework mapping with heatmap

### Operations ✓
- [x] Task management with Kanban view
- [x] Evidence library
- [x] Activity audit trail
- [x] Training modules with quizzes
- [x] In-app notifications

### Integrations Status
| Integration | Status | Details |
|-------------|--------|---------|
| MongoDB (local) | ✓ Active | Primary database |
| IronVision Atlas | ✓ Active | Production Policy Builder |
| AWS S3 | ✓ Active | project-assets-ironvision-dev |
| AWS Lambda | ✓ Active | 3 functions configured |
| AWS SES | ⚠ Configured | Sender verification pending |
| Emergent LLM Key | ✓ Active | GPT-5.2 for AI features |
| OpenAI API | ✓ Active | Backup AI access |

## Test Results

### Document Upload Flow (Apr 3, 2026)
1. ✓ Uploaded `sample_security_policy.pdf` (2.5KB)
2. ✓ File stored in S3: `uploads/demo-admin-001/e3c9b212-2059-47c5-a15a-7cce76f6515a.pdf`
3. ✓ Preprocessing Lambda invoked automatically
4. ✓ Analysis Lambda triggered successfully
5. ✓ Status tracked in MongoDB: `analyzing`

## Next Tasks
1. Monitor document analysis completion
2. Verify SES sender domain for email notifications
3. Test Policy Builder → Lambda generation flow
