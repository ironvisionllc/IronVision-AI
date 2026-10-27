import { useEffect } from "react";

type Progress = { phase?: string; stage?: string; pct?: number; controls_screened?: number; requirements_total?: number; requirements_analyzed?: number;
  requirement_gaps_so_far?: number; audit_findings?: number; batches_done?: number; batches_total?: number; failed_batches?: number; retries?: number;
  elapsed_s?: number; eta_s?: number };

export function AnalysisProgress({ p, testId }: { p?: Progress; testId: string }) {
  if (!p) return null;
  return <div className="mt-1 min-w-[220px] text-[11px] text-slate-600" data-testid={testId}>
    <div className="h-1.5 w-full rounded bg-slate-200"><div className="h-1.5 rounded bg-blue-700 transition-[width] duration-500" style={{ width: `${p.pct ?? 0}%` }} /></div>
    <div className="mt-0.5 font-medium" data-testid={`${testId}-stage`}>{p.pct ?? 0}% · {p.stage ?? p.phase ?? "starting"}</div>
    {p.requirements_total != null && <div>{p.requirements_analyzed ?? 0} of {p.requirements_total} requirements analysed · {p.controls_screened ?? 0} controls
      {p.batches_total != null && ` · batch ${p.batches_done ?? 0} of ${p.batches_total}`}</div>}
    <div>{p.requirement_gaps_so_far != null && `${p.requirement_gaps_so_far} requirement gaps so far · `}
      {p.audit_findings != null && `${p.audit_findings} audit findings · `}{Math.round(p.elapsed_s ?? 0)} s elapsed{p.eta_s != null && ` · ETA ~${Math.round(p.eta_s)} s`}
      <span className="italic"> (analysis in progress – results not final)</span></div>
    {(p.failed_batches || p.retries) ? <div className="text-amber-700">{p.failed_batches ?? 0} failed batch(es) · {p.retries ?? 0} retried</div> : null}
  </div>;
}

export function usePollWhile(active: boolean, reload: () => void, ms = 3000) {
  useEffect(() => {
    if (!active) return;
    const t = setInterval(reload, ms);
    return () => clearInterval(t);
  }, [active, reload, ms]);
}
