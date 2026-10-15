# Keycloak authentication – demo.ironvisionai.com

IronVision AI signs users in with OpenID Connect against a **self-hosted Keycloak 26.8.1** that runs next to the app on the same
Droplet. Keycloak lives on its own hostname, `auth.demo.ironvisionai.com`, and has its own database and role on the existing
Postgres server. IronVision never sees Keycloak passwords. IronVision RBAC alone decides roles.

> STATUS: implemented and tested against a real Keycloak 26.8.1 in the build pod (see §11). It has not been run on DigitalOcean
> yet. The customer reviews the change, pushes it and runs §10.

## 1. Architecture

```
browser ──https──► edge nginx ──► frontend / backend            (demo.ironvisionai.com)
        ──https──► edge nginx ──► keycloak:8080 (internal)      (auth.demo.ironvisionai.com: only /realms/ironvision-demo, /resources, /js)
backend ──http───► keycloak:8080 (token endpoint, JWKS; internal network)
postgres: database aegisrmf (app, unchanged) + database keycloak (role keycloak, created by keycloak-db-init, never dropped)
```

* **Flow:** Authorization Code + PKCE S256 with a confidential client (`ironvision-app` plus its secret). State, nonce and the PKCE verifier
  are stored in `oidc_pending` (single use, 5-minute TTL, DELETE … RETURNING). This survives backend restarts and works with
  more than one replica.
* **Token delivery:** the callback never puts tokens in a URL. It redirects to `/login?oidc_code=…`, a single-use code that
  expires after 60 seconds (only its SHA-256 is stored). The SPA swaps it for app tokens with `POST /api/v1/auth/oidc/exchange`.
* **Validation:** the ID token's signature (JWKS), `iss`, `aud`, `exp`, `iat`, `sub` and `nonce` (constant-time comparison) are
  all checked. Discovery is cached for 1 hour. JWKS is cached and refetched once when a `kid` is unknown (key rotation).
* **Logout:** `POST /auth/logout` revokes the app session. For OIDC sessions it also returns Keycloak's `end_session_endpoint`
  URL with `id_token_hint`, `client_id` and `post_logout_redirect_uri=https://demo.ironvisionai.com/login`. The SPA follows that
  URL, which ends the Keycloak SSO session too (RP-initiated logout).
* **Identity mapping:** a login succeeds only when an `auth_identities` row exists for `(issuer|sub)`. Users are **never**
  matched by e-mail. The email fallback only works with `OIDC_ALLOW_EMAIL_LINKING=true` in development/test. An unmapped
  identity gets HTTP 403 and an audit event `auth.login denied reason=identity_not_mapped`. Mappings are created only by the
  operator CLI (`keycloak-migrate`, `identity-map`). Each one records the Keycloak user id, `mapped_by`, `mapped_at` and
  `reason`, and writes an `identity.mapped` audit event. One Keycloak subject maps to exactly one app user (DB unique
  constraint). One app user has at most one identity per issuer. Admins can view mappings read-only under
  **Admin → Sign-in identity mappings**.

## 2. Realm configuration (applied by `python -m app.tools.keycloak_config`)

The configurator is idempotent. `plan` prints a diff with secrets masked, and `apply` executes it.

| Setting | Value |
|---|---|
| Realm | `ironvision-demo` (`KEYCLOAK_REALM`) |
| Client | `ironvision-app`: confidential, standard flow only. Implicit, direct grants, device and CIBA are off. PKCE S256 required. Exact redirect `https://demo.ironvisionai.com/api/v1/auth/oidc/callback`, post-logout `https://demo.ironvisionai.com/login`, web origin `https://demo.ironvisionai.com` |
| Password policy | `length(12) and notUsername and notEmail and passwordHistory(5)` |
| Brute force | on. 5 failures, then a 60 s wait that grows to 15 min; quick-login check on |
| Registration / reset-by-email / verify-email | off / off (no SMTP) / off |
| Tokens / sessions | access token 5 min. SSO idle = `SESSION_IDLE_MINUTES` (30), SSO max = `SESSION_ABSOLUTE_HOURS` (12), same as the app |
| OTP | TOTP (6 digits, 30 s). **Optional per user** (default conditional flow). `KEYCLOAK_REQUIRE_MFA=true` switches the realm to the `browser-otp-required` flow (OTP mandatory for everyone; required for a future `-prod` realm) |
| sslRequired | `external` |

Realm per environment: this deployment uses only `ironvision-demo`. A future customer production uses a separate realm
`ironvision-prod` on a separate deployment (§9).

## 3. Keycloak admin security

1. On the first `./deploy.sh`, Keycloak creates the temporary **bootstrap admin** (`KC_BOOTSTRAP_ADMIN_*`, generated into the env
   file). The configurator uses it **once** to:
   * create the service account client `ironvision-configurator` in master (client_credentials; roles `create-realm`, read-only
     master roles, and management roles for `ironvision-demo` only). Later runs authenticate with this account;
   * create the **named permanent admin** `KEYCLOAK_ADMIN_USERNAME` (role `admin`, required action **CONFIGURE_TOTP**);
   * make OTP **required** in the master browser flow (`browser-otp-required`);
   * **disable the bootstrap admin** (last step, only after everything else succeeded).
2. The public auth domain returns **403** for `/admin/` and `/realms/master/` unless the client IP is in
   `KEYCLOAK_ADMIN_ALLOWED_CIDRS`. That list is empty by default, so everyone is denied. Ports 9000 (health/metrics) are never
   proxied.
3. The admin console is reached **only through an SSH tunnel** to the loopback port:
   ```bash
   ssh -L 8081:127.0.0.1:8081 root@<droplet-ip>
   # then open http://localhost:8081/admin/  → log in as KEYCLOAK_ADMIN_USERNAME, enrol TOTP on first login
   ```
   Passwords: `python3 scripts/envget.py deploy/digitalocean/.env.production KEYCLOAK_ADMIN_PASSWORD` (on the Droplet only).

## 4. Credential management (audited, no secrets in the audit log, never automatic)

```bash
scripts/keycloak.sh user list                                   # username, enabled, OTP configured, required actions, mapped app user
scripts/keycloak.sh user set-password demo@ironvision.ai        # reads the new password from the terminal/stdin (>= 12 chars)
scripts/keycloak.sh user set-password someone@org --temporary   # must be changed at next login
scripts/keycloak.sh user rotate demo@ironvision.ai              # generates a new password → /srv/ironvision/secrets/rotated-credential-<ts>.csv (600); ends sessions
scripts/keycloak.sh user disable someone@org                    # also ends the user's Keycloak sessions
scripts/keycloak.sh user enable someone@org
scripts/keycloak.sh user reset-mfa someone@org                  # removes OTP credentials, forces TOTP enrolment at next login
scripts/keycloak.sh identity-list                               # all identity mappings with who/when/why
```

**Password reset procedure** (admin-driven, no e-mail): confirm the user's identity out of band, then run `user set-password <email>
--temporary` (or `rotate`) and hand over the new password through a separate channel. Delete any credential file afterwards.

## 5. Passwords and the migration

App passwords are stored as bcrypt hashes. Keycloak can't verify bcrypt without a third-party SPI, so **hashes are not migrated**.
Instead, every user Keycloak creates gets an **individual** random password (20 chars, unique per user; no shared password). By
default it is non-temporary, because the customer chose fixed demo credentials. `--temporary` forces a change at first login.
The passwords are written **once** to `/srv/ironvision/secrets/demo-credentials-<ts>.csv` (mode 600, root/uid 10001 only). They are
never logged, never committed to git, and stored nowhere else. Hand them out, then delete the file.

## 6. Migration runbook (separate, explicit step – `deploy.sh` never migrates users)

```bash
# 1) Dry run (read-only): table + JSON report (/srv/ironvision/secrets/keycloak-migrate-<ts>.json) + plan hash
scripts/keycloak.sh migrate
```
Example dry-run output (from the pod test run; e-mail addresses are synthetic):
```
EMAIL                                  ORG                    ACTIVE ROLES KC USER    ACTION             REASON
admin@aegisrmf.demo                    Demo Agency (synthet…  yes    1     -          create             no Keycloak user yet
ao@aegisrmf.demo                       Demo Agency (synthet…  yes    1     2b0f6c1e-4 CONFLICT           Keycloak user already mapped to another app user
assessor@aegisrmf.demo                 Demo Agency (synthet…  yes    2     -          create             no Keycloak user yet
isso@aegisrmf.demo                     Demo Agency (synthet…  yes    3     -          create             no Keycloak user yet
old.user@agency.test                   Demo Agency (synthet…  no     1     -          skip               inactive (reactivate only with --reactivate)
summary: CONFLICT=1, create=3, skip=1
plan hash: 3f9a1c0d2e7b6a54
DRY RUN – nothing changed. To apply: --apply --create-identities --link [--reactivate a@x,b@y] --backup-ref <dir> --yes --plan-hash 3f9a1c0d2e7b6a54
```
Actions: `create` (new Keycloak user plus mapping), `link` (a Keycloak user with exactly this e-mail exists and is not mapped yet),
`ok` (already linked), `skip` (inactive), `CONFLICT` (duplicate app e-mails, several matching Keycloak users, Keycloak user already
mapped to someone else, username matches but e-mail differs, mapped Keycloak user missing). Conflicts block the apply until they
are resolved, or are skipped explicitly with `--allow-conflicts`.

```bash
# 2) Apply exactly the reviewed plan (the wrapper first runs the full backup: app DB + keycloak DB + objects; refuses if it fails)
scripts/keycloak.sh migrate --apply --create-identities --link --yes --plan-hash <hash-from-step-1>
#    reactivation is never implicit:            --reactivate someone@org,other@org
#    temporary passwords instead of fixed ones:  --temporary
# 3) Verify: scripts/keycloak.sh identity-list ; scripts/keycloak.sh user list
```
The apply refuses to run if the plan changed since the dry run (hash mismatch). It never deletes or modifies app users, orgs,
role assignments or data (except `--reactivate`). Re-runs are idempotent: done rows show `ok`.

```bash
# 4) Switch sign-in to Keycloak (explicit; backup of the env file first)
cp -p deploy/digitalocean/.env.production deploy/digitalocean/.env.production.bak-before-oidc
# edit: AUTH_PROVIDERS=oidc   (removes password sign-in, demo button and sign-up)
./deploy.sh
```

## 7. "Explore the demo": Option B, the demo launcher (approved, implemented)

`POST /api/v1/auth/demo-login` with `AUTH_PROVIDERS=oidc` runs a **server-side** password grant against the dedicated client
`ironvision-demo-launcher` using `KEYCLOAK_DEMO_PASSWORD`. Keycloak tokens never reach the browser. The visitor gets a normal
app session with provider label `oidc-demo`.

| Control | Where it is enforced |
|---|---|
| Client `ironvision-demo-launcher`: confidential, **direct access grants only**. Standard flow, implicit, service accounts, token exchange, device and CIBA are off. No redirect URIs, no web origins, `fullScopeAllowed=false`. The secret comes from env (`KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET`) | Keycloak (configurator) |
| Client-specific direct-grant flow `direct-grant-demo-launcher`: username → **deny unless `demo_launcher=true`** → password. Any other user is refused *before* the password is checked (live test: `isso@…` with its correct password gets 401) | Keycloak |
| `demo_launcher` is declared admin-only in the realm user profile (users can neither see nor set it) | Keycloak |
| Realm browser flow `ironvision-browser` (two steps: username, then password): users with `demo_launcher=true` are **denied right after the username step**. So no browser session, no account console (can't change password or e-mail), and no OTP enrolment for the demo user | Keycloak |
| **Lockout protection:** Keycloak counts even a deny-access result as a brute-force failure, and has no per-user exemption. The launcher user's Keycloak username is therefore an **unpublished handle** (`KEYCLOAK_DEMO_USERNAME`, generated, e.g. `demo-launcher-3f9a…`), and its e-mail is `<handle>@demo-launcher.invalid`. Visitors only know `demo@ironvision.ai`, which matches no Keycloak user, so there is nothing to lock (live test: 7 attempts → `numFailures=0`). **Never publish the handle.** If it leaks, rotate it: change `KEYCLOAK_DEMO_USERNAME`, then run `scripts/keycloak.sh apply` (creates a new launcher user) and `scripts/keycloak.sh migrate` (links it) | ops |
| The demo user has no realm default roles (no `manage-account`) and no OTP credential | Keycloak (configurator) |
| The ID token is validated (signature, iss, aud = launcher client, exp). An explicit identity mapping is required (403 `identity_not_mapped` otherwise). The mapped app user must be `demo@ironvision.ai`, whose roles live only in its own sandbox tenant (persona mode; admin personas are scoped to that sandbox). Other tenants are invisible (live test) | backend |
| The Keycloak session is **ended immediately** after login (backchannel logout with the refresh token; live test: 0 sessions). App logout then revokes the app session | backend |
| Gating: `ALLOW_DEMO_LOGIN=true` **and** oidc enabled **and** launcher configured, otherwise 404. Rate limits: per IP (`DEMO_LOGIN_RATE_LIMIT`) and global (`DEMO_LOGIN_GLOBAL_RATE_LIMIT`), otherwise 429. Keycloak errors return 503 (never a fallback). Audit `auth.demo_login` records the client IP and mode | backend |
| `check_env`: in production, `ALLOW_DEMO_LOGIN` is allowed only with `DEPLOYMENT_KIND=demo` and the launcher vars present. A customer deployment refuses it. `ALLOW_INSECURE_PRODUCTION` is not involved | check_env |

Rotate the demo password with `scripts/keycloak.sh rotate-demo`. It sets a new password in Keycloak, writes it into the env file
in place (backup, mode 600), and recreates the backend.

### Option C (future design – NOT implemented): ephemeral per-visitor users
Each visit would create a temporary Keycloak user and a fresh sandbox tenant (random handle, random password, attribute
`demo_launcher=true`, expiry attribute), log in server-side through the same launcher flow, and delete both after N hours with a
cleanup job. Benefits: no shared account, full isolation between visitors, nothing worth locking. Costs: the backend needs a
narrowly scoped `manage-users` service account (a privilege the app currently does not have), user and tenant cleanup jobs, and
growth/abuse limits (CAPTCHA, a global cap). Revisit if the demo becomes high-traffic or public marketing.

## 8. Environment variables

`AUTH_DOMAIN`, `KEYCLOAK_REALM`, `KEYCLOAK_REALM_DISPLAY_NAME`, `KEYCLOAK_REQUIRE_MFA`, `KEYCLOAK_DB_NAME`, `KEYCLOAK_DB_USER`,
`KEYCLOAK_DB_PASSWORD`*, `KEYCLOAK_DB_INIT_URL`, `KC_BOOTSTRAP_ADMIN_USERNAME`, `KC_BOOTSTRAP_ADMIN_PASSWORD`*,
`KEYCLOAK_ADMIN_USERNAME`, `KEYCLOAK_ADMIN_PASSWORD`*, `KEYCLOAK_CONFIGURATOR_CLIENT_ID`, `KEYCLOAK_CONFIGURATOR_CLIENT_SECRET`*,
`KEYCLOAK_ADMIN_ALLOWED_CIDRS`, `KEYCLOAK_ADMIN_URL`, `KEYCLOAK_URL`, `AUTH_CERT_FULLCHAIN_PATH`, `AUTH_CERT_KEY_PATH`, `CREDENTIALS_DIR`,
`DEPLOYMENT_KIND` (demo|customer), `KEYCLOAK_DEMO_USERNAME`* (unpublished handle), `KEYCLOAK_DEMO_PASSWORD`*,
`KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID`, `KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET`*, `DEMO_LOGIN_GLOBAL_RATE_LIMIT`,
`OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`*, `OIDC_REDIRECT_URI`, `OIDC_POST_LOGOUT_REDIRECT_URI`, `OIDC_ALLOW_EMAIL_LINKING`
(dev only). Variables marked * are generated by `gen_env_secrets` when empty and never overwritten. `check_env` enforces the
issuer = `https://AUTH_DOMAIN/realms/KEYCLOAK_REALM`, https issuer/redirect/post-logout URLs, a client secret in staging and
production, secret strength, valid CIDRs (no `0.0.0.0/0`), named admin ≠ bootstrap admin, and MFA for `-prod` realms.

## 9. Future customer production (`app.ironvisionai.com`) – templates only, NOT deployed

`deploy/digitalocean/env.customer-production.template` (and `.env.customer-production.example`): separate Droplet or compose
project, separate Postgres DB/role (`ironvision_prod`, `keycloak_prod`), separate bucket, **new secrets** (never copied from the
demo), realm `ironvision-prod` with `KEYCLOAK_REQUIRE_MFA=true`, `AUTH_PROVIDERS=oidc`, no demo seed, no demo login, no sign-up,
no demo accounts. Its auth hostname would be e.g. `auth.app.ironvisionai.com`.

## 10. Droplet steps (demo.ironvisionai.com)

1. DNS: create **A record `auth.demo.ironvisionai.com` → the Droplet public IPv4** (same IP as `demo.ironvisionai.com`). Check it:
   `getent ahostsv4 auth.demo.ironvisionai.com`.
2. Get the code, from inside your checkout (customer: `/opt/ironvision/IronVision-AI`; any path works):
   `cd /opt/ironvision/IronVision-AI && git pull` (or `cd "$(git rev-parse --show-toplevel)" && git pull`).
3. Add Keycloak (in-place env additions with a backup; empty secrets generated; sign-in mode unchanged):
   ```bash
   ./deploy.sh --set-auth-domain auth.demo.ironvisionai.com
   ```
   Deploy order: backup → postgres → keycloak-db-init → keycloak → `keycloak_config` plan (applied automatically only if the
   realm is absent; later changes use `./deploy.sh --apply-realm` or `scripts/keycloak.sh apply`) → TLS for both domains → app →
   public checks (both certificates, `/api/v1/ready`, OIDC discovery, `/admin` → 403).
4. Admin: SSH tunnel (§3) → log in as `KEYCLOAK_ADMIN_USERNAME` → enrol TOTP.
5. Users: `scripts/keycloak.sh migrate` (dry run) → review → apply with the plan hash (§6).
6. Switch: set `AUTH_PROVIDERS=oidc` (§6 step 4) → `./deploy.sh`. With `ALLOW_DEMO_LOGIN=true` and `DEPLOYMENT_KIND=demo` the
   Explore button uses the launcher (§7). The demo row in `migrate` must show `link` (the launcher user is created by the realm apply).

### Verification
```bash
curl -s https://auth.demo.ironvisionai.com/realms/ironvision-demo/.well-known/openid-configuration | python3 -m json.tool | head
curl -s -o /dev/null -w '%{http_code}\n' https://auth.demo.ironvisionai.com/admin/master/console/     # 403
curl -s -o /dev/null -w '%{http_code}\n' https://auth.demo.ironvisionai.com/realms/master/            # 403
scripts/keycloak.sh plan                                                                              # "no changes (in sync)"
docker compose --env-file deploy/digitalocean/.env.production ps keycloak                             # healthy
```

### Rollback
* **Sign-in:** restore the env backup (`.env.production.bak-before-oidc`, or the `.bak-<ts>` files written by `--set-auth-domain`
  and set_domain), so `AUTH_PROVIDERS` is back to the previous value. Then run `./deploy.sh`. The app database and the
  `auth_identities` rows are left alone. Mappings are inert without the oidc provider, so password sign-in works exactly as before.
* **Keycloak data:** every backup holds `keycloak.dump`. To restore it:
  `docker compose … stop keycloak` → `pg_restore --clean --if-exists -d postgresql://keycloak:<pw>@127.0.0.1:5432/keycloak <backup>/keycloak.dump` → start keycloak.
* **Remove Keycloak completely:** set `AUTH_DOMAIN=` and run `./deploy.sh` (the overlay is no longer applied). The `keycloak`
  database is **kept**. Drop it manually only if you are sure you no longer need it.
* Migration 0012 only adds two tables and one nullable column. Nothing is dropped.

## 11. Tests

* `tests/test_keycloak_live.py`: **real Keycloak 26.8.1** (official tarball + Temurin JDK 21, Postgres DB `keycloak_test`), real
  HTTP, scripted browser through Keycloak's login pages. Covers: configurator apply/idempotency/drift; migration dry-run, conflicts,
  plan-hash, backup refusal, apply, unique passwords in the 600 CSV, idempotent re-run; OIDC login and role enforcement; invalid
  credentials; unmapped identity → 403 and audit; OTP enrolment and TOTP login (pyotp); logout ends the Keycloak session; idle
  expiry; cross-tenant denial; Keycloak and backend restart mid-session followed by re-login. Run with
  `KEYCLOAK_LIVE_URL=… pytest -n 0 tests/test_keycloak_live.py`. Skipped when no Keycloak is reachable.
* `tests/test_keycloak_infra.py`: compose overlay, edge auth block (and real nginx in front of the live Keycloak: `/admin` and
  `/realms/master` → 403), TLS for two domains (fake certbot/DNS), `--set-auth-domain`, secrets generation, check_env rules,
  demo-login 404, mapping conflicts, dev-only e-mail linking, one-time code expiry, RP-logout URL.
