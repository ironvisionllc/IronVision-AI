import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { useSystems } from "@/context/SystemContext";

export const TYPES: Row = { system_details: "System Details", categorization: "Categorization", test_results: "Test Results", slcm: "SLCM Worksheet", hwsw: "Hardware/Software List",
  ppsm: "PPSM Boundaries", control_information: "Control Information (deferred)", poam: "POA&M (deferred)" };

/** Context-aware prompt after upload: in a system → update it (mismatch warning) / register new / cancel; no system → register / pick / cancel. */
export function ImportPrompt({ imp, contextSystem, onTargeted }: { imp: Row; contextSystem?: Row; onTargeted: (d: Row) => void }) {
  const det = imp.detected || {};
  const nav = useNavigate();
  const { systems } = useSystems();
  const [type, setType] = useState<string>(det.type || "");
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const who = [det.identity?.name, det.identity?.acronym && `(${det.identity.acronym})`, det.identity?.emass_id && `eMASS ID ${det.identity.emass_id}`].filter(Boolean).join(" ") || "an unnamed system";
  const go = async (action: string, system_id?: string) => {
    setBusy(true);
    try {
      const r = await api.post<Row>(`/emass-imports/${imp.id}/target`, { action, system_id, report_type: type || null });
      if (action === "register") { sessionStorage.setItem("emassPrefill", JSON.stringify({ ...r.data.prefill, import_id: imp.id })); toast.info("Registration form pre-filled from the eMASS file – nothing has been created"); nav("/systems/new"); return; }
      if (action === "cancel") { toast.info("Import cancelled"); nav(-1); return; }
      onTargeted(r.data);
    } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };
  return (
    <Panel title="eMASS file detected" testId="emass-import-prompt">
      <div className="space-y-3 text-[13px]">
        <div data-testid="import-detected-type">Detected: <b>eMASS {TYPES[det.type] || "unknown report"}</b> · confidence <b data-testid="import-confidence">{det.confidence}</b>
          {det.ambiguous && <span className="ml-2 text-amber-800">– unsure, please confirm the type</span>}</div>
        <label className="flex items-center gap-2 text-[12px]">Report type <select className="input" value={type} onChange={(e) => setType(e.target.value)} data-testid="import-type-override">
          <option value="">— choose —</option>{Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{String(v)}{(det.candidates || []).includes(k) ? " (candidate)" : ""}</option>)}</select></label>
        <p className="text-[11px] text-slate-500">{det.labels?.[type] || "Compatibility pending verification against a real eMASS export"}</p>
        {contextSystem ? <>
          <p data-testid="import-prompt-in-system">This looks like an eMASS <b>{TYPES[type] || "report"}</b> for <b>{who}</b>. Update <b>{contextSystem.acronym || contextSystem.name}</b> with it?</p>
          {det.mismatch && <div className="rounded border border-rose-300 bg-rose-50 px-3 py-2 text-rose-800" role="alert" data-testid="import-mismatch-warning">System mismatch: {det.mismatch}. Check the file before continuing.</div>}
          <div className="flex gap-2"><button className="btn-primary" disabled={busy || !type} onClick={() => go("update", contextSystem.id)} data-testid="import-update-this">Update this system</button>
            <button className="btn-secondary" disabled={busy} onClick={() => go("register")} data-testid="import-register-new">Register a new system instead</button>
            <button className="btn-secondary" disabled={busy} onClick={() => go("cancel")} data-testid="import-cancel">Cancel</button></div>
        </> : <>
          <p data-testid="import-prompt-no-system">This looks like an eMASS <b>{TYPES[type] || "report"}</b> for <b>{who}</b>. Register a new system from this file?</p>
          <div className="flex flex-wrap items-center gap-2"><button className="btn-primary" disabled={busy} onClick={() => go("register")} data-testid="import-register-new">Register new system</button>
            <select className="input" value={pick} onChange={(e) => setPick(e.target.value)} data-testid="import-pick-system"><option value="">Pick an existing system…</option>
              {systems.map((s: Row) => <option key={s.id} value={s.id}>{s.acronym} – {s.name}</option>)}</select>
            <button className="btn-secondary" disabled={busy || !pick || !type} onClick={() => go("update", pick)} data-testid="import-update-picked">Update the picked system</button>
            <button className="btn-secondary" disabled={busy} onClick={() => go("cancel")} data-testid="import-cancel">Cancel</button></div>
        </>}
      </div>
    </Panel>);
}
