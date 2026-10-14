# Security – IronVision AI

IronVision AI is **not** FedRAMP-authorized, has **no** ATO, and has **not** been assessed for IL4–IL6 or CUI. Nothing here claims FIPS 140-3 validation or CAC/PIV conformance. This file describes the controls that exist in the code and how to deploy them.

## Authentication (`AUTH_PROVIDERS`)
| Provider | Status | Notes |
|---|---|---|
| `dev_password` | Simulated, DEV ONLY | bcrypt-hashed synthetic demo accounts. The login picker is shown **only** when this provider is enabled. `docker-compose.prod.yml` turns it off. |
| `oidc` | Implemented. Automated test against a **mocked** IdP (`test_oidc_code_pkce_flow_with_mocked_idp`: RS256-signed ID token, PKCE verifier sent, state replay and bad nonce rejected) | Authorization Code + PKCE (S256), `state` + `nonce`, discovery issuer check, JWKS signature check, `iss`/`aud`/`exp` validation, allowed algorithms from `OIDC_ALLOWED_ALGS`. Users must already be provisioned (matched by email claim, then linked by `issuer|sub`). **Roles always come from IronVision AI RBAC, never from IdP claims.** A Keycloak dev realm is included (`--profile keycloak`). It has **not** been run against a real IdP in this environment. |
| `mtls_header` | Stub for CAC/PIV fronted by a TLS proxy | Accepts identity headers (`MTLS_HEADER_VERIFY/DN/EDIPI`) **only** from IPs listed in `MTLS_TRUSTED_PROXIES`, and only when verify = `SUCCESS`. The proxy must overwrite these headers (see `deploy/nginx/edge.conf`). The proxy does certificate path validation and revocation checking (OCSP/CRL). |

## Sessions
- Server-side session rows. The JWT carries a session id (`sid`), and every request checks that the session is active.
- Idle timeout `SESSION_IDLE_MINUTES` (30) and absolute lifetime `SESSION_ABSOLUTE_HOURS` (12).
- Refresh tokens rotate on every use and are stored as hashes. Logout revokes the session. All of this is covered by `tests/test_phase5_security.py`.
- Lockout: 5 consecutive failures lock an identifier for 15 minutes (`app/security/login_guard.py`). Lockouts are audited.

## Web hardening (`app/security/web.py`)
- Headers on every API response: `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'` (the docs UI gets a relaxed CSP), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cache-Control: no-store`, plus HSTS over HTTPS.
- CORS uses the exact-origin allowlist in `CORS_ORIGINS`. `*` is refused (startup error + `check_env`), and `allow_credentials` is false (auth is bearer-token, not cookies), so a wildcard is never combined with credentials. Origins not on the list get no `Access-Control-Allow-Origin` header, and their preflights are rejected (400).
  - **Preview caveat:** the Emergent preview ingress adds `access-control-allow-origin: *` (plus allow-headers/methods `*`) to every proxied response, on top of what the app sends. This can't be changed from inside the pod. It doesn't expose sessions, because tokens live in `sessionStorage` and are sent as `Authorization` headers; no cookies are used. DigitalOcean / Docker Compose deployments use the repo's Caddy/Nginx edge, which adds no CORS headers, so only the app's allowlist applies there.
- Rate limits, per client IP: `RATE_LIMIT_AUTH` (20/60 s) and `RATE_LIMIT_UPLOAD` (30/60 s). Rejections return 429 with `Retry-After`. Limits are kept in memory **per process**, so a multi-replica deployment needs a shared limiter at the proxy or in Redis. `X-Forwarded-For` is trusted only when `TRUST_PROXY_HEADERS=true`.

## Uploads (`app/services/upload_security.py`)
Each upload is checked against an extension allowlist per upload kind, magic bytes, and `MAX_UPLOAD_MB`. XML is parsed with `defusedxml` (no DTD, entities, or external references). Archives are checked for zip-bomb ratio, member count, and path traversal. File names are never used as storage paths: storage is content-addressed by SHA-256. With `UPLOAD_SCANNER=clamav` the file is streamed to clamd (`--profile clamav`) and infected files are rejected. With `none`, evidence is recorded as `not_scanned`. The ClamAV path has **not** been run against a live clamd here.

## Authorization and tenant isolation
- RBAC is scoped to the system or org. Denials are audited (`authz.denied`).
- Every query is filtered by the caller's organization. `test_tenant_isolation` checks that a tenant-B user gets 403/404 or empty results for tenant-A systems, POA&Ms, findings, search, and audit.
- Separation of duties: no self-approval, ISSO cannot accept risk, AO-only decisions, SCA independence.
- Every mutating route (POST/PUT/PATCH/DELETE) declares a permission dependency: `require_permission`, `require_object_permission` (system resolved from the addressed object, 404 across tenants) or `require_body_permission`, or `self_scoped` for the caller's own records. `tests/test_route_authz.py` enumerates the router and fails on any route without one; only login/refresh/mTLS login/logout/signup are public.
- Finding dispositions (false positive, not applicable, out of scope, informational, no control mapping) always create a review under the active decision rule; nothing changes until approved. POA&M status cannot change while a closure/risk review is pending, and later due dates need an extension/waiver request. eMASS "keep local" conflict resolution needs a fresh ISSM approval.
- Sign-up bot checks: an off-screen trap field with an unusual name (`iv_hp_fax_only`, autocomplete off, excluded from password managers/tab order/a11y tree) plus a signed form token from `GET /auth/signup/start` enforcing `SIGNUP_MIN_SECONDS` (default 2). Bot rejections show a generic "reload and try again"; every rejection is audited (`auth.signup` denied, `details.reason`, peer + X-Forwarded-For chain). User-fixable cases (password rules, duplicate email, rate limit with minutes remaining) get specific messages. Only successful sign-ups count toward the limit.
- Behind a CDN/load balancer, list every proxy hop in `TRUSTED_PROXIES` (e.g. Cloudflare ranges + the LB address) so the real client IP is used; otherwise all users share the edge address.
- `SIGNUP_RATE_LIMIT_EXEMPT_CIDRS` (empty by default) exempts exact test-runner addresses from the sign-up limit; `check_env` warns if set in production.

## Secrets and encryption
- `SECRET_STORE_BACKEND=env_key`: Fernet (AES-128-CBC + HMAC-SHA256) with `SECRET_STORE_KEY`. Used for connector credentials such as eMASS.
- `SECRET_STORE_BACKEND=vault`: HashiCorp Vault KV v2 (`VAULT_ADDR` with `VAULT_TOKEN`, or AppRole `VAULT_ROLE_ID`/`VAULT_SECRET_ID`). Covered by `test_vault_secret_store_with_mocked_client` (mocked `hvac` client only; never run against a live Vault). The DB stores only a `vault:<path>` reference. Old `env_key` ciphertexts stay readable during migration.
- AWS Secrets Manager / KMS: not implemented. Add a class with the same `put/get` interface in `app/services/secrets.py`, or inject secrets as env vars via ECS/EKS secret mounts.
- Encryption at rest: use encrypted volumes or managed storage (RDS/Aurora with KMS, S3 SSE-KMS, LUKS). TLS in transit is handled by the edge proxy (`docker-compose.prod.yml`).
- FIPS: the code uses only standard algorithms (SHA-256, AES, HMAC, RSA/ECDSA via `cryptography`). FIPS 140-3 operation requires a FIPS-validated OpenSSL provider in the base image (for example a RHEL UBI FIPS image) and host FIPS mode. **This is not done or validated here.**

## Audit
The audit log is append-only and hash-chained. The retention job refuses to purge `audit_events`. Every purge supports a dry run and is itself audited.

## Scanning (`scripts/security_scan.sh` → `docs/security/`)
| Tool | Latest result |
|---|---|
| pip-audit (`requirements.prod.txt`) | No known vulnerabilities (after FastAPI 0.143.0 / Starlette 1.7.0 upgrade) |
| Bandit (`app/`) | High 0, Medium 0, Low 7 (see `docs/security/bandit.txt`; not individually triaged) |
| yarn audit (frontend) | 0 Critical, 12 High, 13 Moderate. **All are in `react-scripts` build-time tooling** (`braces` with no upstream fix, and `svgo` 1.x via `@svgr`). None ship in the static nginx bundle. Remediation: migrate off CRA (Vite) – backlog. |
| Trivy (images) | Not run in this environment (no Docker). Runs in CI (`.github/workflows/ci.yml`). |

## Reporting
Report suspected vulnerabilities privately to the IronVision security contact. Do not open public issues.


## Sandbox tenants, self sign-up and persona mode (demo feature)
- One-click demo login (`ALLOW_DEMO_LOGIN`, `POST /api/v1/auth/demo-login`) issues a normal session (same idle/absolute timeouts) for the **shared, synthetic** `demo@ironvision.ai` workspace, which resets nightly. No password is sent from or embedded in the browser. Disabled → 404 and the button is hidden. `check_env` refuses it in production unless `ALLOW_DEMO_LOGIN_IN_PRODUCTION=true` (then warns). Rate-limited per real client IP (`DEMO_LOGIN_RATE_LIMIT`, default 30/hour) and audited (`auth.demo_login`, client IP). The demo account has no password/email-change or self-delete paths, and inviting users is refused in the demo tenant.
- Self sign-up (`ALLOW_SIGNUP`) is **off in production** (`check_env.py` warns if it is on). It needs local password accounts, is rate-limited per real client IP, has bot checks (trap field + minimum time-to-submit), and enforces password strength (12+ characters, mixed case, digit, symbol). New sign-up tenants start clean (no data); only the demo account is seeded. Login lockout and session rules are unchanged.
- Each sign-up gets an isolated sandbox tenant. Tenant isolation is covered by `tests/test_sandbox.py`.
- **Persona mode** (`sandbox_personas=true`) can only be set on sandbox tenants. `/sandbox/act-as` returns 403 for every other tenant.
  - Actions run as synthetic persona identities, so requester ≠ decider and SCA ≠ implementer are enforced.
  - Every audit event records `operated_by` = the real user.
  - Persona approvals are labelled "simulated signature – not CAC/PIV · sandbox persona".
  - **One human holds all personas, so this is NOT acceptable separation of duties for production.** Production tenants keep strict real-identity SoD and real role assignments.
- Sandbox data is purged after `SANDBOX_INACTIVITY_DAYS` without activity: tenant rows, evidence objects and accounts. A platform audit record keeps only the tenant id and counts. Purge never applies to non-sandbox tenants.

## AI data handling (`AI_PROVIDER=openrouter` / `openai_compatible` / `anthropic`)
- Prompts contain control context, evidence metadata, policy text and finding titles. With `openrouter` they go to OpenRouter **and onward to the provider of the selected model**. Choose models and providers that fit the data policy (OpenRouter provider routing, data-retention and "no training" settings), and prefer self-hosted `openai_compatible` endpoints for data that must not leave your boundary.
- Dev and staging use **synthetic data only**.
- Only one key is used (`OPENAI_COMPAT_API_KEY` for OpenRouter). It is sent only as a bearer header. It is never logged, returned by the API or shown in the UI; the admin page shows only "configured". `ANTHROPIC_API_KEY` is never read in openrouter mode.
- Every call is recorded in `ai_interactions` (provider, model, prompt id/version, input SHA-256, token usage, validation status). Output is schema-validated and never auto-approved; human approval stays locked on.

