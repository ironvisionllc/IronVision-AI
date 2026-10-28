#!/usr/bin/env python3
"""Phase-1 UX mockups (NON-FUNCTIONAL static HTML, SYNTHETIC demo data, real IronVision tokens). Not wired into the app.
Run: python3 scripts/ux_baseline/mockups.py → docs/ux/mockups/*.html, then render.py → docs/ux/mockups/png/*.png"""
from pathlib import Path

OUT = Path("/app/docs/ux/mockups")
CSS = """
@font-face{font-family:Inter;src:url(../../../frontend/public/fonts/Inter-400.woff2)}@font-face{font-family:Inter;font-weight:600;src:url(../../../frontend/public/fonts/Inter-600.woff2)}
@font-face{font-family:"Plus Jakarta Sans";font-weight:700;src:url(../../../frontend/public/fonts/PlusJakartaSans-700.woff2)}
*{box-sizing:border-box}body{margin:0;font:13px/1.45 var(--iv-font-body);color:var(--iv-text);background:var(--iv-page-bg)}
.banner{background:#F5A623;color:#1E293B;font:700 10px var(--iv-font-heading);letter-spacing:.12em;text-align:center;padding:4px}
header{display:flex;align-items:center;gap:16px;height:52px;padding:0 20px;background:var(--iv-header-bg);border-bottom:1px solid var(--iv-border)}
.logo{font:700 17px var(--iv-font-heading)}.logo b{color:#1B839F}.search{flex:1;max-width:520px;border:1px solid var(--iv-border-strong);border-radius:10px;padding:7px 12px;color:#64748B;background:#fff}
.pill{border-radius:999px;padding:3px 10px;font-size:11px;font-weight:600;display:inline-block}.role{background:#0f4f5f;color:#fff}
.wrap{display:flex;min-height:calc(100vh - 76px)}aside{width:248px;flex:none;background:var(--iv-sb-bg);border-right:1px solid var(--iv-sb-border);padding:14px 10px}
aside .sys{border:1px solid var(--iv-border-strong);border-radius:10px;padding:8px 10px;background:#fff;font-weight:600;margin-bottom:12px}
aside h6{font:700 10px var(--iv-font-heading);letter-spacing:.1em;text-transform:uppercase;color:var(--iv-sb-muted);margin:14px 8px 6px}
aside a{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:8px;color:var(--iv-sb-text);text-decoration:none}aside a.on{background:var(--iv-sb-active-bg);color:var(--iv-sb-active-text);font-weight:600}
aside a small{margin-left:auto;color:var(--iv-sb-muted);font-size:10px}.sub{padding-left:26px!important;font-size:12px}
.dot{width:9px;height:9px;border-radius:50%;flex:none;display:inline-block}.g{background:#10B981}.a{background:#F5A623}.b{background:#2597B2}.r{background:#F97066}.n{background:#CBD5E1}.v{background:#8B5CF6}
main{flex:1;padding:22px 30px;min-width:0}.crumb{font-size:11px;color:#64748B;margin-bottom:6px}h1{font:700 26px var(--iv-font-heading);margin:0 0 4px;letter-spacing:-.02em}.lead{color:var(--iv-text-muted);margin:0 0 16px;max-width:820px}
.panel{background:var(--iv-card);border:1px solid var(--iv-border);border-radius:16px;box-shadow:var(--iv-shadow);padding:16px;margin-bottom:14px}.panel h3{font:700 14px var(--iv-font-heading);margin:0 0 10px}
.grid{display:grid;gap:12px}.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(4,1fr)}.g7{grid-template-columns:repeat(4,1fr)}
.btn{display:inline-block;border-radius:10px;padding:7px 13px;font-weight:600;border:1px solid var(--iv-border-strong);background:#fff;color:var(--iv-text)}.pri{background:var(--iv-grad-brand);color:#fff;border:0}
.chip{border-radius:6px;padding:2px 7px;font-size:11px;font-weight:600;display:inline-block}.cg{background:#ecfdf5;color:#065f46}.ca{background:#fffbeb;color:#92400e}.cb{background:#ecfeff;color:#155e75}.cr{background:#fef2f2;color:#991b1b}.cn{background:#f1f5f9;color:#475569}.cv{background:#f5f3ff;color:#5b21b6}
.muted{color:#64748B;font-size:12px}.row{display:flex;align-items:center;gap:10px}.sp{margin-left:auto}table{width:100%;border-collapse:collapse}td,th{padding:7px 6px;border-top:1px solid var(--iv-border);text-align:left;vertical-align:top}th{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#64748B;border:0}
.step{border:1px solid var(--iv-border);border-radius:14px;padding:12px;background:#fff}.step h4{margin:0;font:700 13px var(--iv-font-heading)}.bar{height:6px;border-radius:9px;background:#e2e8f0;overflow:hidden;margin:8px 0}.bar i{display:block;height:100%;background:var(--iv-grad-brand)}
.stepper{display:flex;gap:6px;margin:6px 0 16px}.stepper span{flex:1;text-align:center;padding:8px;border-radius:10px;background:#f1f5f9;color:#64748B;font-weight:600;font-size:12px}.stepper .done{background:#ecfdf5;color:#065f46}.stepper .cur{background:#1B839F;color:#fff}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--iv-border);margin-bottom:12px}.tabs span{padding:8px 12px;font-weight:600;color:#64748B}.tabs .on{color:#0f4f5f;border-bottom:2px solid #1B839F}
.hero{background:linear-gradient(135deg,#0f4f5f,#1B839F);color:#fff;border-radius:16px;padding:16px 18px;margin-bottom:14px}.hero .btn{border:0}
.guide{background:#f5f3ff;border:1px solid #ddd6fe;border-radius:14px;padding:12px 14px;margin-bottom:14px}.guide b{color:#5b21b6}
.tree div{padding:4px 6px;border-radius:6px;display:flex;align-items:center;gap:6px;font-size:12px}.tree .on{background:var(--iv-sb-active-bg);font-weight:600}.tree .in{padding-left:22px}
.field{border:1px solid var(--iv-border-strong);border-radius:8px;padding:7px 10px;background:#fff;min-height:32px}.label{font-size:11px;font-weight:600;color:#475569;margin:8px 0 3px}
.anno{border:2px dashed #8B5CF6;border-radius:10px;padding:6px 10px;color:#5b21b6;background:#faf5ff;font-size:11px;margin:6px 0}
"""
STEPS = [("Prepare", "g", "Complete"), ("Categorize", "g", "Complete"), ("Select", "g", "Complete"), ("Implement", "b", "62% · 110 remaining"),
         ("Assess", "a", "Awaiting SCA"), ("Authorize", "n", "Not started"), ("Monitor", "n", "Optional until ATO")]
SHORT = {"Complete": "Done", "62% · 110 remaining": "62%", "Awaiting SCA": "SCA", "Not started": "–", "Optional until ATO": "Optional"}
SUBS = {"Prepare": ["Roles & people", "System profile & boundary", "HW/SW inventory", "PPSM ports"],
        "Categorize": ["Information types & impact", "Privacy (PII)", "AO approval"],
        "Select": ["Baseline & overlays", "Tailoring & parameters", "Monitoring strategy"],
        "Implement": ["Control Workbench", "Policies", "Evidence", "Inheritance"],
        "Assess": ["Assessment workspace", "Test results", "Findings", "Mapping review"],
        "Authorize": ["Package & documents", "POA&M", "Risk acceptance", "Decision"],
        "Monitor": ["Dashboard", "Schedules & due", "Evidence freshness", "eMASS sync"]}


def shell(title, body, active="Dashboard", role="ISSO", expand=None, crumb="LTP › Dashboard"):
    nav = "".join(f'<a class="{"on" if active == x else ""}">{x}</a>' for x in ("My Work", "Systems", "Import Center", "Search", "Admin"))
    steps = ""
    for n, (s, c, st) in enumerate(STEPS, 1):
        steps += f'<a class="{"on" if active == s else ""}"><span class="dot {c}"></span>{n} · {s}<small>{SHORT[st]}</small></a>'
        if expand == s:
            steps += "".join(f'<a class="sub">{x}</a>' for x in SUBS[s])
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><link rel="stylesheet" href="tokens.css"><style>{CSS}</style></head><body>
<div class="banner">MOCKUP – NON-FUNCTIONAL · SYNTHETIC DEMONSTRATION DATA</div>
<header><span class="logo">IronVision<b> AI</b></span><span class="search">Search systems, controls (AC-2, ac-2.1), findings, POA&amp;M, people…  ⌘K</span>
<span class="sp pill role">Acting as {role}</span><span class="pill cn">Guided mode: off</span></header>
<div class="wrap"><aside><div class="sys">LTP – Logistics Tracking Platform ▾</div>{nav}
<h6>LTP · RMF steps</h6><a class="{"on" if active == "Dashboard" else ""}"><span class="dot v"></span>System dashboard</a>{steps}
<h6>Recently viewed</h6><a class="sub">AC-2 Account Management</a><a class="sub">P-0015 Log4Shell</a><a class="sub">MPP – Mission Planning</a></aside>
<main><div class="crumb">{crumb}</div>{body}</main></div></body></html>"""


def dashboard():
    cards = ""
    info = {"Prepare": ("4/4 roles · boundary set", "", "System Owner, ISSO"), "Categorize": ("Moderate · approved rev 3", "", "ISSO → AO"),
            "Select": ("291 controls · strategy draft", "ISSM approval of the monitoring strategy", "ISSO → ISSM"),
            "Implement": ("181/291 implemented", "38 controls without a statement", "ISSO, System Owner"),
            "Assess": ("0/291 determined", "SCA assessment requested", "SCA"), "Authorize": ("SSP 92% valid · 6 open POA&M", "", "ISSM → AO"),
            "Monitor": ("12 evidence items stale", "", "ISSO")}
    nexts = {"Prepare": "View", "Categorize": "View", "Select": "Remind ISSM", "Implement": "Write 38 statements", "Assess": "Open SCA queue",
             "Authorize": "Check SSP validation", "Monitor": "Refresh stale evidence"}
    for n, (s, c, st) in enumerate(STEPS, 1):
        a, pend, who = info[s]
        pct = {"g": 100, "b": 62, "a": 30, "n": 5}[c]
        cards += f"""<div class="step"><div class="row"><span class="dot {c}"></span><h4>{n} · {s}</h4><span class="sp chip {'cg' if c == 'g' else 'cb' if c == 'b' else 'ca' if c == 'a' else 'cn'}">{st}</span></div>
<div class="bar"><i style="width:{pct}%"></i></div><div>{a}</div>{f'<div class="muted">⏳ Awaiting: {pend}</div>' if pend else '<div class="muted">No pending approvals</div>'}
<div class="muted">Roles: {who}</div><div style="margin-top:8px"><span class="btn {'pri' if s == 'Implement' else ''}">{nexts[s]} →</span></div></div>"""
    body = f"""<h1>Logistics Tracking Platform</h1><p class="lead">Moderate (C M · I M · A L) · FIPS 199 · In assessment · eMASS DEMO-1000 · ATO target 2027-02-01</p>
<div class="hero row"><div><div style="font-size:11px;opacity:.8">CONTINUE WHERE YOU LEFT OFF</div><div style="font:700 16px var(--iv-font-heading)">AC-2 Account Management – implementation statement (draft, edited 14 min ago)</div>
<div style="opacity:.85">Recommended next: submit AC-2 for ISSO review, then 37 more controls without a statement in the AC family.</div></div><span class="sp btn">Resume AC-2 →</span></div>
<div class="grid g4">{cards}<div class="step" style="background:#f8fafc"><h4>Readiness for authorization</h4><div class="bar"><i style="width:58%"></i></div>
<div>58% – 3 blockers</div><div class="muted">• 38 statements missing • SCA determinations 0/291 • ISCM strategy not approved</div><div style="margin-top:8px"><span class="btn">See package checklist →</span></div></div></div>
<div class="grid g2"><div class="panel"><h3>Pending approvals for this system</h3><table><tr><th>Item</th><th>Waiting for</th><th>Since</th></tr>
<tr><td>Continuous Monitoring Strategy v4 (from SLCM import)</td><td>ISSM Morgan Lee</td><td>2 days</td></tr><tr><td>SCA assessment request (291 controls)</td><td>SCA Dana Brooks</td><td>5 days</td></tr>
<tr><td>Risk acceptance P-0031</td><td>AO Col. Taylor</td><td>1 day</td></tr></table></div>
<div class="panel"><h3>Recent activity (one shared record)</h3><table><tr><td>eMASS Implementation Plan imported – 287 controls updated</td><td class="muted">ISSO · today</td></tr>
<tr><td>ACAS scan ltp_weekly_scan.nessus → 2 findings, 1 asset, linked to P-0015</td><td class="muted">auto · today</td></tr><tr><td>Policy AC-policy v3 → 14 mapping suggestions</td><td class="muted">ISSO · yesterday</td></tr></table></div></div>"""
    return shell("System RMF dashboard", body)


def mywork(role):
    data = {"ISSO": ("Your work across 4 systems", [("LTP", "Write 38 implementation statements (AC, IA, SC)", "Implement", "cb"), ("LTP", "14 policy mapping suggestions to review", "Implement", "cb"),
                                                    ("MPP", "12 evidence items are stale (> 90 days)", "Monitor", "ca"), ("FMDH", "3 unmapped open findings", "Assess", "cr"), ("TRS", "Import the eMASS Test Results you started", "Assess", "cn")]),
            "SCA": ("Assessments assigned to you", [("LTP", "Assess 291 controls – requested by ISSM 5 days ago", "Assess", "ca"), ("MPP", "Re-test 4 controls after POA&M closure", "Assess", "cb"),
                                                    ("LTP", "Approve 22 imported eMASS test results (historical)", "Assess", "cn")]),
            "ISSM": ("Approvals and oversight", [("LTP", "Approve Continuous Monitoring Strategy v4", "Select", "ca"), ("MPP", "Review package before AO submission", "Authorize", "cb"),
                                                ("LTP", "2 implementation statements returned for rework", "Implement", "cn"), ("Portfolio", "2 ATOs expire within 90 days", "Monitor", "cr")]),
            "AO": ("Decisions waiting for you", [("LTP", "Risk acceptance P-0031 (CAT II, residual Moderate)", "Authorize", "ca"), ("MPP", "Authorization decision – package complete, SAR & RAR attached", "Authorize", "cb"),
                                                ("FMDH", "Approve categorization revision 2 (High)", "Categorize", "ca")])}
    sub, items = data[role]
    rows = "".join(f'<tr><td><b>{s}</b></td><td>{t}</td><td><span class="chip {c}">{st}</span></td><td><span class="btn">Open →</span></td></tr>' for s, t, st, c in items)
    hide = {"ISSO": "No approve/authorize actions shown (SoD).", "SCA": "Only assessment actions – no statement editing (SCA independence).",
            "ISSM": "Approvals + oversight; assessment determinations stay with the SCA.", "AO": "Decisions only; nothing to edit. Package summary opens read-only."}[role]
    body = f"""<h1>My Work – {role}</h1><p class="lead">{sub}. Ordered by what blocks authorization first.</p>
<div class="grid g4"><div class="step"><div class="muted">Due this week</div><h1>{len(items) + 2}</h1></div><div class="step"><div class="muted">Waiting on others</div><h1>3</h1></div>
<div class="step"><div class="muted">Overdue</div><h1 style="color:#b91c1c">1</h1></div><div class="step"><div class="muted">Systems</div><h1>4</h1></div></div>
<div class="panel" style="margin-top:14px"><h3>Next actions</h3><table><tr><th>System</th><th>Task</th><th>Step</th><th></th></tr>{rows}</table></div>
<div class="anno">Role-based: {hide}</div>"""
    return shell(f"My Work {role}", body, "My Work", role, crumb="My Work")


def workbench():
    tree = """<div><span class="dot b"></span><b>AC</b> Access Control <span class="sp muted">18/25</span></div><div class="in on"><span class="dot a"></span>AC-2 Account Management</div>
<div class="in" style="padding-left:38px"><span class="dot g"></span>AC-2(1) Automated Account Mgmt</div><div class="in" style="padding-left:38px"><span class="dot n"></span>AC-2(3) Disable Accounts</div>
<div class="in"><span class="dot g"></span>AC-3 Access Enforcement</div><div class="in"><span class="dot r"></span>AC-17(2) Protection of Confidentiality</div>
<div><span class="dot b"></span><b>AT</b> Awareness &amp; Training <span class="sp muted">5/6</span></div><div><span class="dot a"></span><b>AU</b> Audit &amp; Accountability <span class="sp muted">9/16</span></div>
<div><span class="dot r"></span><b>CM</b> Configuration Mgmt <span class="sp muted">12/22</span></div><div><span class="dot n"></span><b>CP</b> Contingency Planning <span class="sp muted">3/13</span></div>"""
    body = f"""<div class="row"><h1>Control Workbench</h1><span class="sp btn">Import…</span><span class="btn">Export ▾</span></div>
<div class="grid" style="grid-template-columns:330px 1fr"><div class="panel"><div class="field">Search ID, title, CCI, keyword… (ac-2.1)</div>
<div class="row" style="margin:8px 0;flex-wrap:wrap"><span class="chip cb">Status ▾</span><span class="chip cn">Family ▾</span><span class="chip ca">Needs action</span><span class="chip cn">Mine</span><span class="sp muted">291</span></div>
<div class="tree">{tree}</div><div class="muted" style="margin-top:8px"><span class="dot g"></span> implemented <span class="dot a"></span> partial <span class="dot r"></span> finding <span class="dot n"></span> not started</div></div>
<div class="panel"><div class="row"><h1 style="font-size:20px">AC-2 Account Management</h1><span class="sp btn pri">Save</span></div>
<div class="row" style="margin:6px 0 12px;flex-wrap:wrap"><span class="chip ca">Implementation: Partially Implemented</span><span class="chip cn">Assessment: Not Assessed</span>
<span class="chip cg">Policy coverage: Covered (AC policy v3)</span><span class="chip cg">Evidence: Current</span><span class="chip cr">1 open finding · P-0015</span></div>
<div class="tabs"><span>Requirements</span><span class="on">Implementation</span><span>Evidence &amp; Policies (3)</span><span>Assessment</span><span>Findings &amp; POA&amp;M (1)</span><span>Monitoring</span></div>
<div class="grid g2"><div><div class="label">Implementation status</div><div class="field">Partially Implemented ▾</div></div><div><div class="label">Responsible entities</div><div class="field">ISSO; System Owner</div></div></div>
<div class="label">Implementation statement</div><div class="field" style="min-height:110px">a. The organization defines the types of accounts allowed (individual, group, system, service)… [ODP: account types = individual, service]<br>b. Account managers are assigned by the System Owner…</div>
<div class="row" style="margin-top:6px"><span class="muted">Draft · autosaved 14 min ago · suggestion from AC policy v3 available</span><span class="sp btn">Submit for review</span></div>
<div class="panel" style="margin-top:12px;background:#f8fafc"><b>▸ Advanced eMASS fields</b> <span class="muted">(designation, SLCM overrides, N/A justification, estimated completion, CCP) – collapsed</span></div></div></div>"""
    return shell("Control Workbench", body, "Implement", expand="Implement", crumb="LTP › 4 · Implement › Control Workbench › AC-2")


def import_center():
    body = """<h1>Import</h1><p class="lead">Drop any eMASS export, scan, checklist or policy. The type is detected and every file goes to the right RMF step – nothing is applied before you confirm.</p>
<div class="stepper"><span class="done">1 Upload ✓</span><span class="cur">2 Preview</span><span>3 Import</span><span>4 Completed</span></div>
<div class="panel"><h3>3 files detected for LTP</h3><table><tr><th>File</th><th>Detected as</th><th>Goes to</th><th>Records</th><th>Preview</th></tr>
<tr><td>IV-eMASS-implementation-plan.xlsx</td><td><span class="chip cg">eMASS Implementation Plan · high</span></td><td>Implement → Control Workbench</td><td>423 rows</td><td>287 update · 136 not in system · 6 warnings</td></tr>
<tr><td>ltp_weekly_scan.nessus</td><td><span class="chip cg">ACAS / Nessus · high</span></td><td>Assess → Findings, Inventory, POA&amp;M</td><td>2 hosts</td><td>2 findings · 1 new asset · 1 POA&amp;M link</td></tr>
<tr><td>slcm_worksheet_v1_3.xlsm</td><td><span class="chip cg">eMASS SLCM · high</span></td><td>Select → Monitoring strategy (draft)</td><td>70 controls</td><td>6 defaults · 8 profiles · 12 exceptions</td></tr></table>
<div class="row" style="margin-top:10px"><span class="muted">Conflicts default to “Use imported”. Every change is audited and can be reverted.</span><span class="sp btn">Review details</span><span class="btn pri">Import 3 files</span></div></div>
<div class="anno">One flow for every type: Upload → Preview → Import → Completed. The completed step links to the RMF step where the data now lives and shows the next action.</div>"""
    return shell("Import Center", body, "Import Center", crumb="Import Center")


def mapping_review():
    rows = "".join(f"""<tr><td><b>{c}</b></td><td>{w}</td><td><span class="chip {k}">{s}</span></td><td class="muted">{why}</td><td><span class="btn pri">Approve</span> <span class="btn">Correct</span> <span class="btn">Reject</span></td></tr>"""
                   for c, w, s, k, why in [("AC-2", "AC policy v3 §4.1 covers account types and reviews", "Policy coverage", "cb", "Quote: “accounts shall be reviewed quarterly…”"),
                                           ("AC-2(3)", "Disable after 35 days inactivity – ODP filled", "Policy coverage", "cb", "Quote §4.3"),
                                           ("CM-6", "STIG rule V-230223 → CM-6", "STIG mapping", "cv", "CCI-000366 crosswalk"),
                                           ("AT-2", "Evidence suggests Implemented", "Status suggestion", "ca", "1 current evidence item, no open finding")])
    body = f"""<h1>Mapping review</h1><p class="lead">Approving a policy mapping updates <b>policy coverage</b> only – never the assessment. Status suggestions change implementation status; only the SCA records determinations.</p>
<div class="row" style="margin-bottom:10px"><span class="chip cb">Policy coverage (14)</span><span class="chip cv">STIG mappings (8)</span><span class="chip ca">Status suggestions (15)</span><span class="sp btn">Approve all high-confidence (9)</span></div>
<div class="panel"><table><tr><th>Control</th><th>Suggestion</th><th>Type</th><th>Why</th><th></th></tr>{rows}</table></div>
<div class="anno">Simplified: 3 tabs instead of 6, one row per suggestion with the reason inline, approve/correct/reject on the row, a bulk action for high-confidence items with a shared rationale.</div>"""
    return shell("Mapping Review", body, "Implement", expand="Implement", crumb="LTP › 4 · Implement › Mapping review")


def assessment():
    body = """<h1>Assessment workspace</h1><p class="lead">SCA Dana Brooks · LTP · 291 controls · independent of the implementer</p>
<div class="stepper"><span class="done">1 Select control ✓</span><span class="done">2 Review evidence ✓</span><span class="cur">3 Record determination</span><span>4 Save → next</span></div>
<div class="grid" style="grid-template-columns:280px 1fr"><div class="panel"><h3>Queue (284 left)</h3><div class="tree"><div class="on"><span class="dot a"></span>AC-2 Account Management</div><div><span class="dot n"></span>AC-2(1)</div><div><span class="dot n"></span>AC-3</div><div><span class="dot g"></span>AT-2 – Satisfied</div></div></div>
<div class="panel"><h3>AC-2 Account Management</h3><div class="grid g2"><div><div class="label">Implementation (by ISSO)</div><div class="field">Partially Implemented – statement v4 approved</div>
<div class="label">Evidence (3)</div><div class="field">✓ ad_accounts_export.csv · current · sha256 4f2a…<br>✓ AC policy v3 §4.1 · approved mapping<br>⚠ quarterly_review.pdf · 120 days (stale)</div>
<div class="label">Imported eMASS test result (historical)</div><div class="field">Compliant · tested 2025-11-02 by J. Smith (eMASS)</div></div>
<div><div class="label">Assessment procedure</div><div class="field">AC-02 Examine / Interview / Test – 4 objectives</div><div class="label">Determination</div>
<div class="row"><span class="btn pri">Satisfied</span><span class="btn">Other Than Satisfied</span><span class="btn">Not Applicable</span></div>
<div class="label">Assessor notes</div><div class="field" style="min-height:70px">Objective (c) not met: review evidence older than 90 days.</div>
<div class="row" style="margin-top:10px"><span class="muted">Other Than Satisfied creates a finding → POA&amp;M suggestion</span><span class="sp btn pri">Save &amp; next →</span></div></div></div></div></div>"""
    return shell("Assessment", body, "Assess", "SCA", expand="Assess", crumb="LTP › 5 · Assess › Assessment workspace › AC-2")


def ssp():
    body = """<h1>Generate SSP</h1><p class="lead">The SSP is built from the shared system record – nothing is typed twice.</p>
<div class="stepper"><span class="done">1 Generate ✓</span><span class="cur">2 Review validation</span><span>3 Download</span></div>
<div class="grid g2"><div class="panel"><h3>Validation – 92% complete</h3><table><tr><td><span class="chip cg">✓</span> System profile, roles, boundary</td><td class="muted">Prepare</td></tr>
<tr><td><span class="chip cg">✓</span> Categorization (approved rev 3)</td><td class="muted">Categorize</td></tr><tr><td><span class="chip cg">✓</span> 291 controls, parameters</td><td class="muted">Select</td></tr>
<tr><td><span class="chip cr">38</span> controls without a statement</td><td><span class="btn">Fix in Workbench →</span></td></tr><tr><td><span class="chip ca">1</span> interconnection without ISA date</td><td><span class="btn">Fix in Prepare →</span></td></tr></table></div>
<div class="panel"><h3>Download</h3><p>SSP (DOCX) · SSP (PDF) · Appendix: control implementation (eMASS xlsx)</p><div class="row"><span class="btn">Download anyway (watermarked DRAFT)</span><span class="sp btn pri">Download SSP</span></div>
<p class="muted">Each issue links to the exact field where the information lives.</p></div></div>"""
    return shell("Generate SSP", body, "Authorize", expand="Authorize", crumb="LTP › 6 · Authorize › Package & documents › SSP")


def categorize(guided):
    g = """<div class="guide"><b>Guided mode · Step 2 Categorize</b><div class="grid g3" style="margin-top:6px"><div><b>Purpose</b><br>Decide how bad a loss of confidentiality, integrity or availability would be (FIPS 199).</div>
<div><b>You need</b><br>The information types the system processes (SP 800-60), PII yes/no.</div><div><b>Who</b><br>ISSO proposes · AO approves. Next: Select picks the baseline from this result.</div></div></div>""" if guided else ""
    body = f"""<h1>Categorize</h1>{g}<div class="grid g2"><div class="panel"><h3>Information types</h3><div class="field">Search 180 information types…</div>
<table><tr><td>D.16.3 Inventory Control</td><td>M · M · L</td></tr><tr><td>C.3.2.4 Logistics Management</td><td>M · M · M</td></tr></table>{'<div class="anno">Why: each type has provisional impact levels; the highest per objective wins (high-water mark).</div>' if guided else ''}</div>
<div class="panel"><h3>Result</h3><h1>Moderate</h1><div class="muted">C Moderate · I Moderate · A Moderate → 800-53B Moderate baseline</div><div class="label">Does this system contain PII?</div><div class="row"><span class="btn">Yes</span><span class="btn pri">No</span></div>
<div class="row" style="margin-top:12px"><span class="chip ca">Awaiting AO approval</span><span class="sp btn pri">Submit for AO approval</span></div></div></div>"""
    return shell("Guided " + ("on" if guided else "off"), body.replace("Guided mode: off", "Guided mode: on") if guided else body, "Categorize", expand="Categorize", crumb="LTP › 2 · Categorize")


def navigation():
    cols = "".join(f'<div class="step"><h4>{n} · {s}</h4>' + "".join(f'<div class="muted">• {x}</div>' for x in SUBS[s]) + "</div>" for n, (s, _, _) in enumerate(STEPS, 1))
    body = f"""<h1>Navigation – 7 RMF steps inside the system</h1><p class="lead">Global: My Work · Systems · Import Center · Search · Admin. Everything else lives under the system's RMF steps (any order). Status dot per step; breadcrumbs and recently viewed everywhere.</p>
<div class="grid g4">{cols}</div>"""
    h = shell("Navigation", body, "Implement", expand="Implement", crumb="LTP › 4 · Implement")
    return h.replace("Guided mode: off", "Guided mode: off") if False else h


PAGES = {"dashboard": dashboard, "navigation": navigation, "workbench": workbench, "import_center": import_center, "mapping_review": mapping_review,
         "assessment": assessment, "ssp": ssp, "guided_on": lambda: categorize(True), "guided_off": lambda: categorize(False),
         **{f"mywork_{r.lower()}": (lambda r=r: mywork(r)) for r in ("ISSO", "SCA", "ISSM", "AO")}}

if __name__ == "__main__":
    for k, f in PAGES.items():
        html = f()
        if k == "guided_on":
            html = html.replace("Guided mode: off", "Guided mode: on")
        (OUT / f"{k}.html").write_text(html)
        print("wrote", k)
