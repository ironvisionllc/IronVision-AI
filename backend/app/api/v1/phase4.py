import asyncio
import uuid
from app.services.queue import fmt_control
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.records import get_system, to_dict
from app.db import get_db
from app.models import (ContentUpdate, ContentVersion, ControlAssignment, EmassChange, EmassSyncRun, Evidence, Finding, FindingControlMap, Poam,
                        PriorityWeight, Policy, ScheduledJob, StigRule, System)
from app.security.deps import CurrentUser, enforce, get_current_user, require_body_permission, require_object_permission, require_permission
from app.security.rbac import has_permission
from app.services import audit, content_updates as cu, emass, oscal_export as ox, risk, scheduler
from app.services import workflow as wf
from app.services.evaluation import evaluate_system
from app.services.people import attach
from app.services.storage import get_storage

router = APIRouter(tags=["phase4"])


class Justify(BaseModel):
    justification: str = Field(min_length=10, max_length=5000)


# ---------- content updates ----------
@router.get("/content-updates")
def content_overview(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    hist = db.scalars(select(ContentUpdate).where(ContentUpdate.org_id == current.user.org_id).order_by(ContentUpdate.created_at.desc()).limit(50))
    rows = []
    for u in hist:
        d = to_dict(u, ("impact",))
        to, fr = db.get(ContentVersion, u.to_version_id), db.get(ContentVersion, u.from_version_id) if u.from_version_id else None
        d.update(to_version=to.version if to else None, from_version=fr.version if fr else None, counts=(u.impact or {}).get("counts"))
        rows.append(d)
    return {"types": cu.overview(db, *tenant_content_flags(db, current.user.org_id)),
            "history": attach(db, attach(db, rows, "applied_by", "applier"), "requested_by", "requester")}


def tenant_content_flags(db: Session, org_id) -> tuple[bool, bool]:
    """(show_synthetic, show_updates) – a clean tenant sees no synthetic sample content and no update/diff offers."""
    from app.services import sandbox as sbx
    demo = sbx.has_demo_data(db, org_id)
    has_systems = db.scalar(select(System.id).where(System.org_id == org_id).limit(1)) is not None
    return demo, demo or has_systems


@router.post("/content-updates/register")
def content_register(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.content.load"))) -> dict:
    r = cu.register_all(db)
    audit.record(db, action="content.registered", actor_user_id=current.user.id, actor_email=current.user.email, details=r)
    db.commit()
    return r


@router.post("/content-versions/{version_id}/preview", status_code=201)
def content_preview(version_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    v = db.get(ContentVersion, version_id)
    show_synth, show_updates = tenant_content_flags(db, current.user.org_id)
    if v is None or ((v.meta or {}).get("synthetic") and not show_synth) or not show_updates:
        raise HTTPException(404, "No content update to preview for this workspace")
    u = cu.preview(db, current.user.org_id, current.user, version_id)
    db.commit()
    return to_dict(u)


@router.get("/content-updates/{update_id}")
def content_update(update_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    u = db.get(ContentUpdate, update_id)
    if u is None or u.org_id != current.user.org_id:
        raise HTTPException(404, "Update not found")
    return to_dict(u)


@router.post("/content-updates/{update_id}/apply")
def content_apply(update_id: uuid.UUID, body: Justify, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("content.apply"))) -> dict:
    u = db.get(ContentUpdate, update_id)
    if u is None or u.org_id != current.user.org_id:
        raise HTTPException(404, "Update not found")
    res = cu.apply(db, u, current.user, body.justification)
    db.commit()
    return {"status": u.status, "result": res}


@router.get("/content-versions/{version_id}/rules")
def stig_rules(version_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    return [to_dict(r) for r in db.scalars(select(StigRule).where(StigRule.content_version_id == version_id).order_by(StigRule.vuln_id))]


# ---------- mappings ----------
@router.get("/findings/{finding_id}/mappings")
def finding_mappings(finding_id: uuid.UUID, request: Request, as_of: uuid.UUID | None = None, db: Session = Depends(get_db),
                     current: CurrentUser = Depends(get_current_user)) -> dict:
    """Mappings now, or as they stood under a given content version (STIG release or CCI list) – reproducible history."""
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    enforce(request, current, "system.read", f.system_id)
    q = select(FindingControlMap).where(FindingControlMap.finding_id == f.id)
    if as_of:
        cv = db.get(ContentVersion, as_of)
        if cv is None:
            raise HTTPException(404, "Content version not found")
        if cv.content_type == "stig_benchmark":
            q = q.where(or_(FindingControlMap.stig_version_id == as_of,
                            (FindingControlMap.stig_version_id.is_(None)) & (or_(FindingControlMap.valid_to.is_(None), FindingControlMap.superseded_by_version_id != as_of))))
        else:
            q = q.where(FindingControlMap.content_version_id == as_of)
    else:
        q = q.where(FindingControlMap.valid_to.is_(None))
    obs = db.execute(select(ContentVersion.version, ContentVersion.id).where(ContentVersion.id == f.content_version_id)).first()
    return {"finding_id": str(f.id), "as_of": str(as_of) if as_of else None, "current_content_version": obs[0] if obs else None,
            "mappings": [to_dict(m) for m in db.scalars(q.order_by(FindingControlMap.control_id))]}


@router.get("/mapping-review")
def mapping_review(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    enforce(request, current, "system.read", system_id)
    rows = db.execute(select(FindingControlMap, Finding).join(Finding, Finding.id == FindingControlMap.finding_id)
                      .where(Finding.system_id == system_id, FindingControlMap.valid_to.is_(None),
                             or_(FindingControlMap.review_status.in_(("suggested", "needs_review", "unresolved")), FindingControlMap.confidence == "low"))
                      .order_by(FindingControlMap.created_at.desc())).all()
    from app.models import Asset
    from app.services.ai.service import get_ai_service

    groups: dict = {}
    for f, host in db.execute(select(Finding, Asset.name).outerjoin(Asset, Asset.id == Finding.asset_id).where(
            Finding.system_id == system_id, Finding.mapping_status == "unmapped", Finding.current_state == "open").order_by(Finding.vuln_id)):
        k = f.vuln_id or f.rule_id or f.plugin_id or str(f.id)
        g = groups.setdefault(k, {"rule_key": k, "id": str(f.id), "title": f.title, "vuln_id": k, "source_type": f.source_type, "ccis": f.ccis,
                                  "severity": f.cat or f.severity, "finding_ids": [], "hosts": []})
        g["finding_ids"].append(str(f.id))
        g["hosts"].append(host or "—")
    passing = db.scalar(select(func.count()).select_from(Finding).where(Finding.system_id == system_id, Finding.mapping_status == "unmapped",
                                                                         Finding.current_state != "open"))
    from app.models import ApprovalRequest, AssetCorrelation
    pend = {str(r.finding_id): r.human_id for r in db.scalars(select(ApprovalRequest).where(ApprovalRequest.system_id == system_id,
                                                                                          ApprovalRequest.status == "pending",
                                                                                          ApprovalRequest.request_type == "finding_out_of_scope"))}
    from app.services import review_queue as rq
    sysobj = db.get(System, system_id)
    from app.services import policy_coverage as pc

    review_needed: list = []
    status_notes: list = []
    queue = rq.status_suggestions(db, sysobj) + pc.suggestions(db, sysobj, review_needed, status_notes) + rq.policy_proposals(db, sysobj) + rq.automated_maps(db, system_id)
    return {"queue": queue, "review_needed": review_needed, "status_notes": status_notes, "queue_counts": {k: sum(1 for q in queue if q["kind"] == k) for k in ("status", "policy_status", "policy_map", "finding_map")},
            "pending": [{**to_dict(m), "finding_title": f.title, "vuln_id": f.vuln_id or f.plugin_id} for m, f in rows],
            "unmapped": [{**g, "host_count": len(set(g["hosts"])), "pending_disposition": next((pend[i] for i in g["finding_ids"] if i in pend), None)}
                         for g in groups.values()],
            "unmapped_findings_total": sum(len(g["finding_ids"]) for g in groups.values()),
            "passing_unmapped_excluded": passing, "ai_configured": get_ai_service().configured,
            "asset_correlations_pending": db.scalar(select(func.count()).select_from(AssetCorrelation).where(
                AssetCorrelation.system_id == system_id, AssetCorrelation.status == "needs_review")),
            "ai_status": get_ai_service().describe()}


class RuleAction(BaseModel):
    system_id: uuid.UUID
    finding_ids: list[uuid.UUID] = Field(min_length=1)
    action: str = Field(pattern="^(map|out_of_scope|informational)$")
    control_ids: list[str] = []
    justification: str = Field(min_length=10, max_length=2000)


@router.post("/mapping-review/rule-action")
def mapping_rule_action(body: RuleAction, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_body_permission("finding.map"))) -> dict:
    """Map manually (multiple controls, human_approved with provenance), mark out of scope / N/A, or accept as informational –
    applied to every selected finding of the rule (all hosts by default)."""
    from app.models import ControlAssignment, EvidenceControl, FindingControlMap
    from app.services import audit
    from app.services.evaluation import evaluate_system

    enforce(request, current, "finding.map", body.system_id)
    fs = [f for f in (db.get(Finding, i) for i in body.finding_ids) if f and f.system_id == body.system_id]
    if len(fs) != len(body.finding_ids):
        raise HTTPException(422, "All findings must belong to the system")
    if body.action == "map":
        ctl = [c.strip().lower().replace("(", ".").replace(")", "") for c in body.control_ids]
        assigns = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == body.system_id,
                                                                                         ControlAssignment.control_id.in_(ctl)))}
        if not ctl or (missing := [c for c in ctl if c not in assigns]):
            raise HTTPException(422, f"Controls not assigned to this system: {', '.join(missing) if ctl else '(none selected)'}")
        for f in fs:
            for c in ctl:
                db.add(FindingControlMap(finding_id=f.id, control_id=c, mapping_source="manual", review_status="human_approved", confidence="human",
                                         justification=body.justification, mapped_by=current.user.id,
                                         source=f"Manual mapping by {current.user.email}", provenance={"rule_key": f.vuln_id or f.rule_id, "bulk": len(fs) > 1}))
                if f.latest_evidence_id and not db.scalar(select(EvidenceControl.id).where(EvidenceControl.evidence_id == f.latest_evidence_id,
                                                                                            EvidenceControl.assignment_id == assigns[c].id)):
                    db.add(EvidenceControl(evidence_id=f.latest_evidence_id, assignment_id=assigns[c].id))
            f.mapping_status = "mapped"
    else:
        from app.models import System

        req = wf.request_disposition(db, system=db.get(System, body.system_id), requester=current.user, findings=fs,
                                     disposition=body.action, justification=body.justification)
        db.commit()
        return {"ok": True, "updated": 0, "pending_request": req.human_id, "request_id": str(req.id),
                "message": f"{req.human_id}: {body.action.replace('_', ' ')} disposition awaiting {req.assigned_role.upper()} – not applied until approved"}
    audit.record(db, action=f"mapping.rule_{body.action}", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="finding",
                 entity_id=str(fs[0].id), after={"findings": len(fs), "controls": body.control_ids, "justification": body.justification})
    db.flush()
    evaluate_system(db, body.system_id)
    db.commit()
    return {"ok": True, "updated": len(fs)}


class MapReview(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    justification: str = Field(min_length=10, max_length=2000)


class QueueItem(BaseModel):
    kind: str = Field(pattern="^(status|policy_status|policy_map|finding_map)$")
    ids: list[str] = Field(min_length=1)
    control_id: str
    evidence_fp: str | None = None


class QueueDecision(BaseModel):
    system_id: uuid.UUID
    items: list[QueueItem] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(approve|reject|edit)$")
    justification: str = Field(default="", max_length=2000)
    edit_control_ids: list[str] = []


@router.post("/mapping-review/decide")
def mapping_review_decide(body: QueueDecision, request: Request, db: Session = Depends(get_db),
                          current: CurrentUser = Depends(require_body_permission("finding.map"))) -> dict:
    """Approve / reject / edit one or many queue items with ONE shared justification (required for reject and edit)."""
    from app.models import ControlAssignment, PolicyControlMap
    from app.services import audit, policy_mapping as pm, review_queue as rq
    from app.services.evaluation import evaluate_system

    enforce(request, current, "finding.map", body.system_id)
    if body.action == "approve" and any(i.kind in ("status", "policy_status") for i in body.items):
        enforce(request, current, "implementation.write", body.system_id)  # checked before any audit row takes the chain lock
    can_assess = has_permission(current.assignments, "assessment.perform", current.user.org_id, body.system_id)
    just = body.justification.strip()
    if body.action in ("reject", "edit") and len(just) < 10:
        raise HTTPException(422, "Please give a reason (at least 10 characters) – it is required to reject or edit and is kept in the audit history.")
    edit = [c.strip().lower().replace("(", ".").replace(")", "") for c in body.edit_control_ids if c.strip()]
    if body.action == "edit" and not edit:
        raise HTTPException(422, "Choose the control(s) the mapping should point to instead")
    system = db.get(System, body.system_id)
    result = {"approved": 0, "rejected": 0, "edited": 0, "partial": []}
    for it in body.items:
        if it.kind == "finding_map":
            rq.decide_finding_maps(db, it.ids, body.action, current.user, just, body.system_id, edit)
        elif it.kind == "policy_status":
            from app.services import policy_coverage as pc

            pol = db.get(Policy, uuid.UUID(it.ids[0]))
            if pol is None or pol.org_id != current.user.org_id:
                raise HTTPException(404, "Policy not found")
            if body.action == "edit":
                raise HTTPException(422, "A coverage status suggestion can only be approved or rejected")
            if body.action == "reject":
                pc.dismiss(db, system, str(pol.id), it.control_id, it.evidence_fp or "", current.user, just)
            else:
                try:
                    r = pc.approve(db, system, pol, it.control_id, current.user)
                except ValueError as e:
                    raise HTTPException(409, str(e)) from e
                result["partial"].append(it.control_id)
                audit.record(db, action="control.policy_coverage_status_approved", actor_user_id=current.user.id, actor_email=current.user.email,
                             entity_type="control_assignment", entity_id=str(r["assignment"].id), before=r["before"],
                             after={"implementation_status": r["target"], "policy_id": str(pol.id), "policy_version": pol.version, "linked_requirements": r["linked"],
                                    "coverage": {k: r["summary"][k] for k in ("total", "met", "partial", "missing", "gaps")}, "justification": just,
                                    "also_approved": [x["text"] for x in r["also_approved"]]},
                             **audit.request_meta(request))
                for x in r["also_approved"]:  # one audit event per related item the approval resolved
                    audit.record(db, action="policy.mapping_approved_with_status", actor_user_id=current.user.id, actor_email=current.user.email,
                                 entity_type="policy_control_map", entity_id=x["map_id"], before={"status": "proposed"},
                                 after={"status": "mapped", "control_id": x["control_id"], "policy_id": x["policy_id"], "policy_version": x["version"],
                                        "reason": "Also approved with the policy coverage status suggestion"}, **audit.request_meta(request))
                    result.setdefault("also_approved", []).append(x["text"])
        elif it.kind == "policy_map":
            m = db.get(PolicyControlMap, uuid.UUID(it.ids[0]))
            pol = db.get(Policy, m.policy_id) if m else None
            if m is None or pol is None or pol.org_id != current.user.org_id:
                raise HTTPException(404, "Policy mapping not found")
            pm.decide(db, pol, m.control_id, "mapped" if body.action == "approve" else "rejected", current.user, just or None)
            for c in edit if body.action == "edit" else []:
                pm.decide(db, pol, c, "mapped", current.user, just)
        else:
            a = db.get(ControlAssignment, uuid.UUID(it.ids[0]))
            if a is None or a.system_id != body.system_id:
                raise HTTPException(404, "Control not found in this system")
            if body.action != "approve":
                rq.dismiss_status(db, system, a.control_id, it.evidence_fp or "", current.user, just)
            else:
                before = {"implementation_status": a.implementation_status, "assessment_status": a.assessment_status}
                a.implementation_status = "implemented"
                if can_assess:   # separation of duties: only the assessor role may set the assessment result
                    a.assessment_status = "satisfied"
                else:
                    result["partial"].append(a.control_id)
                ev = [e["id"] for e in next((s for s in rq.status_suggestions(db, system) if s["control_id"] == a.control_id), {"evidence": []})["evidence"]]
                audit.record(db, action="control.status_suggestion_approved", actor_user_id=current.user.id, actor_email=current.user.email,
                             entity_type="control_assignment", entity_id=str(a.id), before=before,
                             after={"implementation_status": a.implementation_status, "assessment_status": a.assessment_status, "evidence_ids": ev,
                                    "justification": just}, **audit.request_meta(request))
        result[{"approve": "approved", "reject": "rejected", "edit": "edited"}[body.action]] += 1
        audit.record(db, action=f"mapping_review.item_{ {'approve': 'approved', 'reject': 'rejected', 'edit': 'edited'}[body.action] }",
                     actor_user_id=current.user.id, actor_email=current.user.email, entity_type=it.kind, entity_id=",".join(it.ids)[:200],
                     after={"system_id": str(body.system_id), "control_id": it.control_id, "kind": it.kind, "justification": just,
                            "awaiting_sca": it.kind in ("status", "policy_status") and body.action == "approve" and not can_assess}, **audit.request_meta(request))
    audit.record(db, action=f"mapping_review.{body.action}", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(body.system_id), after={"items": [i.model_dump() for i in body.items], "justification": just, "edit": edit},
                 **audit.request_meta(request))
    evaluate_system(db, body.system_id)
    db.commit()
    return result


@router.post("/mappings/{map_id}/review")
def review_mapping(map_id: uuid.UUID, body: MapReview, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("finding.map", "FindingControlMap", "map_id"))) -> dict:
    m = db.get(FindingControlMap, map_id)
    if m is None:
        raise HTTPException(404, "Mapping not found")
    f = db.get(Finding, m.finding_id)
    enforce(request, current, "finding.map", f.system_id)
    before = m.review_status
    m.review_status = "human_approved" if body.action == "approve" else "rejected"
    m.justification, m.reviewed_by, m.reviewed_at = body.justification, current.user.id, datetime.now(timezone.utc)
    if body.action == "reject":
        m.valid_to = datetime.now(timezone.utc)
    db.flush()
    live = db.scalar(select(FindingControlMap.id).where(FindingControlMap.finding_id == f.id, FindingControlMap.valid_to.is_(None),
                                                        FindingControlMap.review_status != "suggested").limit(1))
    if f.mapping_status != "dispositioned":
        f.mapping_status = "mapped" if live else "unmapped"
    audit.record(db, action=f"mapping.{body.action}d", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="finding_control_map",
                 entity_id=str(m.id), before={"review_status": before}, after={"review_status": m.review_status, "control_id": m.control_id,
                                                                            "justification": body.justification})
    evaluate_system(db, f.system_id)
    db.commit()
    return to_dict(m)


@router.post("/findings/{finding_id}/suggest-mapping")
def suggest_mapping(finding_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("finding.map", "Finding", "finding_id"))) -> dict:
    from app.models import Control
    from app.services.ai.service import get_ai_service
    from app.services.content.loader import active_catalog_id
    from app.services.rmf import require_ai_use_case

    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    enforce(request, current, "finding.map", f.system_id)
    require_ai_use_case(db, current.user.org_id, "mapping.suggest")
    svc = get_ai_service()
    if not svc.configured:
        raise HTTPException(503, "AI provider not configured")
    try:
        r = asyncio.run(svc.run("mapping.suggest", "1.0.0", {"title": f.title, "source": f.source_type, "rule": f.vuln_id or f.plugin_id or "",
                                                              "cves": ", ".join(f.cves or []) or "none", "ccis": ", ".join(f.ccis or []) or "none"},
                                current.user.id))
    except Exception as exc:
        raise HTTPException(502, f"AI suggestion failed: {str(exc)[:200]}")
    cat = active_catalog_id(db)
    valid = {c for (c,) in db.execute(select(Control.control_id).where(Control.catalog_version_id == cat))}
    made, dropped = [], []
    for s in r.output.suggestions:
        cid = s.control_id.lower().replace("(", ".").replace(")", "").strip()
        if cid not in valid:
            dropped.append(cid)
            continue
        if db.scalar(select(FindingControlMap.id).where(FindingControlMap.finding_id == f.id, FindingControlMap.control_id == cid, FindingControlMap.cci_id == "",
                                                        FindingControlMap.valid_to.is_(None))):
            continue
        m = FindingControlMap(finding_id=f.id, control_id=cid, mapping_source="ai_suggestion", review_status="suggested", confidence=s.confidence,
                              justification=s.rationale, source=f"AI {r.model} · mapping.suggest@1.0.0 (proposal – needs human approval)",
                              ai_interaction_id=r.interaction_id, provenance={"prompt": "mapping.suggest@1.0.0"})
        db.add(m)
        made.append(cid)
    audit.record(db, action="mapping.ai_suggested", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="finding",
                 entity_id=str(f.id), details={"suggested": made, "dropped_invalid": dropped, "interaction_id": str(r.interaction_id)})
    db.commit()
    return {"suggested": made, "dropped_invalid": dropped, "interaction_id": str(r.interaction_id)}


# ---------- risk scoring ----------
@router.get("/risk/weights")
def risk_weights(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)) -> dict:
    return {"label": risk.LABEL, "formula": "score = Σ weight × factor (each factor 0–1)",
            "weights": [to_dict(w) for w in db.scalars(select(PriorityWeight).where(PriorityWeight.reason_code.like("rf_%")).order_by(PriorityWeight.reason_code))]}


class WeightsIn(BaseModel):
    weights: dict[str, int]


@router.put("/risk/weights")
def set_weights(body: WeightsIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("risk.admin"))) -> dict:
    before = {}
    for code, val in body.weights.items():
        w = db.scalar(select(PriorityWeight).where(PriorityWeight.reason_code == code))
        if w is None or not code.startswith("rf_") or not 0 <= val <= 100:
            raise HTTPException(422, f"Unknown weight or out of range: {code}")
        before[code], w.weight = w.weight, val
    n = risk.recompute(db)
    audit.record(db, action="risk.weights.updated", actor_user_id=current.user.id, actor_email=current.user.email, before=before, after=body.weights,
                 details={"findings_rescored": n})
    db.commit()
    return {"findings_rescored": n}


@router.get("/findings/{finding_id}/score")
def finding_score(finding_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    enforce(request, current, "system.read", f.system_id)
    return {"score": f.priority_score, "breakdown": f.priority_breakdown, "label": risk.LABEL}


# ---------- OSCAL ----------
@router.get("/systems/{system_id}/oscal")
def oscal_list(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    enforce(request, current, "system.read", system_id)
    evs = db.scalars(select(Evidence).where(Evidence.system_id == system_id, Evidence.evidence_type == "oscal_export").order_by(Evidence.collected_at.desc()).limit(40))
    return {"models": list(ox.MODELS), "oscal_version": ox.OSCAL_VERSION, "unsupported": ox.UNSUPPORTED, "limitations": ox.LIMITATIONS,
            "exports": [{"evidence_id": str(e.id), "file_name": e.file_name, "sha256": e.sha256, "collected_at": e.collected_at.isoformat(),
                         "model": (e.provenance or {}).get("oscal_model"), "validation": (e.provenance or {}).get("validation"),
                         "errors": (e.provenance or {}).get("validation_errors")} for e in evs]}


@router.post("/systems/{system_id}/oscal/{model}", status_code=201)
def oscal_export(system_id: uuid.UUID, model: str, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.read", system_id)
    if model not in ox.MODELS:
        raise HTTPException(422, f"Unsupported OSCAL model {model}. Supported: {', '.join(ox.MODELS)}")
    res = ox.export(db, get_system(db, system_id), model, current.user.email)
    db.commit()
    return res


@router.get("/oscal-exports/{evidence_id}/download")
def oscal_download(evidence_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> Response:
    e = db.get(Evidence, evidence_id)
    if e is None or e.evidence_type != "oscal_export":
        raise HTTPException(404, "Export not found")
    enforce(request, current, "system.read", e.system_id)
    return Response(get_storage().get(e.storage_key), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{e.file_name}"', "X-Content-SHA256": e.sha256})


# ---------- eMASS ----------
@router.get("/emass/status")
def emass_status(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    from app.services.metrics import last_emass_sync

    return {**emass.status(db, current.user.org_id), "last_sync_at": last_emass_sync(db, current.user.org_id)}


class EmassConfigIn(BaseModel):
    mode: str = Field(pattern="^(mock|read|write|oscal_export_only)$")
    base_url: str | None = Field(None, max_length=500)
    api_user_uid: str | None = Field(None, max_length=200)
    api_key: str | None = Field(None, max_length=500)
    client_cert_path: str | None = Field(None, max_length=500)
    app_registration_id: str | None = Field(None, max_length=200)


@router.put("/emass/config")
def emass_config(body: EmassConfigIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("emass.admin"))) -> dict:
    cfg = emass.config(db, current.user.org_id)
    upd = body.model_dump(exclude={"api_key"})
    if body.api_key:
        from app.services.secrets import SecretStore
        upd["api_key_ciphertext"] = SecretStore().encrypt(body.api_key)
    emass.save_config(db, current.user.org_id, {**cfg, **upd})
    audit.record(db, action="emass.config.updated", actor_user_id=current.user.id, actor_email=current.user.email,
                 after={**body.model_dump(exclude={"api_key"}), "api_key": "set" if body.api_key else "unchanged"})
    db.commit()
    return emass.status(db, current.user.org_id)


@router.post("/emass/test")
def emass_test(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("emass.admin"))) -> dict:
    r = emass.test_connection(db, current.user.org_id, current.user.email)
    db.commit()
    return r


class FailSim(BaseModel):
    mode: str = Field(pattern="^(off|500|timeout|409)$")
    remaining: int = Field(0, ge=0, le=20)


@router.put("/emass/failure-sim")
def emass_failure_sim(body: FailSim, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("emass.admin"))) -> dict:
    from app.services.rmf import set_setting
    if emass.config(db, current.user.org_id)["mode"] != "mock":
        raise HTTPException(409, "Failure simulation exists only for the MOCK connector")
    v = set_setting(db, current.user.org_id, "emass_mock_failures", body.model_dump())
    audit.record(db, action="emass.failure_sim", actor_user_id=current.user.id, actor_email=current.user.email, after=v)
    db.commit()
    return v


def _change_out(db: Session, rows) -> list[dict]:
    return attach(db, [to_dict(c) for c in rows], "requested_by", "requester")


@router.get("/systems/{system_id}/emass")
def emass_system(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    enforce(request, current, "system.read", system_id)
    ch = list(db.scalars(select(EmassChange).where(EmassChange.system_id == system_id).order_by(EmassChange.created_at.desc()).limit(200)))
    runs = db.scalars(select(EmassSyncRun).where(EmassSyncRun.system_id == system_id).order_by(EmassSyncRun.created_at.desc()).limit(50))
    from app.models import Poam
    from app.services.metrics import emass_states, last_emass_sync, poam_summary

    poams = list(db.scalars(select(Poam).where(Poam.system_id == system_id).order_by(Poam.seq)))
    states = emass_states(db, poams)
    st = {**emass.status(db, current.user.org_id), "last_sync_at": last_emass_sync(db, current.user.org_id, system_id)}
    ps = poam_summary(db, [system_id])
    return {"status": st, "changes": _change_out(db, ch), "runs": [to_dict(r) for r in runs],
            "summary": {s: sum(1 for c in ch if c.status == s) for s in ("proposed", "pending_approval", "approved", "pending_retry", "conflict", "failed", "succeeded")},
            "poam_states": [{"id": str(p.id), "human_id": p.human_id, **states[p.id]} for p in poams],
            "pending_emass_sync": ps["pending_emass_sync"], "emass_by_state": ps["emass_by_state"], "pending_definition": ps["definitions"]["pending_emass_sync"]}


@router.post("/systems/{system_id}/emass/compare")
def emass_compare(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("emass.queue"))) -> dict:
    enforce(request, current, "emass.queue", system_id)
    r = emass.compare(db, get_system(db, system_id), current.user.email)
    db.commit()
    return r


@router.post("/systems/{system_id}/emass/import")
def emass_import(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("emass.queue"))) -> dict:
    enforce(request, current, "emass.queue", system_id)
    r = emass.import_metadata(db, get_system(db, system_id), current.user.email)
    db.commit()
    return r


class QueueIn(BaseModel):
    entity_type: str = Field(pattern="^(poam|control)$")
    entity_id: str


@router.post("/systems/{system_id}/emass/changes", status_code=201)
def emass_queue(system_id: uuid.UUID, body: QueueIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("emass.queue"))) -> dict:
    enforce(request, current, "emass.queue", system_id)
    s = get_system(db, system_id)
    if body.entity_type == "poam":
        p = db.get(Poam, uuid.UUID(body.entity_id))
        if p is None or p.system_id != s.id:
            raise HTTPException(404, "POA&M not found")
        label, after = f"{p.human_id} {p.weakness[:80]}", {k: str(v) if v is not None else None for k, v in emass._poam_view(p).items()}
    else:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == s.id, ControlAssignment.control_id == body.entity_id.lower()))
        if a is None:
            raise HTTPException(404, "Control not assigned")
        from app.models import Implementation
        impl = db.scalar(select(Implementation).where(Implementation.assignment_id == a.id, Implementation.is_current.is_(True)))
        label, after = f"{fmt_control(a.control_id)} implementation", {"control_id": a.control_id, "implementation_status": a.implementation_status,
                                                                 "narrative": (impl.narrative if impl else "")[:4000], "responsibility": a.responsibility}
    if db.scalar(select(EmassChange.id).where(EmassChange.system_id == s.id, EmassChange.entity_id == body.entity_id,
                                              EmassChange.status.in_(("proposed", "pending_approval", "approved", "pending_retry", "conflict")))):
        raise HTTPException(409, "An open outbound change already exists for this record")
    ch = emass.queue_change(db, system=s, entity_type=body.entity_type, entity_id=body.entity_id, label=label, after=after, before=None,
                            trigger="manual", requester=current.user)
    if body.entity_type == "poam":
        p.emass_status = "queued"
    db.commit()
    return to_dict(ch)


def _change(db: Session, change_id: uuid.UUID, request: Request, current: CurrentUser, perm="emass.queue") -> EmassChange:
    ch = db.get(EmassChange, change_id)
    if ch is None or ch.org_id != current.user.org_id:
        raise HTTPException(404, "Change not found")
    enforce(request, current, perm, ch.system_id)
    return ch


@router.post("/emass/changes/{change_id}/request-approval")
def emass_request_approval(change_id: uuid.UUID, body: Justify, request: Request, db: Session = Depends(get_db),
                           current: CurrentUser = Depends(require_object_permission("emass.queue", "EmassChange", "change_id"))) -> dict:
    ch = _change(db, change_id, request, current)
    req = emass.request_approval(db, ch, current.user, body.justification)
    db.commit()
    return {"change": to_dict(ch), "request_id": str(req.id), "human_id": req.human_id}


@router.post("/emass/changes/{change_id}/submit")
def emass_submit(change_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("emass.queue", "EmassChange", "change_id"))) -> dict:
    ch = _change(db, change_id, request, current)
    if ch.status == "failed":
        ch.status = "pending_retry"
    emass.submit(db, ch, current.user.email)
    db.commit()
    return to_dict(ch)


class ResolveIn(BaseModel):
    choice: str = Field(pattern="^(keep_local|accept_remote)$")
    rationale: str = Field(min_length=10, max_length=2000)


@router.post("/emass/changes/{change_id}/resolve")
def emass_resolve(change_id: uuid.UUID, body: ResolveIn, request: Request, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_object_permission("emass.queue", "EmassChange", "change_id"))) -> dict:
    ch = _change(db, change_id, request, current)
    emass.resolve_conflict(db, ch, body.choice, current.user, body.rationale)
    db.commit()
    return to_dict(ch)


# ---------- scheduler ----------
@router.get("/scheduled-jobs")
def scheduled_jobs(db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("admin.health.read"))) -> list[dict]:
    scheduler.ensure_defaults(db)
    db.commit()
    return [to_dict(j) for j in db.scalars(select(ScheduledJob).order_by(ScheduledJob.job_type))]


class ScheduleIn(BaseModel):
    interval_minutes: int = Field(ge=1, le=10080)
    enabled: bool


@router.put("/scheduled-jobs/{job_id}")
def update_schedule(job_id: uuid.UUID, body: ScheduleIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("risk.admin"))) -> dict:
    j = db.get(ScheduledJob, job_id)
    if j is None:
        raise HTTPException(404, "Schedule not found")
    before = {"interval_minutes": j.interval_minutes, "enabled": j.enabled}
    j.interval_minutes, j.enabled = body.interval_minutes, body.enabled
    audit.record(db, action="schedule.updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="scheduled_job",
                 entity_id=j.job_type, before=before, after=body.model_dump())
    db.commit()
    return to_dict(j)


@router.post("/scheduled-jobs/{job_id}/run")
def run_schedule(job_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("risk.admin"))) -> dict:
    j = db.get(ScheduledJob, job_id)
    if j is None:
        raise HTTPException(404, "Schedule not found")
    job = scheduler.run_now(db, j, current.user.id)
    if job is None:
        raise HTTPException(409, "A job of this type is already queued or running")
    db.commit()
    return {"job_id": str(job.id)}


# ---------- impact review acknowledgements ----------
class AckIn(BaseModel):
    rationale: str = Field(min_length=10, max_length=2000)
    apply_new_cat: bool = False


@router.post("/poams/{poam_id}/content-impact/ack")
def poam_impact_ack(poam_id: uuid.UUID, body: AckIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("poam.manage", "Poam", "poam_id"))) -> dict:
    p = db.get(Poam, poam_id)
    if p is None or not p.content_impact:
        raise HTTPException(404, "No content impact pending")
    enforce(request, current, "poam.manage", p.system_id)
    old = p.cat
    if body.apply_new_cat and p.content_impact.get("new_cat"):
        p.cat = p.content_impact["new_cat"]
        p.severity = {"CAT I": "high", "CAT II": "medium", "CAT III": "low"}.get(p.cat, p.severity)
    p.content_impact = {**p.content_impact, "status": "reviewed", "reviewed_by": current.user.email, "rationale": body.rationale}
    wf.history(db, p, current.user, "content_impact_reviewed", old_cat=old, new_cat=p.cat, rationale=body.rationale)
    evaluate_system(db, p.system_id)
    db.commit()
    return {"cat": p.cat, "content_impact": p.content_impact}


@router.post("/systems/{system_id}/controls/{control_id}/content-change/ack")
def control_change_ack(system_id: uuid.UUID, control_id: str, body: Justify, request: Request, db: Session = Depends(get_db),
                       current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    enforce(request, current, "system.write", system_id)
    a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == system_id, ControlAssignment.control_id == control_id.lower()))
    if a is None or not a.content_change:
        raise HTTPException(404, "No content change pending")
    a.content_change = {**a.content_change, "acknowledged": True, "by": current.user.email, "justification": body.justification}
    audit.record(db, action="control.content_change.acknowledged", actor_user_id=current.user.id, actor_email=current.user.email,
                 entity_type="control_assignment", entity_id=str(a.id), details=a.content_change)
    evaluate_system(db, system_id)
    db.commit()
    return a.content_change
