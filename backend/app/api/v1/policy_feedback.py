"""Policy Auditor "no silent misses" endpoints: "Found it here" / "Use this passage" (human-sourced mapping proposal through normal review,
audited, never auto-approved; stored as a missed-language feedback record) and the admin export of those records as gold test cases."""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditEvent, Policy, PolicyControlMap
from app.security.deps import CurrentUser, require_permission
from app.services import audit
from app.services import policy_mapping as pm
from app.services.policy_profile import find_quote

router = APIRouter()
FEEDBACK = "policy.missed_language_feedback"


class FoundIn(BaseModel):
    control_id: str = Field(pattern=r"^[a-z]{2}-\d+(\.\d+)?$")
    requirement_id: str | None = Field(default=None, max_length=80)
    text: str = Field(min_length=12, max_length=2000)
    via: str = Field(default="found_it_here", pattern="^(found_it_here|use_candidate)$")


@router.post("/policies/{policy_id}/found-it-here", status_code=201)
def found_it_here(policy_id: uuid.UUID, body: FoundIn, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    p = db.get(Policy, policy_id)
    if p is None or p.org_id != current.user.org_id:
        raise HTTPException(404, "Policy not found")
    hit = find_quote(p.text_content or "", body.text)
    if hit is None:
        raise HTTPException(422, "The highlighted text was not found in this policy's extracted text")
    quote = (p.text_content or "")[hit[0]:hit[1]]
    cur = next((m for m in pm.current(db, p.id) if m.control_id == body.control_id), None)
    proposal = None
    if cur is None:  # an OPEN proposal: decided only by an authorized reviewer in Mapping Review
        proposal = PolicyControlMap(id=uuid.uuid4(), policy_id=p.id, org_id=p.org_id, control_id=body.control_id, status="proposed",
                                    source="human_found", confidence="Medium", review_flag=True, parts=[], snippets=[quote[:500]],
                                    basis=f"passage highlighted by {current.user.email} ({body.via}){' for ' + body.requirement_id if body.requirement_id else ''}")
        db.add(proposal)
    rec = {"policy_id": str(p.id), "policy_sha256": p.sha256, "control_id": body.control_id, "requirement_id": body.requirement_id,
           "quote": quote[:2000], "offset": hit[0], "via": body.via, "proposal_id": str(proposal.id) if proposal else None,
           "existing_mapping_status": cur.status if cur else None}
    audit.record(db, action=FEEDBACK, actor_user_id=current.user.id, actor_email=current.user.email, entity_type="policy",
                 entity_id=str(p.id), details=rec)
    db.commit()
    return {"proposal_id": rec["proposal_id"], "mapping_status": "proposed" if proposal else cur.status, "quote": quote,
            "message": ("Sent to Mapping Review as a human proposal – an authorized reviewer decides." if proposal else
                        f"{body.control_id.upper()} already has a mapping ({cur.status}); the passage is recorded as missed-language feedback.")}


@router.get("/admin/policy-feedback/export")
def export_feedback(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("audit.read"))) -> Response:
    """Missed-language feedback of this organization as gold-set entries (label 'met' = the auditor should have found this passage)."""
    pids = [str(x) for x in db.scalars(select(Policy.id).where(Policy.org_id == current.user.org_id))]  # tenant scope via the policy
    rows = db.scalars(select(AuditEvent).where(AuditEvent.action == FEEDBACK, AuditEvent.entity_id.in_(pids or ["-"]))
                      .order_by(AuditEvent.occurred_at)).all()
    gold = {"source": "missed-language feedback (Found it here / Use this passage)",
            "requirements": [{"control_id": r.details["control_id"], "requirement_id": r.details.get("requirement_id"), "label": "met",
                              "quote": r.details["quote"], "policy_sha256": r.details.get("policy_sha256"), "recorded_at": r.occurred_at.isoformat()}
                             for r in rows]}
    return Response(json.dumps(gold, indent=1), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="policy_missed_language_gold.json"'})
