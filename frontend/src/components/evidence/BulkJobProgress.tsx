import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";

/** Server-side bulk decision job: progress, succeeded / failed (reason) / skipped (already decided), retry failed only. */
export function BulkJobProgress({ job, onDone, onRetry }: { job: Row; onDone: () => void; onRetry: (j: Row) => void }) {
  const [j, setJ] = useState<Row>(job);
  const [err, setErr] = useState("");
  const fired = useRef(false);
  useEffect(() => {
    setJ(job); fired.current = false;
    const t = setInterval(async () => {
      try {
        const r = (await api.get<Row>(`/mapping-review/bulk-jobs/${job.id}`)).data;
        setJ(r);
        if (["succeeded", "failed"].includes(r.status)) { clearInterval(t); if (!fired.current) { fired.current = true; onDone(); } }
      } catch (e) { setErr(errorMessage(e)); clearInterval(t); }
    }, 1500);
    return () => clearInterval(t);
  }, [job.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const pct = j.total ? Math.round((100 * j.processed) / j.total) : 0;
  const fin = ["succeeded", "failed"].includes(j.status);
  const retry = async () => { try { onRetry((await api.post<Row>(`/mapping-review/bulk-jobs/${j.id}/retry`)).data); } catch (e) { setErr(errorMessage(e)); } };
  return <div className="mb-2 rounded border border-blue-200 bg-blue-50/50 p-2 text-[12px]" data-testid="bulk-job" aria-live="polite">
    <div className="flex items-center gap-2"><b>{fin ? "Bulk decision finished" : `Processing ${j.action} for ${j.total} item(s)…`}</b><span className="text-slate-500">batches of 100, one transaction each{j.retry_of ? " · retry of failed items" : ""}</span></div>
    <div className="mt-1 h-2 w-full rounded bg-slate-200"><div className="h-2 rounded bg-blue-700 transition-[width]" style={{ width: `${pct}%` }} data-testid="bulk-job-bar" /></div>
    <div className="mt-1" data-testid="bulk-job-summary">{j.processed} of {j.total} processed · <span className="text-emerald-800">{j.succeeded} succeeded</span> · <span className="text-rose-800">{j.failed.length} failed</span> · <span className="text-slate-600">{j.skipped.length} skipped (already decided)</span></div>
    {fin && j.failed.length > 0 && <><ul className="mt-1 max-h-32 overflow-auto text-rose-900" data-testid="bulk-job-failed">{j.failed.slice(0, 50).map((f: Row) => <li key={f.key}>{f.control_id?.toUpperCase()}: {f.reason}</li>)}</ul>
      <button className="btn-secondary mt-1 px-2 py-0.5" onClick={retry} data-testid="bulk-job-retry">Retry {j.failed.length} failed item(s)</button></>}
    {j.status === "queued" && <div className="mt-1 text-amber-800" data-testid="bulk-job-queued">Queued{j.queued_behind ? ` behind ${j.queued_behind} other bulk decision job(s)` : " – starting"} · {j.lane}</div>}
    {j.error && <div className="text-rose-800">{j.error}</div>}{err && <div className="text-rose-800" role="alert">{err}</div>}
  </div>;
}
