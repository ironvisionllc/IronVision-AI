import { useCallback, useEffect, useState } from "react";
import { Play } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";
import type { Job } from "@/lib/types";
import { fmtDate } from "@/lib/format";
import { Panel } from "@/components/common/Panel";
import { StatusPill, Tone } from "@/components/common/StatusPill";

const TONE: Record<string, Tone> = { succeeded: "success", running: "info", queued: "neutral", failed: "critical" };

export function JobsPanel() {
  const { can } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<Job[]>("/jobs").then((r) => setJobs(r.data)).catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const enqueue = async () => {
    try {
      await api.post("/admin/content/load", { force: false });
      load();
      setTimeout(load, 4000);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <Panel title="Worker jobs" eyebrow="Postgres-backed queue" testId="jobs-panel"
      actions={can("admin.content.load") && (
        <button className="btn-secondary" onClick={enqueue} data-testid="content-load-enqueue-btn">
          <Play className="h-3.5 w-3.5" aria-hidden /> Enqueue content load (idempotent)
        </button>
      )}>
      {error && <p className="mb-2 text-sm text-rose-700" role="alert">{error}</p>}
      <table className="w-full border-collapse" data-testid="jobs-table">
        <thead><tr><th className="th">Type</th><th className="th">Status</th><th className="th">Attempts</th><th className="th">Created</th><th className="th">Finished</th><th className="th">Result</th></tr></thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id}>
              <td className="td font-mono text-[12px]">{j.job_type}</td>
              <td className="td"><StatusPill tone={TONE[j.status] ?? "neutral"} dot>{j.status}</StatusPill></td>
              <td className="td font-mono text-[12px]">{j.attempts}</td>
              <td className="td font-mono text-[11px]">{fmtDate(j.created_at)}</td>
              <td className="td font-mono text-[11px]">{fmtDate(j.finished_at)}</td>
              <td className="td max-w-md truncate font-mono text-[11px] text-slate-500" title={JSON.stringify(j.result ?? j.error)}>{j.error ? j.error.slice(0, 120) : JSON.stringify(j.result)?.slice(0, 120)}</td>
            </tr>
          ))}
          {jobs.length === 0 && <tr><td colSpan={6} className="td text-center text-slate-500">No jobs yet.</td></tr>}
        </tbody>
      </table>
    </Panel>
  );
}
