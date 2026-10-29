"""3:10 marketing cut: writes the ElevenLabs narration, teleprompter, SRT and scene timeline from BLOCKS + the recorder timeline.
Run after record_demo.py (DEMO_SCENES=scenes_marketing DEMO_OUT=/tmp/demo_mkt). Spoken forms are written exactly as they should be read."""
import json
import os
from pathlib import Path

REC = Path(os.environ.get("DEMO_OUT", "/tmp/demo_mkt")) / "timeline.json"
FIX = Path("/tmp/demo_fix/timeline.json")  # pick-up recording spliced in by splice_mkt.py
FIX_MAP = [((0, 45), 85), ((45, 65), 105)]  # fix window → shift into the final video (85–130 s, 150–170 s)
OUT = Path("/app/backend/app/static/demo")
WPS_MAX, BREATH, SPEAK_WPS = 2.3, 0.5, 2.5  # budget words/s, min silence per block, estimate for speaking time (150 wpm)

SPOKEN = [("IronVision AI", "IronVision A-I"), ("AI", "A-I"), ("RMF", "R-M-F"), ("NIST", "nist (one word)"), ("eMASS", "e-Mass"),
          ("SSP", "S-S-P"), ("SAR", "S-A-R"), ("RAR", "R-A-R"), ("OSCAL", "OS-cal"), ("SCA", "assessor (not spelled out)"),
          ("30-day", "thirty days"), ("3:10", "not spoken")]

# (scene, start, end, spoken text)
BLOCKS = [
    (1, 0.8, 6.8, "IronVision A-I. Human-approved A-I for the Risk Management Framework."),
    (2, 8.5, 18.5, "Every system starts on one dashboard. The seven R-M-F steps are connected, so you always see progress and the next action."),
    (2, 19.5, 29.5, "Guided Mode explains each step in plain language: what it's for, who acts, and what comes next."),
    (3, 30.5, 43.0, "Bring in your existing work. Drop an e-Mass export into the Import Center, and IronVision recognizes the file type and the target system automatically."),
    (3, 44.0, 56.5, "Nothing is written until you review it. Safe changes are accepted in one click, conflicts wait for a person, then you apply the import."),
    (4, 57.3, 64.6, "Every import stays manageable: delete selectively, restore, or undo for thirty days."),
    (5, 65.5, 74.5, "In the Control Workbench, each control shows its implementation status, statement, and the evidence behind it."),
    (5, 75.5, 84.5, "Attach evidence right from the control. It's linked, versioned, and you move straight to the next task."),
    (6, 85.5, 96.5, "The A-I Policy Auditor reads your whole policy and checks every requirement of every mapped control. Take one requirement for account management."),
    (6, 97.0, 108.0, "When the policy covers it, you see the exact supporting quote, verified word for word against the document, and the A-I's coverage determination."),
    (6, 108.5, 119.5, "When it's unclear, nothing is marked missing. It's flagged for manual review with candidate passages, and a person turns one into a proposal."),
    (7, 120.4, 129.5, "A-I suggestions are proposals, not approvals. In Mapping Review, a person approves the mapping."),
    (8, 130.5, 140.0, "The independent assessor works from the same evidence, in one focused workspace."),
    (8, 141.0, 149.5, "The determination is recorded by the assessor, never by A-I, and the next control is ready."),
    (9, 150.5, 160.0, "Authorization packages come together automatically: the S-S-P, S-A-R, and R-A-R, plus OS-cal exports."),
    (9, 161.0, 169.5, "e-Mass Implementation Plan and Test Results exports are validated and ready to upload."),
    (10, 170.5, 184.5, "Continuous monitoring keeps it current: scheduled activities, evidence freshness, open findings, and full traceability from requirement to evidence."),
    (11, 185.5, 189.5, "IronVision A-I. Get audit-ready. Stay audit-ready."),
]

SCENES = {
    1: ("Intro", "Intro card", "Brand card fades in and out"),
    2: ("RMF dashboard & Guided Mode", "/dashboard, /rmf/categorize", "Point through the seven RMF steps and readiness; Guided Mode on → panel → off"),
    3: ("Import Center", "/systems/:id/import-center, review page", "Upload SYNTHETIC eMASS Control Information → detected → review → accept safe → apply"),
    4: ("Import management", "/import-center/manage/:id", "Delete everything this import created → 30-day Undo (restore)"),
    5: ("Control Workbench", "/systems/:id/controls/ac-2", "Status + statement, Evidence tab → Attach evidence → upload → Completed – next"),
    6: ("AI Policy Auditor", "/policy-auditor/:id", "AC-2 checklist (AC-2 not yet mapped): CCI-000010 met with AI-verified quote; CCI-002124 needs manual review with candidate passages → Use this passage → “Sent to Mapping Review as a human proposal – an authorized reviewer decides.”"),
    7: ("Mapping Review", "/mapping-review", "Policy coverage tab: that new AC-2 human proposal (pending) → Approve → “1 item(s) approved”"),
    8: ("SCA workspace", "/assess/workspace", "SCA persona: evidence panel → objective, method, result → Save → Saved – moved to next control"),
    9: ("Authorization & exports", "/systems/:id/authorization, /test-results", "SSP/SAR/RAR status, OSCAL, eMASS Implementation Plan; TR export mode + history"),
    10: ("Continuous monitoring", "/rmf/monitor, /traceability", "Current/stale evidence, findings, POA&Ms, schedule; traceability"),
    11: ("Closing", "Closing card", "IronVision AI · Enterprise GRC, Made Intelligent. · Get audit-ready. Stay audit-ready. · Request Your Demo Today"),
}


def ts(t):
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}"


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def fit():
    rows = []
    for i, (sc, a, b, txt) in enumerate(BLOCKS, 1):
        w, win = len(txt.split()), b - a
        speak = w / SPEAK_WPS
        rows.append({"block": i, "scene": sc, "start": a, "end": b, "words": w, "window": win, "wps": round(w / win, 2), "speak_s": round(speak, 1), "slack_s": round(win - speak, 1)})
        assert w <= WPS_MAX * (win - BREATH) and win - speak >= BREATH, rows[-1]
    for (_, _, b1, _), (_, a2, _, _) in zip(BLOCKS, BLOCKS[1:]):
        assert a2 >= b1, (b1, a2)
    return rows


def main():
    tl = json.loads(REC.read_text())
    if FIX.exists():
        fx = json.loads(FIX.read_text())
        keep = [e for e in tl["events"] if not any(a + off <= e[0] < b + off for (a, b), off in FIX_MAP)]
        add = [[round(e[0] + off, 2), e[1]] for e in fx["events"] for (a, b), off in FIX_MAP if a <= e[0] < b]
        tl["events"] = sorted(keep + add)
    rows = fit()
    n = ["IronVision AI – 3:10 product demo · narration script (ElevenLabs, voice “Matilda”)",
         "Plain spoken text only. Place each block at its Start time; leave the gaps silent. Natural, confident, professional tone.",
         "Spoken forms used: " + "; ".join(f"{a} → “{b}”" for a, b in SPOKEN), ""]
    for r, (sc, a, b, txt) in zip(rows, BLOCKS):
        n += [f"[Block {r['block']} · Scene {sc} · {mmss(a)} – {mmss(b)} · {r['words']} words · ~{r['speak_s']} s]", txt, ""]
    (OUT / "ironvision_ai_rmf_narration.txt").write_text("\n".join(n))
    t = ["# IronVision AI – 3:10 product demo · teleprompter", "", "Read at ~150 wpm. Pause at each `/`. Timestamps are video time.", ""]
    for sc, (name, _, _) in SCENES.items():
        t += [f"## Scene {sc} · {name}", ""]
        t += [f"**[{mmss(a)} – {mmss(b)}]**\n\n" + txt.replace(", ", ", / ").replace(". ", ". / ").replace(": ", ": / ") + "\n" for s2, a, b, txt in BLOCKS if s2 == sc]
    (OUT / "ironvision_ai_rmf_teleprompter.md").write_text("\n".join(t))
    srt = []
    for i, (_, a, b, txt) in enumerate(BLOCKS, 1):
        srt += [str(i), f"{ts(a)} --> {ts(b)}", txt, ""]
    (OUT / "ironvision_ai_rmf_captions.srt").write_text("\n".join(srt))
    starts = {s["scene"]: s["start"] for s in tl["scenes"]}
    md = ["# IronVision AI – 3:10 product demo · scene timeline", "",
          f"Video: 1920×1080, 30 fps, H.264 High, silent, no burned-in captions, duration {tl['end']:.2f} s. Scene starts measured by the recorder.", "",
          "| # | Scene | Start | End | Screens | What happens |", "|---|---|---|---|---|---|"]
    for sc, (name, screens, actions) in SCENES.items():
        md.append(f"| {sc} | {name} | {mmss(starts[sc])} | {mmss(starts.get(sc + 1, tl['end']))} | {screens} | {actions} |")
    md += ["", "## On-screen events", "", "| Time | Event |", "|---|---|"] + [f"| {mmss(e[0])} | `{e[1]}` |" for e in tl["events"]]
    (OUT / "ironvision_ai_rmf_scene_timeline.md").write_text("\n".join(md) + "\n")
    print(json.dumps({"blocks": len(BLOCKS), "words": sum(r["words"] for r in rows), "starts": starts, "end": tl["end"]}))
    return rows


if __name__ == "__main__":
    main()
