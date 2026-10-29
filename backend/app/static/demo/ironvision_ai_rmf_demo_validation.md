# IronVision AI – RMF product demo · validation report

Recording date: 2026-10-28 (re-recorded after review). Source: shared SYNTHETIC demo workspace on the preview host. **No AI calls were made.**

## File

| Property | Value |
|---|---|
| File | ironvision_ai_rmf_demo.mp4 (served at /demo-video) |
| Duration | 259.267 s (7,778 frames) |
| Video | H.264 High, 1920×1080, 30 fps, yuv420p, faststart (moov before mdat) |
| Audio | none (silent) |
| Captions | none burned in (clean video, re-encoded 2026-10-29 at user request); separate ironvision_ai_rmf_captions.srt kept, not auto-displayed (no &lt;track&gt; on /demo-video) |
| Size | 12,428,018 bytes (~383 kbit/s) |
| Container tags | major_brand isom, encoder Lavf only – no title/author/location/host metadata |
| Delivery | HTTP 206 byte ranges, Content-Type video/mp4 (iPhone Safari compatible) |

## Storyline (scene starts measured from the recorder)

| # | Scene | Start |
|---|---|---|
| 1 | Intro, Explore-the-demo sign-in, ISSO persona | 0:00 |
| 2 | System dashboard + the 7 RMF steps, Guided Mode on/off | 0:14 |
| 3 | Import Center: detect → review → accept safe → apply | 0:39.5 |
| 4 | Manage imported data: sections, delete everything → 30-day Undo | 1:02 |
| 5 | Control Workbench (AC-2): Attach evidence → upload → “Completed – next” | 1:24 |
| 6 | Policy Auditor: stored AI analysis – met rows with verified quotes, candidate passages, reading report, Found it here | 1:52 |
| 7 | Mapping Review queue | 2:28 |
| 8 | SCA workspace: human determination → “Saved – moved to next control” → Undo | 2:44 |
| 9 | Authorize package (SSP/SAR/RAR, OSCAL, eMASS Implementation Plan) + TR export mode/history | 3:14 |
| 10 | Continuous monitoring + traceability | 3:46 |
| 11 | Closing card (0.5 s crossfade from traceability) | 4:03.5 |

## Data and privacy

- All content is SYNTHETIC. Persona e-mail addresses are masked to “Demo persona” in every frame by an init script in the recorder (verified on /my-work, /import-center, /audit-log, /systems: 0 addresses remain).
- Policy Auditor scene: an existing stored AI result for the SYNTHETIC `ac_raven` fixture was copied into the demo workspace (no new model call); its reading-report extraction stats were computed from the same fixture file.
- Demo-only preparation (prep_v2.py): copied policy result; blank eMASS TR template uploaded, rows generated deterministically and exported once.
- After recording and screenshots the shared demo was re-seeded (same as the nightly reset), removing the import, the attached evidence, the SCA determination, the copied policy and the TR workbook.

## Reproduce

`python3 scripts/demo_video/prep_v2.py` → `record_demo.py` → `build_docs.py` → `assemble.py` → `prep_v2.py --reset`

## Revision 2026-10-29

- Bottom caption bar removed; scenes, timing and on-screen cards (intro, closing) unchanged. Re-recorded with the same script (the raw frames had been lost in a pod restart), then the shared demo was re-seeded.
- Captioned version archived (unlinked): archive/2026-10-28-captioned/ironvision_ai_rmf_demo.mp4.
- Verified: ffprobe (300.000 s, 9,000 frames, H.264 High 1920×1080, 30 fps, yuv420p, moov before mdat, no audio); 5 sampled frames (0:20, 1:15, 2:10, 3:20, 4:10) show no caption text; HTTP 200 + 206 byte ranges.

## Revision 2026-10-29 (b)

- Removed the light ↔ dark switch and the phone-width segment (recorder 4:04.0–4:44.2) by cutting the caption-free 300 s file with ffmpeg (scripts/demo_video/cut_segments.py) – no re-recording, every other frame identical in content; 0.5 s crossfade from the last traceability frame into the closing card.
- Archived (unlinked): archive/2026-10-29-with-phone/ (full 300 s caption-free) and archive/2026-10-29-no-phone-with-themes/ (interim cut).
- Verified: ffprobe 259.267 s, 7,778 frames, H.264 High 1920×1080, 30 fps, yuv420p, moov before mdat, no audio; 22 sampled frames (0:10–4:19, incl. 4:03.0–4:04.3 around the cut) show only light-mode desktop screens and the closing card – no theme switch, no phone frame; HTTP 200 + 206.
- SRT, narration, teleprompter and scene timeline regenerated for the new timing (20 blocks, closing 4:04–4:19.2).
