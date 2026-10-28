"""Writes narration.txt, teleprompter.md, captions.srt and scene_timeline.md from one source (BLOCKS + SCENES) and the recorder's
timeline.json (actual on-screen event times). Run after assemble.py."""
import json
from pathlib import Path

REC = Path("/tmp/demo_rec/timeline.json")
OUT = Path("/app/backend/app/static/demo")

# (scene, start, end, text) – on-screen captions (silent video) and an optional voice-over script; every block fits its window.
BLOCKS = [
    (1, 0.0, 6.0, "IronVision AI: human-approved AI for the NIST Risk Management Framework."),
    (1, 6.5, 13.0, "This is a shared demonstration workspace with synthetic data only, one click from sign-in."),
    (1, 13.5, 20.0, "Personas let one presenter act as ISSO, assessor or AO; the active role is always shown."),
    (2, 20.0, 31.0, "The RMF overview is the command center: all seven NIST 800-37 steps, computed from live records."),
    (2, 31.0, 38.0, "Navigation follows the RMF steps, with the Import Center and Policies one click away."),
    (2, 38.0, 45.0, "Every screen works on the selected system, shown at the top."),
    (3, 45.0, 56.0, "The Import Center takes eMASS workbooks, test results, inventories, scans and policies, and detects each file's type."),
    (3, 56.0, 66.0, "Here a synthetic eMASS Control Information export is imported into the current system."),
    (3, 66.0, 80.0, "Review shows every change before it lands: current value, imported value, and anything that needs a decision."),
    (3, 80.0, 95.0, "Conflict-free changes are accepted in one step and applied through the normal save paths, with full audit."),
    (4, 95.0, 106.0, "Manage imported data shows everything one import populated, grouped by section, with the value before and after."),
    (4, 106.0, 117.0, "Restore, clear or delete per field, per section, or everything the import created. The system itself is kept."),
    (4, 117.0, 128.0, "Every operation can be undone for thirty days, and approved decisions are never removed, only flagged for re-review."),
    (4, 128.0, 140.0, "Destination screens mark imported rows with their source file, with multi-select delete and undo."),
    (5, 140.0, 152.0, "The Policy Auditor checks each policy against every control requirement, reading the whole document."),
    (5, 152.0, 164.0, "No silent misses: a requirement is only reported missing after a second look finds nothing."),
    (5, 164.0, 175.0, "Otherwise it says needs manual review, with confidence and the closest candidate passages."),
    (5, 175.0, 185.0, "If the reviewer finds the language, Found it here records the passage for a human mapping decision."),
    (6, 185.0, 196.0, "Scan findings arrive hashed, deduplicated and mapped through CCIs to NIST 800-53 controls."),
    (6, 196.0, 210.0, "The authorization package brings the SSP, assessment results, POA&Ms and OSCAL exports together."),
    (6, 210.0, 225.0, "The decision is AO-only: the ISSO submits, the ISSM endorses, and separation of duties is enforced."),
    (7, 225.0, 235.0, "Continuous monitoring watches evidence freshness, CAT I findings, CISA KEV and overdue POA&Ms."),
    (7, 235.5, 250.0, "The Evidence Ledger keeps every artifact with its SHA-256 hash, provenance and versions."),
    (7, 250.0, 265.0, "Traceability links each control to evidence, findings, POA&Ms and assessments."),
    (8, 265.0, 278.0, "From preparation to continuous monitoring, the whole lifecycle stays in one place."),
    (8, 278.5, 290.0, "IronVision AI: AI does the heavy lifting; people keep the authority."),
    (8, 290.5, 299.5, "Get audit-ready, and stay audit-ready. Request your demo today."),
]

SCENES = {
    1: ("Intro & Login", "Intro card (synthetic-data notice) → login → Explore the demo → RMF overview",
        "Intro card; points at brand and the synthetic-data caption; clicks Explore the demo; points at the SYNTHETIC banner and the persona switcher (ISSO).",
        "Intro card is an authored HTML branding card. Sign-in load time is cut."),
    2: ("Command center & navigation", "RMF overview (LTP)", "Walks the 7 step cards and Next action; points at Import Center and Policies in the RMF-ordered navigation and the system selector; opens the Import Center.",
        "Persona and system were set before the scene (cut)."),
    3: ("Import Center", "System Import Center; eMASS import review", "Uploads SYNTHETIC_LTP_ControlInfo.xlsx; type detected; Import; opens the review; points at Accept all conflict-free changes; Apply.",
        "The file is a synthetic 3-row Control Information export. The apply wait is cut."),
    4: ("Manage imported data", "Import Center history; Manage imported data; scan run findings", "Opens Manage imported data from history; sections and Imported-from chips; selects a field; Delete everything this import created; Undo from History; scan run shows Imported-from chips and the multi-select delete bar (not clicked).",
        "After recording the demo import is reverted in full (audited)."),
    5: ("Policy Auditor – no silent misses", "Policy detail (Access Control Policy)", "Coverage checklist; keyword-only/needs manual review labels, confidence, candidate passages; reading report warnings; Found it here (not sent).",
        "Shows the stored analysis; no AI call is made during recording."),
    6: ("Assess & Authorize", "Scan run (ltp_weekly_scan.nessus); Authorization package; POA&M", "Findings mapped to controls; package POA&Ms and OSCAL exports; AO-only decision panel; POA&M list.",
        "No decision is recorded."),
    7: ("Continuous Monitoring", "Step 7 Monitor; Evidence Ledger; Traceability", "Monitor stat cards; ledger with Verify integrity and hashes; traceability count.",
        "The audit log is not shown (it lists client IP details)."),
    8: ("Closing", "RMF overview; closing card", "Returns to the RMF overview; closing card fades in and holds.", "Authored HTML branding card."),
}


def ts(t, sep=","):
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{int(round((s % 1) * 1000)):03d}"


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def main():
    tl = json.loads(REC.read_text())
    for sc, a, b, txt in BLOCKS:
        wps = len(txt.split()) / (b - a)
        assert wps <= 2.55, (sc, a, txt, round(wps * 60))
    n = ["IronVision AI – RMF product demo · narration (ElevenLabs-ready)", "Voice: conversational, authoritative; federal cyber audience; ~140–150 wpm.",
         "Each block: Scene #, Block #, Start, Target End, then the exact text to speak. Leave silence between blocks.", ""]
    for i, (sc, a, b, txt) in enumerate(BLOCKS, 1):
        n += [f"Scene {sc} | Block {i} | Start {mmss(a)} | Target End {mmss(b)} | {len(txt.split())} words", txt, ""]
    (OUT / "ironvision_ai_rmf_narration.txt").write_text("\n".join(n))
    t = ["# IronVision AI – RMF product demo · teleprompter", "", "Read at ~145 wpm. Pause at each `/`. Timestamps are video time.", ""]
    for sc in SCENES:
        t += [f"## Scene {sc} · {SCENES[sc][0]}", ""]
        for i, (s2, a, b, txt) in enumerate(BLOCKS, 1):
            if s2 == sc:
                t += [f"**[{mmss(a)} – {mmss(b)}]**", "", txt.replace(", ", ", / ").replace(". ", ". / ").replace("; ", "; / "), ""]
    (OUT / "ironvision_ai_rmf_teleprompter.md").write_text("\n".join(t))
    srt = []
    for i, (sc, a, b, txt) in enumerate(BLOCKS, 1):
        srt += [str(i), f"{ts(a)} --> {ts(b)}", txt, ""]
    (OUT / "ironvision_ai_rmf_captions.srt").write_text("\n".join(srt))
    starts = {int(s["scene"]): s["start"] for s in tl["scenes"] if float(s["scene"]).is_integer()}
    ends = {k: starts.get(k + 1, tl["end"]) for k in starts}
    md = ["# IronVision AI – RMF product demo · scene timeline", "",
          f"Video: 1920×1080, 30 fps, H.264, no audio, duration {tl['end']:.2f} s. Times below are measured from the recording (event log of the recorder).", ""]
    for sc, (name, screens, actions, notes) in SCENES.items():
        md += [f"## Scene {sc} · {name}", "", f"- **Start / end:** {mmss(starts[sc])} – {mmss(ends[sc])}", f"- **Screens:** {screens}",
               f"- **Actions:** {actions}", f"- **Production notes:** {notes}", "", "| Time | On-screen event |", "|---|---|"]
        md += [f"| {mmss(e[0])} | `{e[1]}` |" for e in tl["events"] if starts[sc] <= e[0] < ends[sc]]
        md += ["", "**Narration**", ""] + [f"- {mmss(a)}–{mmss(b)}: {txt}" for s2, a, b, txt in BLOCKS if s2 == sc] + [""]
    (OUT / "ironvision_ai_rmf_scene_timeline.md").write_text("\n".join(md))
    print("docs written", {k: round(v, 2) for k, v in starts.items()})


if __name__ == "__main__":
    main()
