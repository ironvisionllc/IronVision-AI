"""eMASS sync engine. Adapters: mock (synthetic demo connector, labelled MOCK), read / write (authorized API stubs that stay
disabled until configured) and oscal_export_only. Outbound changes go through a queue that needs approval. A remote
change is never overwritten blindly: if the remote version moved past our base version, the change becomes a conflict
that a person must resolve.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EmassChange, EmassRemoteRecord, EmassSyncRun, Poam, System, User
from app.services import audit

MODES = {"mock": "MOCK eMASS (synthetic demo connector – no real eMASS contacted)", "read": "Authorized read (eMASS REST API)",
         "write": "Authorized read/write (eMASS REST API)", "oscal_export_only": "OSCAL export only – no live synchronization"}
DEFAULTS = {"mode": "mock", "base_url": None, "api_user_uid": None, "api_key_ciphertext": None, "client_cert_path": None,
            "app_registration_id": None, "last_sync_at": None, "last_error": None, "last_connectivity": None}
MAX_ATTEMPTS = 5
OPEN_STATES = ("proposed", "pending_approval", "approved", "pending_retry", "conflict", "submitting")


class EmassError(Exception):
    def __init__(self, kind: str, message: str, recoverable: bool = True):
        super().__init__(message)
        self.kind, self.recoverable = kind, recoverable


def now() -> datetime:
    return datetime.now(timezone.utc)


def config(db: Session, org_id) -> dict:
    from app.services.rmf import get_setting
    return get_setting(db, org_id, "emass", DEFAULTS)


def save_config(db: Session, org_id, cfg: dict) -> dict:
    from app.services.rmf import set_setting
    return set_setting(db, org_id, "emass", cfg)


def failure_sim(db: Session, org_id) -> dict:
    from app.services.rmf import get_setting
    return get_setting(db, org_id, "emass_mock_failures", {"mode": "off", "remaining": 0})


def status(db: Session, org_id) -> dict:
    """Truthful state of each prerequisite. Nothing is marked done unless it is actually configured or verified."""
    c = config(db, org_id)
    cert = c.get("client_cert_path")
    real = c["mode"] in ("read", "write")
    checks = {
        "application_registration": bool(c.get("app_registration_id")),
        "api_credential": bool(c.get("api_key_ciphertext")),
        "client_certificate": bool(cert and os.path.exists(cert)),
        "user_authorization": bool(c.get("api_user_uid")),
        "base_url": bool(c.get("base_url")),
    }
    configured = all(checks.values())
    return {"mode": c["mode"], "mode_label": MODES[c["mode"]], "checks": checks, "client_cert_path": cert,
            "client_cert_note": "file not found" if cert and not os.path.exists(cert) else None,
            "capabilities": {"read": c["mode"] == "mock" or (real and configured), "write": c["mode"] == "mock" or (c["mode"] == "write" and configured),
                             "live_sync": c["mode"] == "mock" or (real and configured)},
            "real_connector_configured": real and configured, "last_sync_at": c.get("last_sync_at"), "last_error": c.get("last_error"),
            "last_connectivity": c.get("last_connectivity"), "failure_simulation": failure_sim(db, org_id) if c["mode"] == "mock" else None,
            "notice": "No live synchronization occurred – OSCAL files are produced for manual upload" if c["mode"] == "oscal_export_only"
            else ("MOCK connector – remote records are synthetic" if c["mode"] == "mock" else None)}


# ---------- adapters ----------
class MockAdapter:
    name = "mock"

    def __init__(self, db: Session, org_id):
        self.db, self.org_id = db, org_id

    def _maybe_fail(self):
        sim = failure_sim(self.db, self.org_id)
        if sim["mode"] != "off" and sim.get("remaining", 0) > 0:
            from app.services.rmf import set_setting
            set_setting(self.db, self.org_id, "emass_mock_failures", {**sim, "remaining": sim["remaining"] - 1})
            if sim["mode"] == "timeout":
                raise EmassError("timeout", "MOCK: request timed out after 30s")
            if sim["mode"] == "409":
                raise EmassError("conflict", "MOCK: 409 Conflict – remote record changed", recoverable=False)
            raise EmassError("http_500", "MOCK: 500 Internal Server Error")

    def test(self) -> tuple[bool, str]:
        self._maybe_fail()
        return True, "MOCK connector reachable (synthetic – no real eMASS contacted)"

    def list(self, system_id, entity_type: str) -> list[EmassRemoteRecord]:
        self._maybe_fail()
        return list(self.db.scalars(select(EmassRemoteRecord).where(EmassRemoteRecord.system_id == system_id, EmassRemoteRecord.entity_type == entity_type)))

    def put(self, ch: EmassChange) -> dict:
        self._maybe_fail()
        rec = self.db.scalar(select(EmassRemoteRecord).where(EmassRemoteRecord.system_id == ch.system_id, EmassRemoteRecord.entity_type == ch.entity_type,
                                                             EmassRemoteRecord.remote_id == (ch.remote_id or "")))
        if rec is not None and ch.base_remote_version is not None and rec.remote_version != ch.base_remote_version:
            raise EmassError("conflict", f"Remote version {rec.remote_version} ≠ base {ch.base_remote_version}", recoverable=False)
        if rec is None:
            n = self.db.scalar(select(func.count()).select_from(EmassRemoteRecord).where(EmassRemoteRecord.system_id == ch.system_id)) + 1
            rec = EmassRemoteRecord(system_id=ch.system_id, entity_type=ch.entity_type, remote_id=ch.remote_id or f"EM-{ch.entity_type[:3].upper()}-{9000 + n}",
                                    data={}, remote_version=0)
            self.db.add(rec)
        rec.data, rec.remote_version = {**(rec.data or {}), **ch.after}, rec.remote_version + 1
        self.db.flush()
        return {"status": 200, "remote_id": rec.remote_id, "remote_version": rec.remote_version, "mock": True}


class RestAdapter:
    """Authorized eMASS REST API. Disabled until all prerequisites are configured; write needs mode=write."""

    def __init__(self, db: Session, org_id, write: bool):
        self.db, self.org_id, self.write = db, org_id, write
        self.st = status(db, org_id)

    def _require(self, write=False):
        if not self.st["real_connector_configured"]:
            missing = [k for k, v in self.st["checks"].items() if not v]
            raise EmassError("not_configured", f"eMASS connector not configured: missing {', '.join(missing)}", recoverable=False)
        if write and not self.write:
            raise EmassError("read_only", "Connector is configured read-only", recoverable=False)

    def _client(self):
        import httpx
        from app.services.secrets import SecretStore
        c = config(self.db, self.org_id)
        return httpx.Client(base_url=c["base_url"], cert=c["client_cert_path"], timeout=30,
                            headers={"api-key": SecretStore().decrypt(c["api_key_ciphertext"]), "user-uid": c["api_user_uid"]})

    def test(self) -> tuple[bool, str]:
        self._require()
        with self._client() as cl:
            r = cl.get("/api")
        return r.status_code == 200, f"HTTP {r.status_code} from {r.request.url}"

    def list(self, system_id, entity_type):
        self._require()
        raise EmassError("not_implemented", "Remote import over the real eMASS API is not implemented in this build", recoverable=False)

    def put(self, ch):
        self._require(write=True)
        raise EmassError("not_implemented", "Remote write over the real eMASS API is not implemented in this build", recoverable=False)


def adapter(db: Session, org_id):
    mode = config(db, org_id)["mode"]
    if mode == "mock":
        return MockAdapter(db, org_id)
    if mode in ("read", "write"):
        return RestAdapter(db, org_id, mode == "write")
    return None


def _run(db: Session, org_id, kind: str, system_id, status_: str, summary=None, error=None, actor=None) -> EmassSyncRun:
    r = EmassSyncRun(org_id=org_id, system_id=system_id, kind=kind, mode=config(db, org_id)["mode"], status=status_, summary=summary, error=error,
                     actor_email=actor)
    db.add(r)
    if status_ == "succeeded":
        save_config(db, org_id, {**config(db, org_id), "last_sync_at": now().isoformat(), "last_error": None})
    elif error:
        save_config(db, org_id, {**config(db, org_id), "last_error": error[:500]})
    db.flush()
    return r


def test_connection(db: Session, org_id, actor_email: str) -> dict:
    a = adapter(db, org_id)
    if a is None:
        res = {"ok": False, "message": "Mode is oscal_export_only – no connection is attempted"}
    else:
        try:
            ok, msg = a.test()
            res = {"ok": ok, "message": msg}
        except Exception as exc:
            res = {"ok": False, "message": str(exc)[:300]}
    save_config(db, org_id, {**config(db, org_id), "last_connectivity": {**res, "at": now().isoformat()}})
    audit.record(db, action="emass.connectivity_test", actor_email=actor_email, entity_type="emass", details=res)
    return res


# ---------- import / compare ----------
POAM_FIELDS = ("weakness", "status", "due_date", "severity")


def _poam_view(p: Poam) -> dict:
    return {"weakness": p.weakness, "status": p.status, "due_date": str(p.due_date) if p.due_date else None, "severity": p.severity, "human_id": p.human_id}


def compare(db: Session, s: System, actor_email: str) -> dict:
    a = adapter(db, s.org_id)
    if a is None:
        raise HTTPException(409, "No live synchronization in oscal_export_only mode")
    try:
        remote = {r.remote_id: r for r in a.list(s.id, "poam")}
        sysrec = a.list(s.id, "system")
        controls = a.list(s.id, "control")
    except EmassError as exc:
        _run(db, s.org_id, "compare", s.id, "failed", error=str(exc), actor=actor_email)
        raise HTTPException(502, f"eMASS {exc.kind}: {exc}")
    rows = []
    for p in db.scalars(select(Poam).where(Poam.system_id == s.id).order_by(Poam.seq)):
        loc = _poam_view(p)
        r = remote.pop(p.emass_remote_id, None) if p.emass_remote_id else None
        if r is None:
            rows.append({"poam_id": str(p.id), "human_id": p.human_id, "state": "local_only", "local": loc, "remote": None, "differences": []})
            continue
        diffs = [{"field": k, "local": loc[k], "remote": r.data.get(k)} for k in POAM_FIELDS if str(loc[k]) != str(r.data.get(k))]
        rows.append({"poam_id": str(p.id), "human_id": p.human_id, "remote_id": r.remote_id, "remote_version": r.remote_version,
                     "state": "different" if diffs else "in_sync", "local": loc, "remote": r.data, "differences": diffs})
    rows += [{"poam_id": None, "human_id": None, "remote_id": r.remote_id, "state": "remote_only", "local": None, "remote": r.data, "differences": []}
             for r in remote.values()]
    summary = {k: sum(1 for x in rows if x["state"] == k) for k in ("in_sync", "different", "local_only", "remote_only")}
    _run(db, s.org_id, "compare", s.id, "succeeded", summary=summary, actor=actor_email)
    return {"system_remote": sysrec[0].data if sysrec else None, "controls_remote": len(controls), "poams": rows, "summary": summary,
            "mock": isinstance(a, MockAdapter)}


def import_metadata(db: Session, s: System, actor_email: str) -> dict:
    """Import system metadata / controls / POA&M links from eMASS. Only fills empty local fields; never overwrites local data."""
    res = compare(db, s, actor_email)
    filled = []
    if res["system_remote"] and not s.emass_id:
        s.emass_id = res["system_remote"].get("emass_id")
        filled.append("emass_id")
    _run(db, s.org_id, "import", s.id, "succeeded", summary={"filled": filled, **res["summary"]}, actor=actor_email)
    return {"filled": filled, **res}


# ---------- outbound queue ----------
def queue_change(db: Session, *, system: System, entity_type: str, entity_id: str, label: str, after: dict, before: dict | None,
                 trigger: str, requester: User | None) -> EmassChange:
    remote_id, base = None, None
    if entity_type == "poam":
        p = db.get(Poam, uuid.UUID(entity_id))
        remote_id = p.emass_remote_id
    rec = db.scalar(select(EmassRemoteRecord).where(EmassRemoteRecord.system_id == system.id, EmassRemoteRecord.entity_type == entity_type,
                                                    EmassRemoteRecord.remote_id == remote_id)) if remote_id else None
    if rec is not None:
        base, before = rec.remote_version, before or rec.data
    ch = EmassChange(org_id=system.org_id, system_id=system.id, entity_type=entity_type, entity_id=entity_id, entity_label=label, remote_id=remote_id,
                     operation="update" if remote_id else "create", before=before, after=after, base_remote_version=base, trigger=trigger,
                     requested_by=requester.id if requester else None, history=[{"at": now().isoformat(), "event": "proposed", "trigger": trigger}])
    db.add(ch)
    db.flush()
    audit.record(db, action="emass.change.queued", actor_user_id=requester.id if requester else None, actor_email=requester.email if requester else "system",
                 entity_type="emass_change", entity_id=str(ch.id), after={"entity": entity_type, "label": label, "operation": ch.operation, "trigger": trigger})
    return ch


def _hist(ch: EmassChange, event: str, **kw) -> None:
    ch.history = [*(ch.history or []), {"at": now().isoformat(), "event": event, **kw}]


def request_approval(db: Session, ch: EmassChange, requester: User, justification: str):
    from app.services import workflow as wf
    if ch.status != "proposed":
        raise HTTPException(409, f"Change is {ch.status}")
    req = wf.create_request(db, system=db.get(System, ch.system_id), requester=requester, request_type="emass_submission", justification=justification,
                            payload={"emass_change_id": str(ch.id)})
    ch.approval_request_id, ch.approval_status, ch.status = req.id, "pending", "pending_approval"
    _hist(ch, "approval_requested", request=req.human_id)
    return req


def on_approval(db: Session, change_id: str, approved: bool, actor: User) -> None:
    ch = db.get(EmassChange, uuid.UUID(change_id))
    ch.approval_status, ch.status = ("approved", "approved") if approved else ("rejected", "cancelled")
    _hist(ch, "approved" if approved else "rejected", by=actor.email)


def submit(db: Session, ch: EmassChange, actor_email: str) -> EmassChange:
    if ch.status not in ("approved", "pending_retry"):
        raise HTTPException(409, f"Only approved changes can be submitted (status: {ch.status})")
    if config(db, ch.org_id)["mode"] == "oscal_export_only":
        _hist(ch, "not_submitted", reason="oscal_export_only")
        raise HTTPException(409, "Mode is oscal_export_only – No live synchronization occurred. Export OSCAL and upload manually.")
    a = adapter(db, ch.org_id)
    ch.attempts += 1
    ch.submitted_at = now()
    try:
        resp = a.put(ch)
    except EmassError as exc:
        ch.response = {"error": exc.kind, "message": str(exc)}
        if exc.kind == "conflict":
            ch.status = "conflict"
        elif exc.recoverable and ch.attempts < MAX_ATTEMPTS:
            ch.status, ch.next_retry_at = "pending_retry", now() + timedelta(minutes=2 ** ch.attempts)
        else:
            ch.status = ch.final_status = "failed"
        _hist(ch, "submit_failed", attempt=ch.attempts, error=exc.kind, message=str(exc)[:200], next_retry_at=ch.next_retry_at.isoformat() if ch.next_retry_at and ch.status == "pending_retry" else None)
        _run(db, ch.org_id, "submit", ch.system_id, "failed", summary={"change_id": str(ch.id)}, error=str(exc), actor=actor_email)
        audit.record(db, action="emass.change.failed", outcome="failure", actor_email=actor_email, entity_type="emass_change", entity_id=str(ch.id),
                     details={"error": exc.kind, "attempt": ch.attempts, "status": ch.status})
        return ch
    ch.status = ch.final_status = "succeeded"
    ch.response, ch.next_retry_at, ch.remote_id = resp, None, resp["remote_id"]
    if ch.entity_type == "poam":
        p = db.get(Poam, uuid.UUID(ch.entity_id))
        p.emass_remote_id, p.emass_status = resp["remote_id"], "synced"
    _hist(ch, "submitted", attempt=ch.attempts, response=resp)
    _run(db, ch.org_id, "submit", ch.system_id, "succeeded", summary={"change_id": str(ch.id), "remote_id": resp["remote_id"]}, actor=actor_email)
    audit.record(db, action="emass.change.succeeded", actor_email=actor_email, entity_type="emass_change", entity_id=str(ch.id), details=resp)
    return ch


def retry_due(db: Session) -> dict:
    done = {"retried": 0, "succeeded": 0}
    for ch in db.scalars(select(EmassChange).where(EmassChange.status == "pending_retry", EmassChange.next_retry_at <= now()).with_for_update(skip_locked=True)):
        submit(db, ch, "worker:emass.retry")
        done["retried"] += 1
        done["succeeded"] += ch.status == "succeeded"
    return done


def resolve_conflict(db: Session, ch: EmassChange, choice: str, actor: User, rationale: str) -> EmassChange:
    if ch.status != "conflict":
        raise HTTPException(409, "Change is not in conflict")
    rec = db.scalar(select(EmassRemoteRecord).where(EmassRemoteRecord.system_id == ch.system_id, EmassRemoteRecord.entity_type == ch.entity_type,
                                                    EmassRemoteRecord.remote_id == ch.remote_id))
    if choice == "keep_local":
        # remote changed since approval: overwriting it needs a fresh ISSM approval under the decision rule
        ch.base_remote_version, ch.before, ch.status = rec.remote_version if rec else None, rec.data if rec else None, "proposed"
        ch.approval_request_id, ch.approval_status = None, "not_requested"
    elif choice == "accept_remote":
        if ch.entity_type == "poam" and rec:
            p = db.get(Poam, uuid.UUID(ch.entity_id))
            for k in ("weakness", "severity"):
                if rec.data.get(k):
                    setattr(p, k, rec.data[k])
            p.emass_status = "synced"
        ch.status = ch.final_status = "resolved_remote"
    else:
        raise HTTPException(422, "choice must be keep_local or accept_remote")
    _hist(ch, f"conflict_{choice}", by=actor.email, rationale=rationale)
    audit.record(db, action="emass.conflict.resolved", actor_user_id=actor.id, actor_email=actor.email, entity_type="emass_change", entity_id=str(ch.id),
                 details={"choice": choice, "rationale": rationale})
    return ch


def pending_by_poam(db: Session, system_id=None) -> dict[str, str]:
    q = select(EmassChange.entity_id, EmassChange.status).where(EmassChange.entity_type == "poam").order_by(EmassChange.created_at)
    if system_id:
        q = q.where(EmassChange.system_id == system_id)
    return {eid: st for eid, st in db.execute(q)}
