import { useEffect } from "react";

type Progress = { phase?: string; pct?: number; controls_screened?: number; requirements_total?: number; requirements_analyzed?: number;
  findings_so_far?: number; batches_done?: number; batches_total?: number; failed_batches?: number; retries?: number; elapsed_s?: number; eta_s?: number };

export function AnalysisProgress({ p, testId }: { p?: Progress; testId: string }) {
  if (!p) return null;
  return <div className="mt-1 min-w-[220px] text-[11px] text-slate-600" data-testid={testId}>
    <div className="h-1.5 w-full rounded bg-slate-200"><div className="h-1.5 rounded bg-blue-700 transition-[width] duration-500" style={{ width: `${p.pct ?? 0}%` }} /></div>
    <div className="mt-0.5">{p.pct ?? 0}% · {p.requirements_analyzed ?? 0}/{p.requirements_total ?? "?"} requirements · {p.controls_screened ?? 0} controls screened</div>
    <div>{p.findings_so_far ?? 0} validated findings so far <span className="italic">(analysis in progress)</span> · {Math.round(p.elapsed_s ?? 0)} s elapsed{p.eta_s != null && ` · ETA ~${Math.round(p.eta_s)} s`}</div>
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
