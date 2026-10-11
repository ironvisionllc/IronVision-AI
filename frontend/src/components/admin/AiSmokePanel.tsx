import { useState } from "react";
import { Bot } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { Panel } from "@/components/common/Panel";
import { StatusPill } from "@/components/common/StatusPill";

interface AiHealth {
  ok: boolean;
  provider: string;
  model: string | null;
  latency_ms: number;
  prompt_id: string;
  prompt_version: string;
  interaction_id: string;
  output: { status: string; nonce: string; summary: string };
}

export function AiSmokePanel() {
  const [res, setRes] = useState<AiHealth | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    setError("");
    setRes(null);
    try {
      const r = await api.post<AiHealth>("/ai/health");
      setRes(r.data);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="AI provider smoke test" eyebrow="POST /api/v1/ai/health" testId="ai-smoke-panel">
      <p className="text-[13px] text-slate-600">One real call through <code className="text-[12px]">AIService</code> using versioned prompt <code className="text-[12px]">ai.health_check@1.0.0</code>; output is schema-validated and logged to <code className="text-[12px]">ai_interactions</code>.</p>
      <button className="btn-primary mt-4" onClick={run} disabled={busy} data-testid="ai-smoke-run-btn">
        <Bot className="h-4 w-4" aria-hidden /> {busy ? "Calling model…" : "Run AI health check"}
      </button>
      {error && <div className="mt-4 rounded border border-rose-300 bg-rose-50 p-3 text-[13px] text-rose-800" role="alert" data-testid="ai-smoke-error">{error}</div>}
      {res && (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3" data-testid="ai-smoke-result">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone="success" dot>SCHEMA VALID</StatusPill>
            <span className="font-mono text-[12px] text-slate-700" data-testid="ai-smoke-provider">{res.provider}</span>
            <span className="font-mono text-[12px] text-slate-700" data-testid="ai-smoke-model">{res.model}</span>
            <span className="font-mono text-[12px] text-slate-700" data-testid="ai-smoke-latency">{res.latency_ms} ms</span>
          </div>
          <p className="mt-2 text-[13px] text-slate-700">{res.output.summary}</p>
          <p className="mt-1 font-mono text-[10px] text-slate-400">interaction {res.interaction_id} · nonce {res.output.nonce}</p>
        </div>
      )}
    </Panel>
  );
}
