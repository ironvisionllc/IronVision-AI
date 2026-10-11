import { useState } from "react";
import { Gavel } from "lucide-react";
import { api, errorMessage, errorStatus } from "@/lib/api";
import { Panel } from "@/components/common/Panel";
import { StatusPill } from "@/components/common/StatusPill";

interface Result { status: number; message: string }

export function RbacDemoPanel() {
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);

  const call = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ message: string }>("/authorization-decisions/test");
      setResult({ status: r.status, message: r.data.message });
    } catch (e) {
      setResult({ status: errorStatus(e) ?? 0, message: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="RBAC enforcement demo" eyebrow="POST /api/v1/authorization-decisions/test" testId="rbac-demo-panel">
      <p className="text-[13px] text-slate-600">
        Requires <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[12px]">authorization.decide</code> (AO only). Other roles — including Platform Admin — receive 403 and an <code className="text-[12px]">authz.denied</code> audit event.
      </p>
      <button className="btn-primary mt-4" onClick={call} disabled={busy} data-testid="rbac-demo-call-btn">
        <Gavel className="h-4 w-4" aria-hidden /> {busy ? "Calling…" : "Call AO-only endpoint"}
      </button>
      {result && (
        <div className="mt-4 flex items-start gap-3 rounded-md border border-slate-200 bg-slate-50 p-3" data-testid="rbac-demo-result">
          <StatusPill tone={result.status === 200 ? "success" : "critical"} dot testId="rbac-demo-status">
            {result.status === 200 ? "200 OK" : result.status === 403 ? "403 FORBIDDEN" : `HTTP ${result.status}`}
          </StatusPill>
          <span className="text-[13px] text-slate-700" data-testid="rbac-demo-message">{result.message}</span>
        </div>
      )}
    </Panel>
  );
}
