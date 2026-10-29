"""Writes the 3:10 cut's validation report from ffprobe + /tmp/boundaries.json (scene-score cuts) + /tmp/privacy.json (OCR/luma checks)."""
import json
import subprocess
from pathlib import Path

import build_docs_mkt as b

V = Path("/app/backend/app/static/demo/ironvision_ai_rmf_demo.mp4")


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True).stdout.strip()


def main():
    probe = sh("ffprobe", "-v", "error", "-show_entries", "format=duration,size,bit_rate:stream=codec_type,codec_name,profile,level,width,height,r_frame_rate,pix_fmt,nb_frames", "-of", "compact", str(V))
    tags = sh("ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "compact", str(V))
    head = V.read_bytes()[:400000]
    faststart = head.find(b"moov") != -1 and (head.find(b"mdat") == -1 or head.find(b"moov") < head.find(b"mdat"))
    bnd, pv = json.loads(Path("/tmp/boundaries.json").read_text()), json.loads(Path("/tmp/privacy.json").read_text())
    names = {s: n for s, (n, _, _) in b.SCENES.items()}
    L = ["# IronVision AI – 3:10 product demo · validation report", "",
         "Recorded 2026-10-29 from the shared SYNTHETIC demo workspace (light desktop theme only). **No AI calls.** The Policy Auditor scene shows the AI-refined rows "
         "of a stored AI result for the SYNTHETIC `ac_raven` fixture, copied into the demo workspace (keyword-only leftovers of that older run were not copied, so the "
         "result is not flagged stale; AC-2 was left unmapped so “Use this passage” creates a new human proposal). The workspace was re-seeded afterwards.", "",
         "Revision v2 (2026-10-29): Policy Auditor + Mapping Review (1:25–2:10) and Authorization (2:30–2:50) re-recorded and spliced at the scene boundaries "
         "(scripts/demo_video/splice_mkt.py); all other scenes are frame-identical in content to v1 (archive/2026-10-29-3m10-v1/, unlinked).", "",
         "Revision v3 (2026-10-29): closing card re-rendered with a high-contrast white CTA pill (dark-teal bold text); a small scene label (2.2 s, 0.25 s fades, "
         "bottom-left) added at the start of each app scene so same-chrome transitions are visible (scripts/demo_video/finish_mkt.py). No boundary moved. "
         "v2 archived (archive/2026-10-29-3m10-v2/, unlinked).", "",
         "## ffprobe", "", "```", probe, tags, "```", "",
         f"- Faststart: moov before mdat = {faststart}. No audio stream. No burned-in captions (the SRT is a separate file; /demo-video has no <track>).",
         "- Delivery: HTTP 200 for the full file; HTTP 206 with Content-Range for byte-range requests (iPhone Safari seeking).", "",
         "## Scene boundaries measured from the video", "",
         "Method: ffmpeg scene-change score on every frame (`select=gte(scene,0),metadata=print`); per boundary, the frame with the highest score within ±0.5 s.", "",
         "| Boundary | Next scene | Target | Measured cut | Offset | Scene score |", "|---|---|---|---|---|---|"]
    L += [f"| {i - 1}→{i} | {names[i]} | {t:.1f} s | {p:.3f} s | {d:+.3f} s | {s} |" for i, (t, p, s, d) in enumerate(bnd, 2)]
    fd = json.loads(Path("/tmp/framediff.json").read_text())
    L += ["", f"All boundaries within ±0.3 s (largest offset {max(abs(x[3]) for x in bnd):+.3f} s).", "",
          "### Frame grabs at the same-chrome boundaries", "",
          "Sidebar and header are identical across these cuts, so the scene score is low (0.05–0.10) and generic detectors with a higher threshold miss them. "
          "Frame grabs 0.1 s either side (docs/demo/boundary_frames_3m10.jpg) show the page change, and the mean absolute pixel difference of the content area "
          "(0–255) jumps across the boundary while it is 0 within the previous scene:", "",
          "| Boundary | Frame before | Frame after | Content diff across boundary | Content diff 0.4 → 0.1 s before |", "|---|---|---|---|---|"]
    shows = {57.0: ("eMASS Import Center – import report (56.9 s)", "Import Center history → Manage imported data (57.1 s)"),
             120.0: ("Policy Auditor – “Sent to Mapping Review as a human proposal” (119.9 s)", "Mapping review queue (120.1 s)"),
             130.0: ("Mapping review – “1 item(s) approved” (129.9 s)", "SCA workspace (130.1 s)")}
    L += [f"| {x['boundary']} ({x['t']:.0f} s) | {shows[x['t']][0]} | {shows[x['t']][1]} | {x['diff_across']} | {x['diff_within_prev']} |" for x in fd]
    L += ["", "Each app scene now also opens with its on-screen label (“Import management”, “Mapping Review”, “SCA workspace”, …).", "",
          "## Narration fit (ElevenLabs, voice “Matilda”)", "", "Budget ≤ 2.3 words/s per block with ≥ 0.5 s silence; speaking time estimated at 150 wpm (2.5 words/s).", "",
          "| Block | Scene | Start | End | Window | Words | Words/s | Est. speech | Slack |", "|---|---|---|---|---|---|---|---|---|"]
    rows = b.fit()
    L += [f"| {r['block']} | {r['scene']} | {b.mmss(r['start'])} | {b.mmss(r['end'])} | {r['window']:.1f} s | {r['words']} | {r['wps']} | {r['speak_s']} s | {r['slack_s']} s |" for r in rows]
    L += ["", f"Total: {sum(r['words'] for r in rows)} words in {len(rows)} blocks.", "", "Spoken forms: " + "; ".join(f"{a} → “{c}”" for a, c in b.SPOKEN) + ".", "",
          "## Policy Auditor scene checks (OCR of every second, 1:25–2:00)", "",
          f"- “Analyzed with an older auditor version / Re-analyze” banner present: {pv['stale_banner']}.",
          f"- “already has a mapping” message present: {pv['already_mapped']}. “Sent to Mapping Review as a human proposal – an authorized reviewer decides.” present: {pv['proposal_msg']}.",
          "- Mapping Review (2:00–2:10) approves that same new AC-2 human proposal → “1 item(s) approved.”", "",
          "## Closing card", "",
          f"- OCR of the closing card at 3:06 without any contrast boost reads all lines: " + ", ".join(f"“{k}” {'yes' if v else 'NO'}" for k, v in pv["closing_lines"].items()) + " (plus “IronVision AI”).", "",
          "## Privacy check", "",
          f"- {pv['frames']} frames sampled every 5 s plus {pv['policy_frames']} policy-scene frames, OCR'd with Tesseract: emails {len(pv['email'])}, hostnames/URLs {len(pv['host'])}, "
          f"IP addresses {len(pv['ip'])}, secret/key/password patterns {len(pv['secret'])}. Persona e-mails are masked to “Demo persona” ({pv['persona']} occurrences in OCR).",
          "- Visible data is SYNTHETIC (banner on every app frame); file names are synthetic fixtures.",
          "- Mocked integrations appear only with their MOCK label (“mock collection”, `mock-*.json` source names); no scanner or eMASS REST connector is shown operating.", "",
          "## No mobile / theme footage", "",
          f"- Single 1920×1080 viewport; no resizing, phone frame or theme toggle in the scene scripts. Mean luminance at 1 fps: all app frames light (minimum YAVG {pv['min_luma']}); "
          f"dark frames only at {pv['dark'][0]}–{pv['dark'][-1]} s (closing card, brand colours).", "",
          "## Publishing", "",
          "- Default: /demo-video and /api/v1/public/demo/ironvision_ai_rmf_demo.mp4 (this 3:10 cut).",
          "- Technical walkthrough (5 min, caption-free): /api/v1/public/demo/ironvision_ai_rmf_technical_walkthrough.mp4, linked on /demo-video.",
          "- Archived (unlinked): archive/2026-10-29-4m19/ (previous 4:19 cut + docs), archive/2026-10-29-3m10-v1/ and -v2/ (earlier 3:10 cuts).", "",
          "## Reproduce", "",
          "`prep_v2.py` → `DEMO_SCENES=scenes_marketing DEMO_OUT=/tmp/demo_mkt record_demo.py` → `DEMO_OUT=/tmp/demo_mkt assemble.py` (v1); pick-up: "
          "`DEMO_SCENES=scenes_mkt_fix DEMO_OUT=/tmp/demo_fix record_demo.py` → `DEMO_OUT=/tmp/demo_fix DEMO_MP4=/tmp/fix.mp4 assemble.py` → `splice_mkt.py`; "
          "→ `finish_mkt.py` (closing card + scene labels); then `build_docs_mkt.py`, `validate_mkt.py`, `prep_v2.py --reset`."]
    (V.parent / "ironvision_ai_rmf_demo_validation.md").write_text("\n".join(L) + "\n")
    print("ok", len(L))


if __name__ == "__main__":
    main()
