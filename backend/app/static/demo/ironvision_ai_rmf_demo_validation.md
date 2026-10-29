# IronVision AI – 3:10 product demo · validation report

Recorded 2026-10-29 from the shared SYNTHETIC demo workspace (light desktop theme only). **No AI calls.** The Policy Auditor scene shows the AI-refined rows of a stored AI result for the SYNTHETIC `ac_raven` fixture, copied into the demo workspace (keyword-only leftovers of that older run were not copied, so the result is not flagged stale; AC-2 was left unmapped so “Use this passage” creates a new human proposal). The workspace was re-seeded afterwards.

Revision v2 (2026-10-29): Policy Auditor + Mapping Review (1:25–2:10) and Authorization (2:30–2:50) re-recorded and spliced at the scene boundaries (scripts/demo_video/splice_mkt.py); all other scenes are frame-identical in content to v1 (archive/2026-10-29-3m10-v1/, unlinked).

## ffprobe

```
stream|codec_name=h264|profile=High|codec_type=video|width=1920|height=1080|pix_fmt=yuv420p|level=41|r_frame_rate=30/1|nb_frames=5700
format|duration=190.000000|size=10684324|bit_rate=449866
format|tag:major_brand=isom|tag:minor_version=512|tag:compatible_brands=isomiso2avc1mp41|tag:encoder=Lavf59.27.100
```

- Faststart: moov before mdat = True. No audio stream. No burned-in captions (the SRT is a separate file; /demo-video has no <track>).
- Delivery: HTTP 200 for the full file; HTTP 206 with Content-Range for byte-range requests (iPhone Safari seeking).

## Scene boundaries measured from the video

Method: ffmpeg scene-change score on every frame (`select=gte(scene,0),metadata=print`); per boundary, the frame with the highest score within ±0.5 s.

| Boundary | Next scene | Target | Measured cut | Offset | Scene score |
|---|---|---|---|---|---|
| 1→2 | RMF dashboard & Guided Mode | 8.0 s | 8.000 s | +0.000 s | 0.238 |
| 2→3 | Import Center | 30.0 s | 30.000 s | +0.000 s | 0.104 |
| 3→4 | Import management | 57.0 s | 57.067 s | +0.067 s | 0.077 |
| 4→5 | Control Workbench | 65.0 s | 65.067 s | +0.067 s | 0.105 |
| 5→6 | AI Policy Auditor | 85.0 s | 85.000 s | +0.000 s | 0.129 |
| 6→7 | Mapping Review | 120.0 s | 120.000 s | +0.000 s | 0.1 |
| 7→8 | SCA workspace | 130.0 s | 130.033 s | +0.033 s | 0.053 |
| 8→9 | Authorization & exports | 150.0 s | 150.000 s | +0.000 s | 0.132 |
| 9→10 | Continuous monitoring | 170.0 s | 170.033 s | +0.033 s | 0.105 |
| 10→11 | Closing | 185.0 s | 185.133 s | +0.133 s | 1.0 |

All boundaries within ±0.3 s (largest offset +0.133 s – the closing card fades in).

## Narration fit (ElevenLabs, voice “Matilda”)

Budget ≤ 2.3 words/s per block with ≥ 0.5 s silence; speaking time estimated at 150 wpm (2.5 words/s).

| Block | Scene | Start | End | Window | Words | Words/s | Est. speech | Slack |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 0:00.8 | 0:06.8 | 6.0 s | 9 | 1.5 | 3.6 s | 2.4 s |
| 2 | 2 | 0:08.5 | 0:18.5 | 10.0 s | 21 | 2.1 | 8.4 s | 1.6 s |
| 3 | 2 | 0:19.5 | 0:29.5 | 10.0 s | 17 | 1.7 | 6.8 s | 3.2 s |
| 4 | 3 | 0:30.5 | 0:43.0 | 12.5 s | 24 | 1.92 | 9.6 s | 2.9 s |
| 5 | 3 | 0:44.0 | 0:56.5 | 12.5 s | 24 | 1.92 | 9.6 s | 2.9 s |
| 6 | 4 | 0:57.3 | 1:04.6 | 7.3 s | 12 | 1.64 | 4.8 s | 2.5 s |
| 7 | 5 | 1:05.5 | 1:14.5 | 9.0 s | 16 | 1.78 | 6.4 s | 2.6 s |
| 8 | 5 | 1:15.5 | 1:24.5 | 9.0 s | 17 | 1.89 | 6.8 s | 2.2 s |
| 9 | 6 | 1:25.5 | 1:36.5 | 11.0 s | 22 | 2.0 | 8.8 s | 2.2 s |
| 10 | 6 | 1:37.0 | 1:48.0 | 11.0 s | 23 | 2.09 | 9.2 s | 1.8 s |
| 11 | 6 | 1:48.5 | 1:59.5 | 11.0 s | 23 | 2.09 | 9.2 s | 1.8 s |
| 12 | 7 | 2:00.4 | 2:09.5 | 9.1 s | 14 | 1.54 | 5.6 s | 3.5 s |
| 13 | 8 | 2:10.5 | 2:20.0 | 9.5 s | 12 | 1.26 | 4.8 s | 4.7 s |
| 14 | 8 | 2:21.0 | 2:29.5 | 8.5 s | 16 | 1.88 | 6.4 s | 2.1 s |
| 15 | 9 | 2:30.5 | 2:40.0 | 9.5 s | 13 | 1.37 | 5.2 s | 4.3 s |
| 16 | 9 | 2:41.0 | 2:49.5 | 8.5 s | 13 | 1.53 | 5.2 s | 3.3 s |
| 17 | 10 | 2:50.5 | 3:04.5 | 14.0 s | 18 | 1.29 | 7.2 s | 6.8 s |
| 18 | 11 | 3:05.5 | 3:09.5 | 4.0 s | 6 | 1.5 | 2.4 s | 1.6 s |

Total: 300 words in 18 blocks.

Spoken forms: IronVision AI → “IronVision A-I”; AI → “A-I”; RMF → “R-M-F”; NIST → “nist (one word)”; eMASS → “e-Mass”; SSP → “S-S-P”; SAR → “S-A-R”; RAR → “R-A-R”; OSCAL → “OS-cal”; SCA → “assessor (not spelled out)”; 30-day → “thirty days”; 3:10 → “not spoken”.

## Policy Auditor scene checks (OCR of every second, 1:25–2:00)

- “Analyzed with an older auditor version / Re-analyze” banner present: False.
- “already has a mapping” message present: False. “Sent to Mapping Review as a human proposal – an authorized reviewer decides.” present: True.
- Mapping Review (2:00–2:10) approves that same new AC-2 human proposal → “1 item(s) approved.”

## Privacy check

- 38 frames sampled every 5 s plus 35 policy-scene frames, OCR'd with Tesseract: emails 0, hostnames/URLs 0, IP addresses 0, secret/key/password patterns 0. Persona e-mails are masked to “Demo persona” (7 occurrences in OCR).
- Visible data is SYNTHETIC (banner on every app frame); file names are synthetic fixtures.
- Mocked integrations appear only with their MOCK label (“mock collection”, `mock-*.json` source names); no scanner or eMASS REST connector is shown operating.

## No mobile / theme footage

- Single 1920×1080 viewport; no resizing, phone frame or theme toggle in the scene scripts. Mean luminance at 1 fps: all app frames light (minimum YAVG 153.1); dark frames only at 185–189 s (closing card, brand colours).

## Publishing

- Default: /demo-video and /api/v1/public/demo/ironvision_ai_rmf_demo.mp4 (this 3:10 cut).
- Technical walkthrough (5 min, caption-free): /api/v1/public/demo/ironvision_ai_rmf_technical_walkthrough.mp4, linked on /demo-video.
- Archived (unlinked): archive/2026-10-29-4m19/ (previous 4:19 cut + docs), archive/2026-10-29-3m10-v1/ (first 3:10 cut).

## Reproduce

`prep_v2.py` → `DEMO_SCENES=scenes_marketing DEMO_OUT=/tmp/demo_mkt record_demo.py` → `DEMO_OUT=/tmp/demo_mkt assemble.py` (v1); pick-up: `DEMO_SCENES=scenes_mkt_fix DEMO_OUT=/tmp/demo_fix record_demo.py` → `DEMO_OUT=/tmp/demo_fix DEMO_MP4=/tmp/fix.mp4 assemble.py` → `splice_mkt.py`; then `build_docs_mkt.py`, `validate_mkt.py`, `prep_v2.py --reset`.
