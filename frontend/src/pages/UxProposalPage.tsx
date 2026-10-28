import { Download } from "lucide-react";
import { BrandLockup } from "@/components/shell/Brand";
import { SyntheticBanner } from "@/components/shell/SyntheticBanner";

const P = "/ux-proposal-assets";
const LABEL = "PROPOSAL – NON-FUNCTIONAL MOCKUPS";
const MOCKUPS: [string, string][] = [
  ["dashboard", "System RMF dashboard: 7 step cards, “Continue where you left off”, readiness, pending approvals"],
  ["navigation", "New navigation: 5 global items + 7 RMF steps inside the system context"],
  ["mywork_isso", "My Work – ISSO: statements, suggestions, stale evidence; no approve actions (SoD)"],
  ["mywork_sca", "My Work – SCA: assessment requests and retests only (SCA independence)"],
  ["mywork_issm", "My Work – ISSM: strategy/package approvals, returned items, ATO expiry"],
  ["mywork_ao", "My Work – AO: decisions only, package opens read-only"],
  ["workbench", "Control Workbench 2-pane: catalog tree + 4 filters | 6 control tabs, advanced fields collapsed"],
  ["import_center", "Import Center: Upload → Preview → Import → Completed, with destinations and next action"],
  ["mapping_review", "Mapping Review simplified: 3 tabs, reason inline, approve/correct/reject on the row"],
  ["assessment", "Assessment workspace: select control → review evidence → record determination → save & next"],
  ["ssp", "Generate SSP: generate → review validation (each issue links to its field) → download"],
  ["guided_on", "Guided Mode ON: purpose, needed information, who, what's next"],
  ["guided_off", "Guided Mode OFF: same screen, same data and rules, streamlined"],
];
const BEFORE_AFTER = ["dashboard", "navigation", "workbench", "import_center", "mapping_review", "assessment"];
const TOP15 = [
  ["Two navigation systems: 29 sidebar links + stepper + 7 hub pages that only link onward", "assess.png, nav.ts"],
  ["Workbench overload: 13 selects, 15 checkboxes, 4 export buttons; list hidden until a filter", "workbench.png"],
  ["Generic, wrong “Next action: Assign key roles” on every step page", "select.png, assess.png"],
  ["SSP/SAR/RAR generation in 4 places", "implement.png, authorization.png"],
  ["SCA work scattered across Reviews, Workbench, Test Results, Mapping Review", "assess.png, reviews.png"],
  ["Mapping Review: 6 tabs + 3 sections, internal labels", "mapping_review.png"],
  ["Data entered twice: info type + PII at registration and in Categorize; inheritance in 2 editors", "metrics register/categorize"],
  ["Imports end without a next action", "metrics import/test results/evidence"],
  ["ISCM strategy (28 fields) inside Select", "select.png"],
  ["Evidence upload needs a “source” first (+3 clicks)", "metrics evidence"],
  ["Internal terminology (Ledger, ingest run, CCI view, eMASS Sync/import, S-5, Trigraph…)", "route inventory"],
  ["Status dimensions mixed without labels (implementation vs coverage vs assessment)", "workbench.png"],
  ["System detail is a second dashboard without step status or “continue”", "system_detail.png"],
  ["No role-based home", "nav.ts"],
  ["Finding → POA&M → control only partly linked", "metrics finding/POA&M"],
];
const STEPS = [
  ["1 Prepare", "Roles & people · System profile & boundary · HW/SW inventory · PPSM", "System Owner, ISSO"],
  ["2 Categorize", "Information types & impact · Privacy (PII) · AO approval", "ISSO → AO"],
  ["3 Select", "Baseline & overlays · Tailoring & parameters · Monitoring strategy", "ISSO → ISSM"],
  ["4 Implement", "Control Workbench · Policies · Evidence · Inheritance", "ISSO, System Owner, CCP"],
  ["5 Assess", "Assessment workspace (SCA) · Test results · Findings · Mapping review", "SCA"],
  ["6 Authorize", "Package & documents · POA&M · Risk acceptance · Decision", "ISSM → AO"],
  ["7 Monitor", "Dashboard · Schedules & due · Evidence freshness · eMASS sync", "ISSO, ISSM"],
];
const METRICS = [
  ["Register a system", 6, 2, 3, "yes*"], ["Categorize", 4, 1, 3, "yes*"], ["Select a baseline", 5, 1, 1, "yes*"],
  ["Import Implementation Plan", 6, 2, 2, "no"], ["Update a control", 6, 2, 2, "no"], ["Attach evidence", 7, 2, 3, "no"],
  ["Import test results", 4, 2, 1, "no"], ["Review a finding", 5, 3, 1, "no"], ["POA&M (link to matching)", 2, 1, 0, "no"],
  ["Generate an SSP", 3, 1, 0, "yes*"], ["Prepare authorization package", 3, 3, 0, "yes*"], ["Configure continuous monitoring", 5, 1, 3, "yes*"],
];
const BACKLOG = [
  ["R1", "System dashboard + step status + step-specific next action; RMF navigation"],
  ["R2", "Control Workbench 2-pane; status glossary chips"],
  ["R3", "Import Center 4-step flow with next action + automatic evidence source; Mapping Review 3 tabs"],
  ["R4", "SCA assessment workspace; Package & documents with live readiness"],
  ["R5", "My Work per role; registration de-duplication"],
  ["R6", "Guided Mode; connectedness gaps (ACAS → POA&M suggestion, strategy-awaiting notice, suggestions on the control)"],
  ["R7", "Saved filters, ⌘K search, Help merge"],
];

function Table({ head, rows, testId }: { head: string[]; rows: (string | number)[][]; testId: string }) {
  return (
    <div className="overflow-x-auto"><table className="w-full text-left text-[13px]" data-testid={testId}>
      <thead><tr>{head.map((h) => <th key={h} className="border-b border-slate-300 px-2 py-1.5 text-[11px] uppercase tracking-wide text-slate-500">{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i} className="border-b border-slate-200">{r.map((c, j) => <td key={j} className="px-2 py-1.5 align-top">{c}</td>)}</tr>)}</tbody>
    </table></div>);
}

function Section({ title, id, children }: { title: string; id: string; children: React.ReactNode }) {
  return <section className="panel mt-8 p-6" data-testid={`ux-${id}`}><h2 className="t-title text-slate-900">{title}</h2><div className="mt-3">{children}</div></section>;
}

function Shot({ src, caption, testId }: { src: string; caption: string; testId: string }) {
  return (
    <figure className="mt-5" data-testid={testId}>
      <figcaption className="mb-2 text-[13px] font-semibold text-slate-800">{caption}</figcaption>
      <a href={src} target="_blank" rel="noreferrer"><img src={src} alt={caption} loading="lazy" className="w-full rounded-lg border border-slate-200 shadow-sm" /></a>
    </figure>);
}

export default function UxProposalPage() {
  return (
    <div className="flex min-h-full flex-col" data-testid="ux-proposal-page">
      <SyntheticBanner />
      <div className="bg-amber-400 py-1.5 text-center text-[11px] font-bold tracking-[0.12em] text-slate-900" data-testid="ux-proposal-label">{LABEL}</div>
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">
        <BrandLockup className="w-40" />
        <p className="eyebrow mt-8">UX simplification · Phase 1 · {LABEL}</p>
        <h1 className="t-headline mt-2 text-slate-900">RMF made simple, logical and connected – the proposal</h1>
        <p className="mt-3 max-w-3xl text-[15px] text-slate-600">An audit of the current UI, the proposed information architecture around the 7 RMF steps, baseline task metrics and
          non-functional mockups built with synthetic demonstration data. Nothing here changes the app. All safeguards (SCA independence, AO authority, separation of duties,
          human approval of AI, audit, provenance, tenant isolation) stay as they are.</p>
        <a className="btn-primary mt-6 inline-flex px-4 py-2.5" href={`${P}/IronVision_UX_Proposal_Phase1.pdf`} data-testid="ux-proposal-download-pdf">
          <Download className="h-4 w-4" aria-hidden /> Download the full proposal (PDF)</a>
        <Section title="Top 15 sources of complexity" id="top15"><Table head={["#", "Source", "Evidence"]} rows={TOP15.map((r, i) => [i + 1, ...r])} testId="ux-top15-table" /></Section>
        <Section title="Proposed navigation: 7 RMF steps inside the system (any order) + My Work · Systems · Import Center · Search · Admin" id="ia">
          <Table head={["Step", "Lives under it", "Roles"]} rows={STEPS} testId="ux-ia-table" />
          <p className="mt-2 text-[12px] text-slate-500">Step status: complete · remaining · awaiting another role · optional · blocked. Old routes stay as redirects.</p></Section>
        <Section title="Baseline task metrics (current UI, scripted, ISSO, synthetic sandbox)" id="metrics">
          <Table head={["Task", "Clicks", "Page changes", "Fields", "Next action shown"]} rows={[...METRICS, ["Total", 56, 21, 19, "6/12"]]} testId="ux-metrics-table" />
          <p className="mt-2 text-[12px] text-slate-500">* often only the generic “Assign key roles” banner. Data entered twice in 3 tasks. eMASS reference column and sources in the PDF.</p></Section>
        <Section title="Implementation backlog – incremental releases (UI-only; data and permission impact: none)" id="backlog">
          <Table head={["Release", "Scope"]} rows={BACKLOG} testId="ux-backlog-table" /></Section>
        <Section title={`Mockups (${MOCKUPS.length}) – ${LABEL}`} id="mockups">
          {MOCKUPS.map(([k, c]) => <Shot key={k} src={`${P}/mockups/${k}.png`} caption={c} testId={`ux-mockup-${k}`} />)}</Section>
        <Section title="Before / after – the 6 priority areas" id="before-after">
          {BEFORE_AFTER.map((k) => <Shot key={k} src={`${P}/before_after/${k}.png`} caption={`${k.replace("_", " ")}: current UI (left) vs proposal (right)`} testId={`ux-before-after-${k}`} />)}</Section>
      </main>
    </div>);
}
