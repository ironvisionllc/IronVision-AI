# API

- Base path `/api/v1`. JSON. Authenticate with `Authorization: Bearer <access_token>`.
- Interactive docs: `/api/docs` (Swagger) and `/api/redoc`.
- The machine-readable spec is committed at **`docs/openapi.json`** (134 paths). Regenerate it with `make openapi`.

## Auth
| Method | Path | Notes |
|---|---|---|
| GET | `/auth/provider` | Enabled providers, `dev_password_enabled`, `oidc_enabled`, dev account picker (dev only) |
| POST | `/auth/login` | dev_password only. Rate limited and locks out after 5 failures. |
| GET | `/auth/oidc/login` → IdP → `/auth/oidc/callback` | Code + PKCE. Tokens are returned to the SPA in the URL fragment. |
| POST | `/auth/mtls/login` | Trusted proxy only |
| POST | `/auth/refresh` | Rotates the refresh token |
| POST | `/auth/logout` | Revokes the server session |
| GET | `/auth/me` | Current user, roles, permissions |

## Main resource groups
Systems and workbench (`/systems/{id}/workbench/*`), uploads and evidence (`/systems/{id}/uploads`, `/evidence`), findings, POA&Ms (`/poams`, milestones, closure/risk-acceptance), reviews (`/reviews`), AI drafts (`/ai/*`), inheritance and attestations, policies (`/policies`), SCA and authorization decisions, RMF workflow, notifications, search (`/search`), audit (`/audit-log`, export), content (`/content/*`, `/content-updates`, `/content-versions/{id}/preview`), mapping review, risk, OSCAL (`/systems/{id}/oscal/{model}`), eMASS (`/emass/*`), scheduled jobs, admin, health (`/health`, `/ready`, `/metrics`).

## Errors
`401` unauthenticated or expired session · `403` RBAC denial (audited) · `404` not found or other tenant · `409` conflict (state transition, eMASS conflict) · `413`/`415`/`422` upload or validation · `429` rate limited (`Retry-After`).
