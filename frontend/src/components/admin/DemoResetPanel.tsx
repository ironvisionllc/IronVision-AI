import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { Panel } from "@/components/common/Panel";

export function DemoResetPanel() {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const reset = async () => {
    if (!window.confirm("Delete and re-seed ALL synthetic demo systems? (audit log is retained)")) return;
    setBusy(true);
    try { await api.post("/admin/demo/reset"); setMsg("Demo data reset and re-seeded through the ingestion pipeline."); }
    catch (e) { setMsg(errorMessage(e)); } finally { setBusy(false); }
  };
  return (
    <Panel title="Reset demo data" eyebrow="Demo tool · synthetic tenant only" testId="demo-reset-panel">
      <button className="btn-secondary border-rose-300 text-rose-700" onClick={reset} disabled={busy} data-testid="demo-reset-btn">{busy ? "Resetting…" : "Reset Demo Data"}</button>
      {msg && <p className="mt-2 text-[13px] text-slate-700" data-testid="demo-reset-msg">{msg}</p>}
    </Panel>
  );
}
