"""HW/SW inventory (eMASS template import/export), consistency discrepancies and scan→asset correlation review."""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (Asset, AssetCorrelation, AssetIdentifier, Finding, InventoryDiscrepancy, InventoryExport, InventoryImport, SoftwareItem, System)
from app.security.deps import CurrentUser, get_current_user, require_object_permission, require_permission
from app.services import audit, jobs, sod
from app.services.inventory import consistency as cs
from app.services.inventory import correlate as cr
from app.services.inventory import hwsw

router = APIRouter(tags=["inventory"])


def _sys(db: Session, sid, current: CurrentUser, perm: str = "system.read") -> System:
    from app.security.rbac import has_permission

    s = db.get(System, sid)
    if s is None or s.org_id != current.user.org_id:
        raise HTTPException(404, "System not found")
    if not has_permission(current.assignments, perm, current.user.org_id, s.id):
        raise HTTPException(403, "Your role cannot change the inventory" if perm != "system.read" else "Your role cannot view this system")
    return s


def _iso(d):
    return d.isoformat() if d else None


def _asset(a: Asset, fcount: dict, linked: dict) -> dict:
    group = [a.id, *[x.id for x in linked.get(a.id, [])]]
    return {"id": str(a.id), "name": a.name, "hostname": a.hostname, "fqdn": a.fqdn, "ip_address": a.ip_address, "ip_addresses": a.ip_addresses or [],
            "mac_address": a.mac_address, "serial_number": a.serial_number, "os": a.os, "asset_type": a.asset_type, "inventory": a.inventory or {},
            "inventory_source": a.inventory_source, "source_label": cs.src_label(a.inventory_source), "collector": (a.provenance or {}).get("collector"),
            "is_inventory": cs.is_inventory(a),
            "correlated_asset_id": str(a.correlated_asset_id) if a.correlated_asset_id else None, "last_observed_at": _iso(a.last_observed_at),
            "findings": sum(fcount.get(i, 0) for i in group), "linked_scan_assets": [{"id": str(x.id), "name": x.name, "source_label": cs.src_label(x.inventory_source)}
                                                                                      for x in linked.get(a.id, [])]}


@router.post("/systems/{system_id}/inventory/imports", status_code=201)
async def upload(system_id: uuid.UUID, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = _sys(db, system_id, current, "system.write")
    data = await file.read()
    if not (file.filename or "").lower().endswith((".xlsm", ".xlsx")) or data[:2] != b"PK":
        raise HTTPException(422, "Upload the eMASS Hardware/Software List template (.xlsm)")
    imp = hwsw.upload(db, s, file.filename, data, current.user)
    audit.record(db, action="inventory.import_uploaded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="inventory_import",
                 entity_id=str(imp.id), after={"file_name": imp.file_name, "sha256": imp.sha256, "version": imp.version}, **audit.request_meta(request))
    db.commit()
    return {"id": str(imp.id), "version": imp.version, "sha256": imp.sha256, "status": imp.status}


@router.get("/systems/{system_id}/inventory")
def overview(system_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    from sqlalchemy import func

    s = _sys(db, system_id, current)
    assets = list(db.scalars(select(Asset).where(Asset.system_id == s.id).order_by(Asset.name)))
    linked: dict = {}
    for a in assets:
        if a.correlated_asset_id:
            linked.setdefault(a.correlated_asset_id, []).append(a)
    fcount = dict(db.execute(select(Finding.asset_id, func.count()).where(Finding.system_id == s.id).group_by(Finding.asset_id)).all())
    imps = db.scalars(select(InventoryImport).where(InventoryImport.system_id == s.id).order_by(InventoryImport.version.desc()))
    exps = db.scalars(select(InventoryExport).where(InventoryExport.system_id == s.id).order_by(InventoryExport.version.desc()))
    return {"imports": [{"id": str(i.id), "file_name": i.file_name, "version": i.version, "sha256": i.sha256, "status": i.status, "error": i.error, "counts": i.counts,
                         "uploaded_by": i.uploaded_by, "created_at": _iso(i.created_at), "has_vba": (i.detection or {}).get("has_vba")} for i in imps],
            "exports": [{"id": str(e.id), "file_name": e.file_name, "version": e.version, "sha256": e.sha256, "exported_by": e.exported_by, "counts": e.counts,
                         "ok": (e.verification or {}).get("ok"), "changed": len((e.verification or {}).get("changed_cells", [])), "created_at": _iso(e.created_at),
                         "sandbox_same_person_changes": (e.verification or {}).get("sandbox_same_person_changes", 0)} for e in exps],
            "hardware": [_asset(a, fcount, linked) for a in assets if cs.is_inventory(a)],
            "scan_observed": [_asset(a, fcount, linked) for a in assets if not cs.is_inventory(a)],
            "software": [{"id": str(x.id), "vendor": x.vendor, "name": x.name, "version": x.version, "sw_type": x.sw_type, "source_label": cs.src_label(x.source),
                          "attributes": x.attributes or {}} for x in db.scalars(select(SoftwareItem).where(SoftwareItem.system_id == s.id).order_by(SoftwareItem.vendor))],
            "can_write": _can(current, "system.write", s.id)}


def _can(current, perm, sid) -> bool:
    from app.security.rbac import has_permission

    return has_permission(current.assignments, perm, current.user.org_id, sid)


@router.get("/systems/{system_id}/inventory/assets/{asset_id}")
def asset_detail(system_id: uuid.UUID, asset_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    s = _sys(db, system_id, current)
    a = db.get(Asset, asset_id)
    if a is None or a.system_id != s.id:
        raise HTTPException(404, "Asset not found")
    group = [a.id, *db.scalars(select(Asset.id).where(Asset.correlated_asset_id == a.id))]
    fs = list(db.scalars(select(Finding).where(Finding.asset_id.in_(group)).order_by(Finding.severity)))
    idents = list(db.scalars(select(AssetIdentifier).where(AssetIdentifier.asset_id.in_(group)).order_by(AssetIdentifier.kind)))
    keys = {f.vuln_id or f.plugin_id for f in fs if f.current_state == "open" and (f.vuln_id or f.plugin_id)}
    related = db.execute(select(Finding.vuln_id, Finding.plugin_id, Asset.name).join(Asset, Asset.id == Finding.asset_id).where(
        Finding.system_id == s.id, Finding.asset_id.notin_(group), Finding.current_state == "open",
        or_(Finding.vuln_id.in_(keys), Finding.plugin_id.in_(keys)))).all() if keys else []
    rel: dict = {}
    for v, p, host in related:
        rel.setdefault(v or p, set()).add(host)
    return {"asset": _asset(a, {}, {}), "identifiers": [{"kind": i.kind, "value": i.value, "source": i.source, "source_label": cs.src_label(i.source),
                                                         "first_seen_at": _iso(i.first_seen_at), "last_seen_at": _iso(i.last_seen_at)} for i in idents],
            "findings": [{"id": str(f.id), "source_type": f.source_type, "vuln_id": f.vuln_id, "plugin_id": f.plugin_id, "title": f.title, "state": f.current_state,
                          "severity": f.cat or f.severity, "benchmark": f.benchmark, "cves": f.cves or [], "last_seen_at": _iso(f.last_seen_at),
                          "observed_on": str(f.asset_id)} for f in fs],
            "applies_to": sorted({i.value for i in idents if i.kind in ("benchmark", "cpe", "os")}),
            "potentially_related": [{"key": k, "other_assets": sorted(h), "note": "Proposal only – the same rule/plugin is open on other assets; no finding is created"}
                                    for k, h in sorted(rel.items())]}


@router.post("/systems/{system_id}/inventory/check", status_code=202)
def check(system_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = _sys(db, system_id, current)
    job = jobs.enqueue(db, "inventory.check", {"system_id": str(s.id)}, requested_by=current.user.id)
    db.commit()
    return {"ok": True, "job_id": str(job.id)}


def _accepted(d: InventoryDiscrepancy) -> dict | None:
    if d.accepted_identity:
        return d.accepted_identity
    return {"real_user_id": str(d.accepted_by_user_id), "persona_user_id": str(d.accepted_by_user_id)} if d.accepted_by_user_id else None


def _real(current: CurrentUser):
    """Real person behind the request (a sandbox persona is operated by its real user)."""
    return current.operator.id if current.operator else current.user.id


def _disc(d: InventoryDiscrepancy, current=None, sandbox: bool = False) -> dict:
    return {"id": str(d.id), "kind": d.kind, "kind_label": cs.KIND_LABEL.get(d.kind, d.kind), "status": d.status, "title": d.title, "records": d.records,
            "details": d.details or {}, "recommendation": d.recommendation, "proposed_change": d.proposed_change, "ai": d.ai, "decided_by": d.decided_by,
            "decided_at": _iso(d.decided_at), "reason": d.reason, "applied_by": d.applied_by, "applied_at": _iso(d.applied_at), "last_detected_at": _iso(d.last_detected_at),
            "approve_locked": sod.evaluate(_accepted(d), current, sandbox, "accepted the resolution for")[0] if d.status == "pending_approval" and current else None,
            "accepted_identity": d.accepted_identity, "sod": d.sod}


@router.get("/systems/{system_id}/inventory/discrepancies")
def discrepancies(system_id: uuid.UUID, status: str = "open,pending_approval", db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list:
    s = _sys(db, system_id, current)
    q = select(InventoryDiscrepancy).where(InventoryDiscrepancy.system_id == s.id).order_by(InventoryDiscrepancy.kind, InventoryDiscrepancy.title)
    if status != "all":
        q = q.where(InventoryDiscrepancy.status.in_(status.split(",")))
    sb = sod.is_sandbox(db, s.org_id)
    return [_disc(d, current, sb) for d in db.scalars(q)]


class DiscAction(BaseModel):
    action: str = Field(pattern="^(accept|approve|reject|ignore|explain)$")
    reason: str = Field(default="", max_length=2000)


def _own(db, model, oid, current):
    o = db.get(model, oid)
    s = db.get(System, o.system_id) if o else None
    if o is None or s.org_id != current.user.org_id:
        raise HTTPException(404, "Not found")
    return o, s


@router.post("/inventory/discrepancies/{did}")
def act(did: uuid.UUID, body: DiscAction, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("system.read", "InventoryDiscrepancy", "did"))) -> dict:
    d, s = _own(db, InventoryDiscrepancy, did, current)
    meta = audit.request_meta(request)
    if body.action == "explain":
        _sys(db, s.id, current)
        job = jobs.enqueue(db, "inventory.ai", {"kind": "discrepancy", "id": str(d.id), "actor_id": str(current.user.id)}, requested_by=current.user.id)
        db.commit()
        return {"ok": True, "job_id": str(job.id)}
    _sys(db, s.id, current, "system.write")
    before = {"status": d.status}
    if body.action == "ignore":
        if len(body.reason.strip()) < 10:
            raise HTTPException(422, "Give a reason (at least 10 characters) – it is kept in the audit history")
        d.status, d.reason = "ignored", body.reason.strip()
    elif body.action == "accept":
        if d.status != "open" or not d.proposed_change:
            raise HTTPException(409, "Only an open discrepancy with a proposed resolution can be accepted")
        d.status, d.accepted_by_user_id, d.accepted_identity = "pending_approval", _real(current), sod.identity(current)
    elif body.action == "reject":
        if d.status != "pending_approval":
            raise HTTPException(409, "Nothing is pending approval")
        d.status, d.reason = "open", body.reason.strip() or None
    else:
        if d.status != "pending_approval":
            raise HTTPException(409, "Accept the resolution first – changes are applied only after approval")
        why, sod_det = sod.evaluate(_accepted(d), current, sod.is_sandbox(db, s.org_id), "accepted the resolution for")
        if why:
            raise HTTPException(403, why)
        d.sod = sod_det
        try:
            change = cs.apply(db, d, current.user.email)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        d.status, d.applied_by, d.applied_at = "applied", current.user.email, cr.now()
        audit.record(db, action="inventory.change_applied", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="inventory_discrepancy",
                     entity_id=str(d.id), before=change["before"], after={**(change["after"] or {}), "proposed_change": d.proposed_change, "accepted_by": d.decided_by},
                     details=sod_det, **meta)
    if body.action != "approve":
        d.decided_by, d.decided_at = current.user.email, cr.now()
    audit.record(db, action=f"inventory.discrepancy_{body.action}", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="inventory_discrepancy",
                 entity_id=str(d.id), before=before, after={"status": d.status, "reason": d.reason, "kind": d.kind, "proposed_change": d.proposed_change}, **meta)
    db.commit()
    return _disc(d, current, sod.is_sandbox(db, s.org_id))


def _corr(db, c: AssetCorrelation) -> dict:
    o = db.get(Asset, c.observed_asset_id) if c.observed_asset_id else None
    return {"id": str(c.id), "status": c.status, "method": c.method, "reason": c.reason, "facts": c.facts, "candidates": c.candidates, "ai": c.ai,
            "observed_asset": {"id": str(o.id), "name": o.name, "source_label": cs.src_label(o.inventory_source)} if o else None,
            "chosen_asset_id": str(c.chosen_asset_id) if c.chosen_asset_id else None, "source_format": c.source_format, "evidence_ids": c.evidence_ids or [],
            "decided_by": c.decided_by, "justification": c.justification, "last_seen_at": _iso(c.last_seen_at)}


@router.get("/systems/{system_id}/inventory/correlations")
def correlations(system_id: uuid.UUID, status: str = "needs_review", db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list:
    s = _sys(db, system_id, current)
    q = select(AssetCorrelation).where(AssetCorrelation.system_id == s.id).order_by(AssetCorrelation.created_at.desc())
    if status != "all":
        q = q.where(AssetCorrelation.status.in_(status.split(",")))
    return [_corr(db, c) for c in db.scalars(q)]


class CorrDecision(BaseModel):
    action: str = Field(pattern="^(confirm|reject|explain)$")
    asset_id: uuid.UUID | None = None
    justification: str = Field(default="", max_length=2000)


@router.post("/inventory/correlations/{cid}")
def decide_correlation(cid: uuid.UUID, body: CorrDecision, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("system.read", "AssetCorrelation", "cid"))) -> dict:
    c, s = _own(db, AssetCorrelation, cid, current)
    if body.action == "explain":
        _sys(db, s.id, current)
        job = jobs.enqueue(db, "inventory.ai", {"kind": "correlation", "id": str(c.id), "actor_id": str(current.user.id)}, requested_by=current.user.id)
        db.commit()
        return {"ok": True, "job_id": str(job.id)}
    _sys(db, s.id, current, "system.write")
    if c.status != "needs_review":
        raise HTTPException(409, "This correlation is not awaiting review")
    if len(body.justification.strip()) < 10:
        raise HTTPException(422, "Give a justification (at least 10 characters) – it is kept in the audit history")
    observed = db.get(Asset, c.observed_asset_id)
    if body.action == "confirm":
        if str(body.asset_id) not in {x["asset_id"] for x in c.candidates}:
            raise HTTPException(422, "Choose one of the listed candidate assets")
        target = db.get(Asset, body.asset_id)
        if target is None or target.system_id != s.id:
            raise HTTPException(404, "Asset not found")
        cr.link(db, observed, target)
        c.status, c.chosen_asset_id = "confirmed", target.id
        cr.record_identifiers(db, target, c.facts, f"ingest:{c.source_format}", "confirmed-correlation")
    else:
        c.status = "rejected"
    c.decided_by, c.decided_at, c.justification = current.user.email, cr.now(), body.justification.strip()
    audit.record(db, action=f"inventory.correlation_{body.action}ed".replace("ee", "e"), actor_user_id=current.user.id, actor_email=current.user.email,
                 entity_type="asset_correlation", entity_id=str(c.id), before={"status": "needs_review"},
                 after={"status": c.status, "observed_asset_id": str(observed.id), "chosen_asset_id": str(c.chosen_asset_id) if c.chosen_asset_id else None,
                        "justification": c.justification, "ai_suggestion": (c.ai or {}).get("ranking", [None])[0] if c.ai else None}, **audit.request_meta(request))
    jobs.enqueue(db, "inventory.check", {"system_id": str(s.id)})
    db.commit()
    return _corr(db, c)


@router.post("/systems/{system_id}/inventory/export")
def export(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = _sys(db, system_id, current)
    try:
        e = hwsw.export(db, s, current.user)
    except ValueError as ex:
        raise HTTPException(409, str(ex)) from ex
    audit.record(db, action="inventory.exported", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="inventory_export", entity_id=str(e.id),
                 after={"version": e.version, "sha256": e.sha256, "counts": e.counts, "changed_cells": len(e.verification["changed_cells"]),
                        "vba_unchanged": all(v["unchanged"] for v in e.verification["vba_parts"].values())}, **audit.request_meta(request))
    db.commit()
    return {"id": str(e.id), "version": e.version, "file_name": e.file_name, "sha256": e.sha256, "counts": e.counts, "verification": e.verification}


@router.get("/inventory/exports/{eid}/download")
def download(eid: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> Response:
    from app.services.storage.base import get_storage

    e, _ = _own(db, InventoryExport, eid, current)
    return Response(get_storage().get(e.storage_key), media_type=hwsw.XLSM, headers={"Content-Disposition": f'attachment; filename="{e.file_name}"'})


@router.get("/inventory/exports/{eid}/validation-report")
def report(eid: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    e, _ = _own(db, InventoryExport, eid, current)
    return {"file_name": e.file_name, "sha256": e.sha256, "exported_by": e.exported_by, "created_at": _iso(e.created_at), **e.verification}
