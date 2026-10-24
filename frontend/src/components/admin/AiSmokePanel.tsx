import { useCallback, useEffect, useState } from "react";
import { Bot, Plug } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Panel } from "@/components/common/Panel";
import { StatusPill } from "@/components/common/StatusPill";

type Row = Record<string, any>;
const when = (v?: string | null) => (v ? new Date(v).toLocaleString() : "never");

function StatusGrid({ s }: { s: Row }) {
  const rows: [string, string, string][] = [
    ["Provider / model", s.configured ? `${s.provider} / ${s.model}` : `${s.provider || "none"} / ${s.model || "—"}`, "ai-status-provider-model"],
    ["Configured", s.configured ? "yes" : `no – ${s.reason ?? "no provider set"}`, "ai-status-configured"],
    ["Analysis mode", s.mode_label, "ai-status-mode"],
    ["Endpoint", s.base_url || "—", "ai-status-endpoint"],
    ["API key", s.api_key_configured ? "configured (hidden)" : "not set", "ai-status-key"],
    ["Last successful call", s.last_success_at ? `${when(s.last_success_at)} (${s.last_success?.provider} / ${s.last_success?.model}, ${s.last_success?.latency_ms} ms)` : "never", "ai-status-last-success"],
    ["Usage (24 h)", `${s.calls_24h} call(s) · ${s.tokens_24h} tokens`, "ai-status-usage"],
  ];
  if (s.last_error_at && s.last_error !== undefined) rows.push(["Last failed call", `${when(s.last_error_at)} – ${s.last_error}`, "ai-status-last-error"]);
  return (<dl className="grid grid-cols-[150px_minmax(0,1fr)] gap-y-1 text-[12px]">{rows.map(([k, v, id]) => <div key={id} className="contents">
    <dt className="text-slate-500">{k}</dt><dd className="break-words font-mono text-slate-800" data-testid={id}>{v}</dd></div>)}</dl>);
}

export function AiSmokePanel() {
  const [s, setS] = useState<Row | null>(null);
  const [res, setRes] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { user } = useAuth();
  const role = user ? user.persona_role : null;
  const load = useCallback(() => { api.get<Row>("/ai/status").then((r) => setS(r.data)).catch((e) => setError(errorMessage(e))); }, [role]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(load, [load]);

  const run = async () => {
    setBusy(true); setError(""); setRes(null);
    try { setRes((await api.post<Row>("/ai/health")).data); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); load(); }
  };

  return (
    <Panel title="AI status" eyebrow="GET /api/v1/ai/status" testId="ai-smoke-panel"
      actions={s && <StatusPill tone={s.configured ? "success" : "warning"} dot testId="ai-status-pill">{s.configured ? "AI CONFIGURED" : "NO AI – DETERMINISTIC"}</StatusPill>}>
      {s ? <StatusGrid s={s} /> : !error && <p className="text-[12px] text-slate-500">Loading…</p>}
      {s?.can_test && <button className="btn-primary mt-4" onClick={run} disabled={busy} data-testid="ai-smoke-run-btn">
        <Plug className="h-4 w-4" aria-hidden /> {busy ? "Calling model…" : "Test AI connection"}</button>}
      {s && !s.can_test && <p className="mt-3 text-[11px] text-slate-500" data-testid="ai-test-restricted">Only a platform admin can run “Test AI connection”.</p>}
      {error && <div className="mt-4 break-words rounded border border-rose-300 bg-rose-50 p-3 text-[13px] text-rose-800" role="alert" data-testid="ai-smoke-error">{error}</div>}
      {res && (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3" data-testid="ai-smoke-result">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone="success" dot>CONNECTION OK</StatusPill><Bot className="h-4 w-4 text-slate-500" aria-hidden />
            <span className="font-mono text-[12px] text-slate-700" data-testid="ai-smoke-provider">{res.provider}</span>
            <span className="font-mono text-[12px] text-slate-700" data-testid="ai-smoke-model">{res.model}</span>
            <span className="font-mono text-[12px] text-slate-700" data-testid="ai-smoke-latency">{res.latency_ms} ms</span>
          </div>
          <p className="mt-2 text-[13px] text-slate-700">{res.output?.summary}</p>
          <p className="mt-1 break-all font-mono text-[10px] text-slate-400">audited · interaction {res.interaction_id} · nonce {res.output?.nonce}</p>
        </div>
      )}
    </Panel>
  );
}
