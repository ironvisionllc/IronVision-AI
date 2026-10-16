# IronVision AI on a DigitalOcean Droplet

> **Status: documentation only – not yet executed on DigitalOcean.**
> Every DigitalOcean step below is marked *Not yet executed on DigitalOcean*. The operator records the real outcome in the [validation checklist](#13-operator-validation-checklist). Nothing in this guide has been tested on a Droplet. The code has no DigitalOcean-specific dependency; `doctl` is optional and only used in examples.

Target: an IronVision-controlled **Ubuntu 24.04 LTS Droplet** running Docker Compose with PostgreSQL 16, SeaweedFS (S3-compatible object store), the FastAPI backend, the worker, the React frontend (nginx) and a TLS edge nginx.
Files: `deploy/digitalocean/` (compose overlays, nginx templates, env templates, systemd units, backup script, Docker log config), `scripts/check_env.py`, `scripts/verify_no_preview_deps.sh`, `backend/app/cli.py` (`create-admin`).

```
Internet ─▶ DO Cloud Firewall (80/443, 22 from admin IPs) ─▶ ufw ─▶ edge nginx :80/:443 (Let's Encrypt)
                                                              ├─▶ frontend nginx :8080 (SPA, CSP)
                                                              └─▶ backend :8001 (/api) ─▶ postgres :5432 (127.0.0.1 only)
                                                                  worker ────────────────▶ seaweedfs S3 :8333 (internal network only; master UI 127.0.0.1:9333)
Block Storage: /srv/ironvision/{postgres,objectstore,letsencrypt,certbot} and /srv/ironvision/backups
```

---

## 0. MinIO removal (read first if a deployment failed pulling `minio/minio`)

MinIO discontinued its community edition. `minio/minio` and `minio/mc` are no longer publicly pullable from Docker Hub, quay.io/minio or registry.min.io, so any deployment that references them fails at `docker compose pull/up`. The stack no longer uses any MinIO image or the `mc` client:
- **Object store:** SeaweedFS `chrislusf/seaweedfs:4.48`. The tag was verified on Docker Hub: pushed 2026-09-28, multi-arch amd64/arm64/arm, and the registry manifest returned HTTP 200. Profile `seaweedfs`, single container, internal network only.
- **Bucket bootstrap:** the one-shot `objectstore-init` service runs **our backend image** (`python -m app.tools.s3_bootstrap`). It creates the bucket if missing, enables versioning if supported, applies an optional bucket policy, and checks a put/get/delete round-trip with SHA-256. It is idempotent.
- **Backup/restore/off-site/migration:** `python -m app.tools.objsync` (inside the backend image) copies objects between directories and any S3 endpoint and verifies each one with SHA-256.
- **Renamed variables:** `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` → `S3_ADMIN_ACCESS_KEY_ID`/`S3_ADMIN_SECRET_ACCESS_KEY`. The old names are still read as a fallback and `check_env` warns. The app identity is `S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`, which **must differ** from the admin key.

### Quick deploy (one command on the Droplet)
Push the repo to GitHub once. Then, on the Droplet, from the repository directory (e.g. `/opt/ironvision/IronVision-AI`):
```bash
cd /opt/ironvision/IronVision-AI
mv deploy.sh deploy.sh.old 2>/dev/null || true    # an old hand-made, untracked deploy.sh would block the pull
git pull
./deploy.sh --apply-demo-settings --yes           # demo.ironvisionai.com values into the EXISTING env file, then deploy
./deploy.sh                                       # later deploys; optional: --no-cache, --force-tls, --no-systemd
```
**`--apply-demo-settings`** (demo deployment only) rewrites only these non-secret keys in `deploy/digitalocean/.env.production`,
in place: `APP_DOMAIN=demo.ironvisionai.com`, `FRONTEND_URL`/`CORS_ORIGINS=https://demo.ironvisionai.com`,
`LETSENCRYPT_EMAIL=k.hill@theironvision.com`, `OIDC_REDIRECT_URI=…/api/v1/auth/oidc/callback`, `AUTH_DOMAIN=auth.demo.ironvisionai.com`,
`OIDC_ISSUER=https://auth.demo.ironvisionai.com/realms/ironvision-demo`, `OIDC_POST_LOGOUT_REDIRECT_URI=…/login`,
`OIDC_CLIENT_ID=ironvision-app`, `ALLOW_DEMO_LOGIN=true`, `KEYCLOAK_ALLOW_REGISTRATION=true`, `DEPLOYMENT_KIND=demo`,
`ALLOW_SIGNUP=false`, `SEED_DEMO_DATA=false`, `APP_ENV=production`, `OPENROUTER_SITE_URL=https://demo.ironvisionai.com`.
- Without `--yes` it is a dry run: it prints the before/after diff of those keys and exits (nothing written, nothing deployed).
- With `--yes`: backup `.env.production.bak-<ts>` (mode 600), in-place rewrite (mode 600), the file is never sourced, secrets are
  neither changed nor printed; then the normal deploy below runs (`gen_env_secrets` fills new empty secrets such as
  `KEYCLOAK_BACKEND_CLIENT_SECRET`).
- Before writing `OIDC_CLIENT_ID` it asks the live Keycloak (discovery + a PKCE authorization request). If Keycloak answers
  "Client not found" (or is unreachable), `OIDC_CLIENT_ID` is **not** changed, exit code 3, the realm's clients are listed
  (`scripts/keycloak.sh … clients`, admin API) and the fix is printed: `./deploy.sh --apply-realm`, then re-run.
- Standalone: `python3 scripts/apply_demo_settings.py deploy/digitalocean/.env.production [--dry-run|--yes]`.
- `deploy/digitalocean/env.production.template` (= `.env.production.example`) is the **demo** template and ships these values;
  customer production uses `env.customer-production.template` (placeholders, sign-up/demo/registration off).

First install / domain change on a fresh Droplet: `./deploy.sh --set-domain demo.ironvisionai.com --email k.hill@theironvision.com`.
The repo-root `./deploy.sh` replaces any hand-made wrapper. What it does:
- **No env file yet:** it creates `deploy/digitalocean/.env.production` from `env.production.template` (mode 600) and generates every secret. It then **stops** (exit 2) and lists the values you must set: `APP_DOMAIN`, `FRONTEND_URL`, `CORS_ORIGINS`, `OIDC_*` when OIDC is enabled, and `OPENAI_COMPAT_API_KEY` + `AI_MODEL` when AI is enabled. Edit the file and run `./deploy.sh` again.
- **Env file exists:**
  1. runs `check_env.py --fix`, which writes a backup first and quotes values such as `OIDC_SCOPES=openid email profile`;
  2. runs `gen_env_secrets.py`, which fills only empty secrets;
  3. refuses to continue while values are empty or still `example.gov` placeholders;
  4. requires `check_env.py` to PASS;
  5. runs `scripts/deploy.sh` (fail-fast, ends with `Ready: https://<APP_DOMAIN>`).
- It refuses to run if the env file is tracked by git. It never sources the file; it reads values with `scripts/envget.py`.
- The real env file exists only on the Droplet. It is git-ignored and must never be committed.

**Always deploy with `scripts/deploy.sh`.** It is the one supported deploy command and it stops at the first failure with a non-zero exit. It prints `#### DEPLOYMENT FAILED at step "<step>"` plus a hint, and `#### DEPLOYMENT SUCCEEDED` only after `/api/v1/ready` answers. In order, it:
1. runs `check_env`;
2. always uses `docker compose -p ironvision --env-file <file> -f docker-compose.yml -f docker-compose.prod.yml -f deploy/digitalocean/docker-compose.do.yml` plus the storage overlays (`deploy/compose/storage-s3.yml`, and `storage-seaweedfs.yml` for the built-in store);
3. takes `COMPOSE_PROFILES` from the env file;
4. inspects containers of the old `aegisrmf` project (`scripts/legacy_project.sh inspect`): **SAFE_TO_STOP** (no dependency,
   no port conflict) → continues automatically, the legacy containers are **retained for recovery** (warning printed);
   **PORT_CONFLICT** → stops with `sudo ./recover.sh resolve-conflict`; **PRODUCTION_DEPENDS_ON_LEGACY** or an unknown state →
   stops (fail-safe) with `sudo ./recover.sh run`. deploy.sh never stops or removes legacy containers itself;
5. creates the `${DATA_ROOT}` directories with the right owners, whether run as root or as `ironvision`;
6. runs `config -q` → pull → build → postgres → seaweedfs → `objectstore-init` → migrate → app → readiness check → summary.

`scripts/deploy.sh deploy/digitalocean/.env.staging --staging` deploys staging. `--skip-edge-check` skips the TLS step and the public HTTPS check (rarely needed now – the certificate is obtained automatically, §4). Any wrapper script must not print "Deployment complete" when a step fails: call `deploy.sh` and check its exit code. **The "Cleaning unused images / Deployment complete" wrapper is not part of this repository.**

### 0.0 Troubleshooting: `containers of the old compose project 'aegisrmf' are still running`
That hard stop is gone. `aegisrmf-postgres-1` (old AegisRMF DB, possibly `aegisrmf_backup_test` / an early `ironvision` DB) and
`aegisrmf-minio-recovery` are **kept on purpose** – they are recovery sources. What happens now:
```bash
scripts/legacy_project.sh inspect aegisrmf     # read-only: image, ports, mounts, networks, env (redacted), DBs + sizes + alembic
                                               # revision + key counts, MinIO buckets + object counts, verdict per container
./deploy.sh                                    # SAFE_TO_STOP → continues, legacy containers keep running (warning)
sudo ./recover.sh resolve-conflict             # only if deploy.sh reports PORT_CONFLICT: verified backup, then `docker stop`
                                               # of ONLY the conflicting container (restart command printed)
sudo ./recover.sh finalize                     # after a successful cutover: graceful `docker stop` of the legacy containers
```
Never `docker rm`, `down` or `-v`: volumes stay; `docker start <names>` (printed and stored in the backup manifest) restores them.
`scripts/legacy_project.sh preserve-and-stop aegisrmf --yes` does backup + stop in one step (refused if the live stack depends on
a legacy container). Backups: `/root/ironvision-predeploy/legacy-<ts>/` (pg_dump -Fc per DB, `pg_dumpall --globals-only
--no-role-passwords`, objsync export of every MinIO bucket under `objects/` with a SHA-256 manifest, `docker inspect` records).

**`run` stopped with `backup of aegisrmf-postgres-1/postgres is unreadable (pg_restore -l)`** (fixed). The `postgres`
maintenance DB is empty; its valid archive lists 0 TOC entries and the old check treated "0 entries" as unreadable. Now every
dump is made with the **same major version** as the server (the container's own `pg_dump`, else a local `postgres:<major>-alpine`
image with `--pull never` – if missing: `docker pull postgres:<major>-alpine`), never through a TTY, written straight to a file,
and verified: `PGDMP` header, `pg_restore -l` exit 0, archive "dumped from/by" versions = server major, sha256. A 0-entry dump is
accepted only after a catalog query proves the DB has no user schemas/tables/large objects/functions/extensions; it is kept and
recorded as `maintenance_db` ("verified, empty maintenance DB, no application data"). Every legacy session runs with
`default_transaction_read_only=on`.

**Verdict `PRODUCTION_DEPENDS_ON_LEGACY` for the legacy backend/migrate/worker** (fixed). `inspect` now lists every piece of
evidence (container, mount source → target + rw/ro, env KEY names only, network) and why it is or is not a dependency. Not a
dependency: shared read-only repo bind mounts (docs, samples, content), a shared network nobody references. Dependency (never
downgraded): a live `*_URL`/`*_HOST`/`*_ENDPOINT` setting that names a legacy container/IP, resolves to it on a shared network,
or reaches its published port; shared writable named volumes / DB or object data dirs; unclassified shared writable bind mounts
(fail-safe). Legacy backend/migrate/worker are reported as "not a recovery source"; `finalize` stops them after verified backups,
`resolve-conflict` if they hold a port; `run` never stops anything.

**`aegisrmf-minio-recovery … bucket listing unavailable`** (fixed diagnosis). Endpoint = the container's IP on its network +
MinIO's internal port (`--address` / `MINIO_ADDRESS`, default 9000) – a `docker run` container on the default bridge has no DNS
name, which is why `http://aegisrmf-minio-recovery:9000` failed. Credentials: `MINIO_ROOT_USER/PASSWORD`, `MINIO_ACCESS_KEY/SECRET_KEY`
or their `*_FILE` secrets (only key names are printed). The probe runs `python -m app.tools.objsync probe` in a local helper image
(`ironvision/recovery:local`, else the live backend image) on the legacy network and reports endpoint, reachable, auth, buckets,
object counts; `mc` inside the MinIO container is a listing-only fallback. If the objects cannot be read, recovery uses the
tarball and the report says **evidence NOT verified** until the rehearsal SHA-256-matches every object to the evidence records.

**MinIO container with no IP (`--network none`) or host networking.** Objects are exported without S3 networking: per object
`docker exec -i aegisrmf-minio-recovery mc cat legacy/<bucket>/<key>` (MinIO's bundled client against its own loopback; never a
TTY; stdout straight to a file; size checked against `mc ls`; SHA-256 manifest), or – without `mc` – a read-only
`docker cp aegisrmf-minio-recovery:/data -` that the recovery image reads with the xl-single reader. Host networking uses
`127.0.0.1:<port>`. A bucket listing (e.g. 44 objects) can exceed the evidence count (38): extra keys are listed and classified
in the rehearsal report and never counted as evidence.

**`recover.sh run` fails building the recovery image: `No matching distribution found for emergentintegrations`** (fixed). The
recovery image installs `deploy/recovery/requirements.recovery.txt` (public PyPI only, same pins as `requirements.prod.txt`);
`python3 scripts/check_requirements.py` must PASS before a push.

### 0.0b Troubleshooting: preflight `seaweedfs image not pinned`
Bug in the first toolkit version: the check rejected every tag (`chrislusf/seaweedfs:4.48` included). Now images are pinned by
digest (`SEAWEEDFS_IMAGE=chrislusf/seaweedfs:4.48@sha256:4e61d15f…`, set by `./deploy.sh --apply-demo-settings --yes`) and
preflight compares the running container's `RepoDigests` with the pin (multi-arch index digest or one of its platform digests).
Mismatch → `docker compose --env-file deploy/digitalocean/.env.production pull seaweedfs && docker compose --env-file … up -d seaweedfs`.
Tag-only: warning on demo, error on customer production. Same for `POSTGRES_IMAGE`, `EDGE_NGINX_IMAGE`, `CERTBOT_IMAGE`,
`KEYCLOAK_BASE_IMAGE` (pinned in the templates; on the existing demo Droplet only `SEAWEEDFS_IMAGE` is changed automatically –
the others stay on their tags until you add the pinned values, so a cutover never swaps the Postgres image underneath you).

### 0.1 Troubleshooting: `"S3_ACCESS_KEY_ID" variable is not set`, no seaweedfs container, `objectstore-init` exit 1
**Symptom:**
- `WARN "S3_ACCESS_KEY_ID" / "S3_SECRET_ACCESS_KEY" variable is not set. Defaulting to a blank string`;
- a volume `aegisrmf_localobjects` and project `aegisrmf`;
- **no** seaweedfs container;
- `service "objectstore-init" didn't complete successfully: exit 1`.

**Cause:** `docker compose up` was run from the repo root with only the base `docker-compose.yml` and the root `.env`. The `--env-file deploy/digitalocean/.env.production` and the DigitalOcean overlays were missing. As a result, `COMPOSE_PROFILES=seaweedfs` was never read, so seaweedfs never started, and the S3 keys were blank.

**What happens now:**
- The base files require `STORAGE_DRIVER`, so a run without an env file fails at `config` with *"STORAGE_DRIVER must be set in your env file"*.
- The storage overlays fail with *"S3_ACCESS_KEY_ID must be set in your env file"*.
- `check_env` and `deploy.sh` refuse the built-in store without *"COMPOSE_PROFILES=seaweedfs is required when using the built-in object store"*.
- `objectstore-init` names each missing variable, or the unreachable endpoint, or the failing identity.

**Quick recovery for exactly this state** (as root in `/opt/ironvision/IronVision-AI`, after the fixed release has been pushed to GitHub):
```bash
cd /opt/ironvision/IronVision-AI
git pull
F=deploy/digitalocean/.env.production
test -f $F || cp deploy/digitalocean/env.production.template $F     # identical to .env.production.example
chmod 600 $F
python3 scripts/gen_env_secrets.py $F          # fills only EMPTY secrets (DB, JWT, Fernet, SeaweedFS app + admin keys); never overwrites
nano $F                                        # set APP_DOMAIN, FRONTEND_URL, CORS_ORIGINS, OIDC_* ; keep COMPOSE_PROFILES=seaweedfs, STORAGE_DRIVER=s3, S3_ENDPOINT_URL= (empty)
docker ps -aq --filter label=com.docker.compose.project=aegisrmf | xargs -r docker rm -f   # removes the failed old-project containers; volumes are kept
docker network rm aegisrmf_default 2>/dev/null || true
python3 scripts/check_env.py $F                # must print RESULT: PASS
./deploy.sh $F                                 # obtains the TLS certificate automatically (§4)
```
The failed run never finished `migrate`, so the old `aegisrmf_*` volumes hold no evidence. Once the new stack is healthy, remove them with `docker volume rm aegisrmf_pgdata aegisrmf_localobjects aegisrmf_objectstore`.

**Fallback without an object-store container** (evidence on the Block Storage volume, `${DATA_ROOT}/objects`):
```bash
sed -i 's/^STORAGE_DRIVER=.*/STORAGE_DRIVER=local/; s/^COMPOSE_PROFILES=.*/COMPOSE_PROFILES=/' $F
python3 scripts/check_env.py $F && scripts/deploy.sh $F    # objectstore-init prints "local storage driver – nothing to initialize"
```

**Older guide versions (recovery from the MinIO-era files):** remove the `MINIO_*` lines from the env file. Then run `python3 scripts/gen_env_secrets.py $F` and `scripts/deploy.sh $F`. The `MINIO_ROOT_*` names are still read as a fallback for the admin key only.

### 0.2 Troubleshooting: `email: command not found` (or `profile: command not found`)
**Cause:** a script or wrapper *sourced* the env file (ran it with `source` or the shell dot command). The unquoted `OIDC_SCOPES=openid email profile` then runs `email` as a shell command. Env files are **data**, not shell scripts. Nothing in this repository sources them any more: `deploy.sh` and `backup-offsite.sh` read single keys with `scripts/envget.py`, and a test fails if any script or doc sources an env file.

**Fix** (rewrites safely: quotes values with spaces or shell characters, removes `export `, converts CRLF to LF, strips trailing spaces, comments out duplicates; it writes a timestamped backup first and keeps mode 600):
```bash
python3 scripts/check_env.py --fix deploy/digitalocean/.env.production
python3 scripts/check_env.py deploy/digitalocean/.env.production      # must print RESULT: PASS
scripts/deploy.sh deploy/digitalocean/.env.production
```
- **Quoting rules:**
  - Wrap any value containing spaces or `$ # ; & | < > ( ) * ` ' " ! ?` in double quotes, e.g. `OIDC_SCOPES="openid profile email"` or `OPENROUTER_APP_NAME="IronVision AI"`.
  - Use single quotes for values containing `$`, because Docker Compose interpolates `$` inside double quotes.
  - Docker Compose, the backend (python-dotenv) and `envget.py` all read these values identically, without the quotes.
- **Reading a value in your own scripts:** use `APP_DOMAIN="$(python3 scripts/envget.py deploy/digitalocean/.env.production APP_DOMAIN)"` – never source the file.
- Your own wrapper must not source the env file either. Call `scripts/deploy.sh` and check its exit code.

**Migrating evidence that already sits in a MinIO volume.** Copying MinIO's raw `/data` files is **not safe**: MinIO stores objects in its own `xl.meta` format, not as plain files.
- **If the old MinIO server is still running**, from an old image you still have locally: point objsync at it as the source.
  ```bash
  $COMPOSE run --rm -T --no-deps -e OLD_S3_ENDPOINT_URL=http://<old-minio-host>:9000 -e OLD_S3_BUCKET=ironvision-evidence \
    -e OLD_S3_REGION=us-east-1 -e OLD_S3_ACCESS_KEY_ID=<old root user> -e OLD_S3_SECRET_ACCESS_KEY=<old root password> \
    backend python -m app.tools.objsync copy s3:OLD s3 --manifest /tmp/minio-migration.json
  ```
  Then run `backup.sh` and `restore.sh` verification; each evidence SHA-256 must match the DB ledger.
- **If MinIO can no longer run:** restore objects from the latest `backup.sh` output (`objects.tar.gz` + `objects-manifest.json` / `manifest.json` hashes) with `restore.sh`. Or re-ingest the original scan files: the evidence ledger lists every file and its SHA-256, so re-uploads are detected as the same content.

*Not yet executed on DigitalOcean.* What **was** executed in the build pod (aarch64): the SeaweedFS 4.48 `weed` binary from GitHub releases (md5 verified), our entrypoint, `s3_bootstrap` (twice, idempotent), a least-privilege check (the app key cannot create or write other buckets; a wrong secret fails with SignatureDoesNotMatch), the live S3 round-trip test, migrate + seed with real ingestion of 25 evidence objects, the integrity job (25/25 ok), `backup.sh` → `restore.sh` into a fresh DB + bucket (**RESTORE_VERIFY: PASS**), and an objsync bucket-to-bucket migration (31/31 verified). `docker compose config -q` passed for every compose/overlay/env-template combination with the standalone Compose v5.6.0 binary. The Docker images themselves were **not** pulled or run here.

---

## 1. Sizing (measured, not guessed)

These numbers were measured in the Emergent build pod (8 shared vCPU, single uvicorn worker, PostgreSQL 16 with default config) by `scripts/measure_memory.py`. Raw data is in `docs/sizing/measurements*.json`. "Load" means `scripts/perf_smoke.py`: a 5,000-finding Nessus ingest (1.7 MB) followed by 120 concurrent read requests. The run took 21.6 s and was sampled every 0.5 s.

| Process | Idle RSS | Idle PSS | Load peak RSS | Load peak PSS | Source |
|---|---|---|---|---|---|
| PostgreSQL 16 (all backends) | 301 MiB | — ¹ | 975 MiB | — ¹ | measured (RSS summed over 7→22 processes) |
| Backend (uvicorn, 1 worker) | 152 MiB | 122 MiB | 228 MiB | 198 MiB | measured |
| Worker | 160 MiB | 144 MiB | 171 MiB | 155 MiB | measured |
| Frontend nginx (static) | ~5–15 MiB | | ~15 MiB | | **estimate** (nginx not run in the pod) |
| Edge nginx (TLS) | ~10–20 MiB | | ~30 MiB | | **estimate** |
| SeaweedFS 4.48 (`weed server`: master + volume + filer + S3 in one container) | **333 MiB** RSS | | ~400–600 MiB | | idle **measured** in the pod (aarch64 binary, 31 objects); load peak is an **estimate** |
| Docker Engine + containerd | ~100–150 MiB | | | | **estimate** |
| Ubuntu 24.04 base | ~300–400 MiB | | | | **estimate** |
| **Frontend production build** (`yarn build`) | — | — | **1,730 MiB** | 1,565 MiB | measured, 11.2 s with warm `node_modules` |
| Backend image build (`pip install`) | — | — | ~400–600 MiB | | **estimate** |

¹ PostgreSQL processes could not be read for PSS in the pod, so RSS is summed per process. This counts `shared_buffers` (128 MB by default) once for every backend, which overstates real usage. A realistic unique footprint under this load is about 400–600 MiB.

Database size after demo reset is 79 MB (reference catalogs plus synthetic data). Evidence objects take 25 MB. A 5,000-finding scan adds about 1.7 MB of evidence plus its rows.

**Steady state under load:** about 0.35 GB (OS) + 0.15 GB (Docker) + 0.6 GB (Postgres) + 0.23 GB (backend) + 0.17 GB (worker) + 0.45 GB (SeaweedFS) + 0.05 GB (nginx), which is about **2.0 GB**. With `STORAGE_DRIVER=local` or Spaces/AWS S3 (no object-store container) it is about **1.55 GB**.
**Peak:** steady state plus an image build on the same host. The frontend build alone is about 1.7 GB, plus yarn install, which comes to about **4–4.5 GB**.

| Tier | Droplet | Reasoning |
|---|---|---|
| **Minimum** | **4 GB RAM / 2 vCPU** (Basic or Premium), 80 GB disk + Block Storage | Runs the stack with about 2 GB headroom. Image builds need **4 GB swap**. Alternatively, build images elsewhere (CI/registry) and only `pull` on the Droplet. One uvicorn worker. No ClamAV. |
| **Preferred** | **8 GB RAM / 4 vCPU** (General Purpose or Premium), 160 GB disk + Block Storage | Builds on the host without swap pressure. Room for 2–4 uvicorn workers, larger `shared_buffers` (1–2 GB), concurrent ingest plus AI drafting, and the optional `--profile clamav` (clamd needs about 1.5–3 GB) or `--profile monitoring`. |

**Disk:**
- Root disk: OS about 10 GB; images and build cache about 6–10 GB (prune with `docker builder prune` after upgrades); Docker logs are capped at 5 × 10 MB per container.
- Block volume **ironvision-data**: 50 GB to start. That covers Postgres (start at 10 GB; grows with observations, about 1–2 GB/year for a mid-size portfolio, estimated) and SeaweedFS evidence (raw scan files; estimate about 2–10 GB/year depending on scan cadence).
- Block volume **ironvision-backups**: at least retention days × (DB dump + evidence). 14 days × about 3 GB means 50 GB to start.
- Grow volumes online with `resize2fs` after resizing in DigitalOcean.

**Swap:** on the 4 GB tier, add a 4 GB swapfile (commands in §2) with `vm.swappiness=10`. On the 8 GB tier, 2 GB of swap is a safety net.

**When to split services:**
- Move Postgres to DO Managed PostgreSQL (§12) when you need PITR, HA or standby replicas, or when the DB passes about 20 GB.
- Move evidence to Spaces/S3 (§12) when it passes about 50 GB or you need cross-region durability.
- Build images in CI and pull them on the Droplet if builds disturb production.
- Run staging on a **separate, smaller Droplet** (2–4 GB). Same-host staging is not recommended.

---

### Keycloak sign-in (auth.demo.ironvisionai.com)

Keycloak 26.8.1 runs as an internal service with a separate `keycloak` database and role on the same Postgres server. To add it:
`./deploy.sh --set-auth-domain auth.demo.ironvisionai.com`. This adds env keys in place (with a backup), generates the empty
secrets, does NOT switch the sign-in mode, and does NOT migrate users. Deploy order: backup → postgres → keycloak-db-init →
keycloak → realm plan/apply → TLS for both domains → app → public checks (the `/admin` console must be 403).
The admin console is reachable only through an SSH tunnel (`ssh -L 8081:127.0.0.1:8081 …`). User migration (dry run first), the
credential CLI, the switch to `AUTH_PROVIDERS=oidc`, verification and rollback are covered in **[docs/KEYCLOAK.md](KEYCLOAK.md)**.
The systemd units now read `/srv/ironvision/compose.env` (written by deploy.sh), so boot start, certificate renewal and backups use
exactly the same overlays as the last deploy (storage + Keycloak).

## 2. Clean-server setup (Ubuntu 24.04 LTS)

*Not yet executed on DigitalOcean.* Run as root on first login (SSH key added at Droplet creation). Replace `ADMIN_IP`, `you@…` and the domain.

```bash
# 2.1 admin user with SSH keys only
adduser --disabled-password --gecos "" ironvision
usermod -aG sudo ironvision
install -d -m 700 -o ironvision -g ironvision /home/ironvision/.ssh
cp /root/.ssh/authorized_keys /home/ironvision/.ssh/authorized_keys
chown ironvision:ironvision /home/ironvision/.ssh/authorized_keys && chmod 600 /home/ironvision/.ssh/authorized_keys
passwd -d ironvision && echo 'ironvision ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-ironvision && chmod 440 /etc/sudoers.d/90-ironvision
#   (prefer setting a sudo password instead of NOPASSWD if your policy requires it)

# 2.2 SSH: key-only, no root login
cat > /etc/ssh/sshd_config.d/10-ironvision.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
EOF
sshd -t && systemctl restart ssh
#   → open a NEW session as ironvision@<droplet> before closing the root session

# 2.3 updates, timezone, NTP
apt-get update && apt-get -y full-upgrade
apt-get install -y unattended-upgrades apt-listchanges ca-certificates curl gnupg git jq python3 apache2-utils postgresql-client-16 rclone
dpkg-reconfigure -f noninteractive unattended-upgrades
timedatectl set-timezone UTC && timedatectl set-ntp true && timedatectl status | grep -E "synchronized|NTP"

# 2.4 swap (4 GB tier; use 2G on 8 GB)
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo 'vm.swappiness=10' > /etc/sysctl.d/99-ironvision.conf && sysctl --system

# 2.5 host firewall (ufw) – mirror of the DO Cloud Firewall (§3)
ufw default deny incoming && ufw default allow outgoing
ufw allow from ADMIN_IP to any port 22 proto tcp
ufw allow 80/tcp && ufw allow 443/tcp
ufw --force enable && ufw status verbose

# 2.6 optional fail2ban for sshd
apt-get install -y fail2ban && systemctl enable --now fail2ban

# 2.7 Docker Engine + Compose v2 from Docker's official apt repository
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ironvision
docker compose version   # must be >= 2.24 (overlays use !reset / !override)

# 2.8 nothing else: backups, restore and off-site copies use our objsync helper inside the backend image (no mc / aws-cli / rclone)
```

> **Docker and ufw:** ports published by Docker bypass ufw's INPUT rules, because Docker writes its own iptables chains. The overlay therefore publishes **only** 80/443 (edge) publicly. Postgres (5432) and the SeaweedFS master UI (9333) bind to **127.0.0.1**; the SeaweedFS S3 API (8333) is not published at all (internal compose network only); the backend (8001) and frontend (8080) are not published at all. The DO Cloud Firewall (§3) is the authoritative perimeter.

### 2.9 Block Storage volumes
*Not yet executed on DigitalOcean.* Create two volumes in the same region and attach them, choosing "manually format & mount". With doctl, for example: `doctl compute volume create ironvision-data --region nyc3 --size 50GiB` and `doctl compute volume-action attach <vol-id> <droplet-id>`. Then run:

```bash
for v in ironvision-data ironvision-backups; do ls -l /dev/disk/by-id/scsi-0DO_Volume_$v; done
sudo mkfs.ext4 -L ivdata   /dev/disk/by-id/scsi-0DO_Volume_ironvision-data      # ONLY on a new, empty volume
sudo mkfs.ext4 -L ivbackup /dev/disk/by-id/scsi-0DO_Volume_ironvision-backups
sudo mkdir -p /srv/ironvision
UUID_DATA=$(sudo blkid -s UUID -o value /dev/disk/by-id/scsi-0DO_Volume_ironvision-data)
UUID_BK=$(sudo blkid -s UUID -o value /dev/disk/by-id/scsi-0DO_Volume_ironvision-backups)
echo "UUID=$UUID_DATA /srv/ironvision ext4 defaults,nofail,discard,noatime 0 2" | sudo tee -a /etc/fstab
sudo mount -a && sudo mkdir -p /srv/ironvision/backups
echo "UUID=$UUID_BK /srv/ironvision/backups ext4 defaults,nofail,discard,noatime 0 2" | sudo tee -a /etc/fstab
sudo mount -a && df -h /srv/ironvision /srv/ironvision/backups
```

### 2.10 Directories and ownership (§5)
```bash
sudo install -d -m 700 -o 70 -g 70 /srv/ironvision/postgres          # postgres:16-alpine runs as uid/gid 70
sudo install -d -m 750 -o root -g root /srv/ironvision/objectstore   # SeaweedFS data (container runs as root)
sudo install -d -m 750 -o 10001 -g 10001 /srv/ironvision/objects     # STORAGE_DRIVER=local (backend/worker run as uid 10001)
sudo install -d -m 755 /srv/ironvision/letsencrypt /srv/ironvision/certbot/www
sudo install -d -m 750 -o ironvision -g ironvision /srv/ironvision/backups
```

### 2.11 Clone, configure, build, migrate, start
```bash
# Any checkout path works (scripts and systemd units resolve the repo root themselves). The customer Droplet uses /opt/ironvision/IronVision-AI.
sudo install -d -o ironvision -g ironvision /opt/ironvision && cd /opt/ironvision
git clone <your-git-remote>/IronVision-AI.git IronVision-AI && cd IronVision-AI && git checkout <release-tag>
cp deploy/digitalocean/env.production.template deploy/digitalocean/.env.production && chmod 600 deploy/digitalocean/.env.production
python3 scripts/gen_env_secrets.py deploy/digitalocean/.env.production   # fills empty secrets in place; never overwrites, never prints them
python3 scripts/check_env.py deploy/digitalocean/.env.production        # must print RESULT: PASS
sudo cp deploy/digitalocean/docker-daemon.json /etc/docker/daemon.json && sudo systemctl restart docker   # log rotation
# TLS first (see §4), then – the only supported deploy command (also creates the §2.10 directories with the right owners):
scripts/deploy.sh deploy/digitalocean/.env.production
```
`deploy.sh` runs, in order: check_env → config → pull → build → postgres → seaweedfs → objectstore-init (bucket, versioning, SHA-256 round-trip) → migrate (alembic + reference content) → backend/worker/frontend/edge → `/api/v1/ready`. It stops at the first failure. For later `ps` / `logs` commands it prints the exact compose command in its summary (`export COMPOSE="docker compose -p ironvision --env-file deploy/digitalocean/.env.production -f docker-compose.yml -f docker-compose.prod.yml -f deploy/digitalocean/docker-compose.do.yml"`).

**Start on boot:** every long-running service uses `restart: unless-stopped`. The optional systemd unit adds an env check and ordered start/stop:
```bash
sudo cp deploy/digitalocean/systemd/ironvision*.service deploy/digitalocean/systemd/ironvision*.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now ironvision.service ironvision-backup.timer ironvision-certbot-renew.timer
```

---

## 3. Networking

*Not yet executed on DigitalOcean.*

**DNS** (at your DNS provider or DO Networking → Domains), example `demo.ironvisionai.com`:
| Record | Name | Value |
|---|---|---|
| A | `demo.ironvisionai.com` | Droplet IPv4 (better: a DO Reserved IP) |
| AAAA | `demo.ironvisionai.com` | Droplet IPv6 (only if IPv6 is enabled on the Droplet) |
| A/AAAA | `staging.<your-domain>` | the **staging** Droplet |
| CAA | `ironvisionai.com` | `0 issue "letsencrypt.org"` (plus `0 iodef "mailto:<security contact>"`) |

`./deploy.sh` checks the A record against the Droplet's public IPv4 (DO metadata) before it requests a certificate.

No separate API host is needed: the SPA calls `/api` on the same origin (`REACT_APP_BACKEND_URL` is empty). Only add `api.example.gov` if you deliberately split origins; in that case also extend `CORS_ORIGINS` and the frontend CSP `connect-src`.

**DigitalOcean Cloud Firewall** (attach it to the Droplet by tag):
| Direction | Protocol/Port | Source/Destination |
|---|---|---|
| Inbound | TCP 22 | admin IPs / VPN CIDR only |
| Inbound | TCP 80, 443 | `0.0.0.0/0`, `::/0` |
| Inbound | ICMP | optional |
| Inbound | **5432, 8333, 9333, 8001, 8080, 3000** | **not opened** |
| Outbound | TCP 443, 80, UDP 53, UDP 123 | all (package updates, ACME, IdP/AI APIs, NTP) |

The matching ufw rules are in §2.5. **SeaweedFS master UI** (read-only cluster status): reach it only through an SSH tunnel: `ssh -L 9333:127.0.0.1:9333 ironvision@<droplet>`, then open http://localhost:9333. The S3 API is never exposed.

---

## 4. TLS reverse proxy (edge nginx + Let's Encrypt)

*Not yet executed on DigitalOcean.* The DO overlay replaces the generic `deploy/nginx/edge.conf` with `deploy/digitalocean/nginx/edge.conf.template`, which uses the official `nginx:1.27-alpine` image. The image runs envsubst on the template, and only `${APP_DOMAIN}` is substituted.

**Automatic, one command:**
```bash
./deploy.sh --set-domain demo.ironvisionai.com --email k.hill@theironvision.com
```
1. **`--set-domain`** (`scripts/set_domain.py`, backup first, mode 600, secrets untouched) sets `APP_DOMAIN`, `FRONTEND_URL`, `CORS_ORIGINS`, `OPENROUTER_SITE_URL`, `OIDC_REDIRECT_URI=https://<domain>/api/v1/auth/oidc/callback` and `LETSENCRYPT_EMAIL`. It also replaces every other occurrence of the old domain or `app.example.gov` in non-secret values, and prints the changed keys.
2. **TLS step** (`scripts/ensure_tls.sh ensure`, runs before edge starts). It does nothing if `${DATA_ROOT}/letsencrypt/live/<domain>/fullchain.pem` is valid for the domain for more than 30 more days. Otherwise it:
   - checks that the domain's A record equals this Droplet's IPv4, and stops with *"Create DNS A record demo.ironvisionai.com → <ip>"* if not (`--force-tls` skips this check);
   - stops edge and checks that port 80 is free;
   - runs `certbot certonly --standalone --non-interactive --agree-tos -m $LETSENCRYPT_EMAIL --no-eff-email -d <domain> --keep-until-expiring` in the certbot container on port 80 (`--staging` when `LETSENCRYPT_STAGING=true`);
   - re-checks the result.
   The edge mounts `${DATA_ROOT}/letsencrypt` read-only and its nginx master runs as root, so no permission changes are needed. TLS settings are inline (no dhparams file).
3. **Verify** (`ensure_tls.sh verify`): `openssl s_client -connect <domain>:443 -servername <domain>` must show `DNS:<domain>` in the SAN, issued by Let's Encrypt. Then `https://<domain>/api/v1/ready` must answer.
4. **Renewal:** when `deploy.sh` runs as root (or with `--install-systemd`), it installs the systemd units with this checkout's path, env file and user, and enables `ironvision-certbot-renew.timer`. Twice a day the timer runs `certbot renew --webroot -w /var/www/certbot` through the running edge, then `nginx -s reload`. `--no-systemd` skips the install. Check with `systemctl list-timers ironvision-certbot-renew.timer`.
5. **Own certificate:** set `CERT_FULLCHAIN_PATH` and `CERT_KEY_PATH` (PEM files on the Droplet). The TLS step checks the hostname and that the key matches, copies them into `${DATA_ROOT}/letsencrypt/live/<domain>/`, and skips Let's Encrypt.
6. **Test runs:** set `LETSENCRYPT_STAGING=true` to avoid Let's Encrypt rate limits (browsers won't trust the certificate). Set it back to `false` and re-run `./deploy.sh`; the staging certificate is replaced automatically.

Prerequisites:
- the DNS A record, plus AAAA if you use IPv6;
- with built-in Keycloak, also the A record **`auth.demo.ironvisionai.com` → the same Droplet IPv4**. `./deploy.sh` DNS-checks it and requests its own certificate (renewed by the same timer);
- the CAA record `0 issue "letsencrypt.org"` if you use CAA;
- the DO Cloud Firewall and ufw open on 80 and 443 (§2.5, §3).

What the edge enforces:
- HTTP → HTTPS redirect and TLS 1.2/1.3.
- HSTS `max-age=31536000; includeSubDomains`.
- `client_max_body_size 60m`, matching `MAX_UPLOAD_MB=50` plus multipart overhead.
- `proxy_read_timeout`/`proxy_send_timeout` of 300 s for large ingests and AI drafting (`AI_TIMEOUT_SECONDS=60`).
- `/metrics` returns 404 and `/api/v1/metrics` is denied publicly.
- Client-supplied mTLS identity headers are blanked. `X-Forwarded-For` is overwritten, which pairs with `TRUST_PROXY_HEADERS=true`.

The SPA security headers come from the frontend nginx: CSP with `frame-ancestors 'none'` (Google Fonts allowed), nosniff, `X-Frame-Options DENY`, `Referrer-Policy no-referrer` and Permissions-Policy. The API sets its own strict headers. **`DEV_FRAME_ANCESTORS` is a dev-server/preview setting only and is not used in production.**

---

## 5. Persistent data

| Data | Container path | Droplet path | Owner |
|---|---|---|---|
| PostgreSQL | `/var/lib/postgresql/data` | `/srv/ironvision/postgres` | uid/gid 70, mode 700 |
| SeaweedFS evidence | `/data` | `/srv/ironvision/objectstore` | root, 750 |
| Local evidence (`STORAGE_DRIVER=local` only) | `/srv/objects` | `/srv/ironvision/objects` | root, 750 |
| Let's Encrypt | `/etc/letsencrypt` | `/srv/ironvision/letsencrypt` | root |
| ACME webroot | `/var/www/certbot` | `/srv/ironvision/certbot/www` | root, 755 |
| Backups | — (host) | `/srv/ironvision/backups` (2nd volume) | ironvision, 750 |

Named volumes from the base compose file (`pgdata`, `objectstore`, `localobjects`) are replaced with `!override` bind mounts. DO volume snapshots of `ironvision-data` are a useful **complement** to `scripts/backup.sh`, not a replacement. A snapshot of a running Postgres is only crash-consistent; dumps are portable and verifiable.

---

## 6. Environment templates

- `deploy/digitalocean/env.production.template` / `env.staging.template` (identical non-dot copies of `.env.production.example` / `.env.staging.example`, so they survive tools that drop dot-files) list **every** variable the backend reads, plus the compose/edge/backup variables. Completeness is enforced by the test `test_env_templates_cover_every_variable_the_code_reads`.
- Preview-only variables (`EMERGENT_LLM_KEY`, `EMERGENT_AI_VENDOR`) are deliberately absent.
- Secrets are generated with the commands in §2.11.
- `scripts/check_env.py <file>` checks the file and **fails** on:
  - a missing required variable;
  - a weak or placeholder `JWT_SECRET`, `POSTGRES_PASSWORD`, `S3_SECRET_ACCESS_KEY` or `S3_ADMIN_SECRET_ACCESS_KEY`; identical app/admin S3 keys; missing S3 settings for `STORAGE_DRIVER=s3` (warns on deprecated `MINIO_*` names and on plain-http S3 endpoints to non-internal hosts);
  - an invalid Fernet key;
  - the publicly documented demo password;
  - non-https or localhost `FRONTEND_URL`/`CORS_ORIGINS`;
  - `AI_PROVIDER=emergent`;
  - disabled rate limiting;
  - missing OIDC/mTLS/AI/Vault settings for the enabled provider;
  - in production, `AUTH_PROVIDERS` containing `dev_password` or `SEED_DEMO_DATA=true`, unless `ALLOW_INSECURE_PRODUCTION=true`.
- The backend and the seed enforce the same production rule at start-up, so the app **refuses to start** in that case.
- Never commit `.env.production` or `.env.staging`, and keep them at `chmod 600`.

---

## 7. Lifecycle procedures

*Not yet executed on DigitalOcean.* `$COMPOSE` is defined in §2.11.

**DB initialisation and migrations:** the one-shot `migrate` service runs `alembic upgrade head && python -m app.seed`. With `SEED_DEMO_DATA=false` the seed loads **reference content only** (hash-verified NIST 800-53 r5, CCI, KEV, STIG). Demo organisations and accounts are never created. To re-run it:
```bash
$COMPOSE run --rm migrate          # idempotent
$COMPOSE exec backend alembic current   # expect: 0009 (head)
```
**Content load status:** Admin → Jobs (`content.load`), or `curl -fsS https://$APP_DOMAIN/api/v1/health | jq .components`.

**First administrator (no demo accounts):**
```bash
$COMPOSE exec backend python -m app.cli create-admin --email admin@agency.gov --name "Jane Admin" --org "Agency Name"
```
With OIDC no password is stored; the admin signs in through the IdP and is matched by email. Other users and roles are then managed under Admin → Users. `--password-stdin` exists only for non-production with `dev_password` enabled.

**Backups** (nightly via `ironvision-backup.timer`):
- `deploy/digitalocean/backup-offsite.sh` runs `scripts/backup.sh` (pg_dump custom format, object copy via `python -m app.tools.objsync` in the backend image with a per-object SHA-256 manifest, and `manifest.json` with SHA-256 hashes, alembic revision and audit-chain head).
- It keeps `BACKUP_RETENTION_DAYS` of backups locally. If `OFFSITE_S3_BUCKET` is set, it copies the backup off the Droplet to DO Spaces / AWS S3 / any S3 with objsync. objsync re-reads every file at the destination and compares its SHA-256.
- Off-site settings (in the env file): `OFFSITE_S3_ENDPOINT_URL` (e.g. `https://nyc3.digitaloceanspaces.com`), `OFFSITE_S3_BUCKET`, `OFFSITE_S3_REGION`, `OFFSITE_S3_ACCESS_KEY_ID`, `OFFSITE_S3_SECRET_ACCESS_KEY`, `OFFSITE_S3_ADDRESSING_STYLE=virtual`.
- Run it manually with `sudo systemctl start ironvision-backup.service && journalctl -u ironvision-backup -n 50`.

**Restore** (always into an empty target first):
```bash
$COMPOSE stop backend worker
TARGET_DATABASE_URL=postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:5432/ironvision_restore \
  bash scripts/restore.sh /srv/ironvision/backups/ironvision-<ts>     # expect RESTORE_VERIFY: PASS
```
`restore.sh` checks the manifest hashes, row counts, alembic revision and audit hash chain. To cut over, point `DATABASE_URL` at the restored DB (or rename the databases), then `$COMPOSE up -d`.

**Upgrade:**
```bash
cd "$(git rev-parse --show-toplevel)" && sudo systemctl start ironvision-backup.service   # 1. backup first (run inside your checkout, e.g. /opt/ironvision/IronVision-AI)
git fetch --tags && git checkout <new-tag>                                          # 2. code
python3 scripts/check_env.py deploy/digitalocean/.env.production                    # 3. new vars?
$COMPOSE build && $COMPOSE run --rm migrate && $COMPOSE up -d                       # 4. build, migrate, restart
curl -fsS https://$APP_DOMAIN/api/v1/ready && curl -fsS https://$APP_DOMAIN/api/v1/health | jq .status   # 5. verify
docker image prune -f && docker builder prune -f --filter until=168h
```

**Rollback:** run `git checkout <previous-tag> && $COMPOSE build && $COMPOSE up -d`. If the new release ran migrations, **prefer restoring the pre-upgrade backup** into a fresh DB (`restore.sh`) over `alembic downgrade`, because downgrades can drop columns and data (see MIGRATION_PROCEDURE.md).

**Logs:** `docker-daemon.json` and the per-service `logging` blocks cap each container at 5 × 10 MB of json logs. View them with `$COMPOSE logs -f --since 1h backend worker`.

---

## 8. AI provider (no Emergent) – OpenRouter recommended

**OpenRouter** is a single key and a single endpoint for many model vendors. Set the model with `AI_MODEL` (any OpenRouter slug, passed through verbatim, no allowlist in code), or in **Admin → AI administration → Model**. No code change is needed to switch models.
```env
AI_PROVIDER=openrouter
OPENAI_COMPAT_API_KEY=sk-or-v1-...            # the ONLY key needed (https://openrouter.ai/keys)
AI_MODEL=openai/gpt-4o                        # e.g. openai/gpt-4.1, anthropic/claude-3.5-sonnet, meta-llama/llama-3.1-70b-instruct, mistralai/mistral-large
# optional
OPENAI_COMPAT_BASE_URL=                       # default https://openrouter.ai/api/v1 (must be https:// in staging/production)
AI_MODEL_DRAFTING=                            # control implementation statements
AI_MODEL_POLICY=                              # policy audit
AI_MODEL_MAPPING=                             # finding → control mapping
AI_MODEL_SUMMARY=                             # summaries
AI_TEMPERATURE=0.2
AI_TIMEOUT_SECONDS=60
OPENROUTER_SITE_URL=https://app.example.gov   # sent as HTTP-Referer
OPENROUTER_APP_NAME="IronVision AI"           # sent as X-Title (quote values with spaces)
ANTHROPIC_API_KEY=                            # leave empty – never read with openrouter (check_env warns if set)
```
- **Model precedence:** admin model (UI, per organization) > `AI_MODEL_<USE CASE>` > `AI_MODEL`. The admin page shows the effective provider, base URL, model, and whether a key is configured. It never shows the key itself.
- **Requests:** OpenAI Chat Completions schema (`POST {base}/chat/completions`) over httpx. Structured output tries `response_format` json_schema (strict), then json_object, then a plain prompt that says "return only JSON matching this schema". The first mode an endpoint/model rejects is skipped on later calls. Every reply is validated with Pydantic (```json fences are stripped) and gets one repair retry; after that the call fails with a clear message.
- **Errors:**
  - 429/502/503 are retried 3 times, honouring `Retry-After`.
  - **402** means *insufficient credits*: add credits at https://openrouter.ai/settings/credits or pick a cheaper model.
  - 401 means the key was rejected. Timeouts report `AI_TIMEOUT_SECONDS`.
  - Each call is logged to `ai_interactions` with provider, model and token usage. The key is never logged.
- **Other providers:** `AI_PROVIDER=openai_compatible` with `OPENAI_COMPAT_BASE_URL` covers self-hosted vLLM, Ollama or LiteLLM (the key is optional there). `AI_PROVIDER=anthropic` with `ANTHROPIC_API_KEY` is the direct Anthropic API. `AI_PROVIDER=none` disables AI.
- **Data handling:** prompts (control context, policy text, finding titles) go to OpenRouter and onward to the chosen model's provider. Pick models and providers that match your data policy (OpenRouter provider routing and data-retention settings). Use synthetic data only in dev and staging. Details are in `docs/SECURITY.md`.
- **Verify:** Admin → **Run AI health check**, or `curl -fsS -X POST -H "Authorization: Bearer <platform admin token>" https://$APP_DOMAIN/api/v1/ai/health`. This sends one schema-validated probe through the configured provider and records it in the audit log.
- The Emergent adapter is **not used in production**. Its library (`emergentintegrations`) is not in `requirements.prod.txt`. `AI_PROVIDER=emergent` is rejected by `check_env.py` and refused when `APP_ENV` is staging or production.

### 8.1 Python dependencies (prevents the python-multipart outage)
The backend and worker images install **only** `backend/requirements.prod.txt`. Its rules:
- It pins every package in `requirements.txt` at the same version.
- The only exceptions are the packages listed in `backend/requirements.prod-exclude.txt`, each with its reason (dev tools, the preview AI adapter and its transitive dependencies, unused template leftovers).
- `python3 scripts/check_requirements.py` enforces this. It also checks that every third-party import in `backend/app`, `backend/worker` and `backend/alembic` maps to a production distribution. It runs in CI and pytest.
- `scripts/deploy.sh` runs `python -m app.tools.selfcheck` inside the freshly built **backend and worker** images, which imports every module. This happens *before* anything is started, so a missing package fails the deploy instead of taking the running service down.

---

## 9. Preview-dependency exclusion

Run `bash scripts/verify_no_preview_deps.sh` (add `--docker` on the Droplet to also inspect the built images). It checks four things:
- **(a) Python packages:** `requirements.prod.txt`, and `pip list` inside the backend, worker and migrate images.
- **(b) Frontend packages:** the Docker `package.json` after the Dockerfile strips `@emergentbase/*`, plus `deploy/index.html` and the index.html swap.
- **(c) Built bundle:** the production JS bundle (built from `deploy/index.html`) and the frontend image's `/usr/share/nginx/html` must contain no `assets.emergent.sh`, `ap.emergent.sh`, `emergentagent.com` or posthog references.
- **(d) AI adapter:** the emergent adapter is never imported when `AI_PROVIDER=none` and is refused when `APP_ENV=production`.

Result in the build pod (non-Docker parts, saved in `docs/security/verify_no_preview_deps.txt`): **RESULT: PASS**, with the image inspection SKIPPED (no Docker in the pod).

---

## 10. Running the tests on the Droplet

*Not yet executed on DigitalOcean.*
- **Never point the tests at the production database.** The suite **wipes** its `TEST_DATABASE_URL`.
- Use a throwaway Postgres container and run the full suite and the acceptance suite **one after the other, not concurrently**, because both reset the same test DB.

```bash
TPW=$(openssl rand -hex 16)
docker run -d --name iv-testdb --network ironvision_default -e POSTGRES_PASSWORD=$TPW postgres:16-alpine
T="postgresql+psycopg://postgres:$TPW@iv-testdb:5432/postgres"
$COMPOSE run --rm --no-deps -e TEST_DATABASE_URL=$T -e APP_ENV=development -e AUTH_PROVIDERS=dev_password backend \
  python -m pytest -c pytest.aegis.ini tests -q                      # full backend suite
$COMPOSE run --rm --no-deps -e TEST_DATABASE_URL=$T -e APP_ENV=development -e AUTH_PROVIDERS=dev_password backend \
  python -m pytest -c pytest.aegis.ini tests/acceptance -v           # AT-1..AT-12 (same as `make acceptance`)
docker rm -f iv-testdb
```
`APP_ENV=development` is required only inside this throwaway test container, because the production start-up guard correctly refuses `dev_password`.

`scripts/verify_portability.sh` drives a full dev-mode stack (dev auth, demo seed). Run it **only on the staging Droplet** or a disposable VM, never against production.

---

## 11. Staging

*Not yet executed on DigitalOcean.* Use a separate Droplet (2–4 GB), with its own Block Storage volume (`DATA_ROOT=/srv/ironvision-staging`), database (`ironvision_staging`), bucket and DNS name.

```bash
cp deploy/digitalocean/env.staging.template deploy/digitalocean/.env.staging && chmod 600 deploy/digitalocean/.env.staging
echo "STAGING_DEMO_PASSWORD=$(openssl rand -base64 24 | tr -d '\n=+/')"      # paste into the env file
sudo install -d /srv/ironvision-staging/staging && sudo htpasswd -B -c /srv/ironvision-staging/staging/htpasswd reviewer
printf 'allow 203.0.113.0/24;\ndeny all;\n' | sudo tee /srv/ironvision-staging/staging/allowlist.conf   # or "allow all;" with basic auth only
python3 scripts/check_env.py deploy/digitalocean/.env.staging
export SCOMPOSE="docker compose -p ironvision-staging --env-file deploy/digitalocean/.env.staging -f docker-compose.yml -f deploy/digitalocean/docker-compose.do.yml -f deploy/digitalocean/docker-compose.staging.yml"
$SCOMPOSE up -d --build
```
- **Synthetic data only.** Demo data is seeded only because the staging overlay sets `SEED_DEMO_DATA=true` explicitly.
  - The single demo account `demo@ironvision.ai` uses the generated `STAGING_DEMO_PASSWORD`.
  - `ALLOW_SIGNUP=true` lets reviewers create private sandboxes. New sign-ups start **clean** (no systems or records); only `demo@ironvision.ai` is seeded with the 4 synthetic systems. `SANDBOX_INACTIVITY_DAYS` (default 30) purges idle ones.
  - Production keeps `ALLOW_SIGNUP=false`, `SEED_DEMO_DATA=false` and `DEMO_PASSWORD` empty.
- **Dev credentials are not public.** `DEV_USER_PICKER=false` hides the account picker, and the edge adds basic auth plus the IP allowlist.
- The build shows a persistent **"STAGING – SYNTHETIC DATA"** banner (`REACT_APP_ENV_LABEL=staging`).
- `X-Robots-Tag: noindex` and a `Disallow: /` robots.txt keep it out of search engines.
- Production refuses to start with `dev_password` or the demo seed (§6).

---

## 12. Future migration (no rewrite)

### 12.1 DigitalOcean Managed PostgreSQL
1. Create a PG 16 cluster in the same region/VPC and add the Droplet as a trusted source. Download the CA certificate to `/opt/ironvision/certs/do-ca.crt` and mount it read-only into backend, worker and migrate.
2. Set `DATABASE_URL=postgresql+psycopg://user:pass@<host>:25060/ironvision?sslmode=verify-full&sslrootcert=/certs/do-ca.crt`. `sslmode=require` is the minimum; `verify-full` is preferred. The DO overlay passes `DATABASE_URL` through.
3. Size connections: (uvicorn workers × SQLAlchemy pool 10 + overflow 10, see `app/db.py`) + worker (≈5) + migrate. Use DO's PgBouncer pool in **session** mode. Transaction mode breaks the worker's `SELECT … FOR UPDATE SKIP LOCKED` sessions, so test it before using it.
4. Cutover:
   - Back up with `backup.sh`, then `$COMPOSE stop backend worker`.
   - `pg_restore --no-owner --no-privileges -d "$MANAGED_URL" db.dump`.
   - `alembic current` should report `0009`.
   - Run `restore.sh` verification against the managed DB (hashes, counts, audit chain), then start.
   - Remove the `postgres` service (or leave it stopped) once validated.
   - Migrations still run through the one-shot `migrate` service (`alembic upgrade head`).
5. Rollback: point `DATABASE_URL` back at the Droplet Postgres, which stays untouched until sign-off.

### 12.2 Storage profiles (env only – no code change)
| Profile | Env | Notes |
|---|---|---|
| **A. SeaweedFS (default)** | `COMPOSE_PROFILES=seaweedfs`, `STORAGE_DRIVER=s3`, `S3_ENDPOINT_URL=` (empty → `http://seaweedfs:8333`), `S3_ADDRESSING_STYLE=path`, app + admin keys | Apache-2.0, image `chrislusf/seaweedfs:4.48` (pinned). Data on Block Storage `/srv/ironvision/objectstore`. App identity limited to Read/Write/List/Tagging on `S3_BUCKET`. Versioning is enabled by `objectstore-init` when supported. No object lock. No SSE: rely on encrypted DO Block Storage plus SHA-256 ledger verification. |
| **B. DigitalOcean Spaces** | remove `seaweedfs` from `COMPOSE_PROFILES`; `S3_ENDPOINT_URL=https://nyc3.digitaloceanspaces.com`, `S3_REGION=nyc3`, `S3_ADDRESSING_STYLE=virtual`, Spaces key pair as `S3_ACCESS_KEY_ID/SECRET` | Use a bucket-scoped Spaces key. Spaces encrypts at rest (no SSE-KMS or customer keys). Create the bucket in the console or let `objectstore-init` create it (needs a full-access key). |
| **C. AWS S3** | no seaweedfs profile; `S3_ENDPOINT_URL=https://s3.<region>.amazonaws.com`, `S3_REGION=<region>`, `S3_ADDRESSING_STYLE=virtual`, IAM user keys scoped to the bucket | SSE-S3/SSE-KMS through bucket default encryption (no code change). Object Lock is available but must be configured at bucket creation (outside the app). |
| **D. Garage (optional)** | add your own `garage` service; `S3_ENDPOINT_URL=http://garage:3900`, `S3_REGION=garage`, `S3_ADDRESSING_STYLE=path` | **AGPL-3.0** – review licensing. No versioning or object lock; `objectstore-init` reports "not supported" and continues. |
| **E. Local disk** | no seaweedfs profile; `STORAGE_DRIVER=local` | Simplest single-Droplet install: evidence under `/srv/ironvision/objects` on Block Storage, backed up by `backup.sh` (tar + SHA-256). No object-store container (~0.45 GB less RAM). |

- **Client:** boto3 with SigV4. `S3_ADDRESSING_STYLE` = `path` (self-hosted) or `virtual` (Spaces/AWS).
- **Switching between S3 stores:**
  1. Copy with verification: `$COMPOSE run --rm -T --no-deps -e OLD_S3_ENDPOINT_URL=… -e OLD_S3_BUCKET=… -e OLD_S3_REGION=… -e OLD_S3_ACCESS_KEY_ID=… -e OLD_S3_SECRET_ACCESS_KEY=… backend python -m app.tools.objsync copy s3:OLD s3 --manifest /tmp/m.json`. The current `S3_*` variables must point at the **new** store; every object is re-hashed at the destination.
  2. Run `backup.sh`, then `restore.sh` verification against a scratch DB: each evidence SHA-256 must match the ledger, and the audit chain must verify.
  3. Switch the env, run `$COMPOSE up -d`, and spot-check evidence downloads.
- **Rollback:** revert the `S3_*` variables; the old store stays intact until sign-off.

**Effect on security posture and claims:** managed services move parts of physical, backup and patching control to DigitalOcean. Commercial DigitalOcean is **not** FedRAMP-authorized and not an IL2–IL6 environment, and nothing in this guide changes the statements in SECURITY.md (no ATO, FedRAMP, CUI or FIPS claims). Record any DO SOC 2/ISO reports you rely on in your own SSP.

---

## 13. Operator validation checklist

**Status: documentation only – not yet executed on DigitalOcean.** Fill in each row.

| # | Step | PASS / FAIL | Date | Operator / notes |
|---|---|---|---|---|
| 1 | Droplet created (Ubuntu 24.04, tier: ____ ) with SSH key | | | |
| 2 | `ironvision` sudo user; root + password SSH login disabled (verified from a 2nd session) | | | |
| 3 | unattended-upgrades enabled; timezone UTC; NTP synchronized | | | |
| 4 | swap configured (`swapon --show`) | | | |
| 5 | ufw active with 22 (admin IPs), 80, 443 only | | | |
| 6 | DO Cloud Firewall attached; external scan shows only 22/80/443 | | | |
| 7 | Docker Engine + Compose ≥ 2.24 from Docker apt repo; `docker run hello-world` | | | |
| 8 | Block volumes mounted by UUID with `nofail`; survive reboot | | | |
| 9 | Directory ownership per §5 | | | |
| 10 | `.env.production` created (600); `check_env.py` → PASS | | | |
| 11 | DNS A/AAAA + CAA resolve | | | |
| 12 | Let's Encrypt certificate issued; `renew --dry-run` OK; timer enabled | | | |
| 13 | `$COMPOSE build` succeeded (peak memory observed: ____ ) | | | |
| 14 | migrate completed; `alembic current` = 0009; reference content loaded | | | |
| 15 | `create-admin` done; admin signs in via OIDC | | | |
| 16 | No demo accounts exist in production (Admin → Users) | | | |
| 17 | `https://<domain>` loads; `/api/v1/ready` = ready; `/metrics` 404; `/api/v1/metrics` blocked | | | |
| 18 | Security headers present (CSP frame-ancestors 'none', HSTS, nosniff, Referrer-Policy, Permissions-Policy) | | | |
| 19 | Upload of a large scan (≥ 20 MB) succeeds; disallowed file rejected | | | |
| 20 | AI provider check OK (or AI_PROVIDER=none confirmed) | | | |
| 21 | `verify_no_preview_deps.sh --docker` → PASS | | | |
| 22 | Backup service run; manifest present; off-droplet copy verified (`rclone check`) | | | |
| 23 | Restore into scratch DB → `RESTORE_VERIFY: PASS` | | | |
| 24 | Reboot test: all services return; data intact | | | |
| 25 | Upgrade + rollback rehearsal on staging | | | |
| 26 | Test suite + acceptance run against throwaway DB (§10) | | | |
| 27 | Staging: banner, noindex, basic auth / allowlist, picker hidden, generated demo password | | | |
| 28 | Measured RSS on the Droplet recorded vs §1 table | | | |
