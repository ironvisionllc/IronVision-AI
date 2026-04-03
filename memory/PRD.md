# IronVision AI - GRC Platform - Product Requirements Document

## Problem Statement
Import and deploy IronVision Framework AI Tool with full AWS Lambda integration for policy generation and comprehensive Policy Library with export options.

## What's Implemented (Apr 3, 2026)

### Policy Library - COMPLETE ✅
- **API Endpoints Added:**
  - `GET /api/ironvision/generated-policies` - List all generated policies with pagination
  - `GET /api/ironvision/generated-policies/{policy_id}` - Get single policy with full content
  - `GET /api/ironvision/generated-policies/{policy_id}/export` - Export as HTML/Markdown/Text

- **UI Features:**
  - Policy Library page with "AI Generated" and "Local Policies" tabs
  - Policy cards showing name, framework, control family, status, version, date
  - View dialog with full policy content (Overview, Roles, Policy, Procedures, etc.)
  - Export dialog with HTML, Markdown, and Plain Text options
  - Search functionality

### Policy Generation Lambda - COMPLETE ✅
- Successfully generates NIST 800-53 compliant policies via Lambda
- ~3 minute generation time using GPT-4o
- 9 sections generated: overview, roles, policy, procedures, enforcement, definitions, revisionHistory, approvals, distribution

### Document Analysis - COMPLETE ✅
- S3 upload → Lambda preprocessing → Analysis Lambda
- Compliance analysis completed in ~79 seconds

### All AWS Integration Working
| Lambda Function | Status | Purpose |
|-----------------|--------|---------|
| ironvision-preprocess-lambda | ✅ Active | Document preprocessing |
| ironvision-analysis-lambda | ✅ Active | Document compliance analysis |
| ironvision-generate-policy | ✅ Active | AI policy generation (GPT-4o) |

## Test Credentials
- **Demo Admin**: demo-admin@grc.com / DemoAdmin123!
- **Demo User**: demo-user@grc.com / DemoUser123!

## Architecture
```
Frontend: React 18 + Shadcn/UI + Tailwind CSS
Backend: FastAPI + Python
Local DB: MongoDB
Atlas DB: IronVision MongoDB Atlas (ironvisioncluster.dois0.mongodb.net)
AWS: S3 (project-assets-ironvision-dev) + Lambda + SES
AI: GPT-4o via Lambda, GPT-5.2 via Emergent LLM Key
```

## Next Steps
1. Configure SES email notifications (verify sender domain)
2. Add PDF export option using ReportLab
3. Add policy versioning and edit capabilities
4. Add policy approval workflow
