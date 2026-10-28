"""Scene script for the 5:00 silent demo (targets in seconds of the final video). SYNTHETIC shared demo workspace only; no AI calls.
The Policy Auditor scene shows a stored AI analysis copied into the demo workspace by prep_v2.py; nothing triggers a model."""
import json

from record_demo import CARDS, EVIDENCE_FILE, IDS, IMPORT_FILE

T = {1: (0, 14), 2: (14, 36), 3: (36, 62), 4: (62, 84), 5: (84, 112), 6: (112, 148), 7: (148, 164), 8: (164, 194),
     9: (194, 226), 10: (226, 244), 11: (244, 284), 12: (284, 300)}
HIST = '[data-testid^="ic-hist-emass-"]:has-text("SYNTHETIC_LTP_ControlInfo.xlsx") [data-testid^="ic-manage-"]'


async def s1(A, p):
    A.mark(1, "Intro & sign-in")
    p.on("dialog", lambda d: __import__("asyncio").ensure_future(d.accept()))
    await A.go((CARDS / "intro.html").as_uri())
    await p.evaluate("document.body.classList.add('show')")
    await A.hold(4.0)
    await p.evaluate("document.body.classList.add('out')")
    await A.hold(0.8)
    await A.go("/login", '[data-testid="demo-login-btn"]')
    await A.point('[data-testid="demo-login-caption"]', 1.0)
    await A.hold(1.5)
    await A.click('[data-testid="demo-login-btn"]', 0.7)
    A.R.stop()
    await p.wait_for_url(lambda u: "/login" not in u, timeout=30000)
    await A.persona("isso")
    await A.system(IDS["LTP"])
    await A.point('[data-testid="acting-as"]', 0.8)
    await A.pad_to(T[1][1])


async def s2(A, p):
    A.mark(2, "System dashboard, 7 RMF steps, Guided Mode")
    await A.go("/dashboard", '[data-testid="dash-steps"]')
    await A.point("main h1", 0.8)
    await A.hold(1.5)
    for k in ("prepare", "categorize", "select", "implement", "assess", "authorize", "monitor"):
        await A.point(f'[data-testid="dash-step-status-{k}"]', 0.4)
        await A.hold(0.5)
    await A.point('[data-testid="dash-readiness"]', 0.6)
    await A.hold(0.8)
    await A.point('[data-testid="nav-step-assess"]', 0.6)
    await A.hold(0.8)
    await A.hold(1.0)
    await A.click('[data-testid="guided-toggle"]', 0.8, wait=1.2)
    await A.go("/rmf/categorize", '[data-testid="guided-panel"]')
    await A.point('[data-testid="guided-panel"]', 0.8)
    await A.hold(3.0)
    await A.point('[data-testid="guided-next"]', 0.8)
    await A.hold(1.8)
    await A.click('[data-testid="guided-toggle"]', 0.8, wait=0.8)
    await A.pad_to(T[2][1])


async def s3(A, p):
    A.mark(3, "Import Center: detect, review, apply")
    await A.go(f"/systems/{IDS['LTP']}/import-center", "main h1")
    await A.point("main h1", 0.6)
    await A.upload('[data-testid="ic-file-input"]', IMPORT_FILE)
    await A.settle('[data-testid="ic-file-0"]', 2.0)
    await A.point('[data-testid="ic-file-0"]', 0.8)
    await A.hold(2.0)
    await A.click('[data-testid="ic-import-0"]', 0.7, then='[data-testid="ic-result-0"]')
    await A.point('[data-testid="ic-result-0"]', 0.7)
    await A.hold(1.2)
    await A.click('[data-testid="ic-result-0"] a', 0.7, then='[data-testid="import-apply-btn"]')
    await A.hold(1.5)
    await A.scroll(420, 1.2)
    await A.hold(2.0)
    await A.click('[data-testid="import-accept-safe"]', 0.7, wait=1.0)
    await A.scroll(-420, 0.8)
    await A.click('[data-testid="import-apply-btn"]', 0.7, wait=0.5)
    A.R.stop()
    await p.wait_for_timeout(5000)
    await A.settle(None, 1.0)
    await A.hold(2.0)
    await A.pad_to(T[3][1])


async def s4(A, p):
    A.mark(4, "Manage imported data")
    await A.go("/import-center", HIST)
    await A.click(HIST, 0.8, then='[data-testid^="mid-entry-"]')
    await A.point('[data-testid^="mid-group-"]', 0.8)
    await A.hold(2.0)
    await A.point('[data-testid^="mid-state-"]', 0.8)
    await A.hold(1.5)
    await A.click('[data-testid="mid-delete-everything"]', 0.8, wait=0.3)
    A.R.stop()
    await p.wait_for_selector('[data-testid^="mid-undo-"]', timeout=30000)
    await A.settle(None, 1.0)
    await A.point('[data-testid="mid-log"]', 0.8)
    await A.hold(2.0)
    await A.click('[data-testid^="mid-undo-"]', 0.8, wait=0.3)
    A.R.stop()
    await p.wait_for_timeout(2500)
    await A.settle(None, 0.8)
    await A.point('[data-testid^="mid-state-"]', 0.8)
    await A.hold(1.5)
    await A.pad_to(T[4][1])


async def s5(A, p):
    A.mark(5, "Control Workbench: attach evidence")
    await A.go(f"/systems/{IDS['LTP']}/controls/ac-2", '[data-testid="wb-tabs"]')
    await A.point('[data-testid="wb-control-id"]', 0.8)
    await A.hold(1.5)
    await A.point('[data-testid="wb-statuses"]', 0.8)
    await A.hold(1.5)
    await A.click('[data-testid="wb-tab-evidence"]', 0.8, wait=1.0)
    await A.click('[data-testid="wb-attach-evidence-btn"]', 0.8, wait=1.0)
    await A.point('[data-testid="wb-attach-evidence-target"]', 0.8)
    await A.hold(1.5)
    await A.point('[data-testid="wb-attach-evidence-choose"]', 0.8)
    await A.upload('[data-testid="wb-attach-evidence-input"]', EVIDENCE_FILE)
    await A.settle('[data-testid="wb-attach-evidence-done"]', 1.0)
    await A.point('[data-testid="wb-attach-evidence-done"]', 0.8)
    await A.hold(3.5)
    await A.point('[data-testid="wb-evidence-summary"]', 0.8)
    await A.hold(1.5)
    await A.pad_to(T[5][1])


async def s6(A, p):
    A.mark(6, "Policy Auditor: verified quotes, no silent misses")
    await A.go(f"/policy-auditor/{IDS['POLICY_AI']}", '[data-testid="policy-detail-page"]')
    await A.point("main h1", 0.8)
    await A.hold(1.2)
    await A.point('[data-testid="policy-control-mappings"]', 0.8)
    await A.hold(2.0)
    await A.click('[data-testid="coverage-toggle-ac-2"]', 0.8, wait=1.0)
    await A.point('[data-testid="coverage-line-ac-2"]', 0.8)
    await A.hold(1.5)
    await A.point('[data-testid="req-table-ac-2"] tr:has(blockquote)', 0.8)
    await A.hold(3.0)
    await A.point('[data-testid="req-table-ac-2"] tr:has(blockquote) blockquote', 0.8)
    await A.hold(2.5)
    await A.point('[data-testid^="req-candidates-"]', 0.8)
    await A.hold(2.5)
    await A.point('[data-testid="policy-reading-report"]', 0.8)
    await A.hold(1.5)
    await A.point('[data-testid="reading-whole-document-check"]', 0.8)
    await A.hold(2.0)
    await A.point('[data-testid="reading-second-look"]', 0.8)
    await A.hold(2.0)
    await A.point('[data-testid="found-it-here"]', 0.8)
    await A.hold(2.0)
    await A.pad_to(T[6][1])


async def s7(A, p):
    A.mark(7, "Mapping Review")
    await A.go("/mapping-review", '[data-testid="mapping-review-page"]')
    await A.point("main h1", 0.8)
    await A.hold(1.0)
    await A.point('[data-testid="queue-review-needed"]', 0.8)
    await A.hold(2.5)
    await A.point('[data-testid="queue-tab-policy_map"]', 0.6)
    await A.hold(1.0)
    await A.point('[data-testid^="queue-item-"]', 0.8)
    await A.hold(2.0)
    await A.point('[data-testid^="queue-approve-"]', 0.6)
    await A.hold(1.5)
    await A.pad_to(T[7][1])


async def s8(A, p):
    A.mark(8, "SCA workspace: human determination")
    await A.persona("sca")
    await A.go("/assess/workspace", '[data-testid="sca-workspace-page"]')
    await A.point('[data-testid="sca-auto-advance"]', 0.8)
    await A.hold(1.2)
    await A.click('[data-testid^="sca-item-"]', 0.8, then='[data-testid="sca-determination"]')
    await A.point('[data-testid="sca-determination"]', 0.8)
    await A.hold(1.5)
    await A.click('[data-testid="sca-determination"] input[type=checkbox]', 0.7, wait=0.4)
    await A.click('[data-testid="method-examine"]', 0.6, wait=0.4)
    await A.point('[data-testid="assessment-result"]', 0.6)
    await A.hold(1.0)
    await A.click('[data-testid="assessment-save"]', 0.7, wait=0.3)
    await A.settle('[data-testid="sca-moved-banner"]', 0.6)
    await A.point('[data-testid="sca-moved-banner"]', 0.8)
    await A.hold(2.5)
    await A.click('[data-testid="sca-moved-undo"]', 0.8, wait=1.5)
    await A.hold(1.0)
    await A.pad_to(T[8][1])


async def s9(A, p):
    A.mark(9, "Authorize package & eMASS exports")
    await A.persona("issm")
    await A.go(f"/systems/{IDS['LTP']}/authorization", '[data-testid="authz-decision-panel"]')
    await A.point("main h1", 0.8)
    await A.hold(1.2)
    await A.point('[data-testid="pkg-export-emass-plan"]', 0.8)
    await A.hold(2.5)
    await A.point('[data-testid="oscal-panel"]', 0.8)
    await A.hold(1.5)
    await A.point('[data-testid="authz-decision-panel"]', 0.8)
    await A.hold(2.0)
    await A.go("/test-results", '[data-testid="tr-exports"]')
    await A.point('[data-testid="tr-export-mode"]', 0.8)
    await A.hold(2.5)
    await A.point('[data-testid="tr-exports"]', 0.8)
    await A.hold(2.0)
    await A.point('[data-testid^="tr-export-mode-"]', 0.8)
    await A.hold(2.0)
    await A.pad_to(T[9][1])


async def s10(A, p):
    A.mark(10, "Continuous monitoring")
    await A.go("/rmf/monitor", '[data-testid="monitor-stats"]')
    for k in ("mon-current", "mon-stale", "mon-cat1", "mon-poams"):
        await A.point(f'[data-testid="{k}"]', 0.5)
        await A.hold(1.0)
    await A.go("/traceability", '[data-testid="trace-count"]')
    await A.point('[data-testid="trace-count"]', 0.8)
    await A.hold(2.0)
    await A.pad_to(T[10][1])


async def s11(A, p):
    A.mark(11, "Light / dark and phone width")
    await A.go("/dashboard", "main h1")
    await A.hold(1.0)
    await A.click('[data-testid="theme-toggle-btn"]', 0.8, wait=1.0)
    await A.hold(2.5)
    await A.go("/rmf-workflow", '[data-testid="rmf-step-monitor"]')
    await A.hold(3.0)
    A.R.stop()
    store = await p.evaluate("() => [JSON.stringify(Object.assign({}, sessionStorage)), JSON.stringify(Object.assign({}, localStorage))]")
    ctx = await p.context.browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, color_scheme="dark", is_mobile=True, has_touch=True)
    await ctx.add_init_script("(([s, l]) => { if (location.protocol === 'file:') return; for (const [k, v] of Object.entries(JSON.parse(s))) sessionStorage.setItem(k, v);"
                              " for (const [k, v] of Object.entries(JSON.parse(l))) localStorage.setItem(k, v); })(%s)" % json.dumps(store))
    from record_demo import MASK_JS, BASE
    await ctx.add_init_script(MASK_JS)
    ph = await ctx.new_page()
    await ph.goto(BASE + "/my-work")
    await ph.wait_for_load_state("networkidle", timeout=30000)
    await ph.wait_for_timeout(2500)
    await ph.screenshot(path=str(CARDS / "phone_shot.png"))
    await ctx.close()
    await A.hold(0.01)
    await A.click('[data-testid="theme-toggle-btn"]', 0.8, wait=1.0)
    await A.hold(2.0)
    await A.go((CARDS / "phone.html").as_uri())
    await p.evaluate("document.body.classList.add('show')")
    await A.pad_to(T[11][1])


async def s12(A, p):
    A.mark(12, "Closing")
    await A.go((CARDS / "closing.html").as_uri())
    await p.evaluate("document.body.classList.add('show')")
    await A.pad_to(T[12][1])


SCENES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12]
