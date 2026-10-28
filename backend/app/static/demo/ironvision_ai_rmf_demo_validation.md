# IronVision AI – RMF product demo · validation report

Recording date: 28 Oct 2026 · environment: preview deployment, shared **Explore Demo** sandbox tenant (SYNTHETIC data only) · **no AI calls were made during recording.** The Policy Auditor scene shows a stored keyword-only analysis; the AC-2/AC-7 mappings were confirmed beforehand by the ISSO persona in Mapping Review, which runs only the deterministic check at no cost.

Previous version (24 Oct 2026) archived unlinked under `static/demo/archive/2026-10-24/`.

## 1. Technical QA (evidence)

| Check | Result |
|---|---|
| Container / codec | MP4, H.264 High profile, yuv420p |
| Resolution / frame rate | 1920×1080, 30 fps constant |
| Duration | 300.03 s |
| Audio | **No audio stream**: `ffprobe -select_streams a` returns 0 streams; encoded with `-an` |
| Captions | Burned in (silent video) from `ironvision_ai_rmf_captions.srt` (27 blocks, each inside its scene window). The SRT is also published. |
| Size / bitrate | 13,056,551 bytes · ≈348 kb/s |
| Fast start | `moov` atom before `mdat`, so playback starts progressively |
| Metadata | Only `major_brand/minor_version/compatible_brands/encoder=Lavf59.27.100`. No title, author, location, host or e-mail tags. |
| iPhone Safari serving | `GET /api/v1/public/demo/ironvision_ai_rmf_demo.mp4` with `Range: bytes=0-1023` → **206**, `Content-Type: video/mp4`, `Accept-Ranges: bytes`, `Content-Range: bytes 0-1023/13056551`, `Content-Disposition: inline` |

## 2. Content QA
- Scenes: intro → RMF command center and RMF-ordered navigation → Import Center (detect, review, accept conflict-free, apply) → **Manage imported data** (sections, before/imported/now values, "Imported from" chips, Delete everything, Undo) → **Policy Auditor no-silent-misses** (keyword-only "needs manual review" labels, confidence, reading report, Found it here) → scan findings with import markers → authorization package (AO-only) → continuous monitoring, Evidence Ledger, traceability → closing card.
- Data: SYNTHETIC only. The imported file is `SYNTHETIC_LTP_ControlInfo.xlsx` (3 rows). Persona names are fictional. Mock integrations appear with their "mock collection" labels.
- The audit log page is not shown, because it lists client IP details. No secrets, hostnames or test e-mails appear in the frames.
- Cleanup: after recording, the demo import was reverted in full through Manage imported data (audited).
