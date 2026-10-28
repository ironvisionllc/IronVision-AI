import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Float,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CoreMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProvenanceMixin:
    source: Mapped[str | None] = mapped_column(String(255))
    provenance: Mapped[dict | None] = mapped_column(JSONB)


class Organization(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sandbox_personas: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    protected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))  # never purge-eligible
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sandbox_status: Mapped[str | None] = mapped_column(String(30))
    sandbox_progress: Mapped[dict | None] = mapped_column(JSONB)


class User(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "users"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    persona_role: Mapped[str | None] = mapped_column(String(50))
    operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    acting_role: Mapped[str | None] = mapped_column(String(50))
    onboarding: Mapped[dict | None] = mapped_column(JSONB)


class AuthIdentity(CoreMixin, Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_auth_identities_provider_subject"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    secret_hash: Mapped[str | None] = mapped_column(String(255))
    attributes: Mapped[dict | None] = mapped_column(JSONB)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginAttempt(CoreMixin, Base):
    __tablename__ = "login_attempts"
    identifier: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RoleAssignment(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "role", "scope_type", "scope_id", name="uq_role_assignment"),
        Index("ix_role_assignments_scope", "scope_type", "scope_id"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class System(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "systems"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    acronym: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    confidentiality_impact: Mapped[str | None] = mapped_column(String(20))
    integrity_impact: Mapped[str | None] = mapped_column(String(20))
    availability_impact: Mapped[str | None] = mapped_column(String(20))
    baseline_key: Mapped[str | None] = mapped_column(String(20))
    lifecycle_status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'draft'"))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    emass_id: Mapped[str | None] = mapped_column(String(50))
    organization_name: Mapped[str | None] = mapped_column(String(255))
    mission_owner: Mapped[str | None] = mapped_column(String(255))
    system_owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    isso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    issm_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ao_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    operating_environment: Mapped[str | None] = mapped_column(String(100))
    deployment_type: Mapped[str | None] = mapped_column(String(100))
    boundary_description: Mapped[str | None] = mapped_column(Text)
    lifecycle_phase: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'Design'"))
    authorization_status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'Not authorized'"))
    nss_determination: Mapped[str | None] = mapped_column(String(10))
    applicability_flags: Mapped[dict | None] = mapped_column(JSONB)
    authorization_type: Mapped[str | None] = mapped_column(String(50))
    authorization_date: Mapped[date | None] = mapped_column(Date)
    authorization_expiration: Mapped[date | None] = mapped_column(Date)
    categorization: Mapped[str | None] = mapped_column(String(20))
    information_types: Mapped[list | None] = mapped_column(JSONB)
    include_privacy: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    overlay_keys: Mapped[list | None] = mapped_column(JSONB)
    mission_criticality: Mapped[str | None] = mapped_column(String(50))
    system_type: Mapped[str | None] = mapped_column(String(80))
    acquisition_category: Mapped[str | None] = mapped_column(String(40))
    categorization_mode: Mapped[str | None] = mapped_column(String(20))
    environment_detail: Mapped[dict | None] = mapped_column(JSONB)
    key_roles: Mapped[dict | None] = mapped_column(JSONB)
    pta: Mapped[dict | None] = mapped_column(JSONB)
    processes_pii: Mapped[bool | None] = mapped_column(Boolean)
    categorization_detail: Mapped[dict | None] = mapped_column(JSONB)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[str | None] = mapped_column(String(255))
    archive_reason: Mapped[str | None] = mapped_column(Text)
    cnssi_baseline: Mapped[dict | None] = mapped_column(JSONB)


class Asset(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "assets"
    system_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str | None] = mapped_column(String(100))
    identifier: Mapped[str | None] = mapped_column(String(255))
    attributes: Mapped[dict | None] = mapped_column(JSONB)
    hostname: Mapped[str | None] = mapped_column(String(255), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), index=True)
    cloud_resource_id: Mapped[str | None] = mapped_column(String(500))
    os: Mapped[str | None] = mapped_column(String(255))
    software_components: Mapped[list | None] = mapped_column(JSONB)
    criticality: Mapped[str | None] = mapped_column(String(30))
    network_zone: Mapped[str | None] = mapped_column(String(100))
    environment: Mapped[str | None] = mapped_column(String(50))
    inventory_source: Mapped[str | None] = mapped_column(String(100))
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_unmatched: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'confirmed'"))
    recheck_reason: Mapped[str | None] = mapped_column(Text)
    fqdn: Mapped[str | None] = mapped_column(String(255), index=True)
    mac_address: Mapped[str | None] = mapped_column(String(64), index=True)
    serial_number: Mapped[str | None] = mapped_column(String(255))
    ip_addresses: Mapped[list | None] = mapped_column(JSONB)
    inventory: Mapped[dict | None] = mapped_column(JSONB)                 # eMASS HW/SW template fields
    correlated_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))  # scan-observed → inventory asset


class ContentVersion(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "catalog_versions"
    __table_args__ = (UniqueConstraint("content_type", "content_key", "sha256", name="uq_catalog_versions_hash"),)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[str | None] = mapped_column(String(100))
    release_tag: Mapped[str | None] = mapped_column(String(100))
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    effective_date: Mapped[date | None] = mapped_column(Date)
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'loaded'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    item_count: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict | None] = mapped_column(JSONB)


class Control(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "controls"
    __table_args__ = (UniqueConstraint("catalog_version_id", "control_id", name="uq_controls_version_control"),)
    catalog_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    control_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(50))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"))
    parent_control_id: Mapped[str | None] = mapped_column(String(50))
    family_id: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    family_title: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    control_class: Mapped[str | None] = mapped_column(String(50))
    is_enhancement: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_withdrawn: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_id: Mapped[str | None] = mapped_column(String(50), index=True)
    statement: Mapped[str | None] = mapped_column(Text)
    statement_parts: Mapped[list | None] = mapped_column(JSONB)
    parameters: Mapped[list | None] = mapped_column(JSONB)
    guidance: Mapped[str | None] = mapped_column(Text)
    assessment_methods: Mapped[list | None] = mapped_column(JSONB)
    links: Mapped[list | None] = mapped_column(JSONB)
    props: Mapped[list | None] = mapped_column(JSONB)


class ControlObjective(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "control_objectives"
    control_uuid: Mapped[uuid.UUID] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True)
    objective_id: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_objective_id: Mapped[str | None] = mapped_column(String(100))
    label: Mapped[str | None] = mapped_column(String(100))
    prose: Mapped[str | None] = mapped_column(Text)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Baseline(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "baselines"
    __table_args__ = (UniqueConstraint("profile_version_id", "baseline_key", name="uq_baselines_profile_key"),)
    profile_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_versions.id", ondelete="CASCADE"), nullable=False)
    catalog_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_versions.id", ondelete="CASCADE"), nullable=False)
    baseline_key: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    control_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class BaselineControl(CoreMixin, Base):
    __tablename__ = "baseline_controls"
    __table_args__ = (UniqueConstraint("baseline_id", "control_uuid", name="uq_baseline_controls"),)
    baseline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("baselines.id", ondelete="CASCADE"), nullable=False, index=True)
    control_uuid: Mapped[uuid.UUID] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True)
    control_id: Mapped[str] = mapped_column(String(50), nullable=False)


class Cci(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "ccis"
    __table_args__ = (UniqueConstraint("content_version_id", "cci_id", name="uq_ccis_version_cci"),)
    content_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    cci_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str | None] = mapped_column(String(50))
    publish_date: Mapped[date | None] = mapped_column(Date)
    contributor: Mapped[str | None] = mapped_column(String(255))
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    cci_type: Mapped[str | None] = mapped_column(String(50))
    references: Mapped[list | None] = mapped_column(JSONB)


class CciControlMap(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "cci_control_map"
    cci_uuid: Mapped[uuid.UUID] = mapped_column(ForeignKey("ccis.id", ondelete="CASCADE"), nullable=False, index=True)
    control_uuid: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("controls.id", ondelete="SET NULL"), index=True)
    cci_id: Mapped[str] = mapped_column(String(20), nullable=False)
    control_id: Mapped[str | None] = mapped_column(String(50), index=True)
    reference_index: Mapped[str] = mapped_column(String(255), nullable=False)
    statement_part: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False)


class AuditEvent(CoreMixin, Base):
    __tablename__ = "audit_events"
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False), unique=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(255))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    ip: Mapped[str | None] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    details: Mapped[dict | None] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class AIInteraction(CoreMixin, Base):
    __tablename__ = "ai_interactions"
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_id: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request: Mapped[dict | None] = mapped_column(JSONB)
    response_text: Mapped[str | None] = mapped_column(Text)
    parsed_output: Mapped[dict | None] = mapped_column(JSONB)
    validation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    correlation_id: Mapped[str | None] = mapped_column(String(100))


class Job(CoreMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_run_after", "status", "run_after"),)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    locked_by: Mapped[str | None] = mapped_column(String(255))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    correlation_id: Mapped[str | None] = mapped_column(String(100))


class WorkerHeartbeat(CoreMixin, Base):
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    info: Mapped[dict | None] = mapped_column(JSONB)


class Notification(CoreMixin, Base):
    __tablename__ = "notifications"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'info'"))
    link: Mapped[str | None] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str | None] = mapped_column(String(50))
    dedupe_key: Mapped[str | None] = mapped_column(String(255), index=True)


# ---------------- Phase 1: core records & ingestion ----------------
def _fk(target: str, nullable: bool = False, ondelete: str = "CASCADE"):
    return mapped_column(ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True)


class Overlay(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "overlays"
    __table_args__ = (UniqueConstraint("overlay_key", "version", name="uq_overlays_key_version"),)
    overlay_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    controls_add: Mapped[list] = mapped_column(JSONB, nullable=False)
    controls_remove: Mapped[list] = mapped_column(JSONB, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    structure_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    group_key: Mapped[str | None] = mapped_column(String(60))
    variant: Mapped[str | None] = mapped_column(String(40))
    details: Mapped[dict | None] = mapped_column(JSONB)


class CommonControlProvider(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "common_control_providers"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    package: Mapped[str | None] = mapped_column(String(255))
    basis: Mapped[str | None] = mapped_column(String(255))
    coverage_text: Mapped[str | None] = mapped_column(Text)
    last_validated_at: Mapped[date | None] = mapped_column(Date)
    package_expiration: Mapped[date | None] = mapped_column(Date)
    authorization_type: Mapped[str | None] = mapped_column(String(60))
    evidence_refs: Mapped[list | None] = mapped_column(JSONB)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class ProviderControl(CoreMixin, Base):
    __tablename__ = "provider_controls"
    __table_args__ = (UniqueConstraint("provider_id", "control_id", name="uq_provider_controls"),)
    provider_id: Mapped[uuid.UUID] = _fk("common_control_providers.id")
    control_id: Mapped[str] = mapped_column(String(50), nullable=False)
    responsibility: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_responsibility: Mapped[str | None] = mapped_column(Text)
    system_responsibility: Mapped[str | None] = mapped_column(Text)
    matrix_source: Mapped[str | None] = mapped_column(String(255))


class ControlAssignment(CoreMixin, Base):
    __tablename__ = "control_assignments"
    __table_args__ = (UniqueConstraint("system_id", "control_id", name="uq_control_assignments"),)
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    control_uuid: Mapped[uuid.UUID] = _fk("controls.id")
    control_id: Mapped[str] = mapped_column(String(50), nullable=False)
    origin: Mapped[str] = mapped_column(String(30), nullable=False)
    origin_detail: Mapped[str | None] = mapped_column(String(255))
    responsibility: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'system'"))
    provider_id: Mapped[uuid.UUID | None] = _fk("common_control_providers.id", True, "SET NULL")
    provider_responsibility_text: Mapped[str | None] = mapped_column(Text)
    system_responsibility_text: Mapped[str | None] = mapped_column(Text)
    implementation_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'not_implemented'"))
    assessment_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'not_assessed'"))
    monitoring_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'no_data'"))
    evidence_freshness_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'no_evidence'"))
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    reasons: Mapped[list | None] = mapped_column(JSONB)
    evaluation: Mapped[dict | None] = mapped_column(JSONB)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_change: Mapped[dict | None] = mapped_column(JSONB)


class TailoringDecision(CoreMixin, Base):
    __tablename__ = "tailoring_decisions"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    control_id: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    overlay_key: Mapped[str | None] = mapped_column(String(100))
    prior_origin: Mapped[str | None] = mapped_column(String(30))
    prior_origin_detail: Mapped[str | None] = mapped_column(String(255))
    applicability: Mapped[str | None] = mapped_column(String(30))
    compensating_control_id: Mapped[str | None] = mapped_column(String(50))

class Implementation(CoreMixin, Base):
    __tablename__ = "implementations"
    __table_args__ = (UniqueConstraint("assignment_id", "version", name="uq_implementations_version"),)
    assignment_id: Mapped[uuid.UUID] = _fk("control_assignments.id")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    implementation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    ai_interaction_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    ai_sections: Mapped[dict | None] = mapped_column(JSONB)
    citations: Mapped[list | None] = mapped_column(JSONB)
    needs_reconsideration: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class ReviewerComment(CoreMixin, Base):
    __tablename__ = "reviewer_comments"
    assignment_id: Mapped[uuid.UUID] = _fk("control_assignments.id")
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    author_email: Mapped[str | None] = mapped_column(String(320))
    body: Mapped[str] = mapped_column(Text, nullable=False)


class EvidenceSource(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "evidence_sources"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    adapter: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB)
    secret_ciphertext: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    health: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'unknown'"))
    health_detail: Mapped[str | None] = mapped_column(Text)
    schedule_hours: Mapped[int | None] = mapped_column(Integer)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class Evidence(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "evidence"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    source_id: Mapped[uuid.UUID | None] = _fk("evidence_sources.id", True, "SET NULL")
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(500))
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signature_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'unsigned'"))
    integrity_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'unverified'"))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    freshness_window_days: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'unverified'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))      # active | removed (logical)
    removed_reason: Mapped[str | None] = mapped_column(Text)
    removed_by: Mapped[str | None] = mapped_column(String(255))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[str | None] = mapped_column(String(255))
    replacement_reason: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'unreviewed'"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceControl(CoreMixin, Base):
    __tablename__ = "evidence_controls"
    __table_args__ = (UniqueConstraint("evidence_id", "assignment_id", name="uq_evidence_controls"),)
    evidence_id: Mapped[uuid.UUID] = _fk("evidence.id")
    assignment_id: Mapped[uuid.UUID] = _fk("control_assignments.id")
    needs_revalidation: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    revalidation_reason: Mapped[str | None] = mapped_column(Text)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrityCheck(CoreMixin, Base):
    __tablename__ = "integrity_checks"
    evidence_id: Mapped[uuid.UUID] = _fk("evidence.id")
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    actual_sha256: Mapped[str | None] = mapped_column(String(64))
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)


class FreshnessPolicy(CoreMixin, Base):
    __tablename__ = "freshness_policies"
    evidence_type: Mapped[str | None] = mapped_column(String(50))
    source_type: Mapped[str | None] = mapped_column(String(50))
    control_id: Mapped[str | None] = mapped_column(String(50))
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    near_expiration_pct: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("20"))
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class IngestRun(CoreMixin, Base):
    __tablename__ = "ingest_runs"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    source_id: Mapped[uuid.UUID | None] = _fk("evidence_sources.id", True, "SET NULL")
    evidence_id: Mapped[uuid.UUID | None] = _fk("evidence.id", True, "SET NULL")
    duplicate_of_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    file_name: Mapped[str | None] = mapped_column(String(500))
    file_format: Mapped[str | None] = mapped_column(String(30))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'received'"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    mapped: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    unmapped: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    controls_touched: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    stats: Mapped[dict | None] = mapped_column(JSONB)
    errors: Mapped[list | None] = mapped_column(JSONB)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class DedupRule(CoreMixin, Base):
    __tablename__ = "dedup_rules"
    __table_args__ = (UniqueConstraint("source_type", "version", name="uq_dedup_rules"),)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    fields: Mapped[list] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    description: Mapped[str | None] = mapped_column(Text)


class Finding(CoreMixin, Base):
    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("system_id", "dedup_key", name="uq_findings_dedup"),)
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    asset_id: Mapped[uuid.UUID | None] = _fk("assets.id", True, "SET NULL")
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    dedup_rule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    dedup_fields: Mapped[dict | None] = mapped_column(JSONB)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(100))
    vuln_id: Mapped[str | None] = mapped_column(String(100))
    plugin_id: Mapped[str | None] = mapped_column(String(50))
    benchmark: Mapped[str | None] = mapped_column(String(255))
    component: Mapped[str | None] = mapped_column(String(255))
    port: Mapped[str | None] = mapped_column(String(20))
    protocol: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20))
    cat: Mapped[str | None] = mapped_column(String(10))
    cves: Mapped[list | None] = mapped_column(JSONB)
    ccis: Mapped[list | None] = mapped_column(JSONB)
    is_kev: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    current_state: Mapped[str] = mapped_column(String(30), nullable=False)
    mapping_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'unmapped'"))
    disposition: Mapped[str | None] = mapped_column(String(50))
    disposition_justification: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    latest_evidence_id: Mapped[uuid.UUID | None] = _fk("evidence.id", True, "SET NULL")
    remediation_status: Mapped[str | None] = mapped_column(String(30))
    remediated_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    content_flag: Mapped[str | None] = mapped_column(String(50))
    priority_score: Mapped[float | None] = mapped_column(Float)
    priority_breakdown: Mapped[list | None] = mapped_column(JSONB)


class FindingObservation(CoreMixin, Base):
    __tablename__ = "finding_observations"
    finding_id: Mapped[uuid.UUID] = _fk("findings.id")
    ingest_run_id: Mapped[uuid.UUID] = _fk("ingest_runs.id")
    evidence_id: Mapped[uuid.UUID | None] = _fk("evidence.id", True, "SET NULL")
    observed_status: Mapped[str] = mapped_column(String(30), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw: Mapped[dict | None] = mapped_column(JSONB)
    content_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class OrgMappingRule(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "org_mapping_rules"
    __table_args__ = (UniqueConstraint("rule_key", "version", name="uq_org_mapping_rules"),)
    rule_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    match: Mapped[dict] = mapped_column(JSONB, nullable=False)
    control_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    effective_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class FindingControlMap(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "finding_control_map"
    __table_args__ = (Index("uq_finding_control_map_current", "finding_id", "control_id", "cci_id", unique=True,
                            postgresql_where=text("valid_to IS NULL")),)
    finding_id: Mapped[uuid.UUID] = _fk("findings.id")
    control_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    cci_id: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("''"))
    mapping_source: Mapped[str] = mapped_column(String(30), nullable=False)
    content_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    org_rule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    effective_date: Mapped[date | None] = mapped_column(Date)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    justification: Mapped[str | None] = mapped_column(Text)
    mapped_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    stig_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_interaction_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class StigRuleCci(CoreMixin, ProvenanceMixin, Base):
    __tablename__ = "stig_rule_cci_map"
    __table_args__ = (UniqueConstraint("benchmark", "rule_id", "cci_id", "evidence_id", name="uq_stig_rule_cci"),)
    benchmark: Mapped[str] = mapped_column(String(255), nullable=False)
    benchmark_version: Mapped[str | None] = mapped_column(String(100))
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    vuln_id: Mapped[str | None] = mapped_column(String(100))
    cci_id: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_id: Mapped[uuid.UUID] = _fk("evidence.id")
    review_status: Mapped[str] = mapped_column(String(30), nullable=False)


class PriorityWeight(CoreMixin, Base):
    __tablename__ = "priority_weights"
    reason_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class RiskSnapshot(CoreMixin, Base):
    __tablename__ = "risk_snapshots"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    system_id: Mapped[uuid.UUID | None] = _fk("systems.id", True)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(50), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


# ---------------- Phase 2: POA&M, reviews, AI drafts ----------------
class Poam(CoreMixin, Base):
    __tablename__ = "poams"
    __table_args__ = (UniqueConstraint("org_id", "seq", name="uq_poams_org_seq"),)
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    human_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    weakness: Mapped[str] = mapped_column(Text, nullable=False)
    security_impact: Mapped[str | None] = mapped_column(Text)
    control_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20))
    cat: Mapped[str | None] = mapped_column(String(10))
    asset_ids: Mapped[list | None] = mapped_column(JSONB)
    vuln_ids: Mapped[list | None] = mapped_column(JSONB)
    source_label: Mapped[str | None] = mapped_column(String(50))
    detection_evidence_ids: Mapped[list | None] = mapped_column(JSONB)
    root_cause: Mapped[str | None] = mapped_column(Text)
    remediation_plan: Mapped[str | None] = mapped_column(Text)
    resources: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'new'"))
    due_date: Mapped[date | None] = mapped_column(Date)
    actual_completion: Mapped[date | None] = mapped_column(Date)
    risk_acceptance_ref: Mapped[str | None] = mapped_column(String(50))
    risk_acceptance_expiration: Mapped[date | None] = mapped_column(Date)
    closure_evidence_ids: Mapped[list | None] = mapped_column(JSONB)
    emass_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'not_sent'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    emass_remote_id: Mapped[str | None] = mapped_column(String(50))
    content_impact: Mapped[dict | None] = mapped_column(JSONB)
    raw_severity: Mapped[str | None] = mapped_column(String(20))  # eMASS Raw Severity (Very Low–Very High); not the technical severity/CAT
    relevance_of_threat: Mapped[str | None] = mapped_column(String(20))
    likelihood: Mapped[str | None] = mapped_column(String(20))
    impact: Mapped[str | None] = mapped_column(String(20))
    residual_risk_level: Mapped[str | None] = mapped_column(String(20))
    mitigations: Mapped[str | None] = mapped_column(Text)
    comments: Mapped[str | None] = mapped_column(Text)
    risk_source: Mapped[dict | None] = mapped_column(JSONB)


class PoamFinding(CoreMixin, Base):
    __tablename__ = "poam_findings"
    __table_args__ = (UniqueConstraint("poam_id", "finding_id", name="uq_poam_findings"),)
    poam_id: Mapped[uuid.UUID] = _fk("poams.id")
    finding_id: Mapped[uuid.UUID] = _fk("findings.id")
    linked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class PoamMilestone(CoreMixin, Base):
    __tablename__ = "poam_milestones"
    poam_id: Mapped[uuid.UUID] = _fk("poams.id")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'open'"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PoamHistory(CoreMixin, Base):
    __tablename__ = "poam_history"
    poam_id: Mapped[uuid.UUID] = _fk("poams.id")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB)


class PoamMatchRule(CoreMixin, Base):
    __tablename__ = "poam_match_rules"
    __table_args__ = (UniqueConstraint("org_id", "version", name="uq_poam_match_rules"),)
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    fields: Mapped[list] = mapped_column(JSONB, nullable=False)
    across_assets: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class DecisionRule(CoreMixin, Base):
    __tablename__ = "decision_rules"
    __table_args__ = (UniqueConstraint("org_id", "request_type", "version", name="uq_decision_rules"),)
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class ApprovalRequest(CoreMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (UniqueConstraint("org_id", "seq", name="uq_approval_requests_seq"),)
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    human_id: Mapped[str] = mapped_column(String(20), nullable=False)
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    decision_rule_id: Mapped[uuid.UUID] = _fk("decision_rules.id", ondelete="RESTRICT")
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    assigned_role: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'pending'"))
    poam_id: Mapped[uuid.UUID | None] = _fk("poams.id", True)
    finding_id: Mapped[uuid.UUID | None] = _fk("findings.id", True)
    control_id: Mapped[str | None] = mapped_column(String(50))
    implementation_id: Mapped[uuid.UUID | None] = _fk("implementations.id", True)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list | None] = mapped_column(JSONB)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    requester_id: Mapped[uuid.UUID] = _fk("users.id", ondelete="RESTRICT")
    deadline: Mapped[date | None] = mapped_column(Date)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalDecision(CoreMixin, Base):
    __tablename__ = "approval_decisions"
    request_id: Mapped[uuid.UUID] = _fk("approval_requests.id")
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    decider_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    decider_email: Mapped[str] = mapped_column(String(320), nullable=False)
    decision_authority: Mapped[str] = mapped_column(String(160), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    signature: Mapped[str] = mapped_column(String(100), nullable=False)


class CatRule(CoreMixin, Base):
    """Severity → DISA CAT derivation. STIG rows mirror the checklist's own severity (DISA); ACAS rows are an ORG RULE."""
    __tablename__ = "cat_rules"
    __table_args__ = (UniqueConstraint("org_id", "source_type", "version", name="uq_cat_rules"),)
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


# ---------------- Phase 3: inheritance, attestations, assessments, authorization, policy auditor ----------------
class Attestation(CoreMixin, Base):
    __tablename__ = "attestations"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    assignment_id: Mapped[uuid.UUID] = _fk("control_assignments.id")
    control_id: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    evidence_required: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    signature: Mapped[str | None] = mapped_column(String(120))
    expires_at: Mapped[date | None] = mapped_column(Date)
    evidence_id: Mapped[uuid.UUID | None] = _fk("evidence.id", True, "SET NULL")
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class Assessment(CoreMixin, Base):
    __tablename__ = "assessments"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    assignment_id: Mapped[uuid.UUID] = _fk("control_assignments.id")
    control_id: Mapped[str] = mapped_column(String(50), nullable=False)
    assessor_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    objectives: Mapped[list] = mapped_column(JSONB, nullable=False)
    methods: Mapped[list] = mapped_column(JSONB, nullable=False)
    findings_text: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_ids: Mapped[list | None] = mapped_column(JSONB)
    decision_rule_version: Mapped[int | None] = mapped_column(Integer)
    content_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class AuthorizationDecision(CoreMixin, Base):
    __tablename__ = "authorization_decisions"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    request_id: Mapped[uuid.UUID | None] = _fk("approval_requests.id", True, "SET NULL")
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    conditions: Mapped[str | None] = mapped_column(Text)
    expiration: Mapped[date | None] = mapped_column(Date)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decider_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    signature: Mapped[str] = mapped_column(String(120), nullable=False)
    package_snapshot: Mapped[dict | None] = mapped_column(JSONB)


class Policy(CoreMixin, Base):
    __tablename__ = "policies"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    policy_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'current'"))
    owner: Mapped[str | None] = mapped_column(String(255))
    approval_date: Mapped[date | None] = mapped_column(Date)
    review_due: Mapped[date | None] = mapped_column(Date)
    system_ids: Mapped[list | None] = mapped_column(JSONB)
    file_name: Mapped[str | None] = mapped_column(String(255))
    storage_key: Mapped[str | None] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64))
    evidence_ids: Mapped[list | None] = mapped_column(JSONB)
    text_content: Mapped[str | None] = mapped_column(Text)
    analysis_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'not_analyzed'"))
    analysis: Mapped[dict | None] = mapped_column(JSONB)
    metadata_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class PolicyFinding(CoreMixin, Base):
    __tablename__ = "policy_findings"
    policy_id: Mapped[uuid.UUID] = _fk("policies.id")
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    control_id: Mapped[str | None] = mapped_column(String(50))
    parameter: Mapped[str | None] = mapped_column(String(100))
    policy_value: Mapped[str | None] = mapped_column(String(255))
    odp_value: Mapped[str | None] = mapped_column(String(255))
    observed_value: Mapped[str | None] = mapped_column(String(255))
    observed_evidence_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'proposed'"))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    justification: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finding_id: Mapped[uuid.UUID | None] = _fk("findings.id", True, "SET NULL")
    ai_interaction_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class OdpValue(CoreMixin, Base):
    __tablename__ = "odp_values"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    control_id: Mapped[str] = mapped_column(String(50), nullable=False)
    parameter: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    numeric_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[date | None] = mapped_column(Date)


class ObservedConfigValue(CoreMixin, Base):
    __tablename__ = "observed_config_values"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    control_id: Mapped[str] = mapped_column(String(50), nullable=False)
    parameter: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    numeric_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(30))
    evidence_id: Mapped[uuid.UUID | None] = _fk("evidence.id", True, "SET NULL")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)


class NotificationPref(CoreMixin, Base):
    __tablename__ = "notification_prefs"
    __table_args__ = (UniqueConstraint("user_id", "kind", name="uq_notification_prefs"),)
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class AppSetting(CoreMixin, Base):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_app_settings"),)
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)


class StigRule(CoreMixin, Base):
    __tablename__ = "stig_rules"
    __table_args__ = (UniqueConstraint("content_version_id", "vuln_id", name="uq_stig_rules_version_vuln"),)
    content_version_id: Mapped[uuid.UUID] = _fk("catalog_versions.id")
    vuln_id: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    check_text: Mapped[str | None] = mapped_column(Text)
    fix_text: Mapped[str | None] = mapped_column(Text)
    ccis: Mapped[list] = mapped_column(JSONB, nullable=False)


class ContentUpdate(CoreMixin, Base):
    __tablename__ = "content_updates"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content_key: Mapped[str] = mapped_column(String(100), nullable=False)
    from_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    to_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'previewed'"))
    diff_summary: Mapped[dict | None] = mapped_column(JSONB)
    impact: Mapped[dict | None] = mapped_column(JSONB)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    applied_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    justification: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB)


class ScheduledJob(CoreMixin, Base):
    __tablename__ = "scheduled_jobs"
    job_type: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(30))
    last_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_result: Mapped[dict | None] = mapped_column(JSONB)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class EmassRemoteRecord(CoreMixin, Base):
    """MOCK eMASS remote store (synthetic). Real modes never use this table."""
    __tablename__ = "emass_remote_records"
    __table_args__ = (UniqueConstraint("system_id", "entity_type", "remote_id", name="uq_emass_remote"),)
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    remote_id: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    remote_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class EmassChange(CoreMixin, Base):
    __tablename__ = "emass_changes"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_label: Mapped[str | None] = mapped_column(String(255))
    remote_id: Mapped[str | None] = mapped_column(String(50))
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict] = mapped_column(JSONB, nullable=False)
    base_remote_version: Mapped[int | None] = mapped_column(Integer)
    trigger: Mapped[str | None] = mapped_column(String(100))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    approval_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'not_requested'"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'proposed'"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response: Mapped[dict | None] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    history: Mapped[list | None] = mapped_column(JSONB)
    final_status: Mapped[str | None] = mapped_column(String(30))


class EmassSyncRun(CoreMixin, Base):
    __tablename__ = "emass_sync_runs"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    system_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    actor_email: Mapped[str | None] = mapped_column(String(255))


class AuthSession(CoreMixin, Base):
    """Server-side session: idle + absolute expiry, refresh-token rotation (hash only), revocation on logout."""
    __tablename__ = "auth_sessions"
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    refresh_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(50))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    id_token_hint: Mapped[str | None] = mapped_column(Text)


class OidcPending(Base):
    """Single-use OIDC authorization state (PKCE verifier + nonce); survives restarts and works across replicas."""
    __tablename__ = "oidc_pending"
    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class OidcLoginCode(Base):
    """One-time, short-lived code handed to the SPA after the OIDC callback (hash only); exchanged by POST for app tokens."""
    __tablename__ = "oidc_login_codes"
    code_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    id_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class RetentionPolicy(CoreMixin, Base):
    """Retention per record type. The purge job never deletes audit events or evidence under legal hold."""
    __tablename__ = "retention_policies"
    record_type: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    retain_days: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    description: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_result: Mapped[dict | None] = mapped_column(JSONB)


class PolicyControlMap(CoreMixin, Base):
    """Versioned policy→control mapping. Rows are never edited in place: a decision closes the current row (valid_to) and adds one."""
    __tablename__ = "policy_control_maps"
    policy_id: Mapped[uuid.UUID] = _fk("policies.id")
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    control_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)          # proposed | mapped | rejected
    source: Mapped[str] = mapped_column(String(30), nullable=False)          # explicit_id | statement_language | title_language | ai | manual
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)      # High | Medium | Low
    basis: Mapped[str | None] = mapped_column(Text)
    snippets: Mapped[list | None] = mapped_column(JSONB)
    parts: Mapped[list | None] = mapped_column(JSONB)
    justification: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, ondelete="SET NULL")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reanalysis: Mapped[dict | None] = mapped_column(JSONB)          # re-analysis result that differs from an approved decision
    review_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    comments: Mapped[list | None] = mapped_column(JSONB)
    coverage_override: Mapped[dict | None] = mapped_column(JSONB)


class PolicyAiCache(CoreMixin, Base):
    """v2 Policy Auditor AI batch results – strictly per tenant (org_id is part of the unique key and of every lookup)."""
    __tablename__ = "policy_ai_cache"
    __table_args__ = (UniqueConstraint("org_id", "cache_key", name="uq_policy_ai_cache_org_key"),)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    analyzer_version: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str | None] = mapped_column(String(120))
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict | None] = mapped_column(JSONB)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)


class PolicyRequirementCoverage(CoreMixin, Base):
    """How well one policy covers one requirement (DISA CCI or 800-53A objective) of a mapped control: met | partial | missing."""
    __tablename__ = "policy_requirement_coverage"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    policy_id: Mapped[uuid.UUID] = _fk("policies.id")
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    control_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    requirement_type: Mapped[str] = mapped_column(String(12), nullable=False)      # cci | objective
    requirement_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    concept: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)                # met | partial | missing
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    snippets: Mapped[list | None] = mapped_column(JSONB)
    parameter: Mapped[str | None] = mapped_column(String(120))
    parameter_value: Mapped[str | None] = mapped_column(String(255))
    needs: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), nullable=False)               # deterministic | ai
    override: Mapped[dict | None] = mapped_column(JSONB)                          # covered elsewhere: {reason, evidence_id, by, at}
    linked: Mapped[dict | None] = mapped_column(JSONB)                            # linked as evidence on approval: {assignment_id, by, at}
    history: Mapped[list | None] = mapped_column(JSONB)                           # prior results kept when a stored row is relabelled


class TrTemplate(CoreMixin, Base):
    """Reusable eMASS Test Result template definition (sheet, header row, column roles, value vocabulary) per org, versioned."""
    __tablename__ = "tr_templates"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255))


class TrWorkbook(CoreMixin, Base):
    __tablename__ = "tr_workbooks"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    template_id: Mapped[uuid.UUID | None] = _fk("tr_templates.id", True, "SET NULL")
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)      # queued | processing | mapped | generating | generated | failed
    error: Mapped[str | None] = mapped_column(Text)
    detection: Mapped[dict | None] = mapped_column(JSONB)
    definition: Mapped[dict | None] = mapped_column(JSONB)
    counts: Mapped[dict | None] = mapped_column(JSONB)
    uploaded_by: Mapped[str | None] = mapped_column(String(255))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrRow(CoreMixin, Base):
    __tablename__ = "tr_rows"
    __table_args__ = (UniqueConstraint("workbook_id", "row_number", name="uq_tr_rows_wb_row"),)
    workbook_id: Mapped[uuid.UUID] = _fk("tr_workbooks.id")
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    added: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    control_acronym: Mapped[str | None] = mapped_column(String(50))
    ap_acronym: Mapped[str | None] = mapped_column(String(50))
    cci_id: Mapped[str | None] = mapped_column(String(20))
    control_id: Mapped[str | None] = mapped_column(String(50), index=True)
    match_status: Mapped[str] = mapped_column(String(20), nullable=False)   # matched | ambiguous | unmatched | resolved
    match_reason: Mapped[str | None] = mapped_column(Text)
    proposed: Mapped[dict | None] = mapped_column(JSONB)
    sources: Mapped[list | None] = mapped_column(JSONB)
    flags: Mapped[list | None] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'missing'"))  # auto | edited | approved | missing | conflict
    prepared_by: Mapped[dict | None] = mapped_column(JSONB)   # last editor/preparer (real user + persona) – SoD for approval
    final: Mapped[dict | None] = mapped_column(JSONB)
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    justification: Mapped[str | None] = mapped_column(Text)
    last_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrExport(CoreMixin, Base):
    __tablename__ = "tr_exports"
    workbook_id: Mapped[uuid.UUID] = _fk("tr_workbooks.id")
    system_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    exported_by: Mapped[str] = mapped_column(String(255), nullable=False)
    counts: Mapped[dict | None] = mapped_column(JSONB)
    evidence_ids: Mapped[list | None] = mapped_column(JSONB)
    verification: Mapped[dict | None] = mapped_column(JSONB)
    template_version: Mapped[int | None] = mapped_column(Integer)


class TrAnalysis(CoreMixin, Base):
    __tablename__ = "tr_analyses"
    row_id: Mapped[uuid.UUID] = _fk("tr_rows.id")
    workbook_id: Mapped[uuid.UUID] = _fk("tr_workbooks.id")
    mode: Mapped[str] = mapped_column(String(20), nullable=False)            # ai | deterministic
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    input_bundle: Mapped[list] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dropped: Mapped[list | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class AssetIdentifier(CoreMixin, Base):
    __tablename__ = "asset_identifiers"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    asset_id: Mapped[uuid.UUID] = _fk("assets.id")
    kind: Mapped[str] = mapped_column(String(20), nullable=False)          # hostname | fqdn | ip | mac | serial | os | cpe | benchmark
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(100))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InventoryImport(CoreMixin, Base):
    __tablename__ = "inventory_imports"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    detection: Mapped[dict | None] = mapped_column(JSONB)
    counts: Mapped[dict | None] = mapped_column(JSONB)
    uploaded_by: Mapped[str | None] = mapped_column(String(255))


class SoftwareItem(CoreMixin, Base):
    __tablename__ = "software_items"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    asset_id: Mapped[uuid.UUID | None] = _fk("assets.id", True, "SET NULL")
    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[str | None] = mapped_column(String(255))
    sw_type: Mapped[str | None] = mapped_column(String(100))
    attributes: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    import_id: Mapped[uuid.UUID | None] = _fk("inventory_imports.id", True, "SET NULL")


class InventoryExport(CoreMixin, Base):
    __tablename__ = "inventory_exports"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    import_id: Mapped[uuid.UUID | None] = _fk("inventory_imports.id", True, "SET NULL")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    exported_by: Mapped[str] = mapped_column(String(255), nullable=False)
    counts: Mapped[dict | None] = mapped_column(JSONB)
    verification: Mapped[dict | None] = mapped_column(JSONB)


class InventoryDiscrepancy(CoreMixin, Base):
    __tablename__ = "inventory_discrepancies"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)       # open | pending_approval | applied | ignored | resolved
    title: Mapped[str] = mapped_column(Text, nullable=False)
    records: Mapped[list] = mapped_column(JSONB, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB)
    recommendation: Mapped[str | None] = mapped_column(Text)
    proposed_change: Mapped[dict | None] = mapped_column(JSONB)
    ai: Mapped[dict | None] = mapped_column(JSONB)
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    applied_by: Mapped[str | None] = mapped_column(String(255))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)     # real person (persona operator) – SoD for approval
    accepted_identity: Mapped[dict | None] = mapped_column(JSONB)            # real user + persona who accepted
    sod: Mapped[dict | None] = mapped_column(JSONB)                          # SoD outcome at approval (e.g. "Sandbox: same person")


class AssetCorrelation(CoreMixin, Base):
    __tablename__ = "asset_correlations"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    facts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    candidates: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)       # matched | new | needs_review | confirmed | rejected
    method: Mapped[str | None] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(Text)
    observed_asset_id: Mapped[uuid.UUID | None] = _fk("assets.id", True)
    chosen_asset_id: Mapped[uuid.UUID | None] = _fk("assets.id", True, "SET NULL")
    source_format: Mapped[str | None] = mapped_column(String(30))
    evidence_ids: Mapped[list | None] = mapped_column(JSONB)
    ai: Mapped[dict | None] = mapped_column(JSONB)
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    justification: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CategorizationRecord(CoreMixin, Base):
    """One revision of a system's security categorization (framework, types, per-objective impacts, rationale, approval)."""
    __tablename__ = "categorization_records"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    framework: Mapped[str] = mapped_column(String(20), nullable=False)
    nss_determination: Mapped[str | None] = mapped_column(String(10))
    information_types: Mapped[list | None] = mapped_column(JSONB)
    impacts: Mapped[dict | None] = mapped_column(JSONB)
    overall: Mapped[str | None] = mapped_column(String(20))
    baseline: Mapped[str | None] = mapped_column(String(20))
    detail: Mapped[dict | None] = mapped_column(JSONB)
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    inputs_hash: Mapped[str | None] = mapped_column(String(64))
    submitted_by: Mapped[str | None] = mapped_column(String(255))
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_by_real: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_rationale: Mapped[str | None] = mapped_column(Text)


class PtaQuestionSet(CoreMixin, Base):
    __tablename__ = "pta_question_sets"
    org_id: Mapped[uuid.UUID | None] = _fk("organizations.id", True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    questions: Mapped[list] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[str | None] = mapped_column(String(255))


class PtaResponse(CoreMixin, Base):
    __tablename__ = "pta_responses"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    question_set_id: Mapped[uuid.UUID | None] = _fk("pta_question_sets.id", True, "SET NULL")
    question_set_key: Mapped[str | None] = mapped_column(String(100))
    question_set_version: Mapped[int | None] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    flags: Mapped[list | None] = mapped_column(JSONB)
    recommendation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String(255))
    reviewer: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_rationale: Mapped[str | None] = mapped_column(Text)
    determination: Mapped[str | None] = mapped_column(String(40))


class AgencyOverlay(CoreMixin, Base):
    __tablename__ = "agency_overlays"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuing_authority: Mapped[str] = mapped_column(String(255), nullable=False)
    source_document: Mapped[str] = mapped_column(String(500), nullable=False)
    framework: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    applicability: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[str | None] = mapped_column(String(255))


class EvidenceVersion(CoreMixin, Base):
    """Immutable file version of an evidence record (the object and its SHA-256 are never overwritten)."""
    __tablename__ = "evidence_versions"
    evidence_id: Mapped[uuid.UUID] = _fk("evidence.id")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(500))
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    uploaded_by: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    scan_result: Mapped[str | None] = mapped_column(String(50))


class EmassControlFields(CoreMixin, Base):
    """eMASS Implementation Plan + Risk Assessment values for one system control. Status itself lives on ControlAssignment
    (implementation_status); manually_inherited distinguishes eMASS "Manually Inherited" from "Inherited"."""
    __tablename__ = "emass_control_fields"
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("control_assignments.id", ondelete="CASCADE"), nullable=False, unique=True)
    control_id: Mapped[str] = mapped_column(String(50), nullable=False)
    manually_inherited: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    control_designation: Mapped[str | None] = mapped_column(String(30))
    estimated_completion_date: Mapped[date | None] = mapped_column(Date)
    responsible_entities: Mapped[str | None] = mapped_column(Text)
    slcm_criticality: Mapped[str | None] = mapped_column(Text)
    slcm_frequency: Mapped[str | None] = mapped_column(String(30))
    slcm_method: Mapped[str | None] = mapped_column(String(30))
    slcm_reporting: Mapped[str | None] = mapped_column(Text)
    slcm_tracking: Mapped[str | None] = mapped_column(Text)
    slcm_comments: Mapped[str | None] = mapped_column(Text)
    na_justification: Mapped[str | None] = mapped_column(Text)
    common_control_provider: Mapped[str | None] = mapped_column(String(20))
    severity: Mapped[str | None] = mapped_column(String(20))
    relevance_of_threat: Mapped[str | None] = mapped_column(String(20))
    likelihood: Mapped[str | None] = mapped_column(String(20))
    impact: Mapped[str | None] = mapped_column(String(20))
    impact_description: Mapped[str | None] = mapped_column(Text)
    residual_risk_level: Mapped[str | None] = mapped_column(String(20))
    vulnerability_summary: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[str | None] = mapped_column(Text)
    mitigations: Mapped[str | None] = mapped_column(Text)
    assisted: Mapped[dict | None] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    slcm_inherit: Mapped[dict | None] = mapped_column(JSONB)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class EmassImport(CoreMixin, Base):
    """eMASS Control Information import session: parsed proposals + per-field decisions; nothing is applied until apply()."""
    __tablename__ = "emass_imports"
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    system_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("systems.id", ondelete="CASCADE"), index=True)
    report_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="control_information")
    detected: Mapped[dict | None] = mapped_column(JSONB)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="review")
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    uploaded_by_email: Mapped[str | None] = mapped_column(String(320))
    detection: Mapped[dict | None] = mapped_column(JSONB)
    report: Mapped[dict | None] = mapped_column(JSONB)
    items: Mapped[list | None] = mapped_column(JSONB)
    counts: Mapped[dict | None] = mapped_column(JSONB)
    applied_by_email: Mapped[str | None] = mapped_column(String(320))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PpsmEntry(CoreMixin, Base):
    """One PPSM boundary row (port / protocol / data service / boundaries) of a system."""
    __tablename__ = "ppsm_entries"
    __table_args__ = (UniqueConstraint("system_id", "record_key", name="uq_ppsm_entries_system_key"),)
    system_id: Mapped[uuid.UUID] = _fk("systems.id")
    record_key: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(String(50))
    port: Mapped[str] = mapped_column(String(20), nullable=False)
    protocol: Mapped[str] = mapped_column(String(20), nullable=False)
    data_service: Mapped[str] = mapped_column(String(100), nullable=False)
    boundaries: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    fqdn: Mapped[str | None] = mapped_column(String(100))
    purpose: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), nullable=False, server_default="manual")
    import_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    source_row: Mapped[int | None] = mapped_column(Integer)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class IscmStrategy(CoreMixin, Base):
    """Continuous Monitoring Strategy (SP 800-37 Task S-5) – one per system; its approved snapshot feeds the eMASS SLCM fields."""
    __tablename__ = "iscm_strategies"
    system_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    narrative: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    defaults: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    reporting: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    review_activities: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    evidence_requirements: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    approved_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    submitted_by: Mapped[dict | None] = mapped_column(JSONB)
    approved_by: Mapped[dict | None] = mapped_column(JSONB)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class IscmProfile(CoreMixin, Base):
    __tablename__ = "iscm_profiles"
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iscm_strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)  # family | control_list | designation
    match_value: Mapped[str] = mapped_column(String(2000), nullable=False)
    values: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
