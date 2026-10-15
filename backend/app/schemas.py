import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=256)


class RoleOut(ORM):
    role: str
    scope_type: str
    scope_id: uuid.UUID


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    title: str | None
    org_id: uuid.UUID
    org_name: str
    roles: list[RoleOut]
    permissions: list[str]
    auth_provider: str
    auth_is_simulated: bool
    persona_role: str | None = None
    is_sandbox: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str | None = None
    idle_timeout_minutes: int | None = None
    user: UserOut


class DevAccount(BaseModel):
    email: str
    display_name: str
    role: str
    role_label: str


class AuthProviderInfo(BaseModel):
    provider: str
    label: str
    is_simulated: bool
    dev_accounts: list[DevAccount]
    enabled_providers: list[str] = []
    dev_password_enabled: bool = True
    signup_enabled: bool = False
    demo_login_enabled: bool = False
    registration_enabled: bool = False
    oidc_enabled: bool = False


class HealthComponent(BaseModel):
    ok: bool
    detail: dict[str, Any] = {}


class HealthOut(BaseModel):
    status: str
    version: str
    components: dict[str, HealthComponent]


class ControlSummary(ORM):
    control_id: str
    label: str | None
    title: str
    family_id: str
    family_title: str
    is_enhancement: bool
    is_withdrawn: bool
    parent_control_id: str | None
    sort_id: str | None
    baselines: list[str] = []


class ControlList(BaseModel):
    total: int
    limit: int
    offset: int
    catalog_version_id: uuid.UUID | None
    items: list[ControlSummary]


class FamilyOut(BaseModel):
    family_id: str
    family_title: str
    count: int


class ObjectiveOut(ORM):
    objective_id: str
    parent_objective_id: str | None
    label: str | None
    prose: str | None
    depth: int


class CciMapOut(BaseModel):
    cci_id: str
    definition: str
    reference_index: str
    statement_part: str | None
    review_status: str
    version: str
    effective_date: date | None
    source: str | None


class ControlDetail(ControlSummary):
    statement: str | None
    parameters: list[dict] | None
    guidance: str | None
    assessment_methods: list[dict] | None
    links: list[dict] | None
    objectives: list[ObjectiveOut]
    ccis: list[CciMapOut]
    enhancements: list[dict]
    source: str | None
    provenance: dict | None


class ContentVersionOut(ORM):
    id: uuid.UUID
    content_type: str
    content_key: str
    title: str
    version: str | None
    release_tag: str | None
    commit_sha: str | None
    source_url: str
    sha256: str
    file_name: str
    storage_key: str | None
    effective_date: date | None
    loaded_at: datetime | None
    status: str
    is_active: bool
    item_count: int | None
    meta: dict | None


class JobOut(ORM):
    id: uuid.UUID
    job_type: str
    status: str
    attempts: int
    payload: dict | None
    result: dict | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ContentLoadRequest(BaseModel):
    force: bool = False


class AuditEventOut(ORM):
    seq: int
    occurred_at: datetime
    actor_user_id: uuid.UUID | None = None
    actor_email: str | None
    actor_name: str | None = None
    actor_roles: list[str] = []
    action: str
    entity_type: str | None
    entity_id: str | None
    outcome: str
    correlation_id: str | None
    ip: str | None
    details: dict | None
    hash: str
    prev_hash: str


class AIHealthOut(BaseModel):
    ok: bool
    provider: str
    model: str | None
    latency_ms: int
    prompt_id: str
    prompt_version: str
    interaction_id: uuid.UUID
    output: dict


class SystemOut(ORM):
    id: uuid.UUID
    name: str
    acronym: str | None
    baseline_key: str | None
    lifecycle_status: str
    is_synthetic: bool


class DecisionTestOut(BaseModel):
    ok: bool
    message: str
    permission: str
    actor: str
    roles: list[str]
