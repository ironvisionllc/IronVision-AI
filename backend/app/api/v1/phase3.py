import csv
import io
import json
import uuid
from app.services.queue import fmt_control
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import String, func, literal, or_, select, true
from sqlalchemy.orm import Session

from app.api.v1.records import get_system, to_dict, visible_systems
from app.db import get_db
from app.models import (ApprovalRequest, Assessment, Attestation, AuditEvent, AuthorizationDecision, CommonControlProvider, ControlAssignment,
                        DecisionRule, NotificationPref, ObservedConfigValue, OdpValue, Policy, PolicyFinding, RoleAssignment, System, User)
from app.security.deps import CurrentUser, enforce, get_current_user, require_object_permission, require_permission, self_scoped
from app.services import audit, jobs as jobsvc
from app.services import rmf
from app.services import workflow as wf
from app.services.evaluation import evaluate_system, take_snapshots
from app.services.people import attach, user_labels

router = APIRouter(tags=["phase3"])


def _is_admin(current) -> bool:
    return any(a.role == "platform_admin" for a in current.assignments)


# ---------- inheritance ----------
@router.get("/systems/{system_id}/inheritance")
def inheritance(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    ac = list(db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system_id)))
    today = date.today()
    atts = list(db.scalars(select(Attestation).where(Attestation.system_id == system_id, Attestation.status != "superseded")))
    att_ctl = {a.control_id for a in atts}
    by = {k: sum(1 for a in ac if a.responsibility == k) for k in ("inherited", "shared", "system")}
    provs = {}
    for a in ac:
        if a.provider_id:
            p = provs.setdefault(a.provider_id, {"inherited": 0, "shared": 0})
            p[a.responsibility] = p.get(a.responsibility, 0) + 1
    org = get_system(db, system_id).org_id
    providers = [{**to_dict(p), "fully_inherited": provs.get(p.id, {}).get("inherited", 0), "shared": provs.get(p.id, {}).get("shared", 0)}
                 for p in db.scalars(select(CommonControlProvider).where(CommonControlProvider.org_id == org))]
    from app.services.responsibility import SYNTHETIC_LABEL, split_missing

    shared = []
    for a in sorted((x for x in ac if x.responsibility in ("shared", "inherited")), key=lambda x: (x.responsibility != "shared", x.control_id)):
        shared.append({"control_id": a.control_id, "provider_id": str(a.provider_id) if a.provider_id else None, "responsibility": a.responsibility,
                       "split_missing": split_missing(a), "matrix_label": SYNTHETIC_LABEL,
                       "provider_responsibility": a.provider_responsibility_text, "system_responsibility": a.system_responsibility_text,
                       "system_part": {"monitoring_status": a.monitoring_status, "evidence_freshness_status": a.evidence_freshness_status,
                                       "open_findings": (a.evaluation or {}).get("open_findings", 0)},
                       "note": "Provider status never satisfies the system portion; system part computed from this system's own findings/evidence."})
    att_rows = attach(db, [{**to_dict(a), "display_status": "overdue" if a.status in ("pending", "expired") and a.due_date and a.due_date < today else a.status}
                           for a in sorted(atts, key=lambda x: (x.control_id, -x.version))], "owner_id", "owner")
    return {"cards": {"assigned": len(ac), "fully_inherited": by["inherited"], "shared": by["shared"], "system_owned": by["system"],
                      "sum_check": by["inherited"] + by["shared"] + by["system"] == len(ac),
                      "manual_attestation": len(att_ctl),
                      "attestation_overdue": sum(1 for a in att_rows if a["display_status"] == "overdue"),
                      "attestation_due_30d": sum(1 for a in atts if a.status == "pending" and a.due_date and today <= a.due_date <= today + timedelta(days=30)),
                      "note": "Inherited/shared/system-owned are mutually exclusive and sum to assigned. Manual attestation OVERLAPS them."},
            "providers": providers, "shared": shared, "attestations": att_rows}


@router.post("/providers/{provider_id}/responsibility-matrix")
async def import_crm(provider_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                     current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    """Import a customer responsibility matrix (CRM) CSV for a provider package; fills missing system assignment text."""
    from app.models import System
    from app.services.responsibility import apply_to_system, import_csv

    p = db.get(CommonControlProvider, provider_id)
    if p is None or p.org_id != current.user.org_id:
        raise HTTPException(404, "Provider not found")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "CRM CSV too large (max 5 MB)")
    try:
        r = import_csv(db, p.id, data, f"CRM import: {file.filename}")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    for sid in db.scalars(select(System.id).where(System.org_id == p.org_id)):
        apply_to_system(db, sid)
    audit.record(db, action="provider.crm_imported", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="provider",
                 entity_id=str(p.id), details={**r, "file": file.filename})
    db.commit()
    return r


class ProviderIn(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    package: str | None = None
    basis: str | None = None
    coverage_text: str | None = None
    last_validated_at: date | None = None
    package_expiration: date | None = None


@router.post("/providers", status_code=201)
def create_provider(body: ProviderIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    p = CommonControlProvider(org_id=current.user.org_id, source="user", **body.model_dump())
    db.add(p)
    db.flush()
    audit.record(db, action="provider.created", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="provider", entity_id=str(p.id),
                 after=body.model_dump(mode="json"))
    db.commit()
    return to_dict(p)


@router.patch("/providers/{provider_id}")
def update_provider(provider_id: uuid.UUID, body: ProviderIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    p = db.get(CommonControlProvider, provider_id)
    if p is None or p.org_id != current.user.org_id:
        raise HTTPException(404, "Provider not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    audit.record(db, action="provider.updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="provider", entity_id=str(p.id),
                 after=body.model_dump(mode="json", exclude_unset=True))
    db.commit()
    return to_dict(p)


class InheritIn(BaseModel):
    control_id: str
    responsibility: str = Field(pattern="^(inherited|shared|system)$")
    provider_id: uuid.UUID | None = None
    provider_responsibility_text: str | None = None
    system_responsibility_text: str | None = None


@router.put("/systems/{system_id}/inheritance")
def set_inheritance(system_id: uuid.UUID, body: InheritIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == system_id, ControlAssignment.control_id == body.control_id.lower()))
    if a is None:
        raise HTTPException(404, "Control not assigned to this system")
    if body.responsibility != "system" and not body.provider_id:
        raise HTTPException(422, "Inherited/shared controls require a provider")
    before = {"responsibility": a.responsibility, "provider_id": str(a.provider_id) if a.provider_id else None}
    a.responsibility, a.provider_id = body.responsibility, body.provider_id if body.responsibility != "system" else None
    a.provider_responsibility_text, a.system_responsibility_text = body.provider_responsibility_text, body.system_responsibility_text
    if body.responsibility == "inherited":
        a.implementation_status = "inherited"
    audit.record(db, action="inheritance.updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="control_assignment",
                 entity_id=str(a.id), before=before, after=body.model_dump(mode="json"))
    evaluate_system(db, system_id)
    db.commit()
    return to_dict(a)


# ---------- attestations ----------
def _att(db, request, current, att_id, perm="system.read") -> Attestation:
    a = db.get(Attestation, att_id)
    if a is None:
        raise HTTPException(404, "Attestation not found")
    enforce(request, current, perm, a.system_id)
    return a


@router.post("/attestations/{att_id}/evidence")
async def attestation_evidence(att_id: uuid.UUID, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                               current: CurrentUser = Depends(require_object_permission("evidence.submit", "Attestation", "att_id"))) -> dict:
    a = _att(db, request, current, att_id, "evidence.submit")
    data = await file.read()
    _vet(file.filename or "upload", data, "evidence")
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(422, "Evidence file must be 1 byte – 20 MB")
    ev = rmf.store_evidence(db, a.system_id, file.filename or "attestation-evidence", data, "attestation", current.user.email, "manual_attestation")
    a.evidence_id = ev.id
    db.commit()
    return {"evidence_id": str(ev.id), "sha256": ev.sha256}


@router.post("/attestations/{att_id}/attest")
def attest(att_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("evidence.submit", "Attestation", "att_id"))) -> dict:
    a = rmf.sign_attestation(db, _att(db, request, current, att_id), current.user)
    evaluate_system(db, a.system_id)
    take_snapshots(db, trigger="attestation.signed")
    db.commit()
    return to_dict(a)


@router.post("/attestations/{att_id}/renew", status_code=201)
def renew(att_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("evidence.submit", "Attestation", "att_id"))) -> dict:
    new = rmf.renew_attestation(db, _att(db, request, current, att_id, "evidence.submit"), current.user)
    db.commit()
    return to_dict(new)


@router.post("/attestations/{att_id}/remind")
def remind(att_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("poam.manage", "Attestation", "att_id"))) -> dict:
    a = _att(db, request, current, att_id, "poam.manage")
    sent = rmf.send(db, a.owner_id, "attestation_overdue", f"Reminder: attest {fmt_control(a.control_id)} (due {a.due_date})", "/inheritance",
                    f"Sent by {current.user.display_name}")
    audit.record(db, action="attestation.reminder_sent", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="attestation", entity_id=str(a.id))
    db.commit()
    return {"sent": sent}


@router.get("/attestations/{att_id}/history")
def att_history(att_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list[dict]:
    a = _att(db, request, current, att_id)
    rows = db.scalars(select(Attestation).where(Attestation.assignment_id == a.assignment_id).order_by(Attestation.version.desc()))
    return attach(db, [to_dict(x) for x in rows], "signed_by", "signer")


class BackdateIn(BaseModel):
    days_ago: int = Field(ge=1, le=3650)


@router.post("/demo/attestations/{att_id}/expire")
def demo_expire(att_id: uuid.UUID, body: BackdateIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("demo.tools"))) -> dict:
    a = db.get(Attestation, att_id)
    if a is None or a.status != "signed":
        raise HTTPException(409, "Only signed attestations can be back-dated")
    a.expires_at = date.today() - timedelta(days=body.days_ago)
    audit.record(db, action="demo.attestation_backdated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="attestation",
                 entity_id=str(a.id), details={"expires_at": str(a.expires_at), "demo_tool": True})
    res = rmf.expire_attestations(db)
    db.commit()
    return {"cascade": res, "attestation": to_dict(a)}


# ---------- SCA assessments & authorization ----------
class AssessmentIn(BaseModel):
    objectives: list[str] = Field(min_length=1)
    methods: list[str] = Field(min_length=1)
    findings_text: str | None = Field(None, max_length=5000)
    result: str = Field(pattern="^(satisfied|other_than_satisfied)$")
    evidence_ids: list[str] = []


@router.post("/systems/{system_id}/controls/{control_id}/assessments", status_code=201)
def assess(system_id: uuid.UUID, control_id: str, body: AssessmentIn, db: Session = Depends(get_db),
           current: CurrentUser = Depends(require_permission("assessment.perform"))) -> dict:
    if bad := [m for m in body.methods if m not in ("examine", "interview", "test")]:
        raise HTTPException(422, f"Unknown methods: {bad}")
    s = get_system(db, system_id)
    a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == system_id, ControlAssignment.control_id == control_id.lower()))
    if a is None:
        raise HTTPException(404, "Control not assigned")
    data = body.model_dump()
    data["evidence_ids"] = wf.evidence_in_system(db, system_id, body.evidence_ids)
    res = rmf.record_assessment(db, system=s, a=a, actor=current.user, assignments=current.assignments, body=data)
    take_snapshots(db, trigger="assessment.recorded")
    db.commit()
    return to_dict(res)


@router.get("/systems/{system_id}/controls/{control_id}/assessments")
def list_assessments(system_id: uuid.UUID, control_id: str, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    rows = db.scalars(select(Assessment).where(Assessment.system_id == system_id, Assessment.control_id == control_id.lower()).order_by(Assessment.created_at.desc()))
    return attach(db, [to_dict(r) for r in rows], "assessor_id", "assessor")


@router.get("/systems/{system_id}/authorization")
def authorization_view(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    reqs = db.scalars(select(ApprovalRequest).where(ApprovalRequest.system_id == system_id, ApprovalRequest.request_type == "authorization_package_review")
                      .order_by(ApprovalRequest.created_at.desc()))
    decs = db.scalars(select(AuthorizationDecision).where(AuthorizationDecision.system_id == system_id).order_by(AuthorizationDecision.created_at.desc()))
    return {"package": rmf.package(db, s), "requests": [to_dict(r) for r in reqs],
            "decisions": attach(db, [to_dict(d, ("package_snapshot",)) for d in decs], "decider_id", "decider")}


class PackageIn(BaseModel):
    justification: str = Field(min_length=10, max_length=5000)


@router.post("/systems/{system_id}/authorization/submit", status_code=201)
def submit_package(system_id: uuid.UUID, body: PackageIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    s = get_system(db, system_id)
    if db.scalar(select(ApprovalRequest.id).where(ApprovalRequest.system_id == system_id, ApprovalRequest.request_type == "authorization_package_review",
                                                  ApprovalRequest.status == "pending")):
        raise HTTPException(409, "A package review is already pending")
    req = wf.create_request(db, system=s, requester=current.user, request_type="authorization_package_review", justification=body.justification,
                            payload={"package_summary": json.loads(json.dumps(rmf.package(db, s)["ssp"], default=str))})
    db.commit()
    return to_dict(req)


class AuthDecisionIn(BaseModel):
    request_id: uuid.UUID
    decision: str = Field(pattern="^(ATO|ATO_with_conditions|IATT|DATO)$")
    conditions: str | None = Field(None, max_length=5000)
    expiration: date | None = None
    rationale: str = Field(min_length=10, max_length=5000)


@router.post("/systems/{system_id}/authorization-decision")
def authorization_decision(system_id: uuid.UUID, body: AuthDecisionIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("authorization.decide"))) -> dict:
    s = get_system(db, system_id)
    rule = wf.rule_for(db, s.org_id, "authorization_decision")
    role = rule.steps[0]["role"]
    if not any(a.role == role and a.scope_id in (s.id, s.org_id) for a in current.assignments):
        audit.record_now(action="authz.denied", outcome="denied", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                         entity_id=str(s.id), details={"reason": f"decision_rule_requires_{role}", "attempted": "authorization_decision", "rule_version": rule.version})
        raise HTTPException(403, f"Decision rule v{rule.version}: only {role.upper()} may record authorization decisions")
    if body.decision in ("ATO", "ATO_with_conditions", "IATT") and (not body.expiration or body.expiration <= date.today()):
        raise HTTPException(422, "ATO / IATT require a future expiration date")
    if body.decision == "ATO_with_conditions" and not body.conditions:
        raise HTTPException(422, "Conditions are required for ATO with conditions")
    req = db.get(ApprovalRequest, body.request_id)
    if req is None or req.system_id != s.id or req.request_type != "authorization_package_review":
        raise HTTPException(404, "Package review request not found")
    req.payload = {**(req.payload or {}), "decision": body.model_dump(mode="json", exclude={"request_id"})}
    db.flush()
    wf.decide(db, req.id, current.user, current.assignments, "approve", body.rationale)
    audit.record(db, action="authorization.decision_recorded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(s.id), after={"decision": body.decision, "expiration": str(body.expiration), "status": s.authorization_status})
    db.commit()
    return {"authorization_status": s.authorization_status, "authorization_expiration": s.authorization_expiration}


# ---------- decision rules admin ----------
class RuleIn(BaseModel):
    steps: list[dict] = Field(min_length=1)
    label: str = Field(min_length=5, max_length=255)


@router.put("/decision-rules/{request_type}")
def edit_rule(request_type: str, body: RuleIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.users.manage"))) -> dict:
    from app.security.rbac import ROLE_PERMISSIONS

    for st in body.steps:
        if st.get("role") not in ROLE_PERMISSIONS or st.get("action") not in ("decide", "endorse"):
            raise HTTPException(422, "Each step needs a known role and action decide|endorse")
    if body.steps[-1]["action"] != "decide":
        raise HTTPException(422, "Final step must be 'decide'")
    old = wf.rule_for(db, current.user.org_id, request_type)
    old.is_active = False
    new = DecisionRule(org_id=old.org_id, request_type=request_type, version=old.version + 1, steps=body.steps, label=body.label,
                       description=f"Edited by {current.user.email}")
    db.add(new)
    db.flush()
    errs = wf.validate_rules(list(db.scalars(select(DecisionRule).where(DecisionRule.org_id == old.org_id))))
    if errs:
        db.rollback()
        raise HTTPException(422, "; ".join(errs))
    audit.record(db, action="decision_rule.updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="decision_rule",
                 entity_id=str(new.id), before={"version": old.version, "steps": old.steps}, after={"version": new.version, "steps": new.steps})
    db.commit()
    return to_dict(new)


# ---------- policy auditor ----------
def _policy_out(db, p: Policy) -> dict:
    q = select(func.count()).select_from(PolicyFinding).where(PolicyFinding.policy_id == p.id)
    from app.services.rmf import policy_review_status

    return {**to_dict(p, ("text_content",)), "review_status": policy_review_status(p), "proposed": db.scalar(q.where(PolicyFinding.status == "proposed")),
            "confirmed": db.scalar(q.where(PolicyFinding.status == "confirmed")), "dismissed": db.scalar(q.where(PolicyFinding.status == "dismissed"))}


@router.get("/policies")
def list_policies(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    pols = list(db.scalars(select(Policy).where(Policy.org_id == current.user.org_id).order_by(Policy.title, Policy.version.desc())))
    cur = [p for p in pols if p.status == "current"]
    sys_ids = [s.id for s in visible_systems(db, current)]
    disagreements = db.scalar(select(func.count()).select_from(PolicyFinding).where(PolicyFinding.system_id.in_(sys_ids), PolicyFinding.status != "dismissed",
                                                                                   PolicyFinding.finding_type.in_(("policy_vs_config_difference", "odp_not_met"))))
    missing = db.scalar(select(func.count()).select_from(PolicyFinding).where(PolicyFinding.system_id.in_(sys_ids), PolicyFinding.status != "dismissed",
                                                                             PolicyFinding.finding_type == "missing_policy_requirement"))
    return {"cards": {"total": len(cur), "audited": sum(1 for p in cur if p.analysis_status == "analyzed"), "requirements_without_coverage": missing,
                      "disagreements": disagreements, "overdue_reviews": sum(1 for p in cur if rmf.policy_review_status(p) == "review_overdue")},
            "policies": [_policy_out(db, p) for p in pols]}


@router.post("/policies", status_code=201)
async def upload_policy(request: Request, file: UploadFile = File(...), title: str = Form(...), owner: str = Form(""), system_ids: str = Form(""),
                        policy_key: str = Form(""), review_due: str = Form(""), db: Session = Depends(get_db),
                        current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    data = await file.read()
    _vet(file.filename or "policy", data, "policy")
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(422, "File must be 1 byte – 20 MB")
    text = rmf.extract_text(file.filename or "", data)
    sids = [x for x in system_ids.split(",") if x] or [str(s.id) for s in visible_systems(db, current)][:1]
    for sid in sids:
        enforce(request, current, "implementation.write", uuid.UUID(sid))
    key = policy_key or title.lower().replace(" ", "-")[:100]
    prev = db.scalar(select(Policy).where(Policy.org_id == current.user.org_id, Policy.policy_key == key, Policy.status == "current"))
    evs = [rmf.store_evidence(db, uuid.UUID(sid), file.filename, data, "policy", current.user.email, "policy_library") for sid in sids]
    p = Policy(org_id=current.user.org_id, policy_key=key, title=title, version=(prev.version + 1) if prev else 1, owner=owner or None,
               system_ids=sids, file_name=file.filename, storage_key=evs[0].storage_key, sha256=evs[0].sha256, evidence_ids=[str(e.id) for e in evs],
               text_content=text, analysis_status="queued", review_due=date.fromisoformat(review_due) if review_due else None,
               supersedes_id=prev.id if prev else None, approval_date=date.today())
    if prev:
        prev.status = "superseded"
    db.add(p)
    db.flush()
    job = jobsvc.enqueue(db, "policy.analyze", {"policy_id": str(p.id)})
    audit.record(db, action="policy.uploaded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="policy", entity_id=str(p.id),
                 details={"sha256": p.sha256, "version": p.version, "job_id": str(job.id)})
    db.commit()
    return {**_policy_out(db, p), "job_id": str(job.id)}


@router.get("/policies/{policy_id}")
def policy_detail(policy_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    p = db.get(Policy, policy_id)
    if p is None or p.org_id != current.user.org_id:
        raise HTTPException(404, "Policy not found")
    sys_ids = [s.id for s in visible_systems(db, current)]
    fs = attach(db, [to_dict(f) for f in db.scalars(select(PolicyFinding).where(PolicyFinding.policy_id == p.id, PolicyFinding.system_id.in_(sys_ids)))],
                "reviewer_id", "reviewer")
    values = []
    for v in (p.analysis or {}).get("values", []):
        for sid in p.system_ids or []:
            obs = db.scalar(select(ObservedConfigValue).where(ObservedConfigValue.system_id == uuid.UUID(sid), ObservedConfigValue.control_id == v["control_id"],
                                                              ObservedConfigValue.parameter == v["parameter"]).order_by(ObservedConfigValue.observed_at.desc()))
            odp = db.scalar(select(OdpValue).where(OdpValue.system_id == uuid.UUID(sid), OdpValue.control_id == v["control_id"], OdpValue.parameter == v["parameter"]))
            values.append({"system_id": sid, "control_id": v["control_id"], "parameter": v["parameter"], "policy_value": v["value"],
                           "odp_value": odp.value if odp else None, "observed_value": obs.value if obs else None,
                           "observed_age_days": (datetime.now(obs.observed_at.tzinfo) - obs.observed_at).days if obs else None,
                           "observed_source": obs.source if obs else None,
                           "result": None if not obs else ("Match" if obs.numeric_value == v["numeric_value"] else "Mismatch"),
                           "quote": v.get("quote"), "quote_location": v.get("location"), "quote_status": v.get("quote_status", "unvalidated"),
                           "quote_offsets": [v.get("start"), v.get("end")]})
    versions = [to_dict(x, ("text_content",)) for x in db.scalars(select(Policy).where(Policy.org_id == p.org_id, Policy.policy_key == p.policy_key)
                                                                   .order_by(Policy.version.desc()))]
    return {"policy": _policy_out(db, p), "findings": fs, "values": values, "versions": versions, "text_preview": (p.text_content or "")[:4000]}


class PFDecision(BaseModel):
    justification: str = Field(default="", max_length=5000)
    control_id: str | None = None


@router.post("/policy-findings/{pf_id}/{action}")
def policy_finding_action(pf_id: uuid.UUID, action: str, body: PFDecision, request: Request, db: Session = Depends(get_db),
                          current: CurrentUser = Depends(require_object_permission("finding.map", "PolicyFinding", "pf_id"))) -> dict:
    pf = db.get(PolicyFinding, pf_id)
    if pf is None:
        raise HTTPException(404, "Policy finding not found")
    enforce(request, current, "finding.map", pf.system_id)
    if action == "confirm":
        f = rmf.confirm_policy_finding(db, pf, current.user)
        db.commit()
        return {"status": pf.status, "finding_id": str(f.id)}
    if action == "dismiss":
        if len(body.justification.strip()) < 10:
            raise HTTPException(422, "Dismissal requires a justification (min 10 chars)")
        pf.status, pf.reviewer_id, pf.justification, pf.decided_at = "dismissed", current.user.id, body.justification, datetime.now().astimezone()
    elif action == "link":
        if not body.control_id:
            raise HTTPException(422, "control_id required")
        pf.control_id = body.control_id.lower()
    elif action == "request-review":
        pf.status = "in_review"
        for uid in rmf.role_users(db, current.user.org_id, pf.system_id, "issm"):
            rmf.send(db, uid, "pending_review", f"Policy finding needs review: {pf.description[:80]}", f"/policy-auditor/{pf.policy_id}")
    else:
        raise HTTPException(404, "Unknown action")
    audit.record(db, action=f"policy_finding.{action}", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="policy_finding",
                 entity_id=str(pf.id), after={"status": pf.status, "justification": pf.justification, "control_id": pf.control_id})
    db.commit()
    return to_dict(pf)


@router.get("/policies/{policy_id}/parameters.csv")
def export_params(policy_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> Response:
    d = policy_detail(policy_id, db, current)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# Parameter comparison export (CSV). OSCAL export arrives in Phase 4."])
    w.writerow(["system_id", "control_id", "parameter", "policy_value", "odp_value", "observed_value", "observed_age_days", "result"])
    for v in d["values"]:
        w.writerow([v[k] for k in ("system_id", "control_id", "parameter", "policy_value", "odp_value", "observed_value", "observed_age_days", "result")])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="policy-{policy_id}-parameters.csv"'})


# ---------- workflow, search, notifications prefs ----------
@router.get("/systems/{system_id}/rmf-workflow")
def rmf_workflow(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    return rmf.workflow_stages(db, get_system(db, system_id))


@router.get("/search")
def global_search(q: str, system_id: uuid.UUID | None = None, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(get_current_user)) -> list[dict]:
    if len(q.strip()) < 2:
        return []
    return rmf.search(db, q.strip(), list(visible_systems(db, current)), current.user.org_id, system_id)


@router.get("/notification-prefs")
def get_prefs(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    return {"kinds": [{"kind": k, "label": v, "enabled": rmf.pref_enabled(db, current.user.id, k)} for k, v in rmf.NOTIFICATION_KINDS.items()],
            "email": {"enabled": rmf.EmailAdapter.enabled, "note": "Email adapter not configured – in-app delivery only"}}


class PrefIn(BaseModel):
    kind: str
    enabled: bool


@router.put("/notification-prefs")
def set_pref(body: PrefIn, db: Session = Depends(get_db), current: CurrentUser = Depends(self_scoped)) -> dict:
    if body.kind not in rmf.NOTIFICATION_KINDS:
        raise HTTPException(422, "Unknown notification kind")
    p = db.scalar(select(NotificationPref).where(NotificationPref.user_id == current.user.id, NotificationPref.kind == body.kind))
    if p is None:
        db.add(NotificationPref(user_id=current.user.id, kind=body.kind, enabled=body.enabled))
    else:
        p.enabled = body.enabled
    db.commit()
    return {"ok": True}


# ---------- audit log ----------
def _audit_q(db, actor, action, entity_type, outcome, date_from, date_to):
    q = select(AuditEvent)
    if actor:
        q = q.where(AuditEvent.actor_email.ilike(f"%{actor}%"))
    if action:
        q = q.where(AuditEvent.action.ilike(f"{action}%"))
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if outcome:
        q = q.where(AuditEvent.outcome == outcome)
    if date_from:
        q = q.where(AuditEvent.occurred_at >= date_from)
    if date_to:
        q = q.where(AuditEvent.occurred_at < date_to + timedelta(days=1))
    return q


@router.get("/audit-log")
def audit_log(actor: str | None = None, action: str | None = None, entity_type: str | None = None, outcome: str | None = None,
              date_from: date | None = None, date_to: date | None = None, page: int = 1, page_size: int = 50, fmt: str | None = None,
              include_system: bool = False,
              db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("audit.read"))):
    from app.models import Organization
    org = db.get(Organization, current.user.org_id)
    tenant_users = select(User.id).where(User.org_id == org.id)
    tenant_entities = select(System.id.cast(String)).where(System.org_id == org.id).union(select(literal(str(org.id))))
    mine = AuditEvent.actor_user_id.in_(tenant_users)
    sys_ev = AuditEvent.actor_user_id.is_(None) & (AuditEvent.entity_id.in_(tenant_entities) if org.is_sandbox else true())
    q = _audit_q(db, actor, action, entity_type, outcome, date_from, date_to).where(mine | sys_ev)  # tenant-scoped
    if fmt in ("csv", "json"):
        rows = [to_dict(e) for e in db.scalars(q.order_by(AuditEvent.seq.desc()).limit(10000))]
        if fmt == "json":
            return Response(json.dumps(rows, default=str), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="audit.json"'})
        buf = io.StringIO()
        cols = ["seq", "occurred_at", "actor_email", "action", "outcome", "entity_type", "entity_id", "ip", "hash"]
        w = csv.writer(buf)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c) for c in cols])
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="audit.csv"'})
    if not include_system:
        q = q.where(AuditEvent.actor_user_id.is_not(None))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    page_size = max(1, min(page_size, 200))
    items = [to_dict(e) for e in db.scalars(q.order_by(AuditEvent.seq.desc()).offset((max(page, 1) - 1) * page_size).limit(page_size))]
    attach(db, items, "actor_user_id", "actor")
    from sqlalchemy import text as sqltext
    _ = sqltext
    cq = q.subquery()
    cat = func.split_part(cq.c.action, ".", 1)
    cats = dict(db.execute(select(cat, func.count()).group_by(cat)).all())
    return {"items": items, "total": total, "page": page, "page_size": page_size, "categories": cats, "chain": audit.verify_chain(db)}


# ---------- admin ----------
class InviteIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.demo$")
    display_name: str = Field(min_length=2, max_length=255)
    role: str
    system_id: uuid.UUID | None = None


@router.post("/admin/users", status_code=201)
def invite(body: InviteIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.users.manage"))) -> dict:
    import secrets

    from app.models import AuthIdentity
    from app.security.passwords import hash_password
    from app.security.rbac import ROLE_PERMISSIONS

    if body.role not in ROLE_PERMISSIONS:
        raise HTTPException(422, "Unknown role")
    if db.scalar(select(User.id).where(User.email == body.email.lower())):
        raise HTTPException(409, "User exists")
    temp = secrets.token_urlsafe(12)
    u = User(org_id=current.user.org_id, email=body.email.lower(), display_name=body.display_name, is_active=True)
    db.add(u)
    db.flush()
    db.add(AuthIdentity(user_id=u.id, provider="dev_password", subject=u.email, secret_hash=hash_password(temp)))
    db.add(RoleAssignment(user_id=u.id, role=body.role, scope_type="system" if body.system_id else "org",
                          scope_id=body.system_id or current.user.org_id, granted_by=current.user.id))
    audit.record(db, action="admin.user_invited", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="user", entity_id=str(u.id),
                 after={"email": u.email, "role": body.role, "scope": str(body.system_id or "org")})
    db.commit()
    return {"id": str(u.id), "email": u.email, "temporary_password": temp, "note": "DEV ONLY: temporary password shown once (development auth, not CAC/PIV)"}


@router.get("/admin/users")
def users(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.users.manage"))) -> list[dict]:
    us = list(db.scalars(select(User).where(User.org_id == current.user.org_id).order_by(User.email)))
    labels = user_labels(db, [u.id for u in us])
    out = []
    for u in us:
        ras = [to_dict(r) for r in db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == u.id))]
        perms = {p for r in ras for p in __import__("app.security.rbac", fromlist=["ROLE_PERMISSIONS"]).ROLE_PERMISSIONS.get(r["role"], set())}
        priv = sorted(perms & {"admin.users.manage", "authorization.decide", "risk.accept", "demo.tools", "system.roles.manage", "assessment.perform"})
        out.append({"id": str(u.id), "email": u.email, "display_name": u.display_name, "is_active": u.is_active, "roles": ras,
                    "privileged_permissions": priv, "last_login_at": getattr(u, "last_login_at", None), "_": labels.get(str(u.id))})
    return out


@router.get("/admin/users/{user_id}/access-history")
def access_history(user_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("admin.users.manage"))) -> list[dict]:
    q = select(AuditEvent).where(or_(AuditEvent.actor_user_id == user_id, AuditEvent.entity_id == str(user_id))).order_by(AuditEvent.seq.desc()).limit(100)
    return [to_dict(e) for e in db.scalars(q)]


@router.get("/admin/security")
def security(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.health.read"))) -> dict:
    from app.config import get_settings

    st = get_settings()
    return {"sign_in": "Development password auth (simulated) – CAC/PIV not configured",
            "cryptography": "Not FIPS-validated (module validation required in target deployment)",
            "session_timeout_minutes": st.jwt_ttl_minutes, "session_timeout_note": "Enforced via JWT expiry (JWT_TTL_MINUTES)",
            "markings_banner": rmf.get_setting(db, current.user.org_id, "banner", {"text": "SYNTHETIC DATA – NOT FOR OPERATIONAL USE"})["text"],
            "tenant_separation": "Single demo tenant; every query is scoped by org_id + system role assignments (row-level enforcement in API layer)",
            "secrets": "Connector credentials encrypted with SECRET_STORE_KEY (Fernet), never returned to browser; app secrets from environment only"}


class BannerIn(BaseModel):
    text: str = Field(min_length=3, max_length=200)


@router.put("/admin/banner")
def set_banner(body: BannerIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.users.manage"))) -> dict:
    rmf.set_setting(db, current.user.org_id, "banner", {"text": body.text})
    audit.record(db, action="admin.banner_updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="setting", entity_id="banner",
                 after={"text": body.text})
    db.commit()
    return {"text": body.text}


@router.get("/banner")
def banner(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    return rmf.get_setting(db, current.user.org_id, "banner", {"text": "SYNTHETIC DATA – NOT FOR OPERATIONAL USE"})


@router.get("/admin/ai-settings")
def ai_settings(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.health.read"))) -> dict:
    from app.services.ai.service import get_ai_service

    svc = get_ai_service()
    s = rmf.get_setting(db, current.user.org_id, "ai", rmf.AI_DEFAULTS)
    return {**s, "effective": svc.describe(), "provider": svc.provider.name if svc.configured else "none", "model": svc.provider.model if svc.configured else None,
            "endpoint": "configured via environment (AI_PROVIDER / base URL)", "human_approval_required": True,
            "human_approval_locked": True, "provider_note": "Provider/model/endpoint are environment-configured; change .env and restart"}


class AISettingsIn(BaseModel):
    use_cases: dict[str, bool]
    logging_policy: str | None = None
    retrieval_restrictions: str | None = None


@router.put("/admin/ai-settings")
def set_ai_settings(body: AISettingsIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.users.manage"))) -> dict:
    cur = rmf.get_setting(db, current.user.org_id, "ai", rmf.AI_DEFAULTS)
    new = {**cur, "use_cases": {**cur["use_cases"], **body.use_cases}, "human_approval_required": True}
    for k in ("logging_policy", "retrieval_restrictions"):
        if getattr(body, k):
            new[k] = getattr(body, k)
    rmf.set_setting(db, current.user.org_id, "ai", new)
    audit.record(db, action="admin.ai_settings_updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="setting", entity_id="ai",
                 before=cur, after=new)
    db.commit()
    return new


_ = (System,)


def _vet(name: str, data: bytes, kind: str) -> None:
    from app.services.upload_security import UploadRejected, validate_upload
    try:
        validate_upload(name, data, kind)
    except UploadRejected as exc:
        raise HTTPException(415 if "type" in str(exc) or "match" in str(exc) else 413 if "limit" in str(exc) else 422, str(exc))
