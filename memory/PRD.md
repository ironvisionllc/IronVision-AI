# IronVision AI - GRC Platform - Product Requirements Document

## Overview
Enterprise GRC (Governance, Risk & Compliance) platform with AI-powered policy generation and intelligent control mapping.

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

### Files Modified
- `/app/frontend/src/index.css` - Complete design system
- `/app/frontend/src/pages/LoginPage.js` - Split-panel login
- `/app/frontend/src/pages/Dashboard.js` - Premium dashboard
- `/app/frontend/src/pages/RisksPage.js` - Risk management
- `/app/frontend/src/pages/TasksPage.js` - Task management with Kanban
- `/app/frontend/src/components/ui/skeleton-loaders.jsx` - Loading states

## Features

### Core Platform
- [x] 12 compliance frameworks (869 controls)
- [x] AI-powered policy generation via Lambda
- [x] Document analysis with S3 + Lambda
- [x] Policy Library with export (HTML/MD/TXT)
- [x] Risk management with task creation
- [x] Task management with Kanban view
- [x] Cross-framework mapping

### AWS Integration
- [x] S3: project-assets-ironvision-dev
- [x] Lambda: ironvision-analysis-lambda, ironvision-generate-policy
- [x] MongoDB Atlas: ironvisioncluster.dois0.mongodb.net

## Test Credentials
- **Demo Admin**: demo-admin@grc.com / DemoAdmin123!
- **Demo User**: demo-user@grc.com / DemoUser123!

## Next Steps
- Add micro-animations (framer-motion)
- Dark mode refinements
- Mobile responsive improvements
- PDF export for policies
