"""3:45 marketing cut (v4, 225.0 s). Light desktop only, no captions, no phone/theme footage, SYNTHETIC shared demo, no AI calls.
Run (after prep_v4.py): DEMO_SCENES=scenes_v4 DEMO_OUT=/tmp/demo_v4 python3 record_demo.py → DEMO_OUT=/tmp/demo_v4 DEMO_MP4=/tmp/v4_raw.mp4 assemble.py → finish_v4.py"""
from datetime import date, timedelta

import scenes_marketing as m
from record_demo import CARDS, IDS

T = {1: (0, 7), 2: (7, 25), 3: (25, 37), 4: (37, 62), 5: (62, 68), 6: (68, 84), 7: (84, 116), 8: (116, 125), 9: (125, 142),
     10: (142, 162), 11: (162, 172), 12: (172, 185), 13: (185, 192), 14: (192, 218), 15: (218, 225)}
TR_FILE = "/app/backend/tests/fixtures/emass/BLANK_TRExport.xlsx"
CI_ROW = '[data-testid^="ic-file-"]:has-text("SYNTHETIC_LTP_ControlInfo.xlsx")'
TR_ROW = '[data-testid^="ic-file-"]:has-text("BLANK_TRExport.xlsx")'
D = lambda days: (date.today() + timedelta(days=days)).isoformat()  # noqa: E731


async def pick(A, sel, value, dur=0.5, hold=0.3):
    await A.point(sel, dur)
    await A.p.select_option(sel, value)
    await A.hold(hold)


async def fill(A, sel, value, dur=0.5, hold=0.3):
    await A.point(sel, dur)
    await A.p.fill(sel, value)
    await A.hold(hold)


async def s1(A, p):
    await m.setup(A, p)
    A.mark(1, "Intro")
    await A.go((CARDS / "intro_mkt.html").as_uri())
    await p.evaluate("document.body.classList.add('show')")
    await A.hold(5.7)
    await p.evaluate("document.body.classList.add('out')")
    await A.pad_to(T[1][1])


async def s2(A, p):
    A.mark(2, "RMF dashboard: seven steps, progress, Guided Mode")
    await A.go("/dashboard", '[data-testid="dash-steps"]')
    await A.point("main h1", 0.6)
    await A.hold(0.8)
    for k in ("prepare", "categorize", "select", "implement", "assess", "authorize", "monitor"):
        await A.point(f'[data-testid="dash-step-status-{k}"]', 0.35)
        await A.hold(0.25)
    await A.point('[data-testid="dash-readiness"]', 0.5)
    await A.hold(1.2)
    await A.click('[data-testid="guided-toggle"]', 0.6, wait=0.5)
    await A.go("/rmf/categorize", '[data-testid="guided-panel"]')
    await A.point('[data-testid="guided-panel"]', 0.6)
    await A.hold(2.4)
    await A.point('[data-testid="guided-next"]', 0.5)
    await A.hold(0.8)
    await A.click('[data-testid="guided-toggle"]', 0.5, wait=0.4)
    await A.pad_to(T[2][1])


async def switch_system(A, p, match):
    """Off-camera system switch (recorder clock stopped) – a cut, like the persona switches."""
    A.R.stop()
    sel = p.locator('[data-testid="system-selector-select"]')
    val = await sel.evaluate("(s, m) => [...s.options].find((o) => o.value === m || o.text.includes(m))?.value", match)
    await sel.select_option(val)
    await p.wait_for_timeout(2500)


async def s3(A, p):
    A.mark(3, "CNSSI 1253 categorization: M-H-L trigraph (approved), NSS baseline")
    await switch_system(A, p, "Training Records")
    await A.go("/rmf/categorize", '[data-testid="cnssi-cia"]')
    await A.point('[data-testid="cat-mode-cnssi1253"]', 0.6)
    await A.hold(0.7)
    for k in ("c", "i", "a"):
        await A.point(f'[data-testid="cnssi-{k}"]', 0.4)
        await A.hold(0.35)
    await A.point('[data-testid="cat-calc"]', 0.5, dy=0.45)
    await A.hold(1.2)
    await A.point('[data-testid="cat-baseline"]', 0.4)
    await A.hold(0.6)
    await A.go("/rmf/select", '[data-testid="select-cat-summary"]')
    await A.point('[data-testid="select-cat-overall"]', 0.5)
    await A.hold(1.0)
    await A.click('[data-testid="select-next-1"]', 0.5, then='[data-testid="select-cnssi-baseline"]')
    await A.point('[data-testid="select-cnssi-baseline"]', 0.5, dy=0.2)
    await A.hold(1.0)
    await A.pad_to(T[3][1])


async def s4(A, p):
    await switch_system(A, p, IDS["LTP"])
    A.mark(4, "Import Center: eMASS Test Results round-trip")
    await A.go(f"/systems/{IDS['LTP']}/import-center", "main h1")
    await A.point("main h1", 0.5)
    A.ev("upload BLANK_TRExport.xlsx + SYNTHETIC_LTP_ControlInfo.xlsx")
    await p.set_input_files('[data-testid="ic-file-input"]', [TR_FILE, str(m.IMPORT_FILE)])
    await A.settle(TR_ROW + ' [data-testid^="ic-import-"]', 0.3)
    await A.settle(CI_ROW + ' [data-testid^="ic-remove-"]', 0.3)
    await A.point('[data-testid="ic-batch-summary"]', 0.5)
    await A.hold(0.9)
    await A.click(CI_ROW + ' [data-testid^="ic-remove-"]', 0.5, wait=0.2)  # 2 s flash: the second file is removed before import
    await A.settle(None, 0.3)
    await A.point(TR_ROW, 0.5)
    await A.hold(0.9)
    await A.click(TR_ROW + ' [data-testid^="ic-import-"]', 0.5, then=TR_ROW + ' [data-testid^="ic-open-"]')
    await A.point(TR_ROW + ' [data-testid^="ic-result-"]', 0.5)
    await A.hold(0.9)
    await A.click(TR_ROW + ' [data-testid^="ic-open-"]', 0.5, then='[data-testid="tr-page"]')
    A.R.stop()
    await p.evaluate("""() => { const s = document.querySelector('[data-testid=tr-workbook-select]'); if (!s) return;
      const o = [...s.options].filter((x) => x.text.startsWith('BLANK_TRExport.xlsx')).sort((a, b) => parseInt(b.text.split(' v')[1]) - parseInt(a.text.split(' v')[1]))[0];
      if (o) { const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(s, o.value); s.dispatchEvent(new Event('change', {bubbles: true})); } }""")
    await p.wait_for_selector('[data-testid="tr-mapping"]', timeout=120000)
    await A.settle('[data-testid="tr-mapping"]', 0.4)
    await A.point('[data-testid="tr-mapping"]', 0.6, dy=0.15)
    await A.hold(1.4)
    await A.scroll(320, 0.8)
    await A.hold(1.4)
    n0 = await p.locator('[data-testid^="tr-report-"]').count()
    await A.click('[data-testid="tr-generate-populate"], [data-testid="tr-generate-btn"]', 0.6, wait=0.2)
    A.R.stop()
    await p.wait_for_function("() => /generated|review/i.test(document.querySelector('[data-testid=tr-status]')?.innerText || '')", timeout=180000)
    await A.settle('[data-testid="tr-export"]', 0.4)
    await A.point('[data-testid="tr-status"]', 0.5)
    await A.hold(1.0)
    await A.click('[data-testid="tr-export"]', 0.5, wait=0.2)
    A.R.stop()
    await p.wait_for_function(f"() => document.querySelectorAll('[data-testid^=tr-report-]').length > {n0}", timeout=120000)
    await A.settle('[data-testid="tr-exports"]', 0.4)
    await A.point('[data-testid="tr-exports"]', 0.5)
    await A.hold(1.4)
    await A.pad_to(T[4][1])


async def s5(A, p):
    A.mark(5, "Import management: selective delete, Undo")
    await A.go("/import-center", m.HIST)
    await A.click(m.HIST, 0.5, then='[data-testid^="mid-entry-"]')
    await A.click('[data-testid="mid-delete-everything"]', 0.5, wait=0.2)
    A.R.stop()
    await p.wait_for_selector('[data-testid^="mid-undo-"]', timeout=30000)
    await A.settle(None, 0.4)
    await A.click('[data-testid^="mid-undo-"]', 0.4, wait=0.1)
    A.R.stop()
    await p.wait_for_timeout(2500)
    await A.settle(None, 0.4)
    await A.point('[data-testid^="mid-state-"]', 0.4)
    await A.pad_to(T[5][1])


async def s6(A, p):
    A.mark(6, "Control Workbench: implementation, attach evidence")
    await A.go(f"/systems/{IDS['LTP']}/controls/ac-2", '[data-testid="wb-tabs"]')
    await A.point('[data-testid="wb-control-id"]', 0.6)
    await A.hold(1.0)
    await A.point('[data-testid="wb-statuses"]', 0.6)
    await A.hold(1.6)
    await A.click('[data-testid="wb-tab-evidence"]', 0.6, wait=0.6)
    await A.click('[data-testid="wb-attach-evidence-btn"]', 0.6, wait=0.6)
    await A.point('[data-testid="wb-attach-evidence-target"]', 0.5)
    await A.hold(0.9)
    await A.point('[data-testid="wb-attach-evidence-choose"]', 0.5)
    await A.upload('[data-testid="wb-attach-evidence-input"]', m.EVIDENCE_FILE)
    await A.settle('[data-testid="wb-attach-evidence-done"]', 0.6)
    await A.point('[data-testid="wb-attach-evidence-done"]', 0.6)
    await A.hold(2.2)
    await A.pad_to(T[6][1])


async def s7(A, p):
    A.mark(7, "AI Policy Auditor: verified quote, manual review, candidate passage, human proposal")
    await A.go(f"/policy-auditor/{IDS['POLICY_AI']}", '[data-testid="coverage-toggle-ac-2"]')
    await A.point("main h1", 0.6)
    await A.hold(1.0)
    await A.click('[data-testid="coverage-toggle-ac-2"]', 0.7, wait=0.7)
    await A.point('[data-testid="coverage-line-ac-2"]', 0.6)
    await A.hold(1.6)
    await A.point('[data-testid="req-CCI-000010"] td:first-child', 0.7)
    await A.hold(1.8)
    await A.point('[data-testid="req-CCI-000010"] blockquote', 0.7)
    await A.hold(3.0)
    await A.point('[data-testid="req-CCI-002124"] td:first-child', 0.8)
    await A.hold(2.4)
    await A.point('[data-testid="req-CCI-002124"] td:nth-child(4)', 0.7, dy=0.25)
    await A.hold(2.2)
    await A.point('[data-testid="req-CCI-002124"] [data-testid^="req-candidates-"]', 0.7)
    await A.hold(2.4)
    await A.click('[data-testid="use-candidate-ac-2-CCI-002124"]', 0.7, wait=0.3)
    await A.settle('[data-testid="policy-msg"]', 0.3)
    await A.point('[data-testid="policy-msg"]', 0.7)
    await A.hold(2.8)
    await A.pad_to(T[7][1])


async def s8(A, p):
    A.mark(8, "Mapping Review: a person approves the proposal")
    await A.go("/mapping-review", '[data-testid="queue-tab-policy_map"]')
    await A.click('[data-testid="queue-tab-policy_map"]', 0.5, then=m.PM_ROW)
    await A.point(m.PM_ROW, 0.5)
    await A.hold(1.6)
    await A.click(m.PM_ROW + ' [data-testid^="queue-approve-"]', 0.5, wait=0.2)
    await A.settle('[data-testid="mapping-review-msg"]', 0.3)
    await A.point('[data-testid="mapping-review-msg"]', 0.5)
    await A.pad_to(T[8][1])


async def s9(A, p):
    A.mark(9, "SCA workspace: acting as SCA, evidence, determination")
    await A.persona("sca")
    await A.go("/assess/workspace", '[data-testid^="sca-item-"]')
    await A.point('[data-testid="acting-as-select"]', 0.6)
    await A.hold(1.4)
    await A.click('[data-testid^="sca-item-"]', 0.6, then='[data-testid="sca-determination"]')
    await A.point('[data-testid="sca-evidence"]', 0.6)
    await A.hold(1.8)
    await A.click('[data-testid="sca-determination"] input[type=checkbox]', 0.5, wait=0.3)
    await A.click('[data-testid="method-examine"]', 0.5, wait=0.3)
    await A.point('[data-testid="assessment-result"]', 0.5)
    await A.hold(0.6)
    await A.click('[data-testid="assessment-save"]', 0.5, wait=0.2)
    await A.settle('[data-testid="sca-moved-banner"]', 0.3)
    await A.point('[data-testid="sca-moved-banner"]', 0.6)
    await A.hold(1.6)
    await A.pad_to(T[9][1])


async def s10(A, p):
    A.mark(10, "POA&M: from an ACAS finding, milestone, risk acceptance routed")
    await A.persona("isso")
    await A.go(f"/ingest-runs/{IDS['SCAN']}", '[data-testid^="add-to-poam-"]')
    await A.point("main h1", 0.5)
    await A.hold(0.5)
    await A.click('[data-testid^="add-to-poam-"]', 0.5, then='[data-testid="poam-form-submit"]')
    await fill(A, '[data-testid="poam-form-controls"]', "SI-2", 0.3, 0.2)
    await fill(A, '[data-testid="poam-form-plan"]', "Apply vendor patch; rescan to confirm.", 0.3, 0.5)
    await A.click('[data-testid="poam-form-submit"]', 0.4, then='[data-testid="poam-milestones"]')
    await fill(A, '[data-testid="milestone-title"]', "Patch deployed", 0.4, 0.1)
    await fill(A, '[data-testid="milestone-due"]', D(45), 0.3, 0.1)
    await A.click('[data-testid="milestone-add"]', 0.3, wait=0.3)
    await A.settle('[data-testid^="milestone-"]:has-text("Patch deployed")', 0.3)
    await A.click('[data-testid="poam-request-risk-btn"]', 0.4, then='[data-testid="poam-risk-modal"]')
    await fill(A, '[data-testid="poam-risk-justification"]', "SYNTHETIC: compensating control in place until the patch.", 0.3, 0.3)
    await fill(A, '[data-testid="poam-risk-expiration"]', D(120), 0.3, 0.1)
    await A.click('[data-testid="poam-risk-submit"]', 0.4, wait=0.2)
    await A.settle('[data-testid="poam-history"]', 0.3)
    await A.point('[data-testid="poam-history"]', 0.5)
    await A.hold(1.0)
    await A.pad_to(T[10][1])


async def s11(A, p):
    A.mark(11, "Tamper-evident audit log: verify chain")
    await A.persona("issm")
    await A.go("/admin", '[data-testid="audit-panel"]')
    await A.point('[data-testid="audit-table"]', 0.6)
    await A.hold(1.2)
    await A.click('[data-testid="audit-verify-btn"]', 0.6, wait=0.1)
    await A.settle('[data-testid="audit-chain-status"]', 0.4)
    await A.point('[data-testid="audit-chain-status"]', 0.6)
    await A.hold(0.8)
    await A.point('[data-testid="audit-panel"] h2, [data-testid="audit-panel"] h3', 0.5)  # cursor off the pill so "CHAIN VALID" reads cleanly
    await A.hold(1.6)
    await A.pad_to(T[11][1])


async def s12(A, p):
    A.mark(12, "Continuous monitoring: freshness, findings, overdue POA&Ms, traceability")
    await A.go("/rmf/monitor", '[data-testid="monitor-stats"]')
    for k in ("mon-current", "mon-stale", "mon-findings", "mon-poams"):
        await A.point(f'[data-testid="{k}"]', 0.45)
        await A.hold(0.6)
    await A.point('[data-testid="mon-schedule"]', 0.5)
    await A.hold(0.8)
    await A.go("/traceability", '[data-testid="trace-count"]')
    await A.point('[data-testid="trace-count"]', 0.6)
    await A.hold(1.4)
    await A.pad_to(T[12][1])


async def s13(A, p):
    A.mark(13, "Authorization package: SSP, SAR, RAR, OSCAL, eMASS Implementation Plan")
    await A.go(f"/systems/{IDS['LTP']}/authorization", '[data-testid="doc-ssp"]')
    for k in ("ssp", "sar", "rar"):
        await A.point(f'[data-testid="doc-{k}"]', 0.4)
        await A.hold(0.4)
    await A.point('[data-testid="oscal-panel"]', 0.5)
    await A.hold(0.6)
    await A.point('[data-testid="pkg-export-emass-plan"]', 0.5)
    await A.pad_to(T[13][1])


async def s14(A, p):
    A.mark(14, "AO decision: ATO with conditions, expiry, recorded by a person")
    await A.persona("ao")
    await A.go(f"/systems/{IDS['LTP']}/authorization", '[data-testid="authz-decision-select"]')
    await A.point('[data-testid="acting-as-select"]', 0.6)
    await A.hold(1.4)
    await A.point('[data-testid="authz-decision-panel"]', 0.6)
    await A.hold(0.8)
    await A.point('[data-testid="authz-decision-select"]', 0.5)
    await A.p.locator('[data-testid="authz-decision-select"]').focus()
    await A.hold(0.3)
    for v in ("ATO", "IATT", "DATO", "ATO_with_conditions"):  # walk the four options on screen
        await A.p.select_option('[data-testid="authz-decision-select"]', v)
        await A.hold(0.7)
    await fill(A, '[data-testid="authz-expiration"]', D(3 * 365))
    await A.type('[data-testid="authz-conditions"]', "1. Close POA&M items rated High within 90 days. 2. Quarterly account reviews.", delay=0.012)
    await A.type('[data-testid="authz-rationale"]', "SYNTHETIC: residual risk acceptable with conditions.", delay=0.012)
    await A.click('[data-testid="authz-record-btn"]', 0.6, wait=0.2)
    await A.settle('[data-testid="authz-msg"]', 0.4)
    await A.point('[data-testid="authz-msg"]', 0.5)
    await A.hold(1.0)
    await A.scroll(-900, 0.5)
    await A.point("main h1", 0.6)
    await A.hold(2.0)
    await A.point('[data-testid="authz-history"]', 0.6)
    await A.hold(1.2)
    await A.pad_to(T[14][1])


async def s15(A, p):
    A.mark(15, "Closing")
    await A.go((CARDS / "closing_mkt.html").as_uri())
    await p.evaluate("document.body.classList.add('show')")
    await A.pad_to(T[15][1])


SCENES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13, s14, s15]
