# 3 · Proposed information architecture

Mockups are in `mockups/*.html` and `mockups/png/*.png`. They are static, non-functional and not wired into the app.

## 3.1 Navigation

**Global** (always visible):
- **My Work** (home)
- **Systems**
- **Import Center**
- **Search** (⌘K: systems, controls in any ID form, CCIs, findings, POA&M, people)
- **Admin** (role-gated)

**System context**: a persistent system switcher at the top of the sidebar. Under it:
- **System dashboard**
- the **7 RMF steps**, each with a status dot and a short status
- **Recently viewed** (systems and controls)

Steps can be visited in any order. Nothing is forced to be linear.

| Step | Lives under it (sub-pages) | Current pages that move here |
|---|---|---|
| 1 Prepare | Roles & people · System profile & boundary · HW/SW inventory · PPSM ports & interconnections | `/rmf/prepare`, `/systems/:id` (profile part), `/inventory`, PPSM (eMASS import) |
| 2 Categorize | Information types & impact · Privacy (PII) · AO approval & history | `/rmf/categorize` (info types removed from registration) |
| 3 Select | Baseline & overlays · Tailoring & parameters · Monitoring strategy (ISCM, its own tab) | `/rmf/select` (split into 3 tabs), `/catalog` becomes the Workbench "Reference catalog" mode |
| 4 Implement | Control Workbench · Policies (auditor + coverage) · Evidence · Inheritance | `/systems/:id/controls`, `/policy-auditor`, `/evidence-sources` + `/evidence-ledger` (browse), `/inheritance`, `/ccis` (into Requirements tab), `/rmf/implement` (removed as a hub, becomes the step overview) |
| 5 Assess | Assessment workspace (SCA queue) · Test results · Findings · Mapping review | `/reviews` (SCA part), `/test-results`, `/findings/:id`, `/mapping-review`, `/rmf/assess` |
| 6 Authorize | Package & documents (SSP/SAR/RAR/POA&M/OSCAL) · POA&M · Risk acceptance · Decision (AO) | `/systems/:id/authorization` + `/rmf/authorize` merged, `/poams` |
| 7 Monitor | Monitoring dashboard · Schedules & due · Evidence freshness · eMASS sync | `/rmf/monitor`, `/emass`, ledger freshness, `/traceability` (also shown per control) |
| Global | My Work · Systems · Import Center · Search · Admin (+ Audit log, Notifications, Help) | `/rmf-workflow` (becomes Help "RMF overview"), `/portfolio` (ISSM/AO My Work + Systems), `/help` + `/docs-center` merged |

**Merged or removed (UI only, all functionality kept):**
- the 7 hub pages become the step overview on the dashboard
- the duplicate document buttons
- the categorization summary on Select (becomes a chip)
- Registration's info-type/PII fields
- separate eMASS import / Test Results import buttons (Import Center)
- `/rmf-workflow`
- Help vs Docs Center

**Unchanged:**
- deep-link routes (redirects)
- APIs
- permissions

## 3.2 Per-step status model

| Status | Meaning | Colour |
|---|---|---|
| Complete | All required activities done and approvals recorded | emerald `#10B981` |
| Remaining | Required work left (shows the count, e.g. "110 remaining") | brand `#2597B2` |
| Awaiting another role | Your part is done; waiting for SCA / ISSM / AO (shows who) | gold `#F5A623` |
| Optional | Not required yet (e.g. Monitor before ATO) | mist `#CBD5E1` |
| Blocked | A prerequisite is missing (shows which, with a link) | coral `#F97066` |

Responsible roles per step:

| Step | Roles |
|---|---|
| Prepare | System Owner, ISSO |
| Categorize | ISSO proposes, AO approves |
| Select | ISSO proposes; ISSM approves the strategy |
| Implement | ISSO, System Owner, CCP |
| Assess | SCA (independent) |
| Authorize | ISSM reviews, AO decides |
| Monitor | ISSO, ISSM |

The status is computed from the existing records with no new data. It uses the same counts as the current stepper (`services/counts.py`, step-status endpoints).

## 3.3 System RMF dashboard (`mockups/png/dashboard.png`)

- **Header:** system name, categorization, framework, phase, eMASS ID, ATO target.
- **"Continue where you left off":** the last edited object plus the recommended next action. The action is computed from that step's own status, not the generic "Assign key roles".
- **7 step cards**, each showing:
  - status and progress
  - required vs completed counts
  - missing information
  - pending approval (with who)
  - roles
  - one primary next action
- **Readiness for authorization:** a live blocker list. These are the same checks the documents use today, shown before generation.
- **Pending approvals** and **Recent activity**, both read from the same shared system record (import, scan and policy events).

## 3.4 My Work by role (`mockups/png/mywork_*.png`)

| Role | Sees first | Not shown |
|---|---|---|
| ISSO | Statements to write, mapping suggestions, stale evidence, unmapped findings, unfinished imports | Approve/authorize actions (SoD) |
| SCA | Assessment requests assigned, retests after POA&M closure, imported historical results to confirm | Statement editing (SCA independence) |
| ISSM | Strategy and package approvals, returned items, ATO expiries | Recording determinations |
| AO | Decisions only: categorization approval, risk acceptance, authorization decision | Any edit actions; the package opens read-only |

The data comes from the existing work queue, reviews and notifications. Permissions are unchanged; actions are hidden only where the role matrix already denies them.

## 3.5 Control Workbench, 2 panes (`mockups/png/workbench.png`)

**Left pane:**
- the existing catalog-tree component, with search (ID/title/CCI/keyword normalisation already built)
- simple status dots
- **4 filters:** Status · Family · Needs action · Mine
- the list is always visible (today it is hidden until you pick a filter)

**Right pane:**
- a header with **4 labelled status chips:** Implementation · Assessment · Policy coverage · Evidence. Open findings / POA&M are added as a chip.
- tabs: **Requirements** (statement, ODPs, CCIs, assessment procedure) | **Implementation** | **Evidence & Policies** | **Assessment** (read-only for ISSO; SCA records) | **Findings & POA&M** | **Monitoring** (SLCM, schedule, freshness)
- **Advanced eMASS fields are collapsed:** designation, SLCM overrides, N/A justification, estimated completion, CCP.

## 3.6 Terminology and status glossary

| Dimension | Labels (eMASS wording where it exists) | Colour | One-line meaning |
|---|---|---|---|
| Implementation status | Planned · Implemented · Partially Implemented · Not Implemented · Not Applicable · Inherited | brand / emerald / gold / coral / slate / violet | What the system owner says is in place (eMASS "Implementation Status"). |
| Policy coverage | Covered · Partially covered · Not covered · Not analysed | outlined chip (no fill) | Whether an approved policy says the control is required. Never an assessment. |
| Assessment determination | Satisfied · Other Than Satisfied · Not Assessed · Not Applicable | solid chip, emerald / coral / mist | The SCA's independent result (eMASS "Compliance Status": Compliant / Non-Compliant). |
| Authorization status | Not yet authorized · ATO · ATO with conditions · IATT · DATO · Expired | header badge | The AO's decision for the whole system. |
| Evidence freshness | Current · Due soon · Stale · Missing | dot + age | Whether evidence is within its required review period. |
| POA&M status | Ongoing · Risk Accepted · Completed · Delayed | chip with due date | eMASS POA&M "Status". |

**Label renames (UI text only):**

| Current label | New label |
|---|---|
| Evidence Ledger | Evidence |
| Evidence Sources | Evidence › Add |
| Templates → Test Results | Assess › Test results |
| CCI view | Requirements tab |
| Reviews | Assessment workspace (SCA) / Approvals (ISSM/AO) |
| eMASS Sync | Monitor › eMASS sync |
| Accept as informational | Keep as information only |
| Never monitored | No monitoring recorded yet |
| Make it the … profile value | Use for these families |
| legacy_unreviewed | Needs review |

## 3.7 Navigation aids

- Breadcrumbs: System › Step › Page › Object.
- Global search (⌘K).
- Recently viewed systems and controls.
- Saved filters per user: Workbench and Mapping Review.
- One toast and loading pattern: sonner plus a skeleton. These already exist; use them everywhere.

## 3.8 Guided Mode (per user toggle; `mockups/png/guided_on.png` vs `guided_off.png`)

When on, each step shows a panel with:
- **Purpose**
- **Why it matters**
- **Information you need**
- **Who does it** (role)
- **What's next**

Inline "why" notes also appear next to complex fields. It uses the same data, rules and permissions as streamlined mode, and only adds explanatory content. Default is on for new users (first 14 days) and off otherwise. The toggle lives in the header.

## 3.9 Standard flows

Diagrams are in `FLOWS.md`.

| Flow | Used by |
|---|---|
| Upload → Preview → Import → Completed (with next action) | every import |
| Upload → Analyze → Review findings → Approve/Correct | policy, STIG, ACAS mapping |
| Select control → Review evidence → Record determination → Save & next | SCA |
| Generate SSP → Review validation → Download | documents |
