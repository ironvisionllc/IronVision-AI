from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import DecisionTestOut
from app.security.deps import CurrentUser, get_current_user, require_permission
from app.security.rbac import PERMISSIONS, ROLE_PERMISSIONS, ROLES
from app.services import audit

router = APIRouter(tags=["authorization"])


@router.post("/authorization-decisions/test", response_model=DecisionTestOut)
def decision_test(request: Request, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("authorization.decide"))) -> DecisionTestOut:
    """Phase 0 placeholder proving AO-only enforcement. Records no decision."""
    audit.record(db, action="authorization_decision.test", actor_user_id=current.user.id, actor_email=current.user.email,
                 entity_type="permission", entity_id="authorization.decide", details={"roles": current.roles},
                 **audit.request_meta(request))
    db.commit()
    return DecisionTestOut(ok=True, message="Permission authorization.decide granted (placeholder – no decision recorded)",
                           permission="authorization.decide", actor=current.user.email, roles=current.roles)


@router.get("/rbac/matrix", tags=["rbac"])
def rbac_matrix(_: CurrentUser = Depends(get_current_user)) -> dict:
    return {"roles": ROLES, "permissions": PERMISSIONS,
            "matrix": {role: sorted(perms) for role, perms in ROLE_PERMISSIONS.items()}}
