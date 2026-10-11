import { useCallback, useEffect, useState } from "react";
import { Link2, RefreshCw } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";
import { fmtDate, shortHash } from "@/lib/format";
import { Panel } from "@/components/common/Panel";
import { StatusPill, Tone } from "@/components/common/StatusPill";

const TONE: Record<string, Tone> = { success: "success", failure: "critical", denied: "critical", locked: "warning" };

export function AuditPanel() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [chain, setChain] = useState<{ valid: boolean; checked: number } | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<AuditEvent[]>("/audit-events", { params: { limit: 50 } }).then((r) => setEvents(r.data)).catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const verify = async () => {
    try {
      const r = await api.get<{ valid: boolean; checked: number }>("/audit-events/verify");
      setChain(r.data);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <Panel title="Audit events" eyebrow="Append-only · SHA-256 hash chain" testId="audit-panel"
      actions={<>
        {chain && <StatusPill tone={chain.valid ? "success" : "critical"} dot testId="audit-chain-status">{chain.valid ? `CHAIN VALID · ${chain.checked} events` : "CHAIN BROKEN"}</StatusPill>}
        <button className="btn-secondary" onClick={verify} data-testid="audit-verify-btn"><Link2 className="h-3.5 w-3.5" aria-hidden /> Verify chain</button>
        <button className="btn-secondary px-2 py-1" onClick={load} data-testid="audit-refresh-btn" aria-label="Refresh audit events"><RefreshCw className="h-3.5 w-3.5" /></button>
      </>}>
      {error && <p className="mb-2 text-sm text-rose-700" role="alert">{error}</p>}
      <div className="max-h-[420px] overflow-auto">
        <table className="w-full border-collapse" data-testid="audit-table">
          <thead className="sticky top-0"><tr><th className="th">#</th><th className="th">Time (UTC)</th><th className="th">Actor</th><th className="th">Action</th><th className="th">Entity</th><th className="th">Outcome</th><th className="th">IP</th><th className="th">Hash</th></tr></thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.seq} data-testid={`audit-row-${e.seq}`}>
                <td className="td font-mono text-[11px] text-slate-500">{e.seq}</td>
                <td className="td whitespace-nowrap font-mono text-[11px]">{fmtDate(e.occurred_at)}</td>
                <td className="td text-[12px]">{e.actor_name ? <>{e.actor_name}<div className="text-[10px] text-slate-500">{e.actor_email} · {(e.actor_roles || []).join("/")}</div></> : e.actor_email ?? "—"}</td>
                <td className="td font-mono text-[12px]">{e.action}</td>
                <td className="td max-w-[220px] truncate font-mono text-[11px] text-slate-500" title={`${e.entity_type}:${e.entity_id}`}>{e.entity_type ? `${e.entity_type}:${e.entity_id}` : "—"}</td>
                <td className="td"><StatusPill tone={TONE[e.outcome] ?? "neutral"}>{e.outcome}</StatusPill></td>
                <td className="td font-mono text-[11px] text-slate-500">{e.ip ?? "—"}</td>
                <td className="td font-mono text-[11px] text-slate-500" title={`prev ${e.prev_hash}\nhash ${e.hash}`}>{shortHash(e.hash, 10)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
