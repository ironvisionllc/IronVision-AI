"""Writes narration.txt, teleprompter.md, captions.srt and scene_timeline.md from one source (BLOCKS + SCENES) and the recorder's
timeline.json (actual on-screen event times). Run after assemble.py."""
import json
from pathlib import Path

REC = Path("/tmp/demo_rec/timeline.json")
OUT = Path("/app/backend/app/static/demo")

# (scene, start, end, text) – ~140–150 wpm; every block fits its window (checked below).
BLOCKS = [
    (1, 0.0, 6.0, "This is IronVision AI: human-approved AI for the NIST Risk Management Framework."),
    (1, 6.5, 13.0, "Everything here runs in a shared demonstration workspace with synthetic data, one click from sign-in."),
    (1, 13.5, 20.0, "Personas let one presenter act as ISSO, assessor and AO, and every action stays labelled."),
    (2, 20.0, 31.0, "The RMF overview is the command center: all seven NIST 800-37 steps, computed from live records, with the criteria behind every status."),
    (2, 31.0, 36.0, "Ongoing work and the single next action are always one click away."),
    (2, 36.0, 45.0, "As the ISSM, the portfolio shows authorizations, CAT I and KEV exposure, overdue POA&Ms, and what is waiting on you."),
    (3, 45.0, 56.0, "Prepare and Categorize start at registration: name the system, assign the RMF key roles, and answer whether it is a National Security System."),
    (3, 56.0, 62.0, "Step one tracks every required role. Here, the assessor is still missing."),
    (3, 62.0, 68.0, "Federal systems use FIPS 199: information types roll up to a high-water mark."),
    (3, 68.0, 76.0, "For a national security system, CNSSI 1253 keeps confidentiality, integrity and availability separate, and prompts for the Privacy Overlay."),
    (3, 76.0, 85.0, "Integrity was raised to High with a recorded rationale, and the change waited for the AO's approval before it took effect."),
    (3, 85.5, 95.0, "Select then applies the CNSSI 1253 baseline: five hundred fifty-nine controls, each traced to its source table, plus overlays, tailoring and parameters."),
    (4, 95.5, 107.5, "Implementation happens in the Control Workbench. For AC-2, the ISSO sees status, supporting evidence with hashes and freshness, open findings and mapped policies in one place."),
    (4, 108.0, 118.0, "AI can draft the statement, grounded in that evidence with validated citations. It is labelled as AI and never auto-approved."),
    (4, 118.5, 140.0, "Mapping Review puts the control requirement next to the exact policy passage. Automated matching and AI only propose; a person accepts, rejects or overrides with a justification. Nothing changes a compliance record until a human decides."),
    (5, 140.0, 146.0, "Evidence arrives as STIG, SCAP, ACAS or Nessus files. Live connectors here are mocked."),
    (5, 146.0, 156.0, "Each ingest run is hashed, deduplicated and mapped through CCIs to NIST 800-53 controls, including this Log4j finding from an ACAS scan."),
    (5, 156.5, 169.0, "Test Results imports the eMASS Test Result template and is designed to preserve it. Rows are proposed from assessments, scans and evidence; AI explains each row."),
    (5, 169.5, 185.0, "Only the Security Control Assessor approves a result, and must record who actually tested and when. AI never sets compliance status, tester or test date."),
    (6, 185.0, 196.0, "The authorization package brings together the SSP, assessment results, POA&Ms and risk acceptances, with OSCAL exports. The ISSO can submit it, but the decision is AO-only."),
    (6, 196.0, 204.0, "POA&Ms rank risk, flag KEV and CAT I items, and show sync status with a mocked eMASS connector."),
    (6, 204.0, 225.0, "After ISSM endorsement, the Authorizing Official records the decision: ATO, ATO with conditions, IATT or denial, with rationale and expiration. Separation of duties is enforced; no one approves their own work, and in a real organization that means a different person."),
    (7, 225.0, 233.0, "Continuous monitoring watches evidence freshness, CAT I findings, CISA KEV and overdue POA&Ms."),
    (7, 233.0, 240.0, "The Evidence Ledger keeps every artifact with its SHA-256 hash, provenance and versions."),
    (7, 240.0, 245.5, "Traceability links each control to evidence, findings, POA&Ms and assessment."),
    (7, 246.0, 265.0, "And every action, including each review and approval, lands in a hash-chained, append-only audit log you can verify and export."),
    (8, 265.0, 273.0, "From preparation to continuous monitoring, the whole lifecycle stays in one place."),
    (8, 273.5, 286.0, "IronVision AI: human-approved AI for the NIST Risk Management Framework. AI does the heavy lifting; people keep the authority."),
    (8, 286.5, 296.0, "Get audit-ready, and stay audit-ready. Request your demo today."),
]

SCENES = {
    1: ("Intro & Login", "Intro card (synthetic-data notice) → login page → Explore demo → RMF overview",
        "Intro card fades out; cursor points at brand and the 'Synthetic data · shared demo workspace' caption; clicks Explore demo; points at the SYNTHETIC banner and the 'Acting as' persona switcher.",
        "Intro card is an authored HTML branding card (not a UI mockup). Sign-in itself is cut (load time removed)."),
    2: ("RMF Command Center", "Getting started · RMF overview; Portfolio / Leadership (as ISSM persona)",
        "Cursor walks the 7 step cards and the stepper, Ongoing activities and Next action; persona switch to ISSM; Portfolio cards (authorized, KEV), Waiting on your decision, operational priority score.",
        "Persona switches are cut; the header shows the active persona at all times."),
    3: ("Prepare / Categorize / Select", "Register system form; Step 1 Prepare – key roles (LTP); Step 2 Categorize (LTP, FIPS 199); Step 2 Categorize (TEG, CNSSI 1253 M-H-L); Step 3 Select (TEG)",
        "Types an example system name (form not submitted); points at key-role pickers and the NSS question; Prepare shows the missing SCA; FIPS 199 selection and summary; system switch to the synthetic NSS 'Tactical Edge Gateway'; CNSSI 1253 + NSS = Yes, Privacy Overlay prompt, scrolls the C/I/A and approval sections; Select counts (CNSSI baseline for M-H-L) and parameter comparison.",
        "TEG was created for the demo (synthetic) and its categorization approved by the AO persona beforehand (audited). The registration form is not submitted."),
    4: ("Implement & AI", "Control Workbench – AC-2 (LTP); Mapping review side-by-side",
        "Control header, scrolls to supporting evidence and mapped policies; clicks 'Generate draft' (live OpenRouter call; the ~12 s wait is cut); points at the AI-draft label, citations and 'Request review'; opens Policy mappings → side-by-side review; points at requirement, policy passage, Accept.",
        "The AI draft is generated live and not saved; nothing is accepted in Mapping review."),
    5: ("Assess", "Evidence Sources; ingest run ltp_db-server-01.ckl (STIG); ingest run ltp_weekly_scan.nessus (ACAS); Step 5 Assess; eMASS Test Results; SCA approval dialog",
        "Upload kinds and MOCK/DEMO connector note; STIG and ACAS findings with control mappings; assessment progress; TR export mode and AI evidence analysis on row 41 (pre-generated); persona SCA opens Approve → Date tested / Tested by fields; dialog cancelled.",
        "The TR workbook is the blank eMASS template imported into the demo workspace; AI analysis of rows 41/42 was generated before recording (live provider). No row is approved."),
    6: ("Authorize", "Authorization package (ISSO view); POA&M list; Authorization package (AO view)",
        "SSP summary, POA&Ms, OSCAL exports, 'Authorization decision (AO only)'; POA&M cards and KEV/CAT I row, MOCK eMASS note; persona AO: decision form, selects ATO with conditions, types a rationale, points at Record (not clicked).",
        "Package was submitted (ISSO persona) and endorsed (ISSM persona) before recording so the AO form is reachable. No decision is recorded."),
    7: ("Continuous Monitoring", "Step 7 Monitor; Evidence Ledger; Traceability matrix; Audit log (filtered 'review')",
        "Monitor stat cards; Evidence Ledger with Verify integrity and the hashed ledger table; traceability row AC-17(2); audit log filtered to review actions.",
        "Audit log is filtered so no client-IP detail is on screen."),
    8: ("Closing", "RMF overview; closing card",
        "Returns to the RMF overview; branded closing card fades in and holds.",
        "Closing card is an authored HTML branding card with the existing logo and brand colours."),
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
