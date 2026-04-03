# IronVision AI - GRC Platform - Product Requirements Document

## Problem Statement
Import and deploy IronVision Framework AI Tool with full AWS Lambda integration for policy generation.

## What's Working (Apr 3, 2026)

### Policy Generation Lambda - FULLY INTEGRATED ✅
Successfully tested end-to-end policy generation:
- **Job ID**: `policy_gen_1775241081325_f28c7a55`
- **Policy ID**: `69d0083c8616a151d0fa02ce`
- **Policy Name**: Incident Response Policy - FinCorp
- **Framework**: NIST 800-53
- **Control Family**: IR (Incident Response)
- **Sections Generated**: 9 (overview, roles, policy, procedures, enforcement, definitions, revisionHistory, approvals, distribution)
- **Generation Time**: ~3 minutes

### Integration Flow (Option B - Atlas Initialization)
```
1. User creates draft via API → Local MongoDB
2. Backend creates controlquestionanswers in Atlas
3. Backend creates analysisprogresses job record in Atlas  
4. Backend invokes ironvision-generate-policy Lambda
5. Lambda reads from Atlas, generates policy via GPT-4o
6. Lambda saves policy to createdpolicies in Atlas
7. Policy available in IronVision system
```

### AWS Lambda Functions
| Function | Status | Purpose |
|----------|--------|---------|
| ironvision-preprocess-lambda | ✅ Active | Document preprocessing |
| ironvision-analysis-lambda | ✅ Active | Document compliance analysis |
| ironvision-generate-policy | ✅ Active | AI policy generation (GPT-4o) |

### All Features Working
- Document Upload → S3 → Lambda Analysis ✅
- Policy Builder Questionnaire (982 questions) ✅
- Policy Generation → Lambda → Atlas ✅
- Dashboard, Risks, Tasks, Frameworks ✅
- IronVision Atlas Integration ✅
- Emergent LLM Key for AI Mappings ✅

## Test Credentials
- **Demo Admin**: demo-admin@grc.com / DemoAdmin123!
- **Demo User**: demo-user@grc.com / DemoUser123!

## Next Steps
1. Add endpoint to fetch generated policies from Atlas
2. Display generated policy content in UI
3. Add policy export (PDF/DOCX)
4. Configure SES email notifications
