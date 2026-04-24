"""
Expanded RBAC (Role-Based Access Control)
- Roles: admin, auditor, system_owner, remediation_engineer, viewer
- Granular permissions per role
- Role assignment UI endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional, List
from datetime import datetime, timezone
import logging

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rbac", tags=["rbac"])

# ─── Role Definitions ─────────────────────────────────

ROLES = {
    "admin": {
        "label": "Administrator",
        "description": "Full access to all features including user management and framework configuration",
        "permissions": [
            "frameworks.read", "frameworks.write", "frameworks.delete",
            "controls.read", "controls.write", "controls.assess",
            "policies.read", "policies.write", "policies.approve", "policies.delete",
            "documents.read", "documents.write", "documents.delete",
            "evidence.read", "evidence.write", "evidence.collect",
            "pipeline.read", "pipeline.write", "pipeline.manage_keys",
            "tenable.read", "tenable.write", "tenable.sync", "tenable.assess",
            "poam.read", "poam.write", "poam.close",
            "risk.read", "risk.write",
            "ingestion.read", "ingestion.write", "ingestion.map",
            "oscal.read", "oscal.write", "oscal.export",
            "users.read", "users.write", "users.assign_roles",
            "settings.read", "settings.write",
            "remediation.read", "remediation.generate",
            "reports.read", "reports.export",
        ],
    },
    "auditor": {
        "label": "Auditor",
        "description": "Read-only access for compliance auditing with export capabilities. Cannot modify data.",
        "permissions": [
            "frameworks.read", "controls.read",
            "policies.read", "documents.read",
            "evidence.read",
            "pipeline.read", "tenable.read",
            "poam.read",
            "risk.read",
            "ingestion.read",
            "oscal.read", "oscal.export",
            "reports.read", "reports.export",
        ],
    },
    "system_owner": {
        "label": "System Owner",
        "description": "Full admin access scoped to assigned projects/frameworks. Can manage compliance for their systems.",
        "permissions": [
            "frameworks.read", "controls.read", "controls.write", "controls.assess",
            "policies.read", "policies.write", "policies.approve",
            "documents.read", "documents.write",
            "evidence.read", "evidence.write", "evidence.collect",
            "pipeline.read", "pipeline.write",
            "tenable.read", "tenable.sync", "tenable.assess",
            "poam.read", "poam.write", "poam.close",
            "risk.read",
            "ingestion.read", "ingestion.write", "ingestion.map",
            "oscal.read", "oscal.export",
            "remediation.read", "remediation.generate",
            "reports.read", "reports.export",
        ],
    },
    "remediation_engineer": {
        "label": "Remediation Engineer",
        "description": "Can close POA&Ms, generate remediation code, and manage pipeline findings. Cannot modify frameworks.",
        "permissions": [
            "frameworks.read", "controls.read",
            "policies.read",
            "documents.read",
            "evidence.read",
            "pipeline.read", "pipeline.write",
            "tenable.read",
            "poam.read", "poam.write", "poam.close",
            "risk.read",
            "ingestion.read",
            "remediation.read", "remediation.generate",
            "reports.read",
        ],
    },
    "viewer": {
        "label": "Viewer",
        "description": "Read-only access to all compliance data. Cannot modify or export.",
        "permissions": [
            "frameworks.read", "controls.read",
            "policies.read", "documents.read",
            "evidence.read",
            "pipeline.read", "tenable.read",
            "poam.read",
            "risk.read",
            "ingestion.read",
            "oscal.read",
            "reports.read",
        ],
    },
}


class RoleAssignment(BaseModel):
    user_id: str
    role: str


# ─── Endpoints ─────────────────────────────────────────

@router.get("/roles")
async def list_roles(current_user: Dict = Depends(get_current_user)):
    """List all available roles with their permissions."""
    return {role: {"label": info["label"], "description": info["description"], "permissions": info["permissions"], "permission_count": len(info["permissions"])} for role, info in ROLES.items()}


@router.get("/users")
async def list_users_with_roles(current_user: Dict = Depends(get_current_user)):
    """List all users in the organization with their roles."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    users = await db.users.find(
        {"roles.organization_id": org_id},
        {"_id": 0, "password_hash": 0}
    ).to_list(200)

    return [{"id": u["id"], "name": u.get("name", ""), "email": u.get("email", ""),
             "role": u["roles"][0]["role"] if u.get("roles") else "viewer",
             "created_at": u.get("created_at", "")} for u in users]


@router.put("/assign")
async def assign_role(data: RoleAssignment, current_user: Dict = Depends(get_current_user)):
    """Assign a role to a user. Requires admin permission."""
    # Check admin permission
    current_role = current_user["roles"][0]["role"] if current_user.get("roles") else "viewer"
    if current_role != "admin":
        raise HTTPException(403, "Only admins can assign roles")

    if data.role not in ROLES:
        raise HTTPException(400, f"Invalid role: {data.role}. Valid: {list(ROLES.keys())}")

    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    # Don't allow changing own role
    if data.user_id == current_user["id"]:
        raise HTTPException(400, "Cannot change your own role")

    result = await db.users.update_one(
        {"id": data.user_id, "roles.organization_id": org_id},
        {"$set": {
            "roles.$.role": data.role,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    if result.modified_count == 0:
        raise HTTPException(404, "User not found in this organization")

    return {"message": f"Role updated to {data.role}", "user_id": data.user_id, "role": data.role}


@router.get("/my-permissions")
async def get_my_permissions(current_user: Dict = Depends(get_current_user)):
    """Get current user's role and permissions."""
    role_name = current_user["roles"][0]["role"] if current_user.get("roles") else "viewer"
    role_def = ROLES.get(role_name, ROLES["viewer"])

    return {
        "user_id": current_user["id"],
        "role": role_name,
        "label": role_def["label"],
        "permissions": role_def["permissions"],
    }


def has_permission(user: Dict, permission: str) -> bool:
    """Check if a user has a specific permission."""
    role_name = user["roles"][0]["role"] if user.get("roles") else "viewer"
    role_def = ROLES.get(role_name, ROLES["viewer"])
    return permission in role_def["permissions"]
