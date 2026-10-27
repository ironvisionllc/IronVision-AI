import { useState } from "react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Modal } from "@/components/common/Modal";
import { OtherSelect } from "@/components/workbench/emass/fields";

const ENUMS: Record<string, [string, string[]]> = {
  control_designation: ["Security Control Designation", ["Common", "System-Specific", "Hybrid"]],
  slcm_frequency: ["SLCM Frequency", ["Constantly", "Daily", "Weekly", "Monthly", "Quarterly", "Semi-Annually", "Annually", "Every Two Years", "Every Three Years", "Undetermined"]],
  slcm_method: ["SLCM Method", ["Automated", "Semi-Automated", "Manual", "Undetermined"]],
  common_control_provider: ["Common Control Provider", ["DoD", "Component", "Enclave"]],
};
const TEXT: [string, string][] = [["responsible_entities", "Responsible Entities"], ["slcm_criticality", "SLCM Criticality"], ["slcm_reporting", "SLCM Reporting"], ["slcm_tracking", "SLCM Tracking"]];

/** Bulk-set eMASS Implementation Plan fields on the selected controls (explicit confirmation; one audit event per control). */
export function BulkEmass({ systemId, ids, onClose, onDone }: { systemId: string; ids: string[]; onClose: () => void; onDone: () => void }) {
  const [v, setV] = useState<Row>({});
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<Row | null>(null);
  const set = (k: string, x: string) => setV((p) => ({ ...p, [k]: x }));
  const fields = Object.fromEntries(Object.entries(v).map(([k, x]) => [k, String(x).trim()]).filter(([, x]) => x));
  const go = async () => {
    setBusy(true);
    try { const r = await api.post<Row>(`/systems/${systemId}/workbench/emass/bulk`, { control_ids: ids, fields, confirm: ok }); setRes(r.data); toast.success(`Updated ${r.data.updated.length} control(s)`); onDone(); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };
  return (
    <Modal title={`Bulk set eMASS Implementation Plan fields – ${ids.length} control(s)`} onClose={onClose} testId="emass-bulk-modal" wide>
      {res ? <div className="text-[12px]" data-testid="emass-bulk-result">Updated {res.updated.length}: {res.updated.join(", ").toUpperCase() || "—"}
        {res.skipped.length > 0 && <div className="mt-2 text-amber-800">Skipped {res.skipped.length}: {res.skipped.map((s: Row) => `${s.control_id.toUpperCase()} (${s.reason})`).join("; ")}</div>}
        <button className="btn-secondary mt-3" onClick={onClose} data-testid="emass-bulk-close">Close</button></div> : <>
        <p className="mb-3 text-[12px] text-slate-600">Only the fields you fill in are changed; empty fields are left as they are. Inherited and Not Applicable controls are skipped. Implementation Status is not changed in bulk.</p>
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(ENUMS).map(([k, [l, opts]]) => <label key={k} className="block text-[12px]"><span className="font-medium">{l}</span>
            <select className="input mt-1 w-full" value={v[k] ?? ""} onChange={(e) => set(k, e.target.value)} data-testid={`emass-bulk-${k}`}><option value="">(leave unchanged)</option>{k.startsWith("slcm_") && <option value="__strategy__">Follow Continuous Monitoring Strategy</option>}{opts.map((o) => <option key={o}>{o}</option>)}</select></label>)}
          <label className="block text-[12px]"><span className="font-medium">Estimated Completion Date</span>
            <input type="date" className="input mt-1 w-full" value={v.estimated_completion_date ?? ""} onChange={(e) => set("estimated_completion_date", e.target.value)} data-testid="emass-bulk-estimated_completion_date" /></label>
          {TEXT.map(([k, l]) => <div key={k} className="text-[12px]" data-testid={`emass-bulk-field-${k}`}><span className="font-medium">{l}</span><OtherSelect field={k} value={v[k] ?? ""} onChange={(x) => set(k, x)} max={2000} /></div>)}
          <label className="block text-[12px]"><span className="font-medium">SLCM Comments</span>
            <textarea className="input mt-1 w-full" rows={2} maxLength={4000} value={v.slcm_comments ?? ""} onChange={(e) => set("slcm_comments", e.target.value)} data-testid="emass-bulk-slcm_comments" /></label>
        </div>
        <label className="mt-3 flex items-center gap-2 text-[12px]"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} data-testid="emass-bulk-confirm" />
          I confirm setting {Object.keys(fields).length} field(s) on {ids.length} control(s). Each change is audited.</label>
        <button className="btn-primary mt-3" disabled={!ok || busy || !Object.keys(fields).length} onClick={go} data-testid="emass-bulk-apply">{busy ? "Applying…" : "Apply to selected controls"}</button></>}
    </Modal>);
}
