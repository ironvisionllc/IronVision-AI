"""3:10 marketing cut (190.0 s). Light desktop only, no captions, no phone/theme footage. SYNTHETIC shared demo; no AI calls
(the Policy Auditor scene shows a stored AI result copied in by prep_v2.py). Run: DEMO_SCENES=scenes_marketing DEMO_OUT=/tmp/demo_mkt python3 record_demo.py"""
from record_demo import BASE, CARDS, EVIDENCE_FILE, IDS, IMPORT_FILE

T = {1: (0, 8), 2: (8, 30), 3: (30, 57), 4: (57, 65), 5: (65, 85), 6: (85, 120), 7: (120, 130), 8: (130, 150),
     9: (150, 170), 10: (170, 185), 11: (185, 190)}
HIST = '[data-testid^="ic-hist-emass-"]:has-text("SYNTHETIC_LTP_ControlInfo.xlsx") [data-testid^="ic-manage-"]'
PM_ROW = '[data-testid^="queue-item-pm:"]:has-text("Raven Logistics"):has(:text-is("AC-2"))'


async def setup(A, p):
    """Sign-in, persona and system selection happen off-camera (recorder clock not running)."""
    p.on("dialog", lambda d: __import__("asyncio").ensure_future(d.accept()))
    await p.goto(BASE + "/login")
    await p.fill("input[type=email]", "demo@ironvision.ai")
    await p.fill("input[type=password]", __import__("os").environ.get("DEMO_PASSWORD", "IronVisionDemo!2026"))
    await p.keyboard.press("Enter")
    await p.wait_for_url(lambda u: "/login" not in u, timeout=60000)
    await p.locator('[data-testid="acting-as-select"]').select_option("isso")
    await p.wait_for_timeout(2500)
    await p.locator('[data-testid="system-selector-select"]').select_option(IDS["LTP"])
    await p.wait_for_timeout(2500)


async def s1(A, p):
    await setup(A, p)
    A.mark(1, "Intro")
    await A.go((CARDS / "intro_mkt.html").as_uri())
    await p.evaluate("document.body.classList.add('show')")
    await A.hold(6.6)
    await p.evaluate("document.body.classList.add('out')")
    await A.pad_to(T[1][1])


async def s2(A, p):
    A.mark(2, "RMF dashboard: seven connected steps, progress, Guided Mode")
    await A.go("/dashboard", '[data-testid="dash-steps"]')
    await A.point("main h1", 0.7)
    await A.hold(1.2)
    for k in ("prepare", "categorize", "select", "implement", "assess", "authorize", "monitor"):
        await A.point(f'[data-testid="dash-step-status-{k}"]', 0.4)
        await A.hold(0.35)
    await A.point('[data-testid="dash-readiness"]', 0.6)
    await A.hold(1.6)
    await A.point('[data-testid="nav-step-categorize"]', 0.6)
    await A.click('[data-testid="guided-toggle"]', 0.7, wait=0.6)
    await A.go("/rmf/categorize", '[data-testid="guided-panel"]')
    await A.point('[data-testid="guided-panel"]', 0.7)
    await A.hold(3.2)
    await A.point('[data-testid="guided-next"]', 0.6)
    await A.hold(1.4)
    await A.click('[data-testid="guided-toggle"]', 0.6, wait=0.5)
    await A.pad_to(T[2][1])


async def s3(A, p):
    A.mark(3, "Import Center: upload, detect, review, import")
    await A.go(f"/systems/{IDS['LTP']}/import-center", 'main h1')
    await A.point("main h1", 0.6)
    await A.hold(0.8)
    await A.upload('[data-testid="ic-file-input"]', IMPORT_FILE)
    await A.settle('[data-testid="ic-file-0"]', 1.5)
    await A.point('[data-testid="ic-file-0"]', 0.7)
    await A.hold(2.6)
    await A.click('[data-testid="ic-import-0"]', 0.6, then='[data-testid="ic-result-0"]')
    await A.point('[data-testid="ic-result-0"]', 0.6)
    await A.hold(1.2)
    await A.click('[data-testid="ic-result-0"] a', 0.6, then='[data-testid="import-apply-btn"]')
    await A.hold(1.6)
    await A.scroll(420, 1.0)
    await A.hold(2.2)
    await A.click('[data-testid="import-accept-safe"]', 0.6, wait=0.9)
    await A.scroll(-420, 0.7)
    await A.click('[data-testid="import-apply-btn"]', 0.6, wait=0.3)
    A.R.stop()
    await p.wait_for_timeout(5000)
    await A.settle(None, 0.8)
    await A.hold(2.0)
    await A.pad_to(T[3][1])


async def s4(A, p):
    A.mark(4, "Import management: delete, restore, 30-day Undo")
    await A.go("/import-center", HIST)
    await A.click(HIST, 0.6, then='[data-testid^="mid-entry-"]')
    await A.point('[data-testid^="mid-group-"]', 0.5)
    await A.hold(0.8)
    await A.click('[data-testid="mid-delete-everything"]', 0.6, wait=0.2)
    A.R.stop()
    await p.wait_for_selector('[data-testid^="mid-undo-"]', timeout=30000)
    await A.settle(None, 0.6)
    await A.point('[data-testid^="mid-undo-"]', 0.5)
    await A.hold(0.9)
    await A.click('[data-testid^="mid-undo-"]', 0.4, wait=0.1)
    A.R.stop()
    await p.wait_for_timeout(2500)
    await A.settle(None, 0.6)
    await A.point('[data-testid^="mid-state-"]', 0.5)
    await A.pad_to(T[4][1])


async def s5(A, p):
    A.mark(5, "Control Workbench: implementation, attach evidence")
    await A.go(f"/systems/{IDS['LTP']}/controls/ac-2", '[data-testid="wb-tabs"]')
    await A.point('[data-testid="wb-control-id"]', 0.7)
    await A.hold(1.4)
    await A.point('[data-testid="wb-statuses"]', 0.7)
    await A.hold(2.0)
    await A.click('[data-testid="wb-tab-evidence"]', 0.7, wait=0.8)
    await A.click('[data-testid="wb-attach-evidence-btn"]', 0.7, wait=0.8)
    await A.point('[data-testid="wb-attach-evidence-target"]', 0.6)
    await A.hold(1.4)
    await A.point('[data-testid="wb-attach-evidence-choose"]', 0.6)
    await A.upload('[data-testid="wb-attach-evidence-input"]', EVIDENCE_FILE)
    await A.settle('[data-testid="wb-attach-evidence-done"]', 0.8)
    await A.point('[data-testid="wb-attach-evidence-done"]', 0.7)
    await A.hold(3.0)
    await A.pad_to(T[5][1])


async def s6(A, p):
    A.mark(6, "AI Policy Auditor: one requirement, verified quote, review, human proposal")
    await A.go(f"/policy-auditor/{IDS['POLICY_AI']}", '[data-testid="coverage-toggle-ac-2"]')
    await A.point("main h1", 0.7)
    await A.hold(1.4)
    await A.click('[data-testid="coverage-toggle-ac-2"]', 0.8, wait=0.8)
    await A.point('[data-testid="coverage-line-ac-2"]', 0.7)
    await A.hold(2.0)
    await A.point('[data-testid="req-CCI-000010"] td:first-child', 0.8)
    await A.hold(2.2)
    await A.point('[data-testid="req-CCI-000010"] blockquote', 0.8)
    await A.hold(3.4)
    await A.point('[data-testid="req-CCI-002124"] td:first-child', 0.9)
    await A.hold(3.0)
    await A.point('[data-testid="req-CCI-002124"] td:nth-child(4)', 0.8, dy=0.25)
    await A.hold(2.6)
    await A.point('[data-testid="req-CCI-002124"] [data-testid^="req-candidates-"]', 0.8)
    await A.hold(3.0)
    await A.click('[data-testid="use-candidate-ac-2-CCI-002124"]', 0.8, wait=0.3)
    await A.settle('[data-testid="policy-msg"]', 0.4)
    await A.point('[data-testid="policy-msg"]', 0.8)
    await A.hold(3.4)
    await A.pad_to(T[6][1])


async def s7(A, p):
    A.mark(7, "Mapping Review: a person approves the proposed mapping")
    await A.go("/mapping-review", '[data-testid="queue-tab-policy_map"]')
    await A.click('[data-testid="queue-tab-policy_map"]', 0.6, then=PM_ROW)
    await A.point(PM_ROW, 0.6)
    await A.hold(2.0)
    await A.click(PM_ROW + ' [data-testid^="queue-approve-"]', 0.6, wait=0.2)
    await A.settle('[data-testid="mapping-review-msg"]', 0.4)
    await A.point('[data-testid="mapping-review-msg"]', 0.6)
    await A.pad_to(T[7][1])


async def s8(A, p):
    A.mark(8, "SCA workspace: independent assessor records the determination")
    await A.persona("sca")
    await A.go("/assess/workspace", '[data-testid^="sca-item-"]')
    await A.click('[data-testid^="sca-item-"]', 0.7, then='[data-testid="sca-determination"]')
    await A.point('[data-testid="sca-evidence"]', 0.7)
    await A.hold(2.4)
    await A.point('[data-testid="sca-determination"]', 0.6)
    await A.hold(1.0)
    await A.click('[data-testid="sca-determination"] input[type=checkbox]', 0.6, wait=0.3)
    await A.click('[data-testid="method-examine"]', 0.5, wait=0.3)
    await A.point('[data-testid="assessment-result"]', 0.5)
    await A.hold(0.8)
    await A.click('[data-testid="assessment-save"]', 0.6, wait=0.2)
    await A.settle('[data-testid="sca-moved-banner"]', 0.4)
    await A.point('[data-testid="sca-moved-banner"]', 0.7)
    await A.hold(2.4)
    await A.pad_to(T[8][1])


async def s9(A, p):
    A.mark(9, "Authorization package and eMASS exports")
    await A.persona("issm")
    await A.go(f"/systems/{IDS['LTP']}/authorization", '[data-testid="doc-ssp"]')
    for k in ("ssp", "sar", "rar"):
        await A.point(f'[data-testid="doc-{k}"]', 0.5)
        await A.hold(0.9)
    await A.point('[data-testid="oscal-panel"]', 0.6)
    await A.hold(1.4)
    await A.point('[data-testid="pkg-export-emass-plan"]', 0.6)
    await A.hold(1.8)
    await A.go("/test-results", '[data-testid="tr-exports"]')
    await A.point('[data-testid="tr-export-mode"]', 0.6)
    await A.hold(2.0)
    await A.point('[data-testid="tr-exports"]', 0.6)
    await A.hold(1.8)
    await A.pad_to(T[9][1])


async def s10(A, p):
    A.mark(10, "Continuous monitoring: activities, freshness, findings, traceability")
    await A.go("/rmf/monitor", '[data-testid="monitor-stats"]')
    for k in ("mon-current", "mon-stale", "mon-findings", "mon-poams"):
        await A.point(f'[data-testid="{k}"]', 0.45)
        await A.hold(0.8)
    await A.point('[data-testid="mon-schedule"]', 0.5)
    await A.hold(1.0)
    await A.go("/traceability", '[data-testid="trace-count"]')
    await A.point('[data-testid="trace-count"]', 0.6)
    await A.hold(1.6)
    await A.pad_to(T[10][1])


async def s11(A, p):
    A.mark(11, "Closing")
    await A.go((CARDS / "closing_mkt.html").as_uri())
    await p.evaluate("document.body.classList.add('show')")
    await A.pad_to(T[11][1])


SCENES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11]
