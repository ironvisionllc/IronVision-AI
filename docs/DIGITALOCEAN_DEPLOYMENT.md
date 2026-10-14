# IronVision AI on a DigitalOcean Droplet

> **Status: documentation only – not yet executed on DigitalOcean.**
> Every DigitalOcean step below is marked *Not yet executed on DigitalOcean*. The operator records the real outcome in the [validation checklist](#13-operator-validation-checklist). Nothing in this guide has been tested on a Droplet. The code has no DigitalOcean-specific dependency; `doctl` is optional and only used in examples.

Target: an IronVision-controlled **Ubuntu 24.04 LTS Droplet** running Docker Compose with PostgreSQL 16, MinIO, the FastAPI backend, the worker, the React frontend (nginx) and a TLS edge nginx.
Files: `deploy/digitalocean/` (compose overlays, nginx templates, env templates, systemd units, backup script, Docker log config), `scripts/check_env.py`, `scripts/verify_no_preview_deps.sh`, `backend/app/cli.py` (`create-admin`).

```
Internet ─▶ DO Cloud Firewall (80/443, 22 from admin IPs) ─▶ ufw ─▶ edge nginx :80/:443 (Let's Encrypt)
                                                              ├─▶ frontend nginx :8080 (SPA, CSP)
                                                              └─▶ backend :8001 (/api) ─▶ postgres :5432 (127.0.0.1 only)
                                                                  worker ────────────────▶ minio :9000/9001 (127.0.0.1 only)
Block Storage: /srv/ironvision/{postgres,minio,letsencrypt,certbot} and /srv/ironvision/backups
```

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
| MinIO (single node) | ~150–300 MiB | | ~300–500 MiB | | **estimate** (MinIO not run in the pod) |
| Docker Engine + containerd | ~100–150 MiB | | | | **estimate** |
| Ubuntu 24.04 base | ~300–400 MiB | | | | **estimate** |
| **Frontend production build** (`yarn build`) | — | — | **1,730 MiB** | 1,565 MiB | measured, 11.2 s with warm `node_modules` |
| Backend image build (`pip install`) | — | — | ~400–600 MiB | | **estimate** |

¹ PostgreSQL processes could not be read for PSS in the pod, so RSS is summed per process. This counts `shared_buffers` (128 MB by default) once for every backend, which overstates real usage. A realistic unique footprint under this load is about 400–600 MiB.

Database size after demo reset is 79 MB (reference catalogs plus synthetic data). Evidence objects take 25 MB. A 5,000-finding scan adds about 1.7 MB of evidence plus its rows.

**Steady state under load:** about 0.35 GB (OS) + 0.15 GB (Docker) + 0.6 GB (Postgres) + 0.23 GB (backend) + 0.17 GB (worker) + 0.4 GB (MinIO) + 0.05 GB (nginx), which is about **1.95 GB**.
**Peak:** steady state plus an image build on the same host. The frontend build alone is about 1.7 GB, plus yarn install, which comes to about **4–4.5 GB**.

| Tier | Droplet | Reasoning |
|---|---|---|
| **Minimum** | **4 GB RAM / 2 vCPU** (Basic or Premium), 80 GB disk + Block Storage | Runs the stack with about 2 GB headroom. Image builds need **4 GB swap**. Alternatively, build images elsewhere (CI/registry) and only `pull` on the Droplet. One uvicorn worker. No ClamAV. |
| **Preferred** | **8 GB RAM / 4 vCPU** (General Purpose or Premium), 160 GB disk + Block Storage | Builds on the host without swap pressure. Room for 2–4 uvicorn workers, larger `shared_buffers` (1–2 GB), concurrent ingest plus AI drafting, and the optional `--profile clamav` (clamd needs about 1.5–3 GB) or `--profile monitoring`. |

**Disk:**
- Root disk: OS about 10 GB; images and build cache about 6–10 GB (prune with `docker builder prune` after upgrades); Docker logs are capped at 5 × 10 MB per container.
- Block volume **ironvision-data**: 50 GB to start. That covers Postgres (start at 10 GB; grows with observations, about 1–2 GB/year for a mid-size portfolio, estimated) and MinIO evidence (raw scan files; estimate about 2–10 GB/year depending on scan cadence).
- Block volume **ironvision-backups**: at least retention days × (DB dump + evidence). 14 days × about 3 GB means 50 GB to start.
- Grow volumes online with `resize2fs` after resizing in DigitalOcean.

**Swap:** on the 4 GB tier, add a 4 GB swapfile (commands in §2) with `vm.swappiness=10`. On the 8 GB tier, 2 GB of swap is a safety net.

**When to split services:**
- Move Postgres to DO Managed PostgreSQL (§12) when you need PITR, HA or standby replicas, or when the DB passes about 20 GB.
- Move evidence to Spaces/S3 (§12) when it passes about 50 GB or you need cross-region durability.
- Build images in CI and pull them on the Droplet if builds disturb production.
- Run staging on a **separate, smaller Droplet** (2–4 GB). Same-host staging is not recommended.

---

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

# 2.8 aws-cli (MinIO object sync for backups)
snap install aws-cli --classic
```

> **Docker and ufw:** ports published by Docker bypass ufw's INPUT rules, because Docker writes its own iptables chains. The overlay therefore publishes **only** 80/443 (edge) publicly. Postgres (5432) and MinIO (9000/9001) bind to **127.0.0.1**; the backend (8001) and frontend (8080) are not published at all. The DO Cloud Firewall (§3) is the authoritative perimeter.

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
sudo install -d -m 750 -o root -g root /srv/ironvision/minio         # minio runs as root by default
sudo install -d -m 755 /srv/ironvision/letsencrypt /srv/ironvision/certbot/www
sudo install -d -m 750 -o ironvision -g ironvision /srv/ironvision/backups
```

### 2.11 Clone, configure, build, migrate, start
```bash
sudo install -d -o ironvision -g ironvision /opt/ironvision && cd /opt/ironvision
git clone <your-git-remote>/ironvision-ai.git app && cd app && git checkout <release-tag>
cp deploy/digitalocean/.env.production.example deploy/digitalocean/.env.production && chmod 600 deploy/digitalocean/.env.production
# generate secrets (paste into the env file; never commit it)
for k in POSTGRES_PASSWORD MINIO_ROOT_PASSWORD JWT_SECRET; do echo "$k=$(openssl rand -base64 48 | tr -d '\n=+/' | cut -c1-48)"; done
echo "SECRET_STORE_KEY=$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
python3 scripts/check_env.py deploy/digitalocean/.env.production        # must print RESULT: PASS
sudo cp deploy/digitalocean/docker-daemon.json /etc/docker/daemon.json && sudo systemctl restart docker   # log rotation

export COMPOSE="docker compose -p ironvision --env-file deploy/digitalocean/.env.production -f docker-compose.yml -f docker-compose.prod.yml -f deploy/digitalocean/docker-compose.do.yml"
$COMPOSE config -q && $COMPOSE build
# TLS first (see §4), then:
$COMPOSE up -d            # postgres → minio-init → migrate (alembic upgrade head + reference content) → backend/worker/frontend/edge
$COMPOSE ps && curl -fsS https://$APP_DOMAIN/api/v1/ready
```

**Start on boot:** every long-running service uses `restart: unless-stopped`. The optional systemd unit adds an env check and ordered start/stop:
```bash
sudo cp deploy/digitalocean/systemd/ironvision*.service deploy/digitalocean/systemd/ironvision*.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now ironvision.service ironvision-backup.timer ironvision-certbot-renew.timer
```

---

## 3. Networking

*Not yet executed on DigitalOcean.*

**DNS** (at your DNS provider or DO Networking → Domains):
| Record | Name | Value |
|---|---|---|
| A | `app.example.gov` | Droplet IPv4 (better: a DO Reserved IP) |
| AAAA | `app.example.gov` | Droplet IPv6 (only if IPv6 is enabled on the Droplet) |
| A/AAAA | `staging.app.example.gov` | the **staging** Droplet |
| CAA | `example.gov` | `0 issue "letsencrypt.org"` (plus `0 iodef "mailto:security@example.gov"`) |

No separate API host is needed: the SPA calls `/api` on the same origin (`REACT_APP_BACKEND_URL` is empty). Only add `api.example.gov` if you deliberately split origins; in that case also extend `CORS_ORIGINS` and the frontend CSP `connect-src`.

**DigitalOcean Cloud Firewall** (attach it to the Droplet by tag):
| Direction | Protocol/Port | Source/Destination |
|---|---|---|
| Inbound | TCP 22 | admin IPs / VPN CIDR only |
| Inbound | TCP 80, 443 | `0.0.0.0/0`, `::/0` |
| Inbound | ICMP | optional |
| Inbound | **5432, 9000, 9001, 8001, 8080, 3000** | **not opened** |
| Outbound | TCP 443, 80, UDP 53, UDP 123 | all (package updates, ACME, IdP/AI APIs, NTP) |

The matching ufw rules are in §2.5. **MinIO console:** reach it only through an SSH tunnel: `ssh -L 9001:127.0.0.1:9001 ironvision@<droplet>`, then open http://localhost:9001.

---

## 4. TLS reverse proxy (edge nginx + Let's Encrypt)

*Not yet executed on DigitalOcean.* The DO overlay replaces the generic `deploy/nginx/edge.conf` with `deploy/digitalocean/nginx/edge.conf.template`, which uses the official `nginx:1.27-alpine` image. The image runs envsubst on the template, and only `${APP_DOMAIN}` is substituted.

```bash
# first certificate: standalone (port 80 must be free, so before `up`)
docker run --rm -p 80:80 -v /srv/ironvision/letsencrypt:/etc/letsencrypt certbot/certbot:v2.11.0 certonly --standalone \
  -d "$APP_DOMAIN" --email you@example.gov --agree-tos --no-eff-email --key-type ecdsa
$COMPOSE up -d edge
# renewals: webroot through the running edge, then reload (the timer installed in §2 runs this twice a day)
$COMPOSE --profile certbot run --rm certbot renew --webroot -w /var/www/certbot --dry-run
```

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
| MinIO evidence | `/data` | `/srv/ironvision/minio` | root, 750 |
| Let's Encrypt | `/etc/letsencrypt` | `/srv/ironvision/letsencrypt` | root |
| ACME webroot | `/var/www/certbot` | `/srv/ironvision/certbot/www` | root, 755 |
| Backups | — (host) | `/srv/ironvision/backups` (2nd volume) | ironvision, 750 |

Named volumes from the base compose file (`pgdata`, `miniodata`) are replaced with `!override` bind mounts. DO volume snapshots of `ironvision-data` are a useful **complement** to `scripts/backup.sh`, not a replacement. A snapshot of a running Postgres is only crash-consistent; dumps are portable and verifiable.

---

## 6. Environment templates

- `deploy/digitalocean/.env.production.example` and `.env.staging.example` list **every** variable the backend reads, plus the compose/edge/backup variables. Completeness is enforced by the test `test_env_templates_cover_every_variable_the_code_reads`.
- Preview-only variables (`EMERGENT_LLM_KEY`, `EMERGENT_AI_VENDOR`) are deliberately absent.
- Secrets are generated with the commands in §2.11.
- `scripts/check_env.py <file>` checks the file and **fails** on:
  - a missing required variable;
  - a weak or placeholder `JWT_SECRET`, `POSTGRES_PASSWORD` or `MINIO_ROOT_PASSWORD`;
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
- `deploy/digitalocean/backup-offsite.sh` runs `scripts/backup.sh` (pg_dump custom format, MinIO sync via aws-cli, and `manifest.json` with SHA-256 hashes, alembic revision and audit-chain head).
- It keeps `BACKUP_RETENTION_DAYS` of backups locally, then copies off the Droplet with `rclone copy --checksum` and verifies with `rclone check`.
- Configure rclone once for Spaces or any S3: `rclone config create spaces s3 provider DigitalOcean endpoint nyc3.digitaloceanspaces.com access_key_id … secret_access_key …`.
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
cd /opt/ironvision/app && sudo systemctl start ironvision-backup.service              # 1. backup first (record the dir)
git fetch --tags && git checkout <new-tag>                                          # 2. code
python3 scripts/check_env.py deploy/digitalocean/.env.production                    # 3. new vars?
$COMPOSE build && $COMPOSE run --rm migrate && $COMPOSE up -d                       # 4. build, migrate, restart
curl -fsS https://$APP_DOMAIN/api/v1/ready && curl -fsS https://$APP_DOMAIN/api/v1/health | jq .status   # 5. verify
docker image prune -f && docker builder prune -f --filter until=168h
```

**Rollback:** run `git checkout <previous-tag> && $COMPOSE build && $COMPOSE up -d`. If the new release ran migrations, **prefer restoring the pre-upgrade backup** into a fresh DB (`restore.sh`) over `alembic downgrade`, because downgrades can drop columns and data (see MIGRATION_PROCEDURE.md).

**Logs:** `docker-daemon.json` and the per-service `logging` blocks cap each container at 5 × 10 MB of json logs. View them with `$COMPOSE logs -f --since 1h backend worker`.

---

## 8. Direct AI provider (no Emergent)

```env
AI_PROVIDER=anthropic           # or openai_compatible, or none
AI_MODEL=<model id from your provider>
ANTHROPIC_API_KEY=<key>
# openai_compatible (self-hosted vLLM/Ollama/LiteLLM or any OpenAI-style endpoint):
OPENAI_COMPAT_BASE_URL=http://llm.internal:8000/v1
OPENAI_COMPAT_API_KEY=<key or empty>
```
- Verify: Admin → **AI provider check** (button), or `curl -fsS -X POST -H "Authorization: Bearer <platform admin token>" https://$APP_DOMAIN/api/v1/ai/health`. This sends a connectivity probe through the configured provider and records it in the audit log. `GET /api/v1/admin/ai-settings` shows the active provider and model.
- Disable AI entirely with `AI_PROVIDER=none`. AI draft buttons then show an honest "AI not configured" state, and nothing is ever auto-approved.
- The Emergent adapter is **not used in production**. Its library (`emergentintegrations`) is not in `requirements.prod.txt`. `AI_PROVIDER=emergent` is rejected by `check_env.py`, and the backend refuses to build it when `APP_ENV` is staging or production.

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
cp deploy/digitalocean/.env.staging.example deploy/digitalocean/.env.staging && chmod 600 deploy/digitalocean/.env.staging
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

### 12.2 S3-compatible storage (DO Spaces, AWS S3, others)
- Uses the existing `STORAGE_DRIVER=s3` with `S3_ENDPOINT_URL` (Spaces: `https://nyc3.digitaloceanspaces.com`), `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`.
- The client uses **path-style** addressing and SigV4, which Spaces, MinIO and S3 all accept. Virtual-host style would need a code change and is not required.
- **Encryption at rest:** Spaces always encrypts at rest, but SSE-KMS and customer keys are not available there. AWS S3 supports SSE-S3/SSE-KMS through a bucket default-encryption policy, which needs no code change. MinIO needs KES for SSE.
- **Copy:**
  1. `rclone sync minio:ironvision-evidence spaces:ironvision-evidence --checksum`, then `rclone check`.
  2. Run a `backup.sh` into the new store's sibling, then `restore.sh` verification: each evidence object's SHA-256 must match the DB ledger, and the audit chain must verify.
  3. Switch the env, `$COMPOSE up -d`, and spot-check evidence downloads in the Evidence Ledger.
- **Rollback:** revert `S3_ENDPOINT_URL` and the keys; MinIO stays intact until sign-off.

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
