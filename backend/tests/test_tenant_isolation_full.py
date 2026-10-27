"""WHOLE-API cross-tenant sweep (security P1). The op list is generated from the OpenAPI schema – a new route is swept automatically and a
route can only be left out via SKIP below (with a written justification). Tenant B (5 personas) calls every operation with tenant A's real
ids in path, query and JSON/multipart body. Pass = no tenant-A identity (org marker, user emails) in ANY response, no tenant-A ids in any
2xx body (ids B itself sent are excluded – echoing your own input is not a leak), and tenant A's data fingerprint unchanged after every
write operation. Counts are printed for the report."""
import hashlib
import json
import re
import uuid

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select

from app import models as M
from app.db import SessionLocal
from app.main import app
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

ROLES = ("isso", "issm", "sca", "ao", "platform_admin")
# (method, path) → justification. Only operations that cannot be swept meaningfully; each is covered elsewhere.
SKIP = {
    ("POST", "/api/v1/auth/logout"): "revokes the caller's own session (would end the sweep); no tenant data",
    ("POST", "/api/v1/sandbox/reset"): "rebuilds the CALLER's own sandbox only (org from token); covered by test_sandbox",
    ("POST", "/api/v1/sandbox/demo-data"): "loads demo data into the CALLER's own sandbox only; covered by test_sandbox",
}
# Global platform operations (no tenant data, platform_admin only). Swept for the 4 tenant roles (must be refused); NOT executed as
# platform_admin because they change global catalog/content/banner state for every tenant. Intentionally cross-tenant by design.
GLOBAL_ADMIN = {
    ("POST", "/api/v1/admin/content/load"), ("POST", "/api/v1/content-updates/register"), ("POST", "/api/v1/content-updates/{update_id}/apply"),
    ("POST", "/api/v1/content-versions/{version_id}/preview"), ("PUT", "/api/v1/admin/banner"), ("PUT", "/api/v1/admin/ai-settings"),
    ("POST", "/api/v1/admin/demo/reset"), ("POST", "/api/v1/overlays/{overlay_key}/import"), ("POST", "/api/v1/overlays/import-reference"),
    ("POST", "/api/v1/admin/users"),
}
AUDIT_READ = ("/api/v1/audit-events", "/api/v1/audit-log")  # B's own authz.denied events echo the ids B tried – identity check only
UUID_RX = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

PARAM_MODEL = {"system_id": "System", "asset_id": "Asset", "assignment_id": "RoleAssignment", "source_id": "EvidenceSource", "run_id": "IngestRun",
               "finding_id": "Finding", "job_id": "Job", "evidence_id": "Evidence", "impl_id": "Implementation", "import_id": "EmassImport",
               "poam_id": "Poam", "milestone_id": "PoamMilestone", "request_id": "ApprovalRequest", "notification_id": "Notification",
               "provider_id": "CommonControlProvider", "att_id": "Attestation", "policy_id": "Policy", "cov_id": "PolicyRequirementCoverage",
               "pf_id": "PolicyFinding", "user_id": "User", "map_id": "FindingControlMap", "change_id": "EmassChange",
               "record_id": "CategorizationRecord", "response_id": "PtaResponse", "wid": "TrWorkbook", "rid": "TrRow", "eid": "TrExport",
               "did": "InventoryDiscrepancy", "cid": "AssetCorrelation", "workbook_id": "TrWorkbook", "strategy_id": "IscmStrategy"}
LITERAL = {"control_id": "ac-2", "model": "ssp", "kind": "ssp", "action": "accept", "slug": "user-guide", "overlay_key": "cnssi-privacy-low",
           "ext": "pdf", "name": "x", "report_type": "poam", "request_type": "poam_closure", "event_id": str(uuid.uuid4())}


def _owner_clause(Mdl, a: dict):
    c = Mdl.__table__.c
    for col, ids in (("org_id", [a["org"]]), ("system_id", a["System"]), ("user_id", a["User"]), ("actor_user_id", a["User"]),
                     ("requested_by", a["User"]), ("assignment_id", a["ControlAssignment"]), ("poam_id", a["Poam"]), ("workbook_id", a["TrWorkbook"]),
                     ("policy_id", a["Policy"]), ("finding_id", a["Finding"])):
        if col in c:
            return c[col].in_(ids)
    return None


def _collect(org_id: uuid.UUID) -> dict:
    a: dict = {"org": org_id}
    order = ["System", "User", "ControlAssignment", "Poam", "TrWorkbook", "Policy", "Finding"]
    names = order + [n for n in sorted({*PARAM_MODEL.values()}) if n not in order]
    with SessionLocal() as db:
        for n in names:
            a.setdefault(n, [])
        for n in names:
            Mdl = getattr(M, n)
            if n == "System":
                a[n] = list(db.scalars(select(Mdl.id).where(Mdl.org_id == org_id)))
            elif n == "User":
                a[n] = list(db.scalars(select(Mdl.id).where(Mdl.org_id == org_id)))
            else:
                cl = _owner_clause(Mdl, a)
                a[n] = list(db.scalars(select(Mdl.id).where(cl))) if cl is not None else []
        a["emails"] = list(db.scalars(select(M.User.email).where(M.User.org_id == org_id)))
        a["org_name"] = db.get(M.Organization, org_id).name
    return a


def fingerprint(a: dict) -> str:
    """Hash of every tenant-A row (all columns) in every tenant-owned table."""
    h = hashlib.sha256()
    with SessionLocal() as db:
        for mapper in sorted(M.Base.registry.mappers, key=lambda m: m.class_.__name__):
            Mdl = mapper.class_
            if Mdl.__name__ in ("AuditEvent", "Job", "AuthSession", "LoginAttempt", "WorkerHeartbeat", "AIInteraction", "Notification"):
                continue  # append-only / session bookkeeping (B's own denials and logins); checked by the response sweep instead
            cl = _owner_clause(Mdl, a) if Mdl.__name__ not in ("System", "User", "Organization") else (
                Mdl.org_id == a["org"] if Mdl.__name__ != "Organization" else Mdl.id == a["org"])
            if cl is None:
                continue
            cols = [c.key for c in sa_inspect(Mdl).column_attrs]
            for row in db.execute(select(*[getattr(Mdl, k) for k in cols]).where(cl).order_by(*[getattr(Mdl, k) for k in cols[:1]])):
                h.update((Mdl.__name__ + json.dumps(list(row), default=str, sort_keys=True)).encode())
    return h.hexdigest()


def _resolve(schema: dict, comps: dict, depth=0):
    if "$ref" in schema:
        return _resolve(comps[schema["$ref"].split("/")[-1]], comps, depth)
    for k in ("allOf", "anyOf", "oneOf"):
        if k in schema:
            opts = [s for s in schema[k] if s.get("type") != "null"]
            return _resolve(opts[0], comps, depth) if opts else {}
    return schema


def _value(name: str, schema: dict, comps: dict, a: dict, depth=0):
    s = _resolve(schema, comps)
    t = s.get("type")
    base = name[:-4] if name.endswith("_ids") else name
    pid = PARAM_MODEL.get(base) or PARAM_MODEL.get(base + "_id")
    if name.endswith("_ids") or (t == "array" and pid):
        return [str(x) for x in a.get(pid or "", [])[:2]]
    if name.endswith("_id") or pid:
        ids = a.get(pid or "", [])
        return str(ids[0]) if ids else str(uuid.uuid4())
    if "enum" in s:
        return s["enum"][0]
    if t == "object" and depth < 3:
        return {k: _value(k, v, comps, a, depth + 1) for k, v in s.get("properties", {}).items()}
    if t == "array":
        return [_value(name, s.get("items", {}), comps, a, depth + 1)] if depth < 3 and _resolve(s.get("items", {}), comps).get("type") == "object" else []
    if t == "integer" or t == "number":
        return max(1, s.get("minimum", 1))
    if t == "boolean":
        return False
    if s.get("format") == "date":
        return "2026-01-01"
    return "SYNTHETIC cross-tenant probe text"


def _ops():
    spec = app.openapi()
    for path, ops in spec["paths"].items():
        for m, op in ops.items():
            if m in ("get", "post", "put", "patch", "delete") and path.startswith("/api/v1"):
                yield m.upper(), path, op, spec.get("components", {}).get("schemas", {})


@pytest.fixture(scope="module")
def world(client, signup_on):  # noqa: F811
    mark = f"ZZFULL{uuid.uuid4().hex[:8]}"
    ta = _signup(client, f"{mark.lower()}@example.com", f"{mark} Org")
    ha = auth(ta["access_token"])
    isso_a = auth(client.post("/api/v1/sandbox/act-as", json={"role": "isso"}, headers=ha).json()["access_token"])
    with SessionLocal() as db:
        org = db.scalar(select(M.User.org_id).where(M.User.email == f"{mark.lower()}@example.com"))
        sid = db.scalar(select(M.System.id).where(M.System.org_id == org))
        uid = db.scalar(select(M.User.id).where(M.User.org_id == org))
        db.add(M.Job(job_type="noop.test", payload={"system_id": str(sid), "note": mark}, status="succeeded", requested_by=uid))
        db.add(M.Notification(user_id=uid, kind="test", title=f"{mark} notification", body=mark) if "kind" in M.Notification.__table__.c else
               M.Notification(user_id=uid, title=f"{mark} notification"))
        db.commit()
    client.post("/api/v1/poams", json={"system_id": str(sid), "weakness": f"{mark} weakness", "control_ids": ["ac-2"]}, headers=isso_a)
    tb = _signup(client, f"zzb-{uuid.uuid4().hex[:6]}@example.com", "Sweep B Org")
    hb = auth(tb["access_token"])
    mint = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=hb).json()["access_token"])  # noqa: E731
    return {"mark": mark, "a": _collect(org), "hb": hb, "mint": mint, "b": {r: mint(r) for r in ROLES}}


def test_whole_api_cross_tenant(client, world):
    a, b = world["a"], world["b"]
    a_ids = {str(x) for k, v in a.items() if isinstance(v, list) and k not in ("emails",) for x in v}
    identity = [world["mark"].lower(), *[e.lower() for e in a["emails"]]]
    missing_real = sorted({p for _, path, _, _ in _ops() for p in re.findall(r"{(\w+)}", path) if PARAM_MODEL.get(p) and not a.get(PARAM_MODEL[p])})
    fp0 = fingerprint(a)
    ops = requests = 0
    leaks, writes_changed, unauth = [], [], []
    swept = set()
    for method, path, op, comps in _ops():
        if (method, path) in SKIP:
            continue
        swept.add((method, path))
        ops += 1
        params = {p: (str(a[PARAM_MODEL[p]][0]) if PARAM_MODEL.get(p) and a.get(PARAM_MODEL[p]) else LITERAL.get(p, str(uuid.uuid4())))
                  for p in re.findall(r"{(\w+)}", path)}
        url = path.format(**params)
        query = {q["name"]: _value(q["name"], q.get("schema", {}), comps, a) for q in op.get("parameters", []) if q["in"] == "query" and
                 (q.get("required") or q["name"].endswith("_id"))}
        body, files, data = None, None, None
        content = op.get("requestBody", {}).get("content", {})
        if "application/json" in content:
            body = _value("body", content["application/json"]["schema"], comps, a)
        elif "multipart/form-data" in content:
            sch = _resolve(content["multipart/form-data"]["schema"], comps)
            files = {k: ("probe.txt", b"SYNTHETIC probe", "text/plain") for k, v in sch.get("properties", {}).items()
                     if _resolve(v, comps).get("format") == "binary" or "binary" in json.dumps(v)}
            data = {k: _value(k, v, comps, a) for k, v in sch.get("properties", {}).items() if k not in files}
            data = {k: (json.dumps(v) if isinstance(v, (list, dict)) else str(v)) for k, v in data.items()}
        sent = set(UUID_RX.findall(url + json.dumps(query) + json.dumps(body) + json.dumps(data)))
        for role in ROLES:
            if role == "platform_admin" and (method, path) in GLOBAL_ADMIN:
                continue
            kw = {"params": query, "headers": b[role]}
            if body is not None:
                kw["json"] = body
            if files is not None:
                kw["files"], kw["data"] = files, data
            r = client.request(method, url, **kw)
            if r.status_code == 401:  # e.g. a route revoked this persona's session – re-mint once and retry
                b[role] = world["mint"](role)
                kw["headers"] = b[role]
                r = client.request(method, url, **kw)
                if r.status_code == 401:
                    unauth.append((method, path, role))
            requests += 1
            txt = r.text.lower()
            if any(i in txt for i in identity):
                leaks.append((method, path, role, r.status_code, "identity"))
            elif 200 <= r.status_code < 300 and not path.startswith(AUDIT_READ):
                if got := (set(UUID_RX.findall(txt)) & a_ids) - sent:
                    leaks.append((method, path, role, r.status_code, sorted(got)[:3]))
        if method != "GET":
            fp = fingerprint(a)
            if fp != fp0:
                writes_changed.append((method, path))
                fp0 = fp
    all_ops = {(m, p) for m, p, _, _ in _ops()}
    print(f"\nSWEEP ops={ops} of {len(all_ops)} (skipped {len(SKIP)} with justification), requests={requests}, roles={len(ROLES)}, "
          f"global-admin ops not executed as platform_admin={len(GLOBAL_ADMIN)}; path params without a real tenant-A row: {missing_real}")
    print("LEAKS", leaks[:20])
    print("A-MODIFIED-BY", writes_changed)
    print("UNAUTHORIZED-AFTER-REMINT", unauth[:10])
    assert all_ops - swept == set(SKIP) & all_ops  # every operation is swept unless explicitly justified
    assert not leaks and not writes_changed
