"""3:45 cut (v4): narration (ElevenLabs “Matilda”), teleprompter, SRT and scene timeline. Run after record_demo.py (DEMO_OUT=/tmp/demo_v4)."""
import json
import os
from pathlib import Path

import build_docs_mkt as b

b.REC = Path(os.environ.get("DEMO_OUT", "/tmp/demo_v4")) / "timeline.json"
b.FIX = Path("/nonexistent")
b.SPOKEN[:] = [("IronVision AI", "IronVision A-I"), ("AI", "A-I"), ("RMF", "R-M-F"), ("CNSSI 1253", "C-N-S-S-I twelve fifty-three"),
               ("M-H-L", "moderate, high, low"), ("eMASS", "e-Mass"), ("STIG", "Stig (one word)"), ("ACAS", "A-cass"), ("POA&M / POA&Ms", "poe-am / poe-ams"),
               ("SSP", "S-S-P"), ("SAR", "S-A-R"), ("RAR", "R-A-R"), ("OSCAL", "OS-cal"), ("ATO", "A-T-O"), ("IATT", "I-A-T-T"), ("DATO", "D-A-T-O"),
               ("AO", "Authorizing Official (not spelled out)"), ("SCA", "assessor (not spelled out)"), ("3:45", "not spoken")]
b.BLOCKS[:] = [
    (1, 0.8, 6.5, "IronVision A-I. Human-approved A-I for the Risk Management Framework."),
    (2, 7.5, 16.0, "Every system starts on one dashboard. The seven R-M-F steps are connected, so you always see progress."),
    (2, 16.5, 24.5, "Guided Mode explains each step in plain language, and what comes next."),
    (3, 25.5, 36.5, "For national security systems, choose C-N-S-S-I twelve fifty-three. Confidentiality, integrity and availability keep their own levels: moderate, high, low."),
    (4, 37.5, 49.0, "Bring in your existing e-Mass work. The Import Center detects each file, a Test Results workbook here, and maps its columns for you."),
    (4, 49.5, 61.5, "Results are generated from your real data, then exported back into the same e-Mass template, validated and ready to upload."),
    (5, 62.3, 67.7, "Every import stays manageable: delete selectively, or undo."),
    (6, 68.5, 83.5, "In the Control Workbench, each control shows its implementation and the evidence behind it. Attach evidence right from the control."),
    (7, 84.5, 95.0, "The A-I Policy Auditor checks every requirement of every mapped control. Take account management."),
    (7, 95.5, 105.5, "Where the policy covers it, you see the exact quote, verified word for word against the document."),
    (7, 106.0, 115.5, "Where it's unclear, it's flagged for manual review, and a person turns a passage into a proposal."),
    (8, 116.4, 124.5, "A-I suggestions are proposals. In Mapping Review, a person approves them."),
    (9, 125.5, 141.5, "The independent assessor works from the same evidence and records the determination. Never the A-I."),
    (10, 142.5, 161.5, "Findings from Stig and A-cass scans become poe-ams, with milestones and dates. Accepting a risk is routed for a human decision."),
    (11, 162.5, 171.5, "Every action is in a tamper-evident audit log. Verify the hash chain in one click."),
    (12, 172.5, 184.5, "Continuous monitoring keeps it current: evidence freshness, open findings, overdue poe-ams, and full traceability."),
    (13, 185.3, 191.7, "The package assembles itself: S-S-P, S-A-R, R-A-R, OS-cal, and e-Mass exports."),
    (14, 192.5, 204.5, "The Authorizing Official makes the call: A-T-O, A-T-O with conditions, I-A-T-T, or D-A-T-O."),
    (14, 205.0, 217.5, "Here, an A-T-O with conditions, with an expiry date, recorded and signed by a person."),
    (15, 218.5, 224.5, "IronVision A-I. Get audit-ready. Stay audit-ready."),
]
b.SCENES.clear()
b.SCENES.update({
    1: ("Intro", "Intro card", "Brand card fades in and out"),
    2: ("RMF dashboard & Guided Mode", "/dashboard, /rmf/categorize", "Seven RMF steps and readiness; Guided Mode on → panel → off"),
    3: ("CNSSI 1253 categorization", "/rmf/categorize (LTP)", "NSS = yes → CNSSI 1253 → C Moderate, I High, A Low → security category per objective (no single high-water mark) → Appendix D baseline (not saved)"),
    4: ("Import Center – eMASS round-trip", "/systems/:id/import-center, /test-results", "Upload BLANK_TRExport.xlsx + SYNTHETIC Control Information (2 s, removed before import) → detected → Import → TR column mapping → generate (rules, no AI) → validated export into the same template"),
    5: ("Import management", "/import-center/manage/:id", "Control Information import (applied off-camera): delete everything → Undo"),
    6: ("Control Workbench", "/systems/:id/controls/ac-2", "Implementation status + statement → Evidence → Attach evidence → Completed"),
    7: ("AI Policy Auditor", "/policy-auditor/:id", "Stored AI result: CCI-000010 verified quote; CCI-002124 manual review + candidate passages → Use this passage → human proposal"),
    8: ("Mapping Review", "/mapping-review", "That AC-2 proposal → Approve"),
    9: ("SCA workspace", "/assess/workspace", "“Acting as SCA” → evidence → objective, method, result → Save"),
    10: ("POA&M", "/ingest-runs/:id (ACAS), /poams/:id", "Open ACAS finding → Add to POA&M → due date + plan → milestone with date → Request risk acceptance (ISSM endorses → AO decides) → pending"),
    11: ("Tamper-evident audit log", "/admin (Audit events)", "Verify chain → “CHAIN VALID · N events”"),
    12: ("Continuous monitoring", "/rmf/monitor, /traceability", "Current/stale evidence, findings, POA&Ms, schedule; traceability"),
    13: ("Authorization package", "/systems/:id/authorization", "SSP/SAR/RAR, OSCAL, eMASS Implementation Plan"),
    14: ("AO decision", "/systems/:id/authorization (AO persona)", "“Acting as AO” → options ATO / IATT / DATO / ATO with conditions → expiry +3 years, 2 conditions, rationale → Record decision (simulated signature) → “Authorized (ATO w/ conditions) · expires …”"),
    15: ("Closing", "Closing card", "IronVision AI · Enterprise GRC, Made Intelligent. · Get audit-ready. Stay audit-ready. · Request Your Demo Today"),
})

if __name__ == "__main__":
    rows = b.main()
    for f in ("narration.txt", "teleprompter.md", "scene_timeline.md"):
        p = b.OUT / f"ironvision_ai_rmf_{f}"
        p.write_text(p.read_text().replace("3:10 product demo", "3:45 product demo"))
    print(json.dumps({"words": sum(r["words"] for r in rows)}))
