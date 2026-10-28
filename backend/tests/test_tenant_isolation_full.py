"""WHOLE-API cross-tenant sweep (security P1). The op list is generated from the OpenAPI schema – a new route is swept automatically and a
route can only be left out via SKIP below (with a written justification). Tenant B (5 personas) calls every operation with tenant A's real
ids in path, query and JSON/multipart body. Pass = no tenant-A identity (org marker, user emails) in ANY response, no tenant-A ids in any
2xx body (ids B itself sent are excluded – echoing your own input is not a leak), and tenant A's data fingerprint unchanged after every
write operation. Counts are printed for the report."""
import os
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

ALL_ROLES = ("isso", "issm", "sca", "ao", "platform_admin")
ROLES = tuple(r for r in os.environ.get("SWEEP_ROLES", ",".join(ALL_ROLES)).split(",") if r in ALL_ROLES)  # shard by persona to fit a foreground run
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
               "did": "InventoryDiscrepancy", "cid": "AssetCorrelation", "workbook_id": "TrWorkbook", "strategy_id": "IscmStrategy", "flag_id": "ReviewFlag"}
LITERAL = {"control_id": "ac-2", "model": "ssp", "kind": "ssp", "action": "accept", "slug": "user-guide", "overlay_key": "cnssi-privacy-low",
           "ext": "pdf", "name": "x", "report_type": "poam", "request_type": "poam_closure", "event_id": str(uuid.uuid4()), "import_kind": "emass",
           "op_id": "abc123"}


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
    order = ["System", "User", "ControlAssignment", "Poam", "TrWorkbook", "Policy", "Finding", "PolicyAiCache"]
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


def fingerprint(a: dict) -> dict:
    """Per-table hash of every tenant-A row (all columns) in every tenant-owned table."""
    out = {}
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
            h = hashlib.sha256()
            rows = sorted(json.dumps(list(row), default=str, sort_keys=True) for row in db.execute(select(*[getattr(Mdl, k) for k in cols]).where(cl)))
            for j in rows:  # sorted rows: the old ORDER BY first column had ties → row order (and hash) flipped without any change
                h.update(j.encode())
                d = dict(zip(cols, json.loads(j)))
                ROWS.setdefault(Mdl.__name__, {})[str(d.get("id", j))] = d
            out[Mdl.__name__] = h.hexdigest()
    return out


ROWS: dict = {}


def _row_diff(before: dict, tables: list) -> list:
    """Which rows/columns changed (diagnoses a fingerprint change: request vs. background activity)."""
    out = []
    for t in tables:
        for rid, row in ROWS.get(t, {}).items():
            old = before.get(t, {}).get(rid)
            if old != row:
                out.append((t, rid[:8], "NEW" if old is None else {k: (old.get(k), row[k]) for k in row if old.get(k) != row[k]}))
    return out[:12]


def _quiesce(a: dict) -> None:
    """Wait until no tenant-A background job is queued/running (demo-data analysis) so fingerprint diffs are caused by the sweep."""
    import time
    for _ in range(30):
        with SessionLocal() as db:
            if not db.scalar(select(M.Job.id).where(M.Job.requested_by.in_(a["User"]), M.Job.status.in_(("queued", "running"))).limit(1)):
                return
        time.sleep(1)
    with SessionLocal() as db:  # test DB has no worker: park tenant-A queued jobs so they cannot run mid-sweep (never waits 10 min)
        for j in db.scalars(select(M.Job).where(M.Job.requested_by.in_(a["User"]), M.Job.status == "queued")):
            j.status, j.error = "cancelled", "parked by the isolation sweep (no worker on the test DB)"
        db.commit()


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
    assert client.post("/api/v1/sandbox/demo-data", headers=ha).status_code in (200, 201, 202)
    isso_a = auth(client.post("/api/v1/sandbox/act-as", json={"role": "isso"}, headers=ha).json()["access_token"])
    with SessionLocal() as db:
        org = db.scalar(select(M.User.org_id).where(M.User.email == f"{mark.lower()}@example.com"))
        sid = db.scalar(select(M.System.id).where(M.System.org_id == org))
        uid = db.scalar(select(M.User.id).where(M.User.org_id == org))
        db.add(M.Job(job_type="noop.test", payload={"system_id": str(sid), "note": mark}, status="succeeded", requested_by=uid))
        # rows the demo data lacks, so every path parameter is probed with a REAL tenant-A id (all SYNTHETIC)
        pol = db.scalar(select(M.Policy.id).where(M.Policy.org_id == org))
        wb = M.TrWorkbook(org_id=org, system_id=sid, file_name=f"{mark}.xlsx", sha256="0" * 64, storage_key=f"synthetic/{mark}.xlsx", version=1, status="mapped")
        db.add(wb)
        db.flush()
        db.add_all([
            M.TrRow(workbook_id=wb.id, row_number=2, match_status="matched"),
            M.TrExport(workbook_id=wb.id, system_id=sid, version=1, file_name=f"{mark}_export.xlsx", sha256="0" * 64, storage_key=f"synthetic/{mark}_e.xlsx", exported_by=mark),
            M.EmassImport(org_id=org, system_id=sid, file_name=f"{mark}_poam.xlsx", sha256="1" * 64, size_bytes=1, storage_key=f"synthetic/{mark}_i.xlsx"),
            M.CategorizationRecord(system_id=sid, revision=1, framework="fips199", status="draft"),
            M.PtaResponse(system_id=sid, revision=1, answers={"q1": mark}, status="draft"),
            M.ApprovalRequest(org_id=org, system_id=sid, seq=9001, human_id=f"R-{mark[-4:]}", request_type="poam_closure", rule_version=1,
                              decision_rule_id=db.scalar(select(M.DecisionRule.id).limit(1)),
                              justification=f"{mark} request", requester_id=uid),
            M.PolicyRequirementCoverage(org_id=org, policy_id=pol, policy_version=1, control_id="ac-2", requirement_type="cci", requirement_id="CCI-000015",
                                        label=mark, text=mark, concept="x", status="missing", confidence="Low", reason=mark, source="rule"),
            M.InventoryDiscrepancy(system_id=sid, kind="unmatched", key=mark, status="open", title=f"{mark} discrepancy", records=[]),
        ])
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
    print("A-ROWS", {k: len(v) for k, v in a.items() if isinstance(v, list)})
    _quiesce(a)
    fp0 = fingerprint(a)
    ops = requests = 0
    leaks, writes_changed, unauth = [], [], []
    swept = set()
    sent_all: set = set()
    k, n = (int(x) for x in os.environ.get("SWEEP_SHARD", "0/1").split("/"))  # optional op shard k/n to fit a foreground run
    for idx, (method, path, op, comps) in enumerate(_ops()):
        if (method, path) in SKIP:
            continue
        if idx % n != k:
            swept.add((method, path))
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
        sent_all |= sent
        for role in ROLES:
            if role == "platform_admin" and (method, path) in GLOBAL_ADMIN:
                continue
            kw = {"params": query, "headers": b[role]}
            if body is not None:
                kw["json"] = body
            if files is not None:
                kw["files"], kw["data"] = files, data
            r = client.request(method, url, **kw)
            if a["System"]:
                with SessionLocal() as db:
                    if db.get(M.System, a["System"][0]) is None:
                        pytest.fail(f"tenant A's system disappeared after {method} {path} as {role}: {r.status_code} {r.text[:200]}")
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
            snap = {t: dict(v) for t, v in ROWS.items()}
            ROWS.clear()
            fp = fingerprint(a)
            if fp != fp0:
                changed = sorted(k for k in fp if fp[k] != fp0.get(k))
                writes_changed.append((method, path, changed, _row_diff(snap, changed)))
                fp0 = fp
    all_ops = {(m, p) for m, p, _, _ in _ops()}
    print(f"\nSWEEP ops={ops} of {len(all_ops)} (skipped {len(SKIP)} with justification), requests={requests}, roles={len(ROLES)}, "
          f"global-admin ops not executed as platform_admin={len(GLOBAL_ADMIN)}; path params without a real tenant-A row: {missing_real}")
    print("LEAKS", leaks[:20])
    print("A-MODIFIED-BY", writes_changed)
    print("UNAUTHORIZED-AFTER-REMINT", unauth[:10])
    assert all_ops - swept == set(SKIP) & all_ops  # every operation is swept unless explicitly justified
    assert not leaks and not writes_changed
    # B's own audit trail (authz.denied etc.): may echo the IDs B itself requested, never any other tenant-A data
    org_b = uuid.UUID(client.get("/api/v1/auth/me", headers=world["hb"]).json()["org_id"])
    with SessionLocal() as db:
        ub = list(db.scalars(select(M.User.id).where(M.User.org_id == org_b)))
        evs = db.scalars(select(M.AuditEvent).where(M.AuditEvent.actor_user_id.in_(ub))).all()
        bad = []
        for e in evs:
            txt = json.dumps({k: getattr(e, k) for k in ("details", "before", "after", "entity_id", "actor_email")}, default=str).lower()
            extra = (set(UUID_RX.findall(txt)) & a_ids) - {x.lower() for x in sent_all}
            if any(i in txt for i in identity) or extra:
                bad.append((e.action, e.entity_type, e.entity_id, json.dumps(e.details, default=str)[:300], sorted(extra)[:2]))
    denied = sum(1 for e in evs if e.action == "authz.denied")
    print(f"B audit events={len(evs)} (authz.denied={denied}); with non-requested A data: {bad[:10]}")
    assert not bad
