export interface RoleAssignment {
  role: string;
  scope_type: "org" | "system";
  scope_id: string;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  title: string | null;
  org_id: string;
  org_name: string;
  roles: RoleAssignment[];
  permissions: string[];
  auth_provider: string;
  auth_is_simulated: boolean;
  persona_role?: string | null;
  is_sandbox?: boolean;
}

export interface DevAccount {
  email: string;
  display_name: string;
  role: string;
  role_label: string;
}

export interface AuthProviderInfo {
  provider: string;
  label: string;
  is_simulated: boolean;
  dev_accounts: DevAccount[];
  enabled_providers: string[];
  dev_password_enabled: boolean;
  signup_enabled?: boolean;
  demo_login_enabled?: boolean;
  registration_enabled?: boolean;
  oidc_enabled: boolean;
}

export interface ControlSummary {
  control_id: string;
  label: string | null;
  title: string;
  family_id: string;
  family_title: string;
  is_enhancement: boolean;
  is_withdrawn: boolean;
  parent_control_id: string | null;
  sort_id: string | null;
  baselines: string[];
}

export interface ControlList {
  total: number;
  limit: number;
  offset: number;
  catalog_version_id: string | null;
  items: ControlSummary[];
}

export interface Family {
  family_id: string;
  family_title: string;
  count: number;
}

export interface OscalParam {
  id: string;
  label?: string;
  rendered?: string;
  props?: { name: string; value: string }[];
}

export interface ControlDetail extends ControlSummary {
  statement: string | null;
  parameters: OscalParam[] | null;
  guidance: string | null;
  assessment_methods: { method: string | null; objects: string[] }[] | null;
  objectives: { objective_id: string; parent_objective_id: string | null; label: string | null; prose: string | null; depth: number }[];
  ccis: { cci_id: string; definition: string; reference_index: string; statement_part: string | null; review_status: string; version: string; effective_date: string | null; source: string | null }[];
  enhancements: { control_id: string; label: string | null; title: string; is_withdrawn: boolean }[];
  source: string | null;
  provenance: Record<string, unknown> | null;
}

export interface ContentVersion {
  id: string;
  content_type: string;
  content_key: string;
  title: string;
  version: string | null;
  release_tag: string | null;
  commit_sha: string | null;
  source_url: string;
  sha256: string;
  file_name: string;
  storage_key: string | null;
  effective_date: string | null;
  loaded_at: string | null;
  status: string;
  is_active: boolean;
  item_count: number | null;
  meta: Record<string, unknown> | null;
}

export interface ContentStats {
  loaded: boolean;
  controls_total?: number;
  base_controls?: number;
  enhancements?: number;
  withdrawn?: number;
  assessment_objectives?: number;
  baselines?: Record<string, number>;
  ccis?: number;
  cci_rev5_mappings?: number;
  cci_rev5_mappings_resolved?: number;
}

export interface HealthComponent {
  ok: boolean;
  detail: Record<string, unknown>;
}

export interface Health {
  status: string;
  version: string;
  components: Record<string, HealthComponent>;
}

export interface AuditEvent {
  seq: number;
  occurred_at: string;
  actor_email: string | null;
  actor_name?: string | null;
  actor_roles?: string[];
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  outcome: string;
  correlation_id: string | null;
  ip: string | null;
  details: Record<string, unknown> | null;
  hash: string;
  prev_hash: string;
}

export interface Job {
  id: string;
  job_type: string;
  status: string;
  attempts: number;
  payload: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface SystemRecord {
  id: string;
  name: string;
  acronym: string | null;
  baseline_key: string | null;
  lifecycle_status: string;
  is_synthetic: boolean;
}

export interface RbacMatrix {
  roles: Record<string, string>;
  permissions: Record<string, string>;
  matrix: Record<string, string[]>;
}
