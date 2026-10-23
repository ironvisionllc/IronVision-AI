import { fmtControl } from "@/lib/format";
import { useSystems } from "@/context/SystemContext";
import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { StatusPill, Tone } from "@/components/common/StatusPill";

// Maps existing record states onto IronVision status categories (meaning unchanged; text is always shown).
const TONES: Record<string, Tone> = {
  passing: "success", failing: "failed", no_data: "neutral", inherited: "info", review_overdue: "critical", review_due_soon: "warning",
  Mismatch: "failed", Match: "success",
  current: "success", near_expiration: "warning", expired: "critical", no_evidence: "neutral", integrity_mismatch: "failed", signature_invalid: "failed",
  not_assessed: "neutral", satisfied: "success", other_than_satisfied: "failed",
  planned: "warning", implemented: "success", partially_implemented: "warning", not_implemented: "neutral",
  open: "critical", pass: "success", not_applicable: "neutral", not_reviewed: "warning",
  mapped: "success", unmapped: "warning", dispositioned: "info", completed: "success", duplicate: "info", failed: "failed", queued: "neutral", processing: "info",
  verified: "success", hash_recorded: "info", unsigned: "neutral", partially_stale: "warning", not_detected: "success", remediated_observed: "info",
  closed_by_review: "success", new: "neutral", in_progress: "info", overdue: "critical", closure_eligible: "success", closure_review: "review",
  risk_acceptance_review: "review", closed: "success", risk_accepted: "info", pending: "review", approved: "success", rejected: "failed",
  returned: "warning", more_evidence_requested: "warning", draft: "draft", in_review: "review", superseded: "neutral", false_positive: "info",
  critical: "critical", high: "critical", medium: "warning", low: "neutral", mismatch: "failed", unverified: "warning", ok: "success", not_configured: "neutral", unknown: "neutral",
  needs_attention: "warning", succeeded: "success", submitted: "review", under_review: "review", accepted: "success", dismissed: "neutral", confirmed: "critical",
};

export function S({ v, label, testId }: { v: string | null | undefined; label?: string; testId?: string }) {
  if (!v) return <span className="text-slate-400">—</span>;
  return <StatusPill tone={TONES[v] ?? "neutral"} dot testId={testId} prefix={label}>{v.replace(/_/g, " ")}</StatusPill>;
}

const SEV: Record<string, Tone> = { "CAT I": "critical", "CAT II": "warning", "CAT III": "info", critical: "critical", high: "critical", medium: "warning", low: "info", info: "neutral" };

/** Consistent CAT I/II/III (and severity) badge – text unchanged. */
export function Sev({ v, testId }: { v: string | null | undefined; testId?: string }) {
  if (!v) return <span className="text-slate-400">—</span>;
  return <StatusPill tone={SEV[v] ?? SEV[v.toLowerCase()] ?? "neutral"} testId={testId}>{v}</StatusPill>;
}

export function ControlLink({ systemId, controlId }: { systemId: string; controlId: string }) {
  return <Link to={`/systems/${systemId}/controls/${controlId}`} className="font-mono text-[12px] font-semibold text-blue-800 hover:underline" data-testid={`control-link-${controlId}`}>{fmtControl(controlId)}</Link>;
}

export function Table({ head, children, testId }: { head: string[]; children: ReactNode; testId?: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0" data-testid={testId}>
        <thead><tr>{head.map((h, i) => <th key={`${h}-${i}`} className="th">{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Stat({ label, value, testId, hint }: { label: string; value: ReactNode; testId: string; hint?: string }) {
  return (
    <div className="panel px-4 py-3.5" data-testid={testId}>
      <div className="eyebrow !text-[10px]">{label}</div>
      <div className="mt-1 font-heading text-2xl font-bold tracking-tight text-slate-900">{value ?? "—"}</div>
      {hint && <div className="text-[11px] leading-snug text-slate-500">{hint}</div>}
    </div>
  );
}

export function NeedSystem() {
  const { systems } = useSystems();
  const none = !systems || systems.length === 0;
  return <div className="panel p-6 text-sm text-slate-600" data-testid="need-system">
    <div className="t-title text-slate-900">{none ? "No system yet" : "Choose a system"}</div>
    <p className="mt-1">{none
      ? "Everything here (controls, evidence, POA&Ms) belongs to a system – the thing you are seeking an ATO for. Start by registering it; you pick its baseline (Low/Moderate/High) and the app assigns the controls. Want to look around first? Use “Load demo data” in the bar above."
      : "This page works on one system at a time. Pick the system in the “Active system” box on the left."}</p>
    {none && <Link to="/systems/new" className="btn-primary mt-3 inline-flex" data-testid="need-system-register">Register your first system</Link>}
  </div>;
}
