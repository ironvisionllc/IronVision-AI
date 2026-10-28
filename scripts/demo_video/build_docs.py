"""Writes narration.txt, teleprompter.md, captions.srt and scene_timeline.md from one source (BLOCKS + SCENES) and the recorder's
timeline.json (actual on-screen event times). Run after assemble.py."""
import json
from pathlib import Path

REC = Path("/tmp/demo_rec/timeline.json")
OUT = Path("/app/backend/app/static/demo")

# (scene, start, end, text) – on-screen captions (silent video) and an optional voice-over script; every block fits its window.
BLOCKS = [
    (1, 0, 5, "IronVision AI – human-approved AI for the NIST Risk Management Framework"),
    (1, 5, 14, "Shared SYNTHETIC demo workspace · sign in and act as the ISSO persona"),
    (2, 14, 25, "System dashboard: the 7 RMF steps with live status and the next action"),
    (2, 25, 39, "Guided Mode explains each step: purpose, why it matters, who acts, what's next"),
    (3, 39, 50, "Import Center: drop eMASS, STIG, Nessus, PPSM or policy files – each is detected and routed"),
    (3, 50, 62, "Review before apply: safe changes are accepted, conflicts wait for a person"),
    (4, 62, 73, "Manage imported data: every applied import, grouped by section, with provenance"),
    (4, 73, 84, "Delete everything an import created – the system stays – and undo for 30 days"),
    (5, 84, 98, "Control Workbench: status, statement, evidence and assessment for one control"),
    (5, 98, 112, "Attach evidence from inside the control: upload → linked → “Completed – next”"),
    (6, 112, 124, "Policy Auditor: a stored AI analysis – every 'met' needs an exact, verified policy quote"),
    (6, 124, 136, "No silent misses: unclear requirements show candidate passages for a human to decide"),
    (6, 136, 148, "Reading report: what was read, whole-document check, second look, “Found it here”"),
    (7, 148, 164, "Mapping Review: every automatic link or suggestion waits for a person to approve"),
    (8, 164, 179, "SCA workspace: the assessor records the determination – AI never does"),
    (8, 179, 194, "“Saved – moved to next control”, with Undo"),
    (9, 194, 210, "Authorize package: SSP/SAR/RAR drafts, OSCAL and the eMASS Implementation Plan"),
    (9, 210, 226, "eMASS Test Results export: pre-populated or blank-template mode, with validation"),
    (10, 226, 244, "Continuous monitoring and traceability across controls, evidence and findings"),
    (11, 244, 257, "Light and dark themes"),
    (11, 257, 284, "Works at phone width"),
    (12, 284, 300, "IronVision AI · Get audit-ready. Stay audit-ready."),
]

SCENES = {
    1: ("Intro & sign-in", "Intro card, /login", "Explore the demo; act as ISSO; select LTP", "Persona emails masked in every frame"),
    2: ("Dashboard, RMF steps, Guided Mode", "/dashboard, /rmf/categorize", "Point at the 7 RMF steps; Guided Mode on → panel → off", "—"),
    3: ("Import Center", "/systems/:id/import-center, review page", "Upload SYNTHETIC Control Information; detect; review; accept safe; apply", "Synthetic workbook"),
    4: ("Manage imported data", "/import-center/manage/:id", "Sections; delete everything; Undo", "System shell kept"),
    5: ("Control Workbench & evidence", "/systems/:id/controls/ac-2", "Evidence tab → Attach evidence → upload → Completed – next", "Synthetic .txt evidence"),
    6: ("Policy Auditor", "/policy-auditor/:id", "RA-1 met rows with verified quotes; candidates; reading report; Found it here", "Stored AI result copied from an existing SYNTHETIC analysis – no new AI call"),
    7: ("Mapping Review", "/mapping-review", "Review-needed note; queue items; approve buttons (not clicked)", "—"),
    8: ("SCA workspace", "/assess/workspace", "SCA persona records a determination → Saved – moved to next control → Undo", "Human determination only"),
    9: ("Authorize & eMASS exports", "/systems/:id/authorization, /test-results", "Package, OSCAL, eMASS Implementation Plan; TR export mode + history", "Deterministic TR export"),
    10: ("Monitoring", "/rmf/monitor, /traceability", "Monitor tiles; traceability count", "—"),
    11: ("Themes & phone", "/dashboard, /rmf-workflow, phone card", "Light → dark → light; live 390 px dark capture", "Phone frame is a live capture"),
    12: ("Closing", "Closing card", "—", "—"),
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
