# Performance smoke test

Run 2026-10-11T03:20:51+00:00 against `http://localhost:8001` (single uvicorn process + 1 worker, preview pod; not a capacity benchmark).

## Ingest
Synthetic `.nessus`: **200 hosts × 25 = 5000 findings** (1.7 MB) → status **completed** in **13.5 s** (upload + worker parse/normalize/dedup/map/evaluate). {}

## Read endpoints (40 requests each, concurrency 8)
| Endpoint | p50 ms | p95 ms | max ms | errors |
|---|---|---|---|---|
| `/systems/f9b415b6-2b14-4d21-b770-e1b49d8a7b53/workbench/controls?page=1` | 136 | 193 | 207 | 0 |
| `/poams?system_id=f9b415b6-2b14-4d21-b770-e1b49d8a7b53` | 193 | 241 | 245 | 0 |
| `/systems/f9b415b6-2b14-4d21-b770-e1b49d8a7b53/workbench/summary` | 108 | 172 | 210 | 0 |
| `/systems/f9b415b6-2b14-4d21-b770-e1b49d8a7b53/rmf-workflow` | 203 | 258 | 263 | 0 |
| `/search?q=ac-2&system_id=f9b415b6-2b14-4d21-b770-e1b49d8a7b53` | 86 | 127 | 128 | 0 |
| `/dashboard/leadership` | 274 | 302 | 328 | 0 |

## Before / after indexes (migration 0009)
Baseline before 0009 (same script, same pod): ingest of 5,000 findings **17.7 s**. Workbench summary p95 199 ms, RMF workflow p95 259 ms, search p95 131 ms.
After 0009: ingest **13.5 s** (−24 %). Read p95 values are in the table above. Read latencies are about the same, since they were already dominated by Python serialization. Single process, preview pod, noisy neighbours: treat these as smoke numbers, not capacity figures.
Re-run with `make perf`. The script uses the ISSO account for upload (needs `ingest.upload`) and leadership.viewer for `/dashboard/leadership`.
