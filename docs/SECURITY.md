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
- CORS uses the exact-origin allowlist in `CORS_ORIGINS`.
- Rate limits, per client IP: `RATE_LIMIT_AUTH` (20/60 s) and `RATE_LIMIT_UPLOAD` (30/60 s). Rejections return 429 with `Retry-After`. Limits are kept in memory **per process**, so a multi-replica deployment needs a shared limiter at the proxy or in Redis. `X-Forwarded-For` is trusted only when `TRUST_PROXY_HEADERS=true`.

## Uploads (`app/services/upload_security.py`)
Each upload is checked against an extension allowlist per upload kind, magic bytes, and `MAX_UPLOAD_MB`. XML is parsed with `defusedxml` (no DTD, entities, or external references). Archives are checked for zip-bomb ratio, member count, and path traversal. File names are never used as storage paths: storage is content-addressed by SHA-256. With `UPLOAD_SCANNER=clamav` the file is streamed to clamd (`--profile clamav`) and infected files are rejected. With `none`, evidence is recorded as `not_scanned`. The ClamAV path has **not** been run against a live clamd here.

## Authorization and tenant isolation
- RBAC is scoped to the system or org. Denials are audited (`authz.denied`).
- Every query is filtered by the caller's organization. `test_tenant_isolation` checks that a tenant-B user gets 403/404 or empty results for tenant-A systems, POA&Ms, findings, search, and audit.
- Separation of duties: no self-approval, ISSO cannot accept risk, AO-only decisions, SCA independence.

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
