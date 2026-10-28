import {
  Activity, BookOpen, ClipboardCheck, Database, FileCheck, FileCode, Gauge, GitFork, HelpCircle, LayoutDashboard, Layers, ListChecks, ListOrdered, LucideIcon,
  Network, Server, Settings, ShieldCheck, Stamp, Upload, Users, Workflow,
} from "lucide-react";

export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: LucideIcon;
  phase: number | null;
  summary: string;
  perm?: string;
  group: string;
  sub?: boolean;
}

// RMF steps (NIST SP 800-37 Rev 2) + Start and Tools. `step` = key returned by /systems/{id}/rmf-steps.
export const NAV_GROUPS: { key: string; label: string; step?: string; path?: string; help: string }[] = [
  { key: "start", label: "Work", help: "Your work, your systems, imports, help and administration." },
  { key: "system", label: "System", help: "The selected system's RMF dashboard." },
  { key: "prepare", label: "1 · Prepare", step: "prepare", path: "/rmf/prepare", help: "Name the people responsible for the system and describe its boundary and inventory." },
  { key: "categorize", label: "2 · Categorize", step: "categorize", path: "/rmf/categorize", help: "Pick SP 800-60 information types; the app derives the FIPS 199 impact level." },
  { key: "select", label: "3 · Select", step: "select", path: "/rmf/select", help: "Baseline, overlays, tailoring and the continuous monitoring strategy." },
  { key: "implement", label: "4 · Implement", step: "implement", path: "/rmf/implement", help: "Write implementation statements, set inheritance, map policies and collect evidence." },
  { key: "assess", label: "5 · Assess", step: "assess", path: "/rmf/assess", help: "The SCA tests the controls; test results, findings and mapping review." },
  { key: "authorize", label: "6 · Authorize", step: "authorize", path: "/rmf/authorize", help: "Assemble the package and POA&M; the AO records ATO / IATT / DATO." },
  { key: "monitor", label: "7 · Monitor", step: "monitor", path: "/rmf/monitor", help: "Keep evidence current, follow the monitoring schedule, sync with eMASS." },
];
// phase: null = available now. Ids are stable (data-testid nav-<id>); sub-items of a step are shown when that step is open.
export const NAV_ITEMS: NavItem[] = [
  { id: "my-work", group: "start", label: "My Work", path: "/my-work", icon: ClipboardCheck, phase: null, summary: "What needs you next, across your systems." },
  { id: "systems", group: "start", label: "Systems", path: "/systems", icon: Server, phase: null, summary: "System registration and the system list." },
  { id: "import-center", group: "start", label: "Import Center", path: "/import-center", icon: Upload, phase: null, perm: "system.read", summary: "One place for every import: policies, STIG/SCAP, Nessus/ACAS, eMASS workbooks." },
  { id: "portfolio", group: "start", label: "Portfolio", path: "/portfolio", icon: LayoutDashboard, phase: null, perm: "portfolio.read", summary: "Cross-system risk posture and ATO expirations." },
  { id: "help", group: "start", label: "Help", path: "/help", icon: HelpCircle, phase: null, summary: "Who can do what, the RMF overview and the documentation." },
  { id: "rmf-workflow", group: "start", label: "RMF overview", path: "/rmf-workflow", icon: Workflow, phase: null, summary: "", sub: true },
  { id: "audit-log", group: "start", label: "Audit Log", path: "/audit-log", icon: FileCode, phase: null, perm: "audit.read", summary: "", sub: true },
  { id: "admin", group: "start", label: "Admin", path: "/admin", icon: Settings, phase: null, summary: "" },
  { id: "dashboard", group: "system", label: "System dashboard", path: "/dashboard", icon: Gauge, phase: null, summary: "Status of every RMF step, pending approvals and the next action." },
  { id: "rmf-prepare", group: "prepare", label: "Roles & people", path: "/rmf/prepare", icon: Users, phase: null, summary: "" },
  { id: "inventory", group: "prepare", label: "HW/SW inventory", path: "/inventory", icon: Database, phase: null, perm: "system.read", summary: "eMASS hardware/software list and scan-to-asset correlation." },
  { id: "rmf-categorize", group: "categorize", label: "Information types & impact", path: "/rmf/categorize", icon: Layers, phase: null, summary: "" },
  { id: "rmf-select", group: "select", label: "Baseline, tailoring & monitoring strategy", path: "/rmf/select", icon: ListChecks, phase: null, summary: "" },
  { id: "catalog", group: "select", label: "Control catalog (reference)", path: "/catalog", icon: BookOpen, phase: null, summary: "" },
  { id: "rmf-implement", group: "implement", label: "Implementation overview", path: "/rmf/implement", icon: Gauge, phase: null, summary: "" },
  { id: "controls", group: "implement", label: "Control Workbench", path: "/controls", icon: ShieldCheck, phase: null, summary: "" },
  { id: "policy-auditor", group: "implement", label: "Policies", path: "/policy-auditor", icon: FileCheck, phase: null, summary: "AI-assisted policy review against control requirements; suggestions go to Mapping review." },
  { id: "evidence-sources", group: "implement", label: "Evidence – add & sources", path: "/evidence-sources", icon: Database, phase: null, summary: "Upload evidence or connect scanners, cloud and ticketing systems." },
  { id: "inheritance", group: "implement", label: "Inheritance", path: "/inheritance", icon: GitFork, phase: null, summary: "Common and hybrid control inheritance." },
  { id: "ccis", group: "implement", label: "CCIs", path: "/ccis", icon: ListChecks, phase: null, summary: "DISA CCIs of the system's controls with policy coverage." },
  { id: "rmf-assess", group: "assess", label: "Assessment overview", path: "/rmf/assess", icon: Gauge, phase: null, summary: "" },
  { id: "sca-workspace", group: "assess", label: "SCA workspace", path: "/assess/workspace", icon: ClipboardCheck, phase: null, summary: "One queue: evidence, implementation and imported test results; record the determination." },
  { id: "test-results", group: "assess", label: "Test results", path: "/test-results", icon: FileCheck, phase: null, perm: "system.read", summary: "eMASS Test Result workbooks: proposals for SCA approval." },
  { id: "mapping-review", group: "assess", label: "Mapping review", path: "/mapping-review", icon: FileCode, phase: null, perm: "system.read", summary: "" },
  { id: "reviews", group: "assess", label: "Reviews & approvals", path: "/reviews", icon: ClipboardCheck, phase: null, summary: "Review requests, SCA assessments and authorization decisions." },
  { id: "rmf-authorize", group: "authorize", label: "Package & documents", path: "/rmf/authorize", icon: Stamp, phase: null, summary: "" },
  { id: "poam", group: "authorize", label: "POA&M", path: "/poams", icon: ListOrdered, phase: null, summary: "Plan of Action & Milestones with weaknesses, milestones and risk." },
  { id: "rmf-monitor", group: "monitor", label: "Monitoring & schedules", path: "/rmf/monitor", icon: Activity, phase: null, summary: "" },
  { id: "evidence-ledger", group: "monitor", label: "Evidence & freshness", path: "/evidence-ledger", icon: FileCode, phase: null, summary: "Every evidence artifact with its hash chain and freshness." },
  { id: "emass", group: "monitor", label: "eMASS sync", path: "/emass", icon: FileCode, phase: null, summary: "" },
  { id: "traceability", group: "monitor", label: "Traceability matrix", path: "/traceability", icon: Network, phase: null, summary: "" },
];
// Deep-link routes → owning nav item (first match wins).
const ROUTE_OWNERS: [RegExp, string][] = [
  [/^\/systems\/[^/]+\/controls/, "controls"], [/^\/findings\//, "controls"],
  [/^\/systems\/[^/]+\/authorization/, "rmf-authorize"], [/^\/docs-center/, "help"], [/^\/systems\/[^/]+\/emass-import/, "import-center"], [/^\/emass-import/, "import-center"], [/^\/systems\/[^/]+\/migration-report/, "import-center"], [/^\/systems\/new/, "systems"], [/^\/settings\//, "admin"], [/^\/ingest-runs\//, "evidence-sources"], [/^\/poams?(\/|$)/, "poam"],
  [/^\/policy-auditor\//, "policy-auditor"], [/^\/reviews\//, "reviews"], [/^\/systems\/[^/]+\/import-center/, "import-center"],
];

export function activeNavId(pathname: string): string | undefined {
  const owner = ROUTE_OWNERS.find(([re]) => re.test(pathname));
  if (owner) return owner[1];
  return NAV_ITEMS.find((n) => pathname === n.path || pathname.startsWith(`${n.path}/`))?.id;
}

export const ROLE_LABELS: Record<string, string> = {
  system_owner: "System Owner",
  isso: "ISSO",
  issm: "ISSM",
  sca: "SCA",
  ao: "AO",
  devsecops: "DevSecOps",
  leadership_viewer: "Leadership",
  privacy_official: "Privacy Official",
  platform_admin: "Platform Admin",
};
