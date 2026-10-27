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
}

// RMF steps (NIST SP 800-37 Rev 2) + Start and Tools. `step` = key returned by /systems/{id}/rmf-steps.
export const NAV_GROUPS: { key: string; label: string; step?: string; help: string }[] = [
  { key: "start", label: "Start", help: "Getting started, your systems and the portfolio view." },
  { key: "prepare", label: "1 · Prepare", step: "prepare", help: "Name the people responsible for the system (owner, ISSO, ISSM, AO, SCA…)." },
  { key: "categorize", label: "2 · Categorize", step: "categorize", help: "Pick SP 800-60 information types; the app derives the FIPS 199 impact level." },
  { key: "select", label: "3 · Select", step: "select", help: "Baseline, overlays and tailoring decide which controls apply." },
  { key: "implement", label: "4 · Implement", step: "implement", help: "Write implementation statements, set inheritance and collect evidence." },
  { key: "assess", label: "5 · Assess", step: "assess", help: "The SCA tests the controls; review automated mappings." },
  { key: "authorize", label: "6 · Authorize", step: "authorize", help: "Assemble the package; the AO records ATO / IATT / DATO." },
  { key: "monitor", label: "7 · Monitor", step: "monitor", help: "Keep evidence current, watch findings and POA&Ms." },
  { key: "tools", label: "Tools", help: "Cross-step tools: traceability, audit log, administration." },
];

// phase: null = available now. Numbers are the tentative delivery phase.
export const NAV_ITEMS: NavItem[] = [
  { id: "rmf-workflow", group: "start", label: "Getting started (RMF overview)", path: "/rmf-workflow", icon: Workflow, phase: null, summary: "Prepare → Categorize → Select → Implement → Assess → Authorize → Monitor workflow." },
  { id: "systems", group: "start", label: "Systems", path: "/systems", icon: Server, phase: null, summary: "System registration, categorization (FIPS 199 / SP 800-60) and baseline selection." },
  { id: "import-center", group: "start", label: "Import Center", path: "/import-center", icon: Upload, phase: null, perm: "system.read", summary: "One place for every system data import: policies, STIG/SCAP, Nessus/ACAS, eMASS workbooks, Test Results, HW/SW." },
  { id: "portfolio", group: "start", label: "Portfolio / Leadership", path: "/portfolio", icon: LayoutDashboard, phase: null, perm: "portfolio.read", summary: "Cross-system risk posture, ATO expirations and trend reporting for leadership." },
  { id: "rmf-prepare", group: "prepare", label: "Key roles", path: "/rmf/prepare", icon: Users, phase: null, summary: "" },
  { id: "rmf-categorize", group: "categorize", label: "Categorization", path: "/rmf/categorize", icon: Layers, phase: null, summary: "" },
  { id: "rmf-select", group: "select", label: "Baseline, overlays & tailoring", path: "/rmf/select", icon: ListChecks, phase: null, summary: "" },
  { id: "catalog", group: "select", label: "Control catalog", path: "/catalog", icon: BookOpen, phase: null, summary: "" },
  { id: "rmf-implement", group: "implement", label: "Implementation progress", path: "/rmf/implement", icon: Gauge, phase: null, summary: "" },
  { id: "controls", group: "implement", label: "Control Workbench", path: "/controls", icon: ShieldCheck, phase: null, summary: "" },
  { id: "inheritance", group: "implement", label: "Inheritance", path: "/inheritance", icon: GitFork, phase: null, summary: "Common and hybrid control inheritance from providers and enclaves." },
  { id: "inventory", group: "implement", label: "HW/SW Inventory", path: "/inventory", icon: Database, phase: null, perm: "system.read", summary: "eMASS hardware/software list, scan-to-asset correlation and consistency checks." },
  { id: "ccis", group: "implement", label: "CCI view", path: "/ccis", icon: ListChecks, phase: null, summary: "DISA CCIs of the system's controls with policy coverage." },
  { id: "policy-auditor", group: "implement", label: "Policy Auditor", path: "/policy-auditor", icon: FileCheck, phase: null, summary: "AI-assisted review of policies and procedures against control requirements." },
  { id: "evidence-sources", group: "implement", label: "Evidence Sources", path: "/evidence-sources", icon: Database, phase: null, summary: "Connectors for scanners, cloud configuration and ticketing systems that feed evidence." },
  { id: "rmf-assess", group: "assess", label: "Assessment progress", path: "/rmf/assess", icon: Gauge, phase: null, summary: "" },
  { id: "reviews", group: "assess", label: "Reviews", path: "/reviews", icon: ClipboardCheck, phase: null, summary: "All review request types, SCA assessments and authorization decisions." },
  { id: "test-results", group: "assess", label: "Templates → Test Results", path: "/test-results", icon: FileCheck, phase: null, perm: "system.read", summary: "Import the eMASS Test Result template, generate proposals, SCA approval and export." },
  { id: "mapping-review", group: "assess", label: "Mapping Review", path: "/mapping-review", icon: FileCode, phase: null, perm: "system.read", summary: "" },
  { id: "rmf-authorize", group: "authorize", label: "Authorization package", path: "/rmf/authorize", icon: Stamp, phase: null, summary: "" },
  { id: "poam", group: "authorize", label: "POA&M", path: "/poams", icon: ListOrdered, phase: null, summary: "Plan of Action & Milestones tracking with weaknesses, milestones and risk." },
  { id: "emass", group: "authorize", label: "eMASS Sync", path: "/emass", icon: FileCode, phase: null, summary: "" },
  { id: "rmf-monitor", group: "monitor", label: "Continuous monitoring", path: "/rmf/monitor", icon: Activity, phase: null, summary: "" },
  { id: "evidence-ledger", group: "monitor", label: "Evidence Ledger", path: "/evidence-ledger", icon: FileCode, phase: null, summary: "Tamper-evident, hash-chained ledger of evidence artifacts." },
  { id: "traceability", group: "tools", label: "Traceability matrix", path: "/traceability", icon: Network, phase: null, summary: "" },
  { id: "help", group: "tools", label: "Help: who can do what", path: "/help", icon: HelpCircle, phase: null, summary: "" },
  { id: "audit-log", group: "tools", label: "Audit Log", path: "/audit-log", icon: FileCode, phase: null, perm: "audit.read", summary: "" },
  { id: "admin", group: "tools", label: "Admin", path: "/admin", icon: Settings, phase: null, summary: "" },
];

// Deep-link routes → owning nav item (first match wins).
const ROUTE_OWNERS: [RegExp, string][] = [
  [/^\/systems\/[^/]+\/controls/, "controls"], [/^\/findings\//, "controls"],
  [/^\/systems\/[^/]+\/authorization/, "rmf-authorize"], [/^\/docs-center/, "admin"], [/^\/ingest-runs\//, "evidence-sources"], [/^\/poams?(\/|$)/, "poam"],
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
