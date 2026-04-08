# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC (Governance, Risk & Compliance) platform with AI-powered policy generation, intelligent control mapping, and LLM-powered compliance assistance.

## UI/UX Premium Redesign Complete (Apr 8, 2026)

### Design System Implemented

**1. Typography**
- Primary: Plus Jakarta Sans (headings, display)
- Secondary: Inter (body, labels)
- Hierarchy: .text-display (48px), .text-headline (32px), .text-title (20px), .text-body (15px), .text-caption (13px), .text-label (11px uppercase)

**2. Color Palette**
- Brand: #2597B2 (primary), #1B839F (hover), #0a3540 (dark)
- Accent: #F5A623 (gold), #10B981 (emerald), #F97066 (coral), #8B5CF6 (violet)
- Neutrals: #1E293B (onyx), #475569 (slate), #64748B (gray), #94A3B8 (silver), #F1F5F9 (cloud)

**3. Component System**
- `.iv-card` - Premium cards with hover border highlight
- `.iv-stat-card` - Stat cards with radial gradient accent
- `.iv-hero-card` - Hero sections with gradient background
- `.iv-badge` - Refined badges with 6 variants
- `.iv-btn-primary/secondary/ghost` - Button system
- `.iv-nav-item` - Sidebar navigation with active indicator
- `.iv-table` - Premium table styling
- `.iv-empty-state` - Consistent empty state pattern

**4. Shadow System**
- shadow-xs through shadow-xl (layered depth)
- shadow-brand for brand-colored elements

**5. Pages Updated**
- Login Page - Split panel with branding
- Dashboard - Grade circle, stat cards, charts
- Risks Page - Score badges, filters, task creation
- Tasks Page - Kanban/List views, priority indicators
- Policy Library - Policy viewing with export

## Features

### Core Platform
- [x] 12 compliance frameworks (869 controls)
- [x] AI-powered policy generation via Lambda
- [x] Document analysis with S3 + Lambda
- [x] Policy Library with export (HTML/MD/TXT)
- [x] Risk management with task creation
- [x] Task management with Kanban view
- [x] Cross-framework mapping

### Breakthrough Features (Apr 8, 2026)
- [x] **Compliance Copilot** - LLM-powered floating chat widget (Intercom-style)
  - GPT-5.2 via Emergent LLM Key
  - Session-based multi-turn conversations
  - Context-aware with org data (policies, risks, frameworks)
  - Suggestion prompts for quick queries
  - Chat history with session management
- [x] **Slack Integration** - Webhook-based GRC notifications
  - Configurable webhook URL (Incoming Webhooks)
  - Per-event toggles (risks, tasks, policies, audits)
  - Test message sending
  - Notification history log
  - Block-formatted Slack messages with severity indicators
- [x] **Control Effectiveness Score** - Auto-calculated 0-100 scoring
  - 5-factor scoring: Policy Mapping (25), Evidence Coverage (25), CCI Completion (20), Risk Exposure (15), Recency (15)
  - Manual override with reason tracking
  - Visual score bar with grade labels
  - Factor breakdown display on ControlDetailPage
  - Framework-level summary endpoint
  - **Dashboard Widget**: Cross-framework effectiveness overview with circular SVG gauge, grade distribution stacked bar, and per-framework progress bars (Apr 8, 2026)

### AWS Integration
- [x] S3: project-assets-ironvision-dev
- [x] Lambda: ironvision-analysis-lambda, ironvision-generate-policy
- [x] MongoDB Atlas: ironvisioncluster.dois0.mongodb.net

## Architecture

### Backend Routes
- `/api/auth` - JWT authentication
- `/api/frameworks` - Framework CRUD
- `/api/controls` - Control details and CCIs
- `/api/policies` - Policy management
- `/api/policy-builder` - AI policy generation via Lambda
- `/api/documents` - S3 document upload/analysis
- `/api/ironvision` - Atlas DB integration
- `/api/copilot` - Compliance Copilot LLM chat
- `/api/slack` - Slack webhook configuration and notifications
- `/api/control-effectiveness` - Control effectiveness scoring
- `/api/risks`, `/api/tasks`, `/api/vendors`, `/api/audits`, etc.

### Key Collections (Local MongoDB)
- `users`, `policies`, `risks`, `tasks`, `frameworks`, `controls`
- `copilot_sessions`, `copilot_messages` (Compliance Copilot)
- `slack_config`, `slack_notifications` (Slack Integration)
- `control_overrides` (Effectiveness Score overrides)

### Key Collections (Atlas MongoDB)
- `createdpolicies`, `controlquestionanswers`, `analysisprogresses`

## Test Credentials
- **Demo Admin**: demo-admin@grc.com / DemoAdmin123!
- **Demo User**: demo-user@grc.com / DemoUser123!

## Next Steps / Backlog
- Micro-animations (framer-motion)
- Dark mode refinements
- Mobile responsive improvements
- PDF export for policies
- Slack bot token integration (full bidirectional)
- Framework detail page: inline effectiveness scores per control row
