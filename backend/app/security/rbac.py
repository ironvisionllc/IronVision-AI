import uuid

ROLES: dict[str, str] = {
    "system_owner": "System Owner",
    "isso": "Information System Security Officer",
    "issm": "Information System Security Manager",
    "sca": "Security Control Assessor",
    "ao": "Authorizing Official",
    "devsecops": "DevSecOps Engineer",
    "leadership_viewer": "Leadership Viewer",
    "privacy_official": "Privacy Official",
    "platform_admin": "Platform Administrator",
}

PERMISSIONS: dict[str, str] = {
    "catalog.read": "Browse reference content (controls, baselines, CCIs)",
    "system.read": "View systems in scope",
    "system.write": "Create/update system records",
    "evidence.submit": "Submit evidence for controls",
    "poam.manage": "Create and manage POA&M items",
    "assessment.perform": "Perform control assessments and record findings (SCA)",
    "authorization.decide": "Issue authorization decisions (ATO/IATT/DATO) (AO)",
    "risk.accept": "Formally accept residual risk (AO)",
    "portfolio.read": "View portfolio/leadership dashboards",
    "audit.read": "Read the audit event ledger",
    "admin.health.read": "View platform health and jobs",
    "admin.users.manage": "Manage users and role assignments",
    "admin.content.load": "Trigger reference content loads",
    "admin.ai.test": "Run AI provider smoke tests",
    "system.register": "Register new systems",
    "system.roles.manage": "Assign/revoke system-scoped roles",
    "source.manage": "Configure evidence sources and run collections",
    "ingest.upload": "Upload scan/checklist files for ingestion",
    "finding.map": "Map or disposition unmapped findings (with justification)",
    "implementation.write": "Edit control implementation narratives",
    "comment.write": "Add reviewer comments",
    "evidence.verify": "Run evidence integrity/freshness jobs",
    "demo.tools": "Demo-only tools (reset demo data, adjust demo evidence dates)",
    "content.apply": "Approve and apply content updates (STIG/KEV/CCI) after impact preview",
    "emass.queue": "Queue outbound eMASS changes and run compare/import",
    "emass.admin": "Configure the eMASS connector and failure simulation",
    "risk.admin": "Edit operational prioritization weights and job schedules",
    "privacy.review": "Review and approve Privacy Threshold Analyses and privacy determinations",
}

_BASE = {"catalog.read", "system.read"}
_ISSO = {"system.write", "evidence.submit", "poam.manage", "audit.read", "source.manage", "ingest.upload", "finding.map",
         "implementation.write", "comment.write", "evidence.verify", "system.register", "emass.queue"}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "system_owner": _BASE | {"system.write", "evidence.submit", "poam.manage", "system.register", "ingest.upload",
                             "implementation.write", "comment.write"},
    "isso": _BASE | _ISSO,
    "issm": _BASE | {"system.write", "poam.manage", "portfolio.read", "audit.read", "admin.health.read", "system.register",
                     "system.roles.manage", "source.manage", "finding.map", "comment.write", "evidence.verify", "content.apply", "emass.queue"},
    "sca": _BASE | {"assessment.perform", "audit.read", "comment.write", "evidence.verify"},
    "ao": _BASE | {"authorization.decide", "risk.accept", "portfolio.read", "audit.read", "comment.write"},
    "devsecops": _BASE | {"evidence.submit", "ingest.upload", "source.manage"},
    "leadership_viewer": _BASE | {"portfolio.read"},
    "privacy_official": _BASE | {"privacy.review", "audit.read", "comment.write"},
    "platform_admin": {"catalog.read", "system.read", "audit.read", "admin.health.read", "admin.users.manage",
                       "admin.content.load", "admin.ai.test", "system.roles.manage", "evidence.verify", "demo.tools",
                       "content.apply", "emass.admin", "risk.admin"},
}

DECISION_PERMISSIONS = {"authorization.decide", "risk.accept", "assessment.perform"}
assert not (ROLE_PERMISSIONS["platform_admin"] & DECISION_PERMISSIONS), "platform_admin must not hold AO/SCA decision rights"
assert all(p in PERMISSIONS for perms in ROLE_PERMISSIONS.values() for p in perms)


def has_permission(assignments: list, permission: str, org_id: uuid.UUID, system_id: uuid.UUID | None = None) -> bool:
    for ra in assignments:
        in_scope = (ra.scope_type == "org" and ra.scope_id == org_id) or (
            system_id is not None and ra.scope_type == "system" and ra.scope_id == system_id
        )
        if in_scope and permission in ROLE_PERMISSIONS.get(ra.role, set()):
            return True
    return False


def effective_permissions(assignments: list) -> list[str]:
    return sorted({p for ra in assignments for p in ROLE_PERMISSIONS.get(ra.role, set())})
