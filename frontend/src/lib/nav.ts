import {
  ClipboardCheck, Database, FileCheck, FileCode, GitFork, LayoutDashboard, ListOrdered, LucideIcon, Server,
  Settings, ShieldCheck, Workflow,
} from "lucide-react";

export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: LucideIcon;
  phase: number | null;
  summary: string;
}

// phase: null = available now. Numbers are the tentative delivery phase.
export const NAV_ITEMS: NavItem[] = [
  { id: "portfolio", label: "Portfolio / Leadership", path: "/portfolio", icon: LayoutDashboard, phase: null, summary: "Cross-system risk posture, ATO expirations and trend reporting for leadership." },
  { id: "systems", label: "Systems", path: "/systems", icon: Server, phase: null, summary: "System registration, categorization (FIPS 199 / SP 800-60) and baseline selection." },
  { id: "evidence-sources", label: "Evidence Sources", path: "/evidence-sources", icon: Database, phase: null, summary: "Connectors for scanners, cloud configuration and ticketing systems that feed evidence." },
  { id: "controls", label: "Controls", path: "/controls", icon: ShieldCheck, phase: null, summary: "" },
  { id: "inheritance", label: "Inheritance", path: "/inheritance", icon: GitFork, phase: null, summary: "Common and hybrid control inheritance from providers and enclaves." },
  { id: "policy-auditor", label: "Policy Auditor", path: "/policy-auditor", icon: FileCheck, phase: null, summary: "AI-assisted review of policies and procedures against control requirements." },
  { id: "poam", label: "POA&M", path: "/poams", icon: ListOrdered, phase: null, summary: "Plan of Action & Milestones tracking with weaknesses, milestones and risk." },
  { id: "reviews", label: "Reviews", path: "/reviews", icon: ClipboardCheck, phase: null, summary: "All review request types, SCA assessments and authorization decisions." },
  { id: "evidence-ledger", label: "Evidence Ledger", path: "/evidence-ledger", icon: FileCode, phase: null, summary: "Tamper-evident, hash-chained ledger of evidence artifacts." },
  { id: "emass", label: "eMASS Sync", path: "/emass", icon: FileCode, phase: null, summary: "" },
  { id: "mapping-review", label: "Mapping Review", path: "/mapping-review", icon: FileCode, phase: null, summary: "" },
  { id: "audit-log", label: "Audit Log", path: "/audit-log", icon: FileCode, phase: null, summary: "" },
  { id: "admin", label: "Admin", path: "/admin", icon: Settings, phase: null, summary: "" },
  { id: "rmf-workflow", label: "RMF Workflow", path: "/rmf-workflow", icon: Workflow, phase: null, summary: "Prepare → Categorize → Select → Implement → Assess → Authorize → Monitor workflow." },
];

// Deep-link routes → owning nav item (first match wins).
const ROUTE_OWNERS: [RegExp, string][] = [
  [/^\/systems\/[^/]+\/controls/, "controls"], [/^\/catalog/, "controls"], [/^\/findings\//, "controls"],
  [/^\/systems\/[^/]+\/authorization/, "rmf-workflow"], [/^\/ingest-runs\//, "evidence-sources"], [/^\/poams?(\/|$)/, "poam"],
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
  platform_admin: "Platform Admin",
};
