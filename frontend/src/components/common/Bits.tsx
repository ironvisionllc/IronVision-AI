import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { StatusPill, Tone } from "@/components/common/StatusPill";

// Maps existing record states onto IronVision status categories (meaning unchanged; text is always shown).
const TONES: Record<string, Tone> = {
  passing: "success", failing: "failed", no_data: "neutral", inherited: "info",
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
  return <Link to={`/systems/${systemId}/controls/${controlId}`} className="font-mono text-[12px] font-semibold text-blue-800 hover:underline" data-testid={`control-link-${controlId}`}>{controlId.toUpperCase()}</Link>;
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
  return <div className="panel p-6 text-sm text-slate-600" data-testid="need-system">Select a system in the sidebar (or register one on the Systems page) to view this module.</div>;
}
