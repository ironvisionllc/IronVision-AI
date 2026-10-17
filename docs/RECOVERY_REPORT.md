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
| 13 | Droplet `run`: `aegisrmf-postgres-1/postgres` dump "unreadable" | Reproduced: an empty DB gives a valid archive with **0 TOC entries** (`pg_restore -l` exit 0); the check treated 0 entries as failure. TTY/encoding/connected-DB ruled out (no `-t`, binary file, header OK); version skew was not the cause but is now guarded | Same-major tools (container client or local `postgres:<major>` image), no TTY, direct-to-file, `PGDMP` header + `pg_restore -l` exit + archive versions + sha256; 0 entries only with a catalog proof of no user objects → `maintenance_db`; `pg_dumpall --globals-only --no-role-passwords` mandatory + verified; sessions `default_transaction_read_only=on` |
| 14 | Droplet `run`: legacy backend/migrate/worker → PRODUCTION_DEPENDS_ON_LEGACY | Any shared mount counted as a dependency, incl. read-only repo bind mounts | Evidence-based classification (mount mode/kind, env KEY → host resolution on shared networks, published ports, data volumes); real dependencies unchanged; app containers reported as not a recovery source |
| 15 | Droplet `run`: MinIO bucket listing unavailable | Endpoint guessed as `http://<name>:9000` (no DNS on the default bridge); no diagnosis | Endpoint from inspect (IP + internal port), `*_FILE` secrets, helper image fallback, `objsync probe` (reachable/auth/buckets/counts, short timeouts), `mc` listing fallback; otherwise tarball + "evidence NOT verified" |
| 16 | Local cutover refused on `devsecops@aegisrmf.demo` CONFLICT | Correct refusal: a leftover Keycloak user from another test had that username with a different email | Conflict detection unchanged; test fixture cleans its own leftover test identities. Refinement: demo-sandbox personas (`persona_role`, role switcher only) are skipped before matching; real and self-registered users keep full conflict checks |
| 17 | Droplet `run`: recovery image build failed – `No matching distribution found for emergentintegrations==0.2.2` | `deploy/recovery/Dockerfile` installed `backend/requirements.txt` (preview freeze incl. a package that only exists on Emergent's private index) | Image installs `deploy/recovery/requirements.recovery.txt` (50 pins = subset of `requirements.prod.txt`, generated from the recovery import closure, public PyPI only); build runs `python -m app.tools.selfcheck --recovery`; `scripts/check_requirements.py` guards closure coverage, prod-pin equality, private packages, and that no Dockerfile installs `requirements.txt` or uses a non-PyPI index. Building it in a clean venv found two more gaps that static analysis alone missed – `python-multipart` (FastAPI Form routes) and `regex` (reached through package `__init__`) – both added; the closure now follows parent packages |
| 18 | Droplet: `aegisrmf-minio-recovery` has no IP on any network; 44 objects listed but none exported | Export required S3 over the network | Network-free export: `docker exec -i <ctr> mc cat` per object (never `-t`, stdout straight to file, size checked against the listing, SHA-256 manifest); without `mc`: read-only `docker cp <ctr>:<data dir> -` → xl-single reader in the recovery image; host network → `127.0.0.1:<port>` |
| 19 | 44 listed objects vs 38 evidence records | A bucket listing counts every current key; evidence is only what the `evidence` table references | Rehearsal/apply report `extra` objects, each classified (bootstrap marker, export file, policy upload, temp/multipart, same bytes as an evidence record under another key, unreferenced) – never counted as evidence; evidence = storage-key match **and** SHA-256 match only |
| 20 | Tarball fallback robustness | Reader accepted only xl.meta 1.3 and trusted on-disk version order | xl.meta 1.0–1.3, inline + `part.1`, null versionId, newest object version by MTime, delete marker on top reported (`latest_is_delete_marker`), refusals for erasure-coded / SSE / compressed |
| 21 | Report said "26 missing" in the replica rehearsal | Production-only evidence (demo sandbox) is not in the legacy source but already in the production bucket | Status `present_in_production` when the production bucket holds the key with the same SHA-256 (read-only GET); `missing` now means truly absent |
| 22 | Droplet: `python3 scripts/check_requirements.py` (host python, commit cc1214e) → 252 errors (missing fastapi, sqlalchemy, …; "pyrsistent (required by jsonschema)") | The checker resolved module→distribution and dependency lists through `importlib.metadata` of the RUNNING interpreter – environment-dependent: on the host the app packages are absent, and the host's own Debian `jsonschema` (older, needs `pyrsistent`) was consulted. The pinned `jsonschema==4.26.0` does not need `pyrsistent` (no manifest gap; prod has none either) | Default mode is a STATIC, stdlib-only manifest check (works with `python3 -I -S`) using committed locks generated in clean `--no-deps` venvs: `backend/requirements.prod.lock.json` (78) and `deploy/recovery/requirements.recovery.lock.json` (50) with manifest sha256 freshness, lock == pins, every dependency pinned (full closure), import coverage via the lock's module map. `--in-env --target prod|recovery` runs inside images: `pip check`, installed == pinned == lock, all modules import. `deploy.sh` and `recover.sh run/cutover`: static check on the host → build → in-image check, fail-safe. Completeness proven: `pip install --no-deps` of each manifest + `pip check` pass |

**Remaining limitations.** (1) Recovery image dependencies were validated with a clean public-PyPI venv, `selfcheck --recovery`,
hadolint and `docker compose config` – there is no Docker daemon in the build pod, so `docker build` itself first runs on the
Droplet. (2) xl.meta fixtures follow MinIO's published format; no MinIO binary was available to produce a real RELEASE layout.
(3) `mc cat` export was exercised through a fake `mc` (SeaweedFS stand-in); the real `aegisrmf-minio-recovery` is first read by
`run` on the Droplet (read-only). (4) Each `run` keeps its rehearsal scratch databases and bucket (nothing is deleted
automatically); after acceptance remove them with `sudo ./recover.sh rehearse --cleanup` (latest rehearsal) – check
`df -h /srv` before repeated runs.

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
| Droplet failure cases reproduced in the run: empty `postgres` maintenance DB (verified `maintenance_db`), legacy backend/worker/migrate with shared read-only repo binds (no dependency, evidence listed), MinIO on the default bridge with `*_FILE` secrets (endpoint by IP, reachable + auth) | PASS | `run` stopped at #13 (before the fix) |
| Unit cases: TTY-mangled dump rejected, client/server major mismatch → same-major image or refusal, archive version mismatch rejected, 0-entry dump of a DB with objects rejected, 5 real dependency kinds never downgraded, MinIO without credentials / without helper image / unreachable (mc fallback) / wrong credentials (auth no) | PASS | – |
| Recovery image deps: clean venv (`python -m venv --clear`, `pip install --no-cache-dir --index-url https://pypi.org/simple -r requirements.recovery.txt`), `selfcheck --recovery` 114/114, no Emergent package installed; hadolint clean; `docker compose config` with recovery.yml OK | PASS (venv emulation – no Docker daemon in the pod) | image build not yet re-run |
| Requirements checker: static mode PASS under normal python, `python3 -I -S` and an empty venv; `--no-deps` installs of prod (78) and recovery (50) from public PyPI + `pip check`; `--in-env` PASS for both; workflow on the `--no-deps` recovery venv | PASS | static check to be re-run after pull |
| Full workflow with the recovery venv as the "image": MinIO with **no network** exported via `mc cat` (SeaweedFS stand-in behind the fake `mc`), run → cutover → rollback → failed cutover auto-rollback → cutover → finalize | PASS | not run |
| xl.meta fixtures 1.0–1.3 × inline/part, multi-version out of order, delete marker newest, refusals; extra-object classification | PASS (fixtures built per the published format – no MinIO binary available) | real archive not yet read |
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

## 12. (#23) Build-time selfcheck independent of the environment

**Droplet symptom (commit 8d57828):** `RUN python -m app.tools.selfcheck --recovery` → 76/114, 38 × `DATABASE_URL is not set`.

**Root cause.** `app/db.py` built the SQLAlchemy engine at import time from `get_settings()`, so every module importing
`app.db` required `DATABASE_URL` just to be imported. Local runs passed – even under `env -i` – because `app/config.py` loads
`backend/.env` (present in the build pod, absent from the image). Reproduced exactly (76/114) by running the selfcheck on a
copy of the tree without `.env` in an `env -i` shell.

**Fix.**
- `app/db.py`: engine + sessionmaker created lazily on first use (thread-safe). `SessionLocal()` and `app.db.engine` behave as
  before. A missing `DATABASE_URL` still fails with the same clear message at the first DB use (startup / first request / job).
- `app.main` (the ASGI entrypoint) still resolves settings at import **by design** – importing it *is* service startup and must
  fail fast.
- `app.tools.selfcheck` imports in a **child process** with a scrubbed environment (`PATH`, `HOME`, `LANG` + the documented
  build profile only; nothing is written to an image `ENV`; `IRONVISION_SELFCHECK=1` stops `config.py` loading `backend/.env`)
  and with **all network blocked** (`socket.connect` / `connect_ex` / `create_connection` / `getaddrinfo` raise).
  - Build profile (allowlist): `DATABASE_URL=postgresql+psycopg://selfcheck:selfcheck@selfcheck.invalid:5432/selfcheck`
    (never connected); prod target only, for the `app.main` entrypoint: dummy `JWT_SECRET`, `STORAGE_DRIVER=local`.
  - Every failure fails the build, classified: `missing-module` (package/internal module missing), `import-config` (a required
    setting read at import that the profile does not provide – a NEW required variable therefore surfaces), `import-network`,
    `import-error` (syntax error etc., attributed to the module). Nothing is blanket-suppressed.
- `check_requirements.py --in-env` runs the same selfcheck → same profile.
- Root `.dockerignore` (new; only the recovery image builds from the repo root): `**/.env`, caches. Previously a `backend/.env`
  on a build host would have been copied into the recovery image (secrets + masking exactly this bug).
- Backend/worker Dockerfiles do **not** run the selfcheck at build (deploy.sh / verify_portability.sh run it in the built
  containers); unchanged – they get the scrubbed child automatically. `recover.sh` and `deploy/recovery/Dockerfile` unchanged.

| Check | Where | Result |
|---|---|---|
| Droplet failure reproduced (tree without `.env`, `env -i`) – before fix | pod, clean recovery venv | 76/114 FAIL (same 38 modules) |
| Dockerfile steps emulated: fresh venv, `pip install --no-cache-dir --index-url https://pypi.org/simple -r requirements.recovery.txt`, `.dockerignore`-filtered copy (no `.env`), `env -i … selfcheck --recovery`, `pip check`, `--in-env --target recovery` | pod venv – **simulated, no Docker daemon** | 114/114 PASS, no broken requirements, PASS |
| Prod selfcheck under `env -i` (prod `--no-deps` venv) | pod venv – simulated | 107/107 PASS |
| Negative tests (`tests/test_selfcheck_profile.py`, all `env -i`, pod `.env` copied in and ignored): clean pass ×2 targets; hidden `msgpack` → `missing-module msgpack`; syntax error → module named; internal ImportError; network at import ×2; new required setting ×2 (even when set in `.env`); engine lazy + fail-fast | pod | 10/10 PASS |
| Full workflow (run → cutover → rollback → failed cutover auto-rollback → cutover → finalize), `recover.sh` with a scrubbed env, clean recovery venv | pod, docker shim | PASS (251 s) |
| Full backend suite / shellcheck / hadolint (recovery Dockerfile) / ruff on changed files | pod | 336 passed, 27 skipped / OK / OK / OK |
| Real `docker build` of `deploy/recovery/Dockerfile`, `recover.sh run` | **customer Droplet** | **not run – to be done by the operator** |

Also fixed: `tests/test_route_authz.py` picked any `LTP` system and could land on a sandbox clone under xdist
(pre-existing flake, failed identically without these changes); now scoped to the demo org.

**Production actions:** none.

## 13. Droplet rehearsal failures (commit 9b7b7f7, plan-hash e4c831f4a432b3b4)

Recovery image, static check, selfcheck 114/114, legacy backups and the 0009→0013 migration were fine on the Droplet;
`recover.sh run` correctly stopped because the rehearsal failed. Each failure, its root cause and fix:

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | `/health/live`, `/ready`, `/auth/provider`: *Temporary failure in name resolution* | The probe ran in a separate `docker compose run recovery` container against `http://rehearsal-backend:8001`, so it depended on Docker DNS for a service whose start was never checked. `up -d rehearsal-backend` had no error check, and the 120 s wait loop never failed. `rehearsal-backend` also lacked most of the live backend's environment (`OIDC_REDIRECT_URI`, which `/oidc/login` reads with `os.environ[...]`, plus the demo launcher, FRONTEND/CORS…), because those come from the `x-backend-env` anchor that `recovery.yml` cannot reuse. | `rehearsal-backend` now takes `env_file: ${RECOVER_ENV_FILE}` (the real production env file) plus scratch-only overrides (scratch DB/bucket, `SEED_DEMO_DATA=false`, no worker). It has a healthcheck and is started with `up --wait` (failure ⇒ diagnostic + rehearsal FAIL). The probes run **inside** that container against `http://127.0.0.1:8001`, so no Docker DNS is needed. Before probing, `app.tools.netdiag` records the container, state, networks, resolv.conf and per-name DNS (`rehearsal-backend`, `postgres`, `keycloak`, `seaweedfs`, issuer host) as seen from **both** the recovery container and the rehearsal backend. Output goes to `netdiag-<ts>*.json` and `rehearsal-backend-<ts>.log`, and the report records the resolved URL and networks (`probe_context`). |
| 2 | `e2e_sso.py` exit 1 with no detail | Same unreachable URL; any exception aborted the script with an unsaved traceback. **Also**: Keycloak redirects to the *public* registered callback, which `drive()` would have followed to the **production** backend (an audit write to the production DB). And the probe turned a demo-launcher 403 into `rc=0` (a faked pass). | Full redacted HTTP transcript (`e2e-sso-<ts>.transcript.log`: status, location, JSON bodies, Keycloak page title/feedback/field names; codes, state, tokens, passwords and `client_data` redacted) and full stdout/stderr (`e2e-sso-<ts>.out`) in the report dir, mode 0600. Every exception is a FAILED step with the exact error. `--rehearsal`: the public callback is delivered to the rehearsal backend, and the step "production backend never contacted" asserts it. Separate steps: authorize redirect, login → callback, code exchange, `/auth/me`, protected 200, **authorization denial 403**, logout + Keycloak end-session, demo login (Explore Demo / Option B launcher), role switch, demo access/denial/logout. The faked pass was removed. Instead the rehearsal runs the cutover's Keycloak step against the **scratch** DB: `keycloak-migrate --apply --link`, *without* `--create-identities`, so Keycloak is only read and mappings are written to the throw-away DB. |
| 3 | effective compose audit: `SyntaxError: unexpected character after line continuation character` | Inline `python3 -c '…'` in `recover_audit.sh`: inside bash single quotes `\"` stays a backslash, so the f-string `{s.get(\"image\",…)}` is invalid on the host's python3 3.12 (and 3.11). | Moved to `scripts/compose_audit.py` (stdlib only). New tests: (a) every embedded `python3 -c` and heredoc snippet in `recover.sh`/`scripts/*.sh` is extracted the way bash passes it and compiled with python 3.11 **and** 3.12.15; (b) every `scripts/*.py` and `backend/app/**/*.py` compiles on both; (c) the old snippet reproduces the exact Droplet error on 3.12. (b) caught a real one: a backslash inside an f-string expression in new code, which is valid on 3.12 but a SyntaxError on the image's 3.11. |
| 4 | frontend audit flagged localhost, bit.ly, react.dev, reactrouter.com, redux(-toolkit).js.org | `grep` of every URL in the bundle, no context. | `scripts/frontend_url_audit.py` classifies each hit with file + context. **FAIL**: a localhost/127.x/0.0.0.0/preview/emergent host used as an API base, fetch/axios/WebSocket/EventSource target, redirect or baked env value. **INFO** (allowlist with reasons): React error decoder, React Router / Redux / RTK / Immer doc links, bit.ly short links in vendor warnings, and `http://localhost` used only as a URL-parsing base or `window.location` fallback (React Router `createURL`, axios platform origin). **WARN**: anything else (e.g. Google Fonts). On this repo's production-shaped build (bundle + `deploy/index.html`): 0 FAIL, 4 WARN, 14 INFO. Tests: a planted `baseURL:"http://localhost:8001/api/v1"` FAILs, as do preview hosts and `ws://127.0.0.1`; react.dev/doc strings and the parsing bases pass. |
| 5 | "evidence NOT verified" despite 44 exported objects | That text was the *static* `sources` note ("not verified until the rehearsal…"). The rehearsal had no per-record result to show, and storage keys were matched only exactly or as a `/<key>` suffix. Bucket-prefixed (`evidence/<key>` vs bucket-relative export), `s3://bucket/` URL, leading-`/` and URL-encoded keys were all MISSING, and only the preferred bucket was used when several were exported. Exact Droplet cause not observable from here; the new report shows it per record. | Per evidence record: VERIFIED / MISSING / MISMATCH / UNREADABLE, with source object, how the key was matched (`matched_by`) and the actual SHA on mismatch. Identical bytes found under another key are reported as a key-mapping **hint**, never counted as verified. Every unreferenced object is listed with key, bytes and classification (older version, delete marker, thumbnail/export/policy, `.minio.sys`, same bytes as evidence…). The report gives exact counts (`records`, `verified`, `verified_from_source`, `verified_in_production`, `objects_in_source`, `orphans`). Multiple exported buckets are all given to the rehearsal. **Complete only if every record verifies.** Otherwise `run` prints the exceptions hash, and cutover/apply refuse unless `--accept-evidence-exceptions <hash>` matches exactly. |
| 6 | plan-hash e4c831f4a432b3b4 must not be usable | Apply only checked "passed" + plan hash. | `TOOL_VERSION = 2026.10.17-rehearsal-v2` is part of every plan hash and recorded in every rehearsal. `rehearsal_gate()` refuses: no rehearsal for this hash, other/no tool version, any failure, no passing probe + SSO e2e. `evidence_gate()` refuses incomplete evidence without the exact ack. e4c831f4a432b3b4 (pre-v2, failed rehearsal) is therefore refused on two counts. |

**Superseded by §14.** The rehearsal no longer contacts production Keycloak for SSO, uses no operator probe account, and needs no `RECOVER_E2E_*` input.

**What ran where (no Docker daemon in this pod)**

| Check | Real / simulated |
|---|---|
| python3 3.12.15 (Ubuntu 24.04 host version) + 3.11 compile of every embedded snippet, script and app module; old snippet's SyntaxError reproduced | real interpreters |
| `compose_audit.py` on a compose-config JSON under `python3 -I -S` (stdlib only) | real; `docker compose config` itself not run |
| frontend audit on a real `yarn build` + `deploy/index.html`; planted-URL tests | real build |
| DNS failure: probe + netdiag + SSO e2e from a process where `rehearsal-backend` does not resolve → ConnectError recorded per probe, e2e "aborted: ConnectError", transcript saved, rehearsal FAIL | real resolver; the "container on the wrong network" is simulated by a process without that name |
| `up --wait`, healthcheck, `exec` inside rehearsal-backend, `docker inspect` networks | **not executed** (YAML + shellcheck only) – first real run is on the Droplet |
| full workflow (run → cutover refused without/with wrong ack → cutover → rollback → failed cutover auto-rollback → run → cutover → finalize), Docker **shim** for legacy containers, real pod Postgres/Keycloak 26/SeaweedFS, clean `--no-deps` recovery venv | shim + real services |

**Production actions:** none.

## 14. Rehearsal SSO on an isolated scratch Keycloak (no restored users, no production Keycloak)

**Inspection (report only, no password read):**
- `keycloak-migrate` writes `/srv/ironvision/secrets/*.csv` only with `--create-identities` (cutover) or `rotate`.
- Files are created 0600 with `O_EXCL` in a 0700 directory.
- Columns: `email, keycloak_username, password, temporary`. There is **no role metadata**, so non-admins can only be identified by joining `role_assignments` in the app DB.
- No recovery code reads these files; `recovery.py` only passes `--credentials-dir`.
- The only password-input path was the operator probe account (`RECOVER_E2E_USER` / `RECOVER_E2E_PASSWORD_FILE`). It is **removed**.

**Design:**

| Piece | What it does |
|---|---|
| `deploy/compose/recovery.yml` → `rehearsal-keycloak` | Keycloak **26.8.1** (`REHEARSAL_KEYCLOAK_IMAGE`, default `quay.io/keycloak/keycloak:26.8.1`), `start-dev`, profile `recovery`, project network only, **no `ports:`**, not behind nginx. Hostname `http://rehearsal-keycloak:8080`, so issuer = `http://rehearsal-keycloak:8080/realms/ironvision-demo` for the setup tool, the rehearsal backend and the e2e browser alike. |
| `scratch-sso prepare` | Creates its own DB **and** role `rec_kc_<ts>` (random password, matches the `SCRATCH` regex) on the rehearsal Postgres. Bootstrap admin is random. Secrets go to `RDIR/scratch-sso-<ts>/` (0700 dir, 0600 files), never to `.env.production`. |
| `scratch-sso setup` | Runs the **production `keycloak_config apply`** code against the scratch Keycloak, in a controlled env that inherits no production `KEYCLOAK_*`/`OIDC_*` value. This sets up realm `ironvision-demo`, clients `ironvision-app` and `ironvision-demo-launcher`, and a scratch demo-launcher user. It then creates the `rehearsal-e2e-<hex>@rehearsal.invalid` user, a dedicated scratch org (`rehearsal-sso-<ts>`), and an app user with **only** `leadership_viewer`, mapped by (scratch issuer, sub). The demo launcher is linked in the scratch DB. |
| rehearsal-backend | `OIDC_*`, `KEYCLOAK_*` and demo-launcher values are overridden with scratch values. Configurator/admin secrets are blanked. Issuer, audience, signature, state, nonce and PKCE validation are unchanged. |
| e2e | `--forbid-host <prod OIDC host>,<APP_DOMAIN>` makes every request to a forbidden host fail the run. The wrong-password step is enabled; it counts only as an expected rejection, never as a login. |
| `scratch-sso cleanup-users` / `cleanup-finish` | Run on **every** exit path (trap): delete the scratch Keycloak users, run `compose rm -sf rehearsal-keycloak` (scratch container only), remove the scratch org and user, drop the `rec_kc_<ts>` DB and role, delete the secret files. Each item is recorded in the rehearsal JSON/MD, and an incomplete cleanup is a rehearsal **FAIL**. |
| Restored users | The fingerprint of users, roles and identities (excluding the scratch org, the demo user and sandbox personas) is taken before and after, and must be equal. |
| Production Keycloak | Gets only an **anonymous** discovery + JWKS GET (`prod-oidc-check`), recorded separately. There is no login and no admin API use; the production `keycloak-migrate` dry run was removed from rehearsal, and cutover still runs its own dry run before any change. |

**Real local run (preview pod, real Postgres 16 and a second real Keycloak 26.8.1 process on :8091 standing in for `rehearsal-keycloak`; "production" Keycloak = :8090):** all 20 SSO steps passed:
- **Negative:** wrong password rejected (expected rejection, not a login).
- **Login:** auth code + PKCE → callback → one-time code exchange.
- **Authenticated access:** `/auth/me` and `/systems` both 200.
- **Authorization denial:** `/admin/identity-mappings` → 403.
- **Session handling:** the same session is still valid on a later request.
- **Logout:** the old app session is rejected, Keycloak end-session returns 302, and the same browser must log in again (no silent SSO).
- **Demo:** demo login, role switch → ISSM, protected 200, restricted 403, logout → app token rejected.
- **Isolation:** production Keycloak and the live backend were never contacted (only `:8015` and `:8091`).

Cleanup was complete: Keycloak users deleted, scratch Keycloak stopped, scratch DB and role dropped, secret files deleted, 9 restored users unchanged. No generated secret appears in any report, transcript, JSON or log.

**Orchestration E2E:** `1 passed in 351.67s`. **Not executed here (no Docker daemon):** `rehearsal-keycloak` container start, `--wait` healthcheck and compose network DNS. Compose wiring was validated statically only (YAML parse, no `ports`, profile `recovery`, image 26.8.1, shellcheck of `recover.sh`).

**Droplet command (no user/password inputs):**
```
cd /srv/ironvision/app && git pull && sudo ./recover.sh run
```
**Production actions:** none.
