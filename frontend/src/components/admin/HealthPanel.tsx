import { useCallback, useEffect, useState } from "react";
import { Bot, Database, HardDrive, RefreshCw, Workflow } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { Health } from "@/lib/types";
import { Panel } from "@/components/common/Panel";
import { StatusPill } from "@/components/common/StatusPill";

const COMPONENTS = [
  { key: "database", label: "Database", icon: Database },
  { key: "storage", label: "Object storage", icon: HardDrive },
  { key: "worker", label: "Worker heartbeat", icon: Workflow },
  { key: "ai", label: "AI configured", icon: Bot },
];

export function HealthPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<Health>("/health").then((r) => { setHealth(r.data); setError(""); }).catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  return (
    <Panel title="Platform health" eyebrow="GET /api/v1/health" testId="admin-health-panel"
      actions={<>
        {health && <StatusPill tone={health.status === "ok" ? "success" : "warning"} dot testId="health-overall-status">{health.status.toUpperCase()}</StatusPill>}
        <button className="btn-secondary px-2 py-1" onClick={load} data-testid="health-refresh-btn" aria-label="Refresh health"><RefreshCw className="h-3.5 w-3.5" /></button>
      </>}>
      {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {COMPONENTS.map(({ key, label, icon: Icon }) => {
          const c = health?.components[key];
          return (
            <div key={key} className="rounded-md border border-slate-200 p-3" data-testid={`health-${key}`}>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-[13px] font-medium text-slate-800"><Icon className="h-4 w-4 text-slate-500" aria-hidden />{label}</span>
                {c && <StatusPill tone={c.ok ? "success" : "critical"} dot testId={`health-${key}-status`}>{c.ok ? "OK" : "FAIL"}</StatusPill>}
              </div>
              <dl className="mt-2 space-y-0.5">
                {c && Object.entries(c.detail).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2 text-[11px]">
                    <dt className="text-slate-500">{k}</dt>
                    <dd className="truncate font-mono text-slate-700" title={String(v)}>{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
