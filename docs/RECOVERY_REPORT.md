# IronVision AI – Recovery & deployment toolkit report

> **Status: built and verified on isolated replicas in the build pod. NOT run on the customer Droplet.** Nothing in this report
> claims the Droplet recovery succeeded – it is unverified until `./recover.sh` runs there and its own report says PASS.
> No production system was touched while building this.

## 1. Situation (customer-provided facts)

| Item | Value |
|---|---|
| Live DB `ironvision` | Alembic 0012, operational tables empty, reference catalogs present (1,196 controls, 5,137 CCIs) |
| Original data | `/root/ironvision-predeploy/aegisrmf-old-db.backup` (restores at 0009: 8 users, 1 org, 4 systems, 25 role assignments, 38 evidence, 111 findings, 1,624 jobs, 1,772 audit events) |
| Rollback backup already taken | `/root/ironvision-predeploy/ironvision-production-before-restore.backup` |
| Objects | `/root/ironvision-predeploy/aegisrmf-minio-backup.tar.gz` (format unknown → auto-detected) |
| Keycloak | separate DB `keycloak`; only the OIDC redirect was proven on the Droplet, full SSO not yet |

## 2. Issues, root causes, fixes

| # | Issue | Root cause | Fix |
|---|---|---|---|
| 1 | Original data missing from the new deployment | New stack deployed on a fresh DB (0012); old data only in a pg_dump at 0009 | `recover.sh`: restore into **new** DB, upgrade 0009→head, merge production-only rows, verify, switch `DATABASE_URL` (old DB kept) |
| 2 | Evidence files not in SeaweedFS | Old MinIO data only in a tarball, not migrated | Archive auto-detect (plain files **or** MinIO `xl-single`: inline msgpack data + `part.1`), SHA-256 checked, copy-only into the live bucket |
| 3 | "Explore the demo" fails with oidc | Demo app user has no explicit `(issuer, sub)` mapping (email linking is forbidden by design) | `scripts/keycloak.sh doctor` names it and prints the exact fix (`migrate` → `--apply --link`) |
| 4 | No clean-workspace accounts | No registration in Keycloak | Demo-only self-registration + JIT sandbox (docs/KEYCLOAK.md §7a) |
| 5 | Restored real data could be purged by sandbox cleanup | Purge only checked inactivity | Migration 0013 `organizations.protected`; restored tenant marked protected; purge hard-refused for protected / non-sandbox / non-persona-role tenants |
| 6 | Catalog equality too strict (found in replica) | The original org had imported STIG content (`stig_rules`, extra `catalog_versions`) | Rule: every production catalog row must exist in the restored DB by natural key (else STOP); backup-only content rows are kept and reported |
| 7 | SSO never proven end-to-end | Only redirect tested | `scripts/e2e_sso.py`: browser-less real OIDC flow (see §6) |
| 8 | `deploy.sh` stops: containers of old project `aegisrmf` running | Hard refusal of any legacy container | `scripts/legacy_project.sh inspect` decides: SAFE_TO_STOP → deploy proceeds (legacy kept running); PORT_CONFLICT / PRODUCTION_DEPENDS_ON_LEGACY → stop with the exact fix |
| 9 | Merge stopped on prod demo-sandbox rows (found in replica) | Prod catalog UUIDs ≠ restored catalog UUIDs for the same natural keys | Catalog FKs of merged prod rows are re-keyed by natural key (unique matches only), counted in the report |
| 10 | First app write after recovery fails (`audit_events` duplicate key) (found in replica) | Merge inserted explicit `seq` values; the sequence did not move | All serial/identity sequences reset to max+1 after the merge |
| 11 | Keycloak refuses some restored users (found in replica) | Keycloak 26 person-name validator rejects `( ) < > & …` in names | Names sanitised for Keycloak only (app display name unchanged); demo-sandbox personas skipped (role switcher, no login) |
| 12 | Backup verification of multi-bucket MinIO export (found in replica) | Manifest stored file name without its bucket dir | Paths relative to the backup dir; every exported object re-hashed against its objsync manifest before any stop |

## 3. Toolkit (`/opt/ironvision/IronVision-AI/recover.sh`)

| Command | What it does | Touches production? |
|---|---|---|
| `preflight` | file readability, `pg_restore -l`, archive listing + layout detection, DB connectivity/revisions, source-vs-prod counts, free space ≥ 3× backups, compose status, Keycloak reachable, SeaweedFS checks (healthy, pinned image, `/srv/ironvision/objectstore`, owner, free ≥ 2× archive, S3 reachable from backend **and** worker, app key scoped to the evidence bucket, separate admin key, versioning, count/bytes manifest, no public port), config-chain audit; prints PLAN + **plan-hash** | no (read-only) |
| `rehearse [--cleanup] [--e2e]` | `rec_src_<ts>`, `rec_prod_<ts>`, `rec_target_<ts>`, bucket `evidence-rehearsal-<ts>`; full recovery + verify there; private rehearsal backend on `127.0.0.1:8012` probed; SeaweedFS restart check; report `/root/ironvision-recovery/report-<ts>.md/.json`. Scratch kept unless `--cleanup` (drops **only** `rec_*` DBs and the rehearsal bucket) | no |
| `apply --plan-hash H` | refuses unless a **passing** rehearsal with the same hash is < 24 h old; fresh backups (prod DB, Keycloak DB, bucket SHA-256 manifest, env, SeaweedFS data dir incl. filer metadata – any failure = refuse); builds `ironvision_recovered_<ts>`; copy-only objects (recovery-added manifest); switches `DATABASE_URL` in place (env backup); redeploys; verifies | yes – only after explicit hash approval; old DB untouched |
| `verify` | DB evidence keys ↔ object hashes, integrity job, upload/download round trip, audit chain, FK orphans, counts, SeaweedFS restart persistence | read-only except integrity job + round-trip probe object |
| `rollback [--remove-recovered-objects] [--restore-db-from F]` | restores the pre-switch env (old `ironvision` DB), redeploys, verifies. Objects kept by default; removal deletes **only** recovery-added keys whose bytes still match. `--restore-db-from` restores only into a **new** DB name | yes (env switch back) |
| `status` / `audit` | latest plan/rehearsal/apply outcome / config-chain audit | no |
| `link --plan-hash H` | wraps `keycloak-migrate --apply --create-identities --link` (backup + reviewed plan hash required; credentials in a 600 CSV) | Keycloak + `auth_identities` only |

Everything is logged (secrets redacted) under `/root/ironvision-recovery/` (mode 700). No `down -v`, no destructive
migration, no `.env.production` overwrite (in-place key edits with backups), `ALLOW_INSECURE_PRODUCTION` never set.

**Data rules:** original user IDs, org and roles preserved; production-only rows merged with conflict detection (same e-mail with
a different ID → STOP, nothing merged); FK integrity checked on all FKs; audit hash chain re-verified after migration; recovery
appends one `recovery.restored` audit event; restored tenant marked protected; no e-mail identity linking – the Keycloak migration
is only a **dry run** in the report and is applied via `recover.sh link`.

## 4. SeaweedFS

| Item | Replica result (pod, SeaweedFS 4.48) | On the Droplet |
|---|---|---|
| Endpoint / bucket / addressing | `http://seaweedfs:8333`, bucket `evidence`, path-style | reported by preflight |
| Versioning | Unversioned (reported, not required) | reported |
| Keys | app key list/put/get/delete in `evidence` ok; cannot create/use other buckets; admin key separate | checked |
| Archive layout | MinIO `xl-single`, 32 inline + 5 `part.1` objects | auto-detected |
| Evidence rows | 38 | 38 expected |
| Recovered / missing / hash mismatch | **36 / 1 / 1** (fixtures deliberately contain one missing and one corrupt object) | reported per key |
| Copy semantics | added 35; 1 already present with identical bytes kept; unrelated live object untouched; conflicting existing bytes are never overwritten | same code |
| Second apply (idempotency) | added 0, identical 36 | — |
| Integrity job after apply | checked 38, ok 36, mismatched 2 (the known two) | reported |
| Restart test | `restart seaweedfs` → all 36 objects intact, hashes equal | `rehearse` + `verify` run it; **reboot test** = run `./recover.sh verify` after `sudo reboot` |
| Rollback removal | removes only recovery-added keys; 2 pre-existing keys left | same |

Not supported (refused with a clear message): erasure-coded multi-drive MinIO, SSE-encrypted, compressed objects. The MinIO
binary could not be downloaded in the pod (HTTP 410), so the `xl.meta` fixtures were built from the documented format
(`XL2 ` header, msgpack versions, inline data / `part.1`); if the real archive differs, preflight stops with the reason.
Note: production compose already runs weed with `-volume.max=0` (auto); a fixed small `-volume.max` would make new buckets fail.

## 5. Replica lifecycle results (`tests/test_recovery_e2e.py`, live PostgreSQL 16 + SeaweedFS 4.48 + Keycloak 26.8.1)

Replicas: source at 0009 with exactly the customer counts above; prod at 0012 with catalogs only (+1 admin user/org/role).

| Step | Result |
|---|---|
| preflight (read-only) incl. SeaweedFS checks, plan-hash | PASS |
| app key scoped to evidence bucket | PASS |
| rehearse: isolated scratch DBs + bucket, no failures | PASS |
| objects 36 recovered, 1 missing, 1 mismatch (inline + part.1) | PASS |
| row-count reconciliation – every delta explained | PASS |
| restored shape: users 9, orgs 2 (8+1 / 1+1 production-only), jobs 1,624, audit 1,773 | PASS |
| audit chain valid after 0009→0013 (1,773 events) | PASS |
| FK integrity: 90 FKs, no orphans | PASS |
| Keycloak migration dry-run in report, not applied | PASS |
| rehearsal backend probe (live/ready/provider 200) | PASS |
| apply refuses wrong plan-hash | PASS |
| apply: fresh backups (prod, keycloak, bucket manifest) + new recovered DB | PASS |
| copy-only (identical kept, unrelated untouched) | PASS |
| live production DB untouched by apply | PASS |
| verify on recovered DB (objects, chain, FK, integrity job, round-trip) | PASS |
| restored tenant protected: purge hard-refused | PASS |
| rollback `--remove-recovered-objects` removes only recovery-added keys | PASS |
| verify after rollback (original DB, redeployed) | PASS |
| plan-hash changes after rollback (stale approval unusable) | PASS |
| re-rehearse, re-probe, re-apply after rollback | PASS |
| `--cleanup` drops only `rec_*` DBs + rehearsal bucket | PASS |
| idempotent second apply adds nothing | PASS |
| SeaweedFS restart: objects intact | PASS |
| merge conflict (same e-mail, different ID) → STOP, nothing merged | PASS |

Reconciliation (source → production → recovered): users 8 → 1 → 9, organizations 1 → 1 → 2, role_assignments 25 → 1 → 26,
systems 4/0/4, evidence 38/0/38, findings 111/0/111, jobs 1,624/0/1,624, audit_events 1,772 → 0 → 1,773 (+1 `recovery.restored`),
controls 1,196 = 1,196, CCIs 5,137 = 5,137, baselines 4, baseline_controls 423, catalog_versions 6 prod ⊆ 9 restored
(+3 org-imported STIG benchmarks), stig_rules 0 → 53 (org-imported).

## 6. End-to-end SSO (`scripts/e2e_sso.py`, real Keycloak 26.8.1, no browser)

| Check | Result |
|---|---|
| provider oidc, launcher + registration enabled | PASS |
| self-registration → clean workspace (0 systems) | PASS |
| duplicate e-mail of an existing account refused | PASS |
| reserved `demo@ironvision.ai` refused | PASS |
| wrong password rejected by Keycloak | PASS |
| login → callback → one-time code exchange; `/auth/me` | PASS |
| protected `/api/v1/systems` 200; restricted `/api/v1/admin/identity-mappings` 403 | PASS |
| logout: app token rejected; Keycloak end-session accepted | PASS |
| demo launcher login 200 (after the doctor's printed fix); role switch → ISSM 200 | PASS |

On the Droplet: `python3 scripts/e2e_sso.py --base https://demo.ironvisionai.com --register --demo` (self-registers its own
throw-away probe user; purge removes it) – or `E2E_USER`/`E2E_PASSWORD` for an existing account.

## 7. Config-chain audit (`./recover.sh audit`, read-only, redacted)

DNS A records for `demo.` and `auth.demo.`; TLS (validity, SAN, expiry, chain) for both; nginx effective config (server names,
upstreams, forwarded headers, `/admin` + master realm blocked, registration rate limit); API URL baked into the frontend bundle
(flags preview/localhost URLs); edge routes (`/api/v1/ready`, discovery); Docker networks and who shares them; effective
`docker compose config` (images, DB, storage, domains, ports – env values redacted); Keycloak realm/client redirect, web
origins, post-logout, secret equality (compared, never printed), PKCE S256, discovery issuer, container → public issuer
reachability (hairpin), session/cookie settings; demo vs customer-production separation (deployment kind, realms, DBs, buckets,
client IDs differ; sign-up disabled for customer production).

## 8. Exact Droplet commands

```bash
cd /opt/ironvision/IronVision-AI && git pull && ./deploy.sh --apply-demo-settings --yes   # pins SEAWEEDFS_IMAGE by digest; legacy containers kept
sudo ./recover.sh run                          # READ-ONLY: legacy inspect + verified backups + preflight + rehearsal + SSO probe → report + PLAN-HASH
sudo ./recover.sh cutover --plan-hash <PLAN-HASH>   # apply → switch → deploy → Keycloak link → verify + live SSO + doctor; failure → auto rollback
sudo reboot && sudo ./recover.sh finalize      # optional: reboot persistence check, then graceful stop of the legacy containers
```
If `./deploy.sh` reports PORT_CONFLICT: `sudo ./recover.sh resolve-conflict` (verified legacy backup first, then stops only that
container; recovery then uses that backup / the backup files as its source). Building blocks (`preflight`, `rehearse`, `apply`,
`verify`, `link`, `status`, `audit`) still work individually.

**What `run` uses as sources** (written to `/root/ironvision-recovery/sources.env`, reused unchanged by `cutover`):
the running legacy Postgres DB `aegisrmf` (read-only `pg_dump` snapshot) **if its key counts match the stated facts**, else any
legacy DB that matches (e.g. `aegisrmf_backup_test`), else `aegisrmf-old-db.backup`; objects from the read-only objsync export of
the running legacy MinIO (bucket `evidence` preferred), else the tarball. Every legacy DB's counts are compared with the stated
facts (8/1/4/25/38/111/1,624/1,772) and discrepancies are listed in the report. After `run`, recovery no longer needs the legacy
containers – everything is a verified snapshot.

**Read-only guarantee of `run`:** production DB, live bucket and Keycloak users are never written (backups are `pg_dump` /
listing / `cp`); the rehearsal SSO probe uses the server-side demo launcher only (a Keycloak session, no new user) against the
private rehearsal backend and a scratch DB; self-registration (which creates a Keycloak user) runs only in `cutover`; the
SeaweedFS restart check runs only in `cutover`.

### Rollback
```bash
sudo ./recover.sh rollback                              # env back to the original `ironvision` DB, redeploy, verify
sudo ./recover.sh rollback --remove-recovered-objects   # additionally delete only the recovery-added objects
```
The recovered DB, the original DB and all backups stay on disk. The Keycloak migration (`link`) is rolled back per
docs/KEYCLOAK.md §10 (env restore; mappings are inert without oidc).

## 9. Image pinning

| Image | Pinned by digest in templates | Preflight check |
|---|---|---|
| SeaweedFS `chrislusf/seaweedfs:4.48@sha256:4e61d15f…7872d` (manifest list, read from the Docker Hub registry API) | yes | running container `RepoDigests`/image ID vs pin (manifest-list or platform digest accepted); mismatch → `docker compose pull seaweedfs && docker compose up -d seaweedfs` |
| Postgres `postgres:16-alpine`, nginx `nginx:1.27-alpine`, certbot `certbot/certbot:v2.11.0`, Keycloak base `quay.io/keycloak/keycloak:26.8.1` | yes (`*_IMAGE=…@sha256:…`) | `check_env`: tag-only = warning (demo) / error (customer-production) |
| Local helper `ironvision/recovery:local`, built `ironvision/keycloak:26.8.1` | built locally from the pinned bases, run with `--pull never` | – |

## 10. Validated locally vs. on the Droplet

| Step | Local replica (build pod) | Customer Droplet |
|---|---|---|
| `legacy_project.sh inspect` verdicts (safe / port conflict / dependency), preserve-and-stop backups + refusal paths | PASS (docker shim, real PostgreSQL) | not run |
| `recover.sh run` ×3: legacy `aegisrmf` DB preferred (matches 8/1/4/25/38/111/1,624/1,772), legacy MinIO export used (SeaweedFS **stand-in** for MinIO), rehearsal + SSO probe, production DB/bucket/Keycloak users unchanged, legacy left running | PASS | not run |
| `cutover`: wrong plan-hash refused; apply → switch → deploy → Keycloak link → verify + live SSO + doctor + SeaweedFS restart | PASS | not run |
| `cutover` with a failing live check → automatic rollback | PASS | not run |
| `rollback`, then re-`run` + re-`cutover` | PASS | not run |
| `finalize` (reminder without reboot; graceful stop; nothing removed) | PASS | not run |
| Docker never asked to rm / down / volume / prune / `-v` | PASS (every call recorded) | – |

**The recovery on the customer Droplet has not been performed and is not claimed as successful.** The legacy
MinIO in the local runs is SeaweedFS acting as an S3 stand-in; the real `aegisrmf-minio-recovery` is exercised
for the first time by `run` on the Droplet (read-only).

## 11. Production actions performed while building this

None. No connection to the customer Droplet, no deployment, no data change anywhere outside the build pod's scratch replicas.
