# Performance smoke test

Run 2026-10-11T04:48:36+00:00 against `http://localhost:8001` (single uvicorn process + 1 worker, preview pod; not a capacity benchmark).

## Ingest
Synthetic `.nessus`: **200 hosts × 25 = 5000 findings** (1.7 MB) → status **completed** in **15.2 s** (upload + worker parse/normalize/dedup/map/evaluate). {}

## Read endpoints (40 requests each, concurrency 8)
| Endpoint | p50 ms | p95 ms | max ms | errors |
|---|---|---|---|---|
| `/systems/dc42149b-0032-4f12-954c-80f5069fc00d/workbench/controls?page=1` | 145 | 185 | 195 | 0 |
| `/poams?system_id=dc42149b-0032-4f12-954c-80f5069fc00d` | 194 | 250 | 253 | 0 |
| `/systems/dc42149b-0032-4f12-954c-80f5069fc00d/workbench/summary` | 106 | 180 | 199 | 0 |
| `/systems/dc42149b-0032-4f12-954c-80f5069fc00d/rmf-workflow` | 188 | 322 | 327 | 0 |
| `/search?q=ac-2&system_id=dc42149b-0032-4f12-954c-80f5069fc00d` | 86 | 159 | 172 | 0 |
| `/dashboard/leadership` | 275 | 325 | 357 | 0 |
