import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.records import get_system, to_dict
from app.db import get_db
from app.models import (Asset, ControlAssignment, Evidence, EvidenceControl, EvidenceSource, Finding, FindingControlMap,
                        FreshnessPolicy, IngestRun, IntegrityCheck)
from app.security.deps import CurrentUser, enforce, get_current_user, require_object_permission, require_permission
from app.services import audit, jobs
from app.services.connectors import SOURCE_TYPES, SOURCE_WHEN, adapter_for
from app.services.evaluation import evaluate_freshness, evaluate_system
from app.services.ingest.parsers import ParseError
from app.services.ingest.pipeline import receive_upload
from app.services.secrets import SecretStore

router = APIRouter(tags=["evidence"])


def _source(db, source_id) -> EvidenceSource:
    s = db.get(EvidenceSource, source_id)
    if s is None:
        raise HTTPException(404, "Source not found")
    return s


def _source_out(db: Session, s: EvidenceSource) -> dict:
    """Card metrics come from canonical findings whose latest evidence is from this source. Mapped + Unmapped = Total."""
    d = to_dict(s, ("secret_ciphertext",))
    d["credential_set"] = bool(s.secret_ciphertext)
    d["type_label"], d["adapter_mode"] = SOURCE_TYPES[s.source_type]
    from app.services.metrics import source_counts

    d.update(source_counts(db, s))
    newest = db.scalar(select(Evidence).where(Evidence.source_id == s.id).order_by(Evidence.collected_at.desc()).limit(1))
    d["freshness"] = newest.state if newest else "no_evidence"
    d["evidence_count"] = db.scalar(select(func.count()).select_from(Evidence).where(Evidence.source_id == s.id))
    return d


@router.get("/source-types")
def source_types(_: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [{"key": k, "label": v[0], "adapter_mode": v[1], "when": SOURCE_WHEN.get(k, "")} for k, v in SOURCE_TYPES.items()]


@router.get("/systems/{system_id}/sources")
def list_sources(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    from app.services.ingest.pipeline import backfill_attribution

    backfill_attribution(db, system_id)
    db.commit()
    return [_source_out(db, s) for s in db.scalars(select(EvidenceSource).where(EvidenceSource.system_id == system_id).order_by(EvidenceSource.name))]


class SourceIn(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    source_type: str | None = None
    config: dict | None = None
    credential: str | None = Field(None, max_length=4000)
    enabled: bool | None = None
    schedule_hours: int | None = Field(None, ge=1, le=720)


@router.post("/systems/{system_id}/sources", status_code=201)
def create_source(system_id: uuid.UUID, body: SourceIn, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("source.manage"))) -> dict:
    if body.source_type not in SOURCE_TYPES or not body.name:
        raise HTTPException(422, "name and a valid source_type are required")
    if SOURCE_TYPES[body.source_type][1] == "file_import" and body.credential:
        raise HTTPException(422, "File-upload sources never take credentials – you upload exported files instead. "
                                 "Use “Connect a tool” for live API sources that need a token.")
    s = EvidenceSource(system_id=get_system(db, system_id).id, name=body.name, source_type=body.source_type,
                       adapter=SOURCE_TYPES[body.source_type][1], config=body.config or {}, schedule_hours=body.schedule_hours,
                       secret_ciphertext=SecretStore().encrypt(body.credential) if body.credential else None, source="ui")
    db.add(s)
    db.flush()
    audit.record(db, action="source.created", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="evidence_source",
                 entity_id=str(s.id), after={"name": s.name, "type": s.source_type, "credential_set": bool(body.credential)})
    db.commit()
    return _source_out(db, s)


@router.patch("/sources/{source_id}")
def update_source(source_id: uuid.UUID, body: SourceIn, request: Request, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_object_permission("source.manage", "EvidenceSource", "source_id"))) -> dict:
    s = _source(db, source_id)
    enforce(request, current, "source.manage", s.system_id)
    ch = body.model_dump(exclude_unset=True, exclude={"credential", "source_type"})
    for k, v in ch.items():
        setattr(s, k, v)
    if body.credential:
        s.secret_ciphertext = SecretStore().encrypt(body.credential)
    audit.record(db, action="source.updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="evidence_source",
                 entity_id=str(s.id), after={**ch, "credential_changed": bool(body.credential)})
    db.commit()
    return _source_out(db, s)


@router.post("/sources/{source_id}/test")
def test_source(source_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("source.manage", "EvidenceSource", "source_id"))) -> dict:
    s = _source(db, source_id)
    enforce(request, current, "source.manage", s.system_id)
    ok, msg = adapter_for(s.source_type).test_connection(s)
    s.health, s.health_detail = ("ok" if ok else "error"), msg
    audit.record(db, action="source.tested", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="evidence_source",
                 entity_id=str(s.id), details={"ok": ok, "message": msg})
    db.commit()
    return {"ok": ok, "message": msg, "adapter_mode": s.adapter}


@router.post("/sources/{source_id}/run")
def run_source(source_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("source.manage", "EvidenceSource", "source_id"))) -> dict:
    s = _source(db, source_id)
    enforce(request, current, "source.manage", s.system_id)
    if not s.enabled:
        raise HTTPException(409, "Source is disabled")
    res = adapter_for(s.source_type).collect(db, s, current.user.id)
    s.last_run_at = datetime.now(timezone.utc)
    s.next_run_at = s.last_run_at + timedelta(hours=s.schedule_hours) if s.schedule_hours else None
    evaluate_freshness(db, s.system_id)
    db.commit()
    return res


@router.post("/systems/{system_id}/uploads", status_code=202)
async def upload(system_id: uuid.UUID, request: Request, file: UploadFile = File(...), source_id: uuid.UUID | None = Form(None),
                 db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("ingest.upload"))) -> dict:
    data = await file.read()
    _vet(file.filename or "upload", data, "scan")
    try:
        run = receive_upload(db, system_id=get_system(db, system_id).id, source_id=source_id, file_name=file.filename or "upload",
                             data=data, actor_id=current.user.id, actor_email=current.user.email)
    except ParseError as exc:
        db.rollback()
        audit.record_now(action="ingest.rejected", outcome="failure", actor_user_id=current.user.id, actor_email=current.user.email,
                         details={"file": file.filename, "error": str(exc)})
        raise HTTPException(422, str(exc))
    if run.status == "queued":
        job = jobs.enqueue(db, "ingest.process", {"run_id": str(run.id)}, requested_by=current.user.id)
        run.stats = {"job_id": str(job.id)}
    db.commit()
    return to_dict(run)


@router.get("/systems/{system_id}/ingest-runs")
def list_runs(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    rows = db.execute(select(IngestRun, EvidenceSource.name).outerjoin(EvidenceSource, EvidenceSource.id == IngestRun.source_id)
                      .where(IngestRun.system_id == system_id).order_by(IngestRun.received_at.desc()).limit(100)).all()
    return [{**to_dict(r), "source_name": n} for r, n in rows]


def _finding_out(db, f: Finding, asset: Asset | None) -> dict:
    d = to_dict(f, ("dedup_fields",))
    d["asset_name"] = asset.name if asset else None
    d["asset_unmatched"] = bool(asset and asset.is_unmatched)
    from app.api.v1.reviews import group_mappings

    d["controls"] = group_mappings(list(db.scalars(select(FindingControlMap).where(FindingControlMap.finding_id == f.id))))
    return d


@router.get("/ingest-runs/{run_id}")
def run_detail(run_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    from app.models import FindingObservation

    run = db.get(IngestRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    enforce(request, current, "system.read", run.system_id)
    target = run.duplicate_of_run_id or run.id
    rows = db.execute(select(Finding, Asset).join(FindingObservation, FindingObservation.finding_id == Finding.id)
                      .outerjoin(Asset, Asset.id == Finding.asset_id).where(FindingObservation.ingest_run_id == target)
                      .order_by(Finding.mapping_status.desc(), Finding.severity)).all()
    ev = db.get(Evidence, run.evidence_id) if run.evidence_id else None
    return {"run": to_dict(run), "evidence": to_dict(ev) if ev else None, "findings": [_finding_out(db, f, a) for f, a in rows]}


@router.get("/systems/{system_id}/findings")
def list_findings(system_id: uuid.UUID, mapping_status: str | None = None, state: str | None = None, db: Session = Depends(get_db),
                  _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    q = select(Finding, Asset).outerjoin(Asset, Asset.id == Finding.asset_id).where(Finding.system_id == system_id)
    if mapping_status:
        q = q.where(Finding.mapping_status == mapping_status)
    if state:
        q = q.where(Finding.current_state == state)
    return [_finding_out(db, f, a) for f, a in db.execute(q.order_by(Finding.last_seen_at.desc()).limit(500)).all()]


class MapIn(BaseModel):
    control_id: str = Field(max_length=50)
    justification: str = Field(min_length=10, max_length=2000)


class DispositionIn(BaseModel):
    disposition: str = Field(pattern="^(not_applicable|out_of_scope|informational|false_positive|no_control_mapping)$")
    justification: str = Field(min_length=10, max_length=2000)


def _finding(db, request, current, finding_id) -> Finding:
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    enforce(request, current, "finding.map", f.system_id)
    return f


@router.post("/findings/{finding_id}/map")
def map_finding(finding_id: uuid.UUID, body: MapIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("finding.map", "Finding", "finding_id"))) -> dict:
    f = _finding(db, request, current, finding_id)
    cid = body.control_id.strip().lower()
    a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == f.system_id, ControlAssignment.control_id == cid))
    if a is None:
        raise HTTPException(422, f"{cid} is not assigned to this system")
    db.add(FindingControlMap(finding_id=f.id, control_id=cid, mapping_source="manual", review_status="human_approved", confidence="human",
                             justification=body.justification, mapped_by=current.user.id, source=f"Manual mapping by {current.user.email}"))
    f.mapping_status = "mapped"
    if f.latest_evidence_id and not db.scalar(select(EvidenceControl.id).where(EvidenceControl.evidence_id == f.latest_evidence_id, EvidenceControl.assignment_id == a.id)):
        db.add(EvidenceControl(evidence_id=f.latest_evidence_id, assignment_id=a.id))
    audit.record(db, action="finding.mapped", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="finding",
                 entity_id=str(f.id), after={"control_id": cid, "justification": body.justification}, **audit.request_meta(request))
    db.flush()
    evaluate_system(db, f.system_id)
    db.commit()
    return {"ok": True}


@router.post("/findings/{finding_id}/disposition")
def disposition_finding(finding_id: uuid.UUID, body: DispositionIn, request: Request, db: Session = Depends(get_db),
                        current: CurrentUser = Depends(require_object_permission("finding.map", "Finding", "finding_id"))) -> dict:
    from app.services import workflow as wf

    f = _finding(db, request, current, finding_id)
    req = wf.request_disposition(db, system=get_system(db, f.system_id), requester=current.user, findings=[f],
                                 disposition=body.disposition, justification=body.justification)
    db.commit()
    return {"ok": True, "applied": False, "pending_request": req.human_id, "request_id": str(req.id),
            "message": f"{req.human_id}: {body.disposition.replace('_', ' ')} disposition awaiting {req.assigned_role.upper()} – not applied until approved"}


@router.get("/systems/{system_id}/evidence")
def ledger(system_id: uuid.UUID, include_removed: bool = False, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    out = []
    q = select(Evidence, EvidenceSource.name, EvidenceSource.source_type).outerjoin(EvidenceSource, EvidenceSource.id == Evidence.source_id).where(Evidence.system_id == system_id)
    if not include_removed:
        q = q.where(Evidence.status == "active")
    for ev, sname, stype in db.execute(q.order_by(Evidence.collected_at.desc())).all():
        d = to_dict(ev)
        d["source_name"], d["source_type"] = sname, stype
        d["controls"] = list(db.scalars(select(ControlAssignment.control_id).join(EvidenceControl, EvidenceControl.assignment_id == ControlAssignment.id)
                                        .where(EvidenceControl.evidence_id == ev.id).order_by(ControlAssignment.control_id)))
        d["assets"] = list(db.scalars(select(func.distinct(Asset.name)).join(Finding, Finding.asset_id == Asset.id).where(Finding.latest_evidence_id == ev.id)))
        last = db.scalar(select(IntegrityCheck).where(IntegrityCheck.evidence_id == ev.id).order_by(IntegrityCheck.created_at.desc()).limit(1))
        d["last_integrity_check"] = to_dict(last) if last else None
        out.append(d)
    return out


@router.post("/systems/{system_id}/evidence/verify", status_code=202)
def verify(system_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("evidence.verify"))) -> dict:
    job = jobs.enqueue(db, "evidence.verify_integrity", {"system_id": str(system_id)}, requested_by=current.user.id)
    db.commit()
    return {"job_id": job.id}


@router.post("/systems/{system_id}/evidence/evaluate-freshness")
def freshness_now(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("evidence.verify"))) -> dict:
    res = evaluate_freshness(db, system_id)
    db.commit()
    return res


@router.get("/jobs/{job_id}")
def job_status(job_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    from app.models import Job, User

    j = db.get(Job, job_id)
    req = db.get(User, j.requested_by) if j is not None and j.requested_by else None
    if j is None or req is None or req.org_id != current.user.org_id:  # tenant-scoped; system jobs are not exposed here
        raise HTTPException(404, "Job not found")
    return to_dict(j)


@router.get("/freshness-policies")
def policies(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [to_dict(p) for p in db.scalars(select(FreshnessPolicy).order_by(FreshnessPolicy.window_days))]


class DemoDate(BaseModel):
    days_ago: int = Field(ge=0, le=3650)


@router.post("/demo/evidence/{evidence_id}/collected-at")
def demo_set_collected(evidence_id: uuid.UUID, body: DemoDate, request: Request, db: Session = Depends(get_db),
                       current: CurrentUser = Depends(require_permission("demo.tools"))) -> dict:
    """DEMO TOOL ONLY: back-date a synthetic evidence item's collected_at to exercise freshness logic."""
    ev = db.get(Evidence, evidence_id)
    if ev is None or not ev.is_synthetic:
        raise HTTPException(404, "Synthetic evidence not found")
    before = ev.collected_at.isoformat()
    ev.collected_at = datetime.now(timezone.utc) - timedelta(days=body.days_ago)
    audit.record(db, action="demo.evidence_collected_at_adjusted", actor_user_id=current.user.id, actor_email=current.user.email,
                 entity_type="evidence", entity_id=str(ev.id), before={"collected_at": before},
                 after={"collected_at": ev.collected_at.isoformat()}, details={"demo_tool": True}, **audit.request_meta(request))
    res = evaluate_freshness(db, ev.system_id)
    db.commit()
    return {"ok": True, "state": ev.state, "freshness": res}


def _vet(name: str, data: bytes, kind: str) -> None:
    from app.services.upload_security import UploadRejected, validate_upload
    try:
        validate_upload(name, data, kind)
    except UploadRejected as exc:
        raise HTTPException(415 if "type" in str(exc) or "match" in str(exc) else 413 if "limit" in str(exc) else 422, str(exc))


STATUS_LABEL = {"open": "Open", "pass": "Not a Finding", "not_applicable": "Not Applicable", "not_reviewed": "Not Reviewed"}
CAT_LABEL = {"high": "CAT I", "medium": "CAT II", "low": "CAT III"}


@router.get("/ingest-runs/{run_id}/stig")
def run_stig_detail(run_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    """Every rule of a STIG checklist / XCCDF import with status, details and comments, totals, and a check against the source file."""
    from collections import Counter

    from app.models import FindingObservation
    from app.services.ingest.parsers import PARSERS, stig_header
    from app.services.storage import get_storage

    run = db.get(IngestRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    enforce(request, current, "system.read", run.system_id)
    if run.file_format not in ("ckl", "cklb", "xccdf"):
        raise HTTPException(409, "This import is not a STIG checklist or XCCDF result")
    target = run.duplicate_of_run_id or run.id
    obs = db.execute(select(FindingObservation, Finding).join(Finding, Finding.id == FindingObservation.finding_id)
                     .where(FindingObservation.ingest_run_id == target)).all()
    rules = [{"finding_id": str(f.id), "vuln_id": f.vuln_id, "rule_id": f.rule_id, "title": f.title, "severity": CAT_LABEL.get((f.severity or "").lower(), f.cat or f.severity),
              "status": STATUS_LABEL.get(o.observed_status, o.observed_status), "finding_details": (o.raw or {}).get("finding_details"),
              "comments": (o.raw or {}).get("comments"), "ccis": f.ccis or [], "current_state": f.current_state} for o, f in obs]
    ev = db.get(Evidence, run.evidence_id) if run.evidence_id else None
    header, source_rules, src_by_rule = {}, None, {}
    if ev is not None:
        try:
            data = get_storage().get(ev.storage_key)
            header = stig_header(run.file_format, data)
            parsed = PARSERS[run.file_format](data)
            source_rules = len(parsed)
            src_by_rule = {x.get("rule_id"): x for x in parsed}
        except Exception:  # noqa: BLE001 – file unreadable: report it instead of failing the page
            header, src_by_rule = {}, {}
    for r, (o, f) in zip(rules, obs):
        x = src_by_rule.get(r["rule_id"])
        # original values from the uploaded file (re-parsed now, so older imports show them too) vs. the app's current record
        r["source"] = ({"title": x.get("title"), "severity": CAT_LABEL.get((x.get("severity") or "").lower(), x.get("cat")),
                        "status": STATUS_LABEL.get(x.get("status"), x.get("status")), **(x.get("raw") or {}), "ccis": x.get("ccis")} if x else None)
        r["edited"] = [k for k in ("title", "severity") if x and r["source"].get(k) and r[k] != r["source"][k]] + \
                      (["state"] if f.current_state not in ("open", None) and (x or {}).get("status") == "open" else [])
    return {"run": {"id": str(run.id), "file_name": run.file_name, "file_format": run.file_format, "received_at": run.received_at.isoformat() if run.received_at else None},
            "header": header or {"title": obs[0][1].benchmark if obs else None},
            "rules": sorted(rules, key=lambda r: (r["status"] != "Open", r["severity"] or "", r["vuln_id"] or "")),
            "totals": {"by_status": dict(Counter(r["status"] for r in rules)), "by_severity": dict(Counter(r["severity"] for r in rules))},
            "parse_check": {"source_rules": source_rules, "stored_rules": len(rules), "match": source_rules == len(rules) if source_rules is not None else None}}


# ---------- evidence record actions: view / download / new version / history / remove ----------
def _ev(db: Session, evidence_id: uuid.UUID, current: CurrentUser, perm: str) -> Evidence:
    from app.models import System
    from app.security.rbac import has_permission

    ev = db.get(Evidence, evidence_id)
    s = db.get(System, ev.system_id) if ev else None
    if ev is None or s is None or s.org_id != current.user.org_id or not has_permission(current.assignments, "system.read", s.org_id, s.id):
        raise HTTPException(404, "Evidence not found")
    if not has_permission(current.assignments, perm, s.org_id, s.id):
        raise HTTPException(403, f"Missing permission: {perm}")
    return ev


def _history_ok(current: CurrentUser, ev: Evidence, db: Session) -> bool:
    from app.models import System
    from app.security.rbac import has_permission

    s = db.get(System, ev.system_id)
    return any(has_permission(current.assignments, p, s.org_id, s.id) for p in ("evidence.submit", "audit.read", "assessment.perform"))


@router.get("/evidence/{evidence_id}")
def evidence_detail(evidence_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    from app.services import evidence_versions as evs

    ev = _ev(db, evidence_id, current, "system.read")
    out = evs.meta(db, ev, _history_ok(current, ev, db))
    db.commit()
    return out


@router.get("/evidence/{evidence_id}/download")
def evidence_download(evidence_id: uuid.UUID, request: Request, version: int | None = None, db: Session = Depends(get_db),
                      current: CurrentUser = Depends(get_current_user)):
    from fastapi.responses import Response
    from app.models import EvidenceVersion
    from app.services.storage import get_storage

    ev = _ev(db, evidence_id, current, "system.read")
    key, name = ev.storage_key, ev.file_name or "evidence"
    if version and version != ev.version:
        if not _history_ok(current, ev, db):
            raise HTTPException(403, "Historical versions are visible to evidence submitters, assessors and auditors only")
        v = db.scalar(select(EvidenceVersion).where(EvidenceVersion.evidence_id == ev.id, EvidenceVersion.version == version))
        if v is None:
            raise HTTPException(404, "Version not found")
        key, name = v.storage_key, v.file_name or name
    audit.record(db, action="evidence.downloaded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="evidence", entity_id=str(ev.id),
                 details={"version": version or ev.version}, **audit.request_meta(request))
    db.commit()
    return Response(get_storage().get(key), media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/evidence/{evidence_id}/versions", status_code=201)
async def evidence_new_version(evidence_id: uuid.UUID, request: Request, reason: str = Form(..., min_length=5, max_length=2000), file: UploadFile = File(...),
                               db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("evidence.submit"))) -> dict:
    """Replace / upload new version: a new immutable version becomes active; the old object and hash stay in the history."""
    from app.services import evidence_versions as evs
    from app.services.upload_security import UploadRejected, validate_upload

    ev = _ev(db, evidence_id, current, "evidence.submit")
    data = await file.read()
    try:
        scan = validate_upload(file.filename or "evidence", data, "evidence")
    except UploadRejected as exc:
        raise HTTPException(415 if "type" in str(exc) or "match" in str(exc) else 413 if "limit" in str(exc) else 422, str(exc))
    before = {"version": ev.version, "sha256": ev.sha256, "file_name": ev.file_name}
    try:
        v, impact = evs.new_version(db, ev, file.filename or "evidence", data, reason, current.user.email, scan)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    audit.record(db, action="evidence.version_added", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="evidence", entity_id=str(ev.id),
                 before=before, after={"version": v.version, "sha256": v.sha256, "file_name": v.file_name}, details={"reason": reason, "flagged": impact, "scan": scan},
                 **audit.request_meta(request))
    db.commit()
    return {**evs.meta(db, ev, True), "flagged_for_revalidation": impact}


class RemoveIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


@router.post("/evidence/{evidence_id}/remove")
def evidence_remove(evidence_id: uuid.UUID, body: RemoveIn, request: Request, db: Session = Depends(get_db),
                    current: CurrentUser = Depends(require_permission("evidence.submit"))) -> dict:
    """Logical removal (record, versions and objects kept; mappings closed and flagged). Blocked while a legal hold is set."""
    from app.services import evidence_versions as evs

    ev = _ev(db, evidence_id, current, "evidence.submit")
    try:
        impact = evs.remove(db, ev, body.reason, current.user.email)
    except PermissionError as exc:
        raise HTTPException(423, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    audit.record(db, action="evidence.removed", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="evidence", entity_id=str(ev.id),
                 after={"status": "removed"}, details={"reason": body.reason, "flagged": impact}, **audit.request_meta(request))
    db.commit()
    return {**evs.meta(db, ev, True), "flagged_for_revalidation": impact}


class HoldIn(BaseModel):
    on: bool
    reason: str = Field(min_length=5, max_length=2000)


@router.post("/evidence/{evidence_id}/legal-hold")
def evidence_legal_hold(evidence_id: uuid.UUID, body: HoldIn, request: Request, db: Session = Depends(get_db),
                        current: CurrentUser = Depends(require_permission("admin.content.load"))) -> dict:
    from app.services import evidence_versions as evs

    ev = _ev(db, evidence_id, current, "admin.content.load")
    ev.legal_hold = body.on
    audit.record(db, action="evidence.legal_hold_set" if body.on else "evidence.legal_hold_lifted", actor_user_id=current.user.id, actor_email=current.user.email,
                 entity_type="evidence", entity_id=str(ev.id), details={"reason": body.reason}, **audit.request_meta(request))
    db.commit()
    return evs.meta(db, ev, True)
