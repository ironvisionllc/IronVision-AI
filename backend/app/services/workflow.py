"""POA&M + review (approval) engine. Decision authority comes ONLY from the versioned decision_rules table."""
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import (ApprovalDecision, ApprovalRequest, ControlAssignment, DecisionRule, Evidence, Finding, FindingControlMap,
                        Implementation, Notification, Poam, PoamFinding, PoamHistory, PoamMatchRule, RoleAssignment, System, User)
from app.services import audit

SIGNATURE = "Record approval (simulated signature – not CAC/PIV)"
ACTIVE_POAM = ("new", "in_progress", "closure_eligible", "closure_review", "risk_acceptance_review")
REQUEST_TYPES = {"finding_out_of_scope": "Out of scope / N/A / informational disposition", "false_positive": "False-positive disposition", "poam_closure": "POA&M closure", "risk_acceptance": "Risk acceptance",
                 "waiver_extension": "Waiver (risk accepted past due date)", "control_implementation_review": "Control implementation review",
                 "deadline_extension": "Deadline extension (≤ 90 days, no risk acceptance)", "authorization_package_review": "Authorization package review",
                 "assessment_result": "Assessment result", "authorization_decision": "Authorization decision",
                 "emass_submission": "eMASS outbound change"}
EXTENSION_LIMIT_DAYS = 90
RULE_PRECEDENCE = ("Exactly one active rule per request type. Deadline extension applies only when the new date is ≤ 90 days past the current "
                   "due date; anything longer, or any extension that accepts residual risk, must be filed as a Waiver (ISSM endorses → AO decides).")


def validate_rules(rules: list) -> list[str]:
    """Reject overlapping rules: more than one active rule for the same request type/scope, or unknown request types."""
    errs, seen = [], {}
    for r in rules:
        if r.request_type not in REQUEST_TYPES:
            errs.append(f"unknown request type {r.request_type}")
        if r.is_active and (r.org_id, r.request_type) in seen:
            errs.append(f"overlapping active rules for {r.request_type}")
        seen[(r.org_id, r.request_type)] = r
    return errs


DEFAULT_RULES = [
    ("false_positive", [{"role": "issm", "action": "decide"}], "False positive → ISSM decides"),
    ("finding_out_of_scope", [{"role": "issm", "action": "decide"}], "Out of scope / not applicable → ISSM decides"),
    ("poam_closure", [{"role": "issm", "action": "decide"}], "POA&M closure → ISSM decides"),
    ("waiver_extension", [{"role": "issm", "action": "endorse"}, {"role": "ao", "action": "decide"}], "Waiver (accept risk beyond the due date, or extension > 90 days) → ISSM endorses, AO decides"),
    ("risk_acceptance", [{"role": "issm", "action": "endorse"}, {"role": "ao", "action": "decide"}], "Risk acceptance → ISSM endorses, AO decides"),
    ("control_implementation_review", [{"role": "issm", "action": "decide"}], "Control implementation statement → ISSM decides"),
    ("assessment_result", [{"role": "sca", "action": "decide"}], "Assessment result → SCA records (independence enforced)"),
    ("deadline_extension", [{"role": "issm", "action": "decide"}], "Deadline extension (new date ≤ 90 days past current due date, no risk acceptance) → ISSM decides"),
    ("authorization_package_review", [{"role": "issm", "action": "endorse"}, {"role": "ao", "action": "decide"}],
     "Authorization package → ISSM endorses, AO records authorization decision"),
    ("authorization_decision", [{"role": "ao", "action": "decide"}], "Authorization decision (ATO/ATO w/ conditions/IATT/DATO) → AO only"),
    ("emass_submission", [{"role": "issm", "action": "decide"}], "eMASS outbound change → ISSM approves before submission"),
]


def now() -> datetime:
    return datetime.now(timezone.utc)


def notify(db: Session, user_id, title: str, link: str, kind: str, body: str | None = None) -> None:
    from app.services.rmf import send

    send(db, user_id, kind, title, link, body)


def users_with_role(db: Session, org_id, system_id, role: str) -> list[uuid.UUID]:
    return list(db.scalars(select(RoleAssignment.user_id).where(RoleAssignment.role == role, (
        ((RoleAssignment.scope_type == "system") & (RoleAssignment.scope_id == system_id)) |
        ((RoleAssignment.scope_type == "org") & (RoleAssignment.scope_id == org_id)))).distinct()))


def next_seq(db: Session, model, org_id) -> int:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"{model.__tablename__}:{org_id}"})
    return (db.scalar(select(func.max(model.seq)).where(model.org_id == org_id)) or 0) + 1


def display_status(p: Poam) -> str:
    if p.status in ("new", "in_progress") and p.due_date and p.due_date < date.today():
        return "overdue"
    return p.status


def history(db: Session, p: Poam, actor: User | None, action: str, **details) -> None:
    db.add(PoamHistory(poam_id=p.id, actor_id=actor.id if actor else None, actor_email=actor.email if actor else "system",
                       action=action, details=details or None))


# ---------- POA&M matching ----------
def active_match_rule(db: Session, org_id) -> PoamMatchRule | None:
    return db.scalar(select(PoamMatchRule).where(PoamMatchRule.org_id == org_id, PoamMatchRule.is_active.is_(True))
                     .order_by(PoamMatchRule.version.desc()))


SOURCE_LABELS = {"stig_checklist": "STIG", "acas": "ACAS", "policy_audit": "Policy audit", "scap": "SCAP", "manual": "Manual review"}


def source_label(source_type: str | None) -> str:
    return SOURCE_LABELS.get(source_type or "", (source_type or "Other").replace("_", " ").title())


def finding_controls(db: Session, f: Finding) -> list[str]:
    return sorted(set(db.scalars(select(FindingControlMap.control_id).where(FindingControlMap.finding_id == f.id))))


def find_matching_poams(db: Session, f: Finding, org_id) -> tuple[list[Poam], PoamMatchRule | None]:
    """Same rule/plugin/CVE AND overlapping control, open POA&M, same system (optionally across assets)."""
    rule = active_match_rule(db, org_id)
    if rule is None:
        return [], None
    ident = {f.rule_id, f.vuln_id, f.plugin_id, *(f.cves or [])} - {None, ""}
    ctl = set(finding_controls(db, f))
    out = []
    for p in db.scalars(select(Poam).where(Poam.system_id == f.system_id, Poam.status.in_(ACTIVE_POAM))):
        linked = list(db.scalars(select(Finding).join(PoamFinding, PoamFinding.finding_id == Finding.id).where(PoamFinding.poam_id == p.id)))
        if any(x.id == f.id for x in linked):
            out.append(p)
            continue
        ids = set(p.vuln_ids or []) | {i for x in linked for i in (x.rule_id, x.vuln_id, x.plugin_id, *(x.cves or [])) if i}
        same_ident = "identifier" not in rule.fields or bool(ident & ids)
        same_ctl = "control" not in rule.fields or bool(ctl & set(p.control_ids or []))
        same_asset = rule.across_assets or f.asset_id is None or str(f.asset_id) in (p.asset_ids or [])
        if same_ident and same_ctl and same_asset:
            out.append(p)
    return out, rule


def link_finding(db: Session, p: Poam, f: Finding, actor: User | None) -> None:
    if not db.scalar(select(PoamFinding.id).where(PoamFinding.poam_id == p.id, PoamFinding.finding_id == f.id)):
        db.add(PoamFinding(poam_id=p.id, finding_id=f.id, linked_by=actor.id if actor else None))
        if f.asset_id and str(f.asset_id) not in (p.asset_ids or []):
            p.asset_ids = [*(p.asset_ids or []), str(f.asset_id)]
        ids = {f.vuln_id or f.rule_id or f.plugin_id, *(f.cves or [])} - {None, ""}
        p.vuln_ids = sorted(set(p.vuln_ids or []) | ids)
        if f.latest_evidence_id and str(f.latest_evidence_id) not in (p.detection_evidence_ids or []):
            p.detection_evidence_ids = [*(p.detection_evidence_ids or []), str(f.latest_evidence_id)]
        history(db, p, actor, "finding_linked", finding_id=str(f.id))


def create_poam(db: Session, *, system: System, actor: User | None, data: dict, findings: list[Finding]) -> Poam:
    seq = data.pop("seq", None) or next_seq(db, Poam, system.org_id)
    p = Poam(id=uuid.uuid4(), org_id=system.org_id, system_id=system.id, seq=seq, human_id=f"P-{seq:04d}", created_by=actor.id if actor else None,
             asset_ids=[], vuln_ids=[], detection_evidence_ids=[], **data)
    db.add(p)
    db.flush()
    history(db, p, actor, "created", status=p.status)
    for f in findings:
        link_finding(db, p, f, actor)
    if p.owner_id:
        notify(db, p.owner_id, f"{p.human_id} assigned to you", f"/poams/{p.id}", "assignment", p.weakness[:200])
    audit.record(db, action="poam.created", actor_user_id=actor.id if actor else None, actor_email=actor.email if actor else "seed",
                 entity_type="poam", entity_id=str(p.id), after={"human_id": p.human_id, "findings": [str(f.id) for f in findings]})
    db.flush()
    return p


def on_remediation_observed(db: Session, findings: list[Finding], run_id=None) -> list[str]:
    """Rescan shows fix: mark finding 'remediated_observed' and POA&M 'closure_eligible'. NEVER closes anything."""
    touched = []
    for f in findings:
        if f.remediation_status in ("remediated_observed", "closed"):
            continue
        poams = list(db.scalars(select(Poam).join(PoamFinding, PoamFinding.poam_id == Poam.id)
                                .where(PoamFinding.finding_id == f.id, Poam.status.in_(("new", "in_progress")))))
        if not poams and not db.scalar(select(PoamFinding.id).where(PoamFinding.finding_id == f.id)):
            continue
        f.remediation_status, f.remediated_observed_at = "remediated_observed", now()
        for p in poams:
            linked = list(db.scalars(select(Finding).join(PoamFinding, PoamFinding.finding_id == Finding.id).where(PoamFinding.poam_id == p.id)))
            if all(x.remediation_status in ("remediated_observed", "closed") or x.disposition == "false_positive" for x in linked):
                p.status = "closure_eligible"
                history(db, p, None, "closure_eligible", reason="rescan observed remediation of all linked findings")
                notify(db, p.owner_id or p.created_by, f"{p.human_id} is closure eligible", f"/poams/{p.id}", "closure_eligible",
                       "A rescan observed the weakness fixed. Request closure with evidence; it is not closed automatically.")
                touched.append(p.human_id)
                from app.models import FindingObservation

                fids = [x.id for x in linked]
                obs = [str(o) for o in db.scalars(select(FindingObservation.id).where(FindingObservation.finding_id.in_(fids),
                                                                                    FindingObservation.ingest_run_id == run_id))] if run_id else []
                audit.record(db, action="poam.closure_eligible", actor_email="system", entity_type="poam", entity_id=str(p.id),
                             after={"status": "closure_eligible", "human_id": p.human_id},
                             details={"ingest_run_id": str(run_id) if run_id else None, "finding_ids": [str(i) for i in fids],
                                      "observation_ids": obs, "note": "System detected remediation; NOT closed – requires ISSM closure approval"})
    return touched


# ---------- review engine ----------
def rule_for(db: Session, org_id, request_type: str) -> DecisionRule:
    r = db.scalar(select(DecisionRule).where(DecisionRule.org_id == org_id, DecisionRule.request_type == request_type,
                                             DecisionRule.is_active.is_(True)).order_by(DecisionRule.version.desc()))
    if r is None and not db.scalar(select(DecisionRule.id).where(DecisionRule.org_id == org_id, DecisionRule.request_type == request_type)):
        default = next((d for d in DEFAULT_RULES if d[0] == request_type), None)
        if default:  # request type added after the tenant was seeded: install its default rule (v1)
            r = DecisionRule(org_id=org_id, request_type=request_type, version=1, steps=default[1], label=default[2],
                             description="Default decision rule (installed on first use)")
            db.add(r)
            db.flush()
    if r is None:
        raise HTTPException(409, f"No active decision rule for {request_type}")
    return r


def create_request(db: Session, *, system: System, requester: User, request_type: str, justification: str, **fields) -> ApprovalRequest:
    rule = rule_for(db, system.org_id, request_type)
    seq = next_seq(db, ApprovalRequest, system.org_id)
    req = ApprovalRequest(id=uuid.uuid4(), org_id=system.org_id, system_id=system.id, seq=seq, human_id=f"R-{seq:04d}",
                          request_type=request_type, decision_rule_id=rule.id, rule_version=rule.version, current_step=0,
                          assigned_role=rule.steps[0]["role"], justification=justification, requester_id=requester.id, **fields)
    db.add(req)
    db.flush()
    for uid in users_with_role(db, system.org_id, system.id, req.assigned_role):
        if uid != requester.id:
            notify(db, uid, f"{req.human_id}: {REQUEST_TYPES[request_type]} awaiting {req.assigned_role.upper()}", f"/reviews/{req.id}", "pending_review")
    audit.record(db, action="review.requested", actor_user_id=requester.id, actor_email=requester.email, entity_type="approval_request",
                 entity_id=str(req.id), after={"type": request_type, "human_id": req.human_id, "rule_version": rule.version,
                                               "poam_id": str(req.poam_id) if req.poam_id else None,
                                               "finding_id": str(req.finding_id) if req.finding_id else None})
    return req


DISPOSITIONS = {"false_positive": "false_positive", "not_applicable": "finding_out_of_scope", "out_of_scope": "finding_out_of_scope",
                "informational": "finding_out_of_scope", "no_control_mapping": "finding_out_of_scope"}


def request_disposition(db: Session, *, system: System, requester: User, findings: list[Finding], disposition: str, justification: str) -> ApprovalRequest:
    """Every finding disposition is a review under the active decision rule; nothing changes until it is approved."""
    if db.scalar(select(ApprovalRequest.id).where(ApprovalRequest.finding_id.in_([f.id for f in findings]), ApprovalRequest.status == "pending")):
        raise HTTPException(409, "A pending disposition request already exists for these findings")
    f0 = findings[0]
    ctl = finding_controls(db, f0)
    return create_request(db, system=system, requester=requester, request_type=DISPOSITIONS[disposition], justification=justification,
                          finding_id=f0.id, control_id=ctl[0] if ctl else None,
                          payload={"finding_ids": [str(f.id) for f in findings], "disposition": disposition, "rule_key": f0.vuln_id or f0.rule_id},
                          evidence_ids=[str(f0.latest_evidence_id)] if f0.latest_evidence_id else [])


def decide(db: Session, req_id: uuid.UUID, actor: User, assignments: list, action: str, rationale: str) -> ApprovalRequest:
    from app.services.evaluation import evaluate_system, take_snapshots

    req = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == req_id).with_for_update())
    if req is None:
        raise HTTPException(404, "Request not found")
    if req.status != "pending":
        raise HTTPException(409, f"Request is already {req.status}")
    if req.requester_id == actor.id:
        _deny(actor, req, "requester_cannot_decide_own_request", action)
        raise HTTPException(403, "Requester cannot decide their own request")
    if len((rationale or "").strip()) < 10:
        raise HTTPException(422, "A rationale (at least 10 characters) is required")
    rule = db.get(DecisionRule, req.decision_rule_id)
    step = rule.steps[req.current_step]
    sys_ = db.get(System, req.system_id)
    has_role = any(ra.role == step["role"] and ((ra.scope_type == "system" and ra.scope_id == req.system_id) or
                                                (ra.scope_type == "org" and ra.scope_id == sys_.org_id)) for ra in assignments)
    if not has_role:
        _deny(actor, req, f"decision_rule_requires_{step['role']}", action)
        raise HTTPException(403, f"Decision rule v{rule.version} assigns this step to {step['role'].upper()}")
    allowed = {"decide": {"approve", "reject", "return", "request_evidence", "escalate"},
               "endorse": {"endorse", "reject", "return", "request_evidence", "escalate"}}[step["action"]]
    if action not in allowed:
        raise HTTPException(422, f"Action '{action}' not allowed at this step ({step['action']})")
    db.add(ApprovalDecision(request_id=req.id, step=req.current_step, action=action, decider_id=actor.id, decider_email=actor.email,
                            decision_authority=f"{step['role']} via decision_rule {rule.request_type} v{rule.version}", rationale=rationale,
                            signature=SIGNATURE if action in ("approve", "endorse") else "n/a"))
    requester_link = f"/reviews/{req.id}"
    if action in ("endorse", "escalate"):
        if req.current_step + 1 < len(rule.steps):
            req.current_step += 1
            req.assigned_role = rule.steps[req.current_step]["role"]
            for uid in users_with_role(db, sys_.org_id, sys_.id, req.assigned_role):
                notify(db, uid, f"{req.human_id} {action}d – awaiting {req.assigned_role.upper()}", requester_link, "pending_review")
        elif action == "endorse":
            raise HTTPException(422, "Nothing to endorse to")
        else:
            req.payload = {**(req.payload or {}), "escalated": True}
    elif action == "approve":
        req.status, req.resolved_at = "approved", now()
        _apply_effects(db, req, actor)
        notify(db, req.requester_id, f"{req.human_id} approved", requester_link, "approved")
    else:
        req.status = {"reject": "rejected", "return": "returned", "request_evidence": "more_evidence_requested"}[action]
        req.resolved_at = now()
        _revert(db, req, actor, action)
        notify(db, req.requester_id, f"{req.human_id} {req.status.replace('_', ' ')}", requester_link,
               "rejected" if action == "reject" else "returned", rationale[:500])
    audit.record(db, action=f"review.{action}", actor_user_id=actor.id, actor_email=actor.email, entity_type="approval_request",
                 entity_id=str(req.id), after={"status": req.status, "step": req.current_step, "rationale": rationale,
                                               "decision_authority": step["role"], "rule_version": rule.version})
    db.flush()
    evaluate_system(db, req.system_id)
    take_snapshots(db, trigger=f"review.{action}")
    return req


def _deny(actor: User, req: ApprovalRequest, reason: str, action: str) -> None:
    """Authorization failures on decisions are audited in a separate transaction (survives the 403 rollback)."""
    audit.record_now(action="authz.denied", outcome="denied", actor_user_id=actor.id, actor_email=actor.email,
                     entity_type="approval_request", entity_id=str(req.id),
                     details={"reason": reason, "attempted_action": action, "request": req.human_id, "request_type": req.request_type,
                              "assigned_role": req.assigned_role, "system_id": str(req.system_id)})


def _revert(db: Session, req: ApprovalRequest, actor: User, action: str) -> None:
    if req.request_type == "emass_submission":
        from app.services.emass import on_approval
        on_approval(db, req.payload["emass_change_id"], False, actor)
    if req.poam_id:
        p = db.get(Poam, req.poam_id)
        prev = (req.payload or {}).get("prev_status")
        if prev and p.status in ("closure_review", "risk_acceptance_review"):
            p.status = prev
        history(db, p, actor, f"request_{action}", request=req.human_id)


def _queue_emass(db: Session, req: ApprovalRequest, entity: str, eid: str, label: str, after: dict, trigger: str) -> None:
    """Approved closures / authorization decisions auto-queue a PROPOSED outbound eMASS change (never auto-submitted)."""
    from app.services.emass import queue_change
    queue_change(db, system=db.get(System, req.system_id), entity_type=entity, entity_id=eid, label=label, after=after, before=None,
                 trigger=trigger, requester=None)


def _apply_effects(db: Session, req: ApprovalRequest, actor: User) -> None:
    t = req.request_type
    if t == "poam_closure":
        p = db.get(Poam, req.poam_id)
        p.status, p.actual_completion, p.closure_evidence_ids = "closed", date.today(), req.evidence_ids
        for f in db.scalars(select(Finding).join(PoamFinding, PoamFinding.finding_id == Finding.id).where(PoamFinding.poam_id == p.id)):
            f.remediation_status = "closed"
            if f.current_state == "open":
                f.current_state = "closed_by_review"
        history(db, p, actor, "closed", request=req.human_id)
        _queue_emass(db, req, "poam", str(p.id), f"{p.human_id} closure", {"status": "Completed", "completion_date": str(p.actual_completion)},
                     "poam_closure_approved")
    elif t == "emass_submission":
        from app.services.emass import on_approval
        on_approval(db, req.payload["emass_change_id"], True, actor)
    elif t == "false_positive":
        f = db.get(Finding, req.finding_id)
        f.disposition, f.disposition_justification = "false_positive", req.justification
    elif t == "finding_out_of_scope":
        disp = (req.payload or {}).get("disposition", "out_of_scope")
        for fid in (req.payload or {}).get("finding_ids", [str(req.finding_id)]):
            f = db.get(Finding, uuid.UUID(fid))
            if f is not None:
                f.mapping_status, f.disposition, f.disposition_justification = "dispositioned", disp, req.justification
        from app.services.evaluation import evaluate_system
        db.flush()
        evaluate_system(db, req.system_id)
    elif t == "risk_acceptance":
        p = db.get(Poam, req.poam_id)
        p.status, p.risk_acceptance_ref = "risk_accepted", req.human_id
        p.risk_acceptance_expiration = date.fromisoformat(req.payload["expiration"])
        history(db, p, actor, "risk_accepted", request=req.human_id, expiration=req.payload["expiration"])
    elif t == "authorization_package_review":
        from app.models import AuthorizationDecision
        from app.services.rmf import package
        d = (req.payload or {}).get("decision")
        if not d:
            raise HTTPException(422, "Use the authorization decision form (decision, expiration, rationale) to approve a package")
        s = db.get(System, req.system_id)
        s.authorization_status = {"ATO": "Authorized (ATO)", "ATO_with_conditions": "Authorized (ATO w/ conditions)",
                                  "IATT": "Authorized (IATT)", "DATO": "Denied (DATO)"}[d["decision"]]
        s.authorization_expiration = date.fromisoformat(d["expiration"]) if d.get("expiration") else None
        db.add(AuthorizationDecision(system_id=s.id, request_id=req.id, decision=d["decision"], conditions=d.get("conditions"),
                                     expiration=s.authorization_expiration, rationale=d["rationale"], decider_id=actor.id,
                                     signature=SIGNATURE, package_snapshot=__import__("json").loads(__import__("json").dumps(package(db, s), default=str))))
        _queue_emass(db, req, "system", str(s.id), f"{s.acronym} authorization ({d['decision']})",
                     {"authorization_status": s.authorization_status, "authorization_expiration": str(s.authorization_expiration)}, "authorization_decision")
    elif t in ("waiver_extension", "deadline_extension"):
        p = db.get(Poam, req.poam_id)
        old = p.due_date
        p.due_date = date.fromisoformat(req.payload["new_due_date"])
        if p.status in ("closure_review", "risk_acceptance_review"):
            p.status = req.payload.get("prev_status", "in_progress")
        history(db, p, actor, "due_date_extended", request=req.human_id, old=str(old), new=str(p.due_date))
    elif t == "control_implementation_review":
        impl = db.get(Implementation, req.implementation_id)
        for i in db.scalars(select(Implementation).where(Implementation.assignment_id == impl.assignment_id, Implementation.review_status == "approved")):
            i.review_status = "superseded"
        impl.review_status, impl.needs_reconsideration = "approved", False
    audit.record(db, action=f"review.effect.{t}", actor_user_id=actor.id, actor_email=actor.email, entity_type="approval_request",
                 entity_id=str(req.id), details={"poam_id": str(req.poam_id) if req.poam_id else None,
                                                 "finding_id": str(req.finding_id) if req.finding_id else None})


def evidence_in_system(db: Session, system_id, ids: list[str]) -> list[str]:
    ok = {str(i) for i in db.scalars(select(Evidence.id).where(Evidence.system_id == system_id,
                                                                Evidence.id.in_([uuid.UUID(x) for x in ids if _is_uuid(x)])))}
    return [x for x in ids if x in ok]


def _is_uuid(x: str) -> bool:
    try:
        uuid.UUID(str(x))
        return True
    except ValueError:
        return False


_ = ControlAssignment
