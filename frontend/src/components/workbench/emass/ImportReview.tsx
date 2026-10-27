import { useState } from "react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";

const val = (v: unknown) => (v === null || v === undefined || v === "" ? <span className="text-slate-400">(empty)</span> : String(v).length > 160 ? `${String(v).slice(0, 160)}…` : String(v));

/** Per control, per field: current vs imported, accept / reject. Nothing is saved until Apply. */
export function ImportReview({ systemId, imp, onChange }: { systemId: string; imp: Row; onChange: (d: Row) => void }) {
  const [showSame, setShowSame] = useState(false);
  const [busy, setBusy] = useState("");
  const ro = !imp.can_apply || imp.status !== "review";
  const labels: Row = imp.labels || {};
  const decide = async (body: Row, tag: string) => {
    setBusy(tag);
    try { const r = await api.put<Row>(`/systems/${systemId}/emass-imports/${imp.id}/decisions`, body); onChange(r.data); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(""); }
  };
  const one = (cid: string, field: string | null, decision: string | null) => decide({ decisions: [{ control_id: cid, field, decision }] }, `${cid}:${field}:${decision}`);
  const items: Row[] = (imp.items || []).filter((i: Row) => showSame || Object.values(i.fields).some((f: any) => f.change || f.error || f.blocked));
  return (
    <Panel title="Review imported values" testId="emass-import-review" actions={!ro && <div className="flex gap-2">
      <button className="btn-secondary" disabled={!!busy} onClick={() => decide({ bulk: "accept_safe" }, "bulk")} data-testid="import-accept-safe">Accept all conflict-free changes</button>
      <button className="btn-secondary" disabled={!!busy} onClick={() => decide({ bulk: "reject_all" }, "bulk")} data-testid="import-reject-all">Reject all</button>
      <button className="btn-secondary" disabled={!!busy} onClick={() => decide({ bulk: "reset" }, "bulk")} data-testid="import-reset">Reset</button></div>}>
      <label className="mb-3 flex items-center gap-2 text-[12px]"><input type="checkbox" checked={showSame} onChange={(e) => setShowSame(e.target.checked)} data-testid="import-show-unchanged" />Show unchanged fields and controls</label>
      {ro && imp.status === "review" && <div className="mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900" data-testid="import-readonly">Read-only: only the ISSO or System Owner can accept, reject and apply an eMASS import.</div>}
      <div className="space-y-3">{items.map((i) => {
        const fs = Object.entries(i.fields as Row).filter(([, f]: [string, any]) => showSame || f.change || f.error || f.blocked);
        return (
          <div key={i.control_id} className="rounded border border-slate-200" data-testid={`import-item-${i.control_id}`}>
            <div className="flex items-center gap-3 border-b border-slate-100 bg-slate-50 px-3 py-1.5 text-[12px]">
              <b>{i.control}</b><span className="text-slate-500">row {i.row}</span>
              {i.required_issue && <span className="rounded bg-rose-50 px-1.5 text-rose-800" data-testid={`import-required-${i.control_id}`}>{i.required_issue} – plan changes will be flagged, not saved</span>}
              {!ro && <span className="ml-auto flex gap-2"><button className="underline" onClick={() => one(i.control_id, "*", "accept")} data-testid={`import-accept-control-${i.control_id}`}>Accept control</button>
                <button className="underline" onClick={() => one(i.control_id, "*", "reject")} data-testid={`import-reject-control-${i.control_id}`}>Reject control</button></span>}
            </div>
            <table className="w-full text-[12px]"><tbody>{fs.map(([k, f]: [string, any]) => (
              <tr key={k} className={f.error ? "bg-rose-50/60" : f.blocked ? "bg-amber-50/60" : f.change ? "bg-blue-50/50" : ""} data-testid={`import-field-${i.control_id}-${k}`}>
                <td className="w-48 px-3 py-1 font-medium">{labels[k] || k}</td>
                <td className="w-1/3 px-3 py-1 text-slate-600">{val(f.current)}</td>
                <td className={`w-1/3 px-3 py-1 ${f.change ? "font-semibold text-blue-900" : ""}`}>{val(f.imported)}
                  {f.error && <div className="text-rose-700" data-testid={`import-error-${i.control_id}-${k}`}>{f.error}</div>}
                  {f.blocked && <div className="text-amber-800" data-testid={`import-blocked-${i.control_id}-${k}`}>{f.blocked}</div>}</td>
                <td className="w-44 px-3 py-1 text-right">{f.change && !f.error && !f.blocked && (ro ? <span data-testid={`import-decision-${i.control_id}-${k}`}>{f.decision || "undecided"}</span> : <span className="flex justify-end gap-1">
                  <button className={`rounded px-2 py-0.5 ${f.decision === "accept" ? "bg-emerald-700 text-white" : "border border-slate-300"}`} onClick={() => one(i.control_id, k, f.decision === "accept" ? null : "accept")} data-testid={`import-accept-${i.control_id}-${k}`}>Accept</button>
                  <button className={`rounded px-2 py-0.5 ${f.decision === "reject" ? "bg-slate-700 text-white" : "border border-slate-300"}`} onClick={() => one(i.control_id, k, f.decision === "reject" ? null : "reject")} data-testid={`import-reject-${i.control_id}-${k}`}>Reject</button></span>)}
                  {!f.change && !f.error && !f.blocked && <span className="text-slate-400">unchanged</span>}</td>
              </tr>))}</tbody></table>
          </div>);
      })}{!items.length && <p className="text-[12px] text-slate-500" data-testid="import-no-changes">No changed fields. Tick "Show unchanged" to see everything.</p>}</div>
    </Panel>);
}
