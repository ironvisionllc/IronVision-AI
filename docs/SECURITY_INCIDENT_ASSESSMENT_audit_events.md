# Security assessment – cross-tenant read via `/api/v1/audit-events` and related endpoints

Status: **assessment only – no conclusion about whether an incident occurred.** Whether any data was actually exposed on the
DigitalOcean Droplet can only be decided from that Droplet's own data. The read-only checks are in section 4.

## 1. What was wrong (fixed in preview: 403aeed, 699d76e)

| Endpoint | Introduced | Defect | Who could call it | Data returned |
|---|---|---|---|---|
| `GET /api/v1/audit-events` | a3fe224 (2026-10-11, initial history) | no tenant filter | any role with `audit.read` (ISSO, ISSM, SCA, AO, privacy official, platform_admin) | up to 500 audit events from **all** orgs: action, actor email, actor user id, entity type/id, before/after, IP address, user agent, correlation id |
| `GET /api/v1/jobs` | a3fe224 | no tenant filter | roles with `admin.health.read` (platform_admin, ISSM) | the last ≤100 jobs of all orgs: job type, payload (system / evidence / policy ids, file names), status, error text |
| `GET /api/v1/jobs/{id}` | a3fe224 | no tenant check | any signed-in user who knows or guesses a job UUID | one job (as above) |
| `GET /api/v1/admin/users/{id}/access-history` | a3fe224 | no tenant check | `admin.users.manage` (platform_admin / org admin) who knows a user UUID | ≤100 audit events of that user (emails, IPs) |
| `POST /api/v1/demo/evidence/{id}/collected-at`, `POST /api/v1/demo/attestations/{id}/expire` | a3fe224 | no tenant check (writes) | `demo.tools` holders who know an id; only rows flagged `is_synthetic` / signed attestations | back-dated SYNTHETIC evidence / expired attestations of another org |

UUIDs are random v4 values, so the id-based endpoints are only reachable by someone who already holds another org's ids. The two list
endpoints (`/audit-events`, `/jobs`) need no prior knowledge.

## 2. Was cross-tenant exposure possible on the Droplet?

- Multi-tenant self sign-up arrived with a8110c9 (2026-10-14). Before that, a deployment served one organization, so there was no other
  tenant to leak to. Section 4 query **Q1** shows how many orgs actually exist on the Droplet.
- The Droplet runs ≥ 94002f0 (2026-10-23; see the P1 #2 analysis), so it contains every defect in the table above. The fixes are only in
  the current HEAD, which is not deployed.
- **If Q1 returns exactly one non-sandbox org and no other orgs: no cross-tenant exposure was possible on that Droplet.** The endpoints
  were still too broad by design and must be fixed by redeploying.
- If more than one org exists, anyone in org X holding `audit.read` could have read org Y's audit events. The section 4 checks show
  whether anyone called the endpoint and as which user.

## 3. Which logs can prove or disprove access

| Source | What it records | Identity? | Retention on the Droplet |
|---|---|---|---|
| nginx edge access log (container stdout → Docker json-file) | time, client IP, method, path + query, status, bytes, user agent | IP only | Docker `log-opts` max-size 10m × 5 files per container (`docker-daemon.json`) – busy servers roll over within days |
| backend structured log `"request"` line (app/main.py) | method, path, status, duration, correlation id | no user id | same Docker rotation |
| `audit_events` table | logins (`auth.login*`), authorization denials (`authz.denied`), all writes | yes (actor user id, email, IP) | kept in Postgres (hash-chained), not rotated |
| reads of `/audit-events` or `/jobs` | **not audit-logged** (reads are not recorded as audit events) | – | – |

So a read can only be tied to a person by correlating the nginx/backend access line (time + IP) with that IP's `auth.login` events in
`audit_events`. If the Docker logs have already rotated past the period of interest, the read can no longer be proven or disproven from
logs.

## 4. Read-only checks to run on the Droplet

None of these change anything. Run them from the deploy directory as the deploy user.

```bash
# which commit is deployed (to confirm the endpoints are present)
git -C /opt/ironvision log -1 --format='%h %ad %s' --date=iso

# nginx edge access log: calls of the affected list endpoints (all rotated files still held by Docker)
docker compose -f deploy/digitalocean/docker-compose.do.yml logs --no-color edge 2>/dev/null \
  | grep -E '"GET /api/v1/(audit-events|jobs)(\?|/| )' | awk '{print $1, $4, $7, $9}' | sort | uniq -c | sort -rn | head -50
# backend structured request log (status 200 only = data was returned)
docker compose -f deploy/digitalocean/docker-compose.do.yml logs --no-color backend 2>/dev/null \
  | grep '"request"' | grep -E '"path": "/api/v1/(audit-events|jobs)' | grep '"status": 200' | head -50
# oldest log line still available (bounds what the logs can prove)
docker compose -f deploy/digitalocean/docker-compose.do.yml logs --no-color --timestamps edge 2>/dev/null | head -1
```

```sql
-- Q1: tenants – is cross-tenant exposure even possible?
SELECT id, name, is_sandbox, created_at, (SELECT count(*) FROM users u WHERE u.org_id = o.id) AS users FROM organizations o ORDER BY created_at;
-- Q2: who could call /audit-events (roles holding audit.read) per org
SELECT o.name AS org, u.email, ra.role, ra.created_at FROM role_assignments ra JOIN users u ON u.id = ra.user_id
  JOIN organizations o ON o.id = u.org_id WHERE ra.role IN ('issm','isso','sca','ao','privacy_official','platform_admin') ORDER BY o.name, u.email;
-- Q3: logins with IPs (correlate with the nginx IPs from above)
SELECT occurred_at, actor_email, ip, action, outcome FROM audit_events WHERE action LIKE 'auth.%login%' ORDER BY occurred_at DESC LIMIT 200;
-- Q4: authorization denials (probing of other orgs' ids shows up here)
SELECT occurred_at, actor_email, ip, entity_type, entity_id, details FROM audit_events
  WHERE action LIKE 'authz.%' ORDER BY occurred_at DESC LIMIT 200;
```

Interpretation:
- **One org (Q1):** not exploitable cross-tenant.
- **Several orgs, but no 200 responses for these paths in the retained logs:** no evidence of access within the log window. This is not
  proof for any period that has already rotated out.
- **200 responses from an IP whose logins (Q3) belong to org X while org Y exists:** treat as a potential exposure of org Y's audit
  metadata and follow the incident procedure. Do not draw this conclusion without that correlation.

## 5. Prevention

`tests/test_tenant_isolation_full.py` calls every API operation (generated from the OpenAPI schema; a new route is included
automatically) as five roles of a second tenant, using the first tenant's real ids. It fails on any tenant-A identity in a response,
any tenant-A id in a 2xx body, or any change to tenant A's rows.
