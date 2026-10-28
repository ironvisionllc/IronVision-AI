import { useState } from "react";
import { Link } from "react-router-dom";
import { Row, useApi } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { fmtControl } from "@/lib/format";

const LABEL: Record<string, [string, string]> = { overdue: ["Overdue", "bg-rose-50 text-rose-800"], never_monitored: ["Never monitored", "bg-amber-50 text-amber-900"],
  due_soon: ["Due ≤ 14 days", "bg-amber-50 text-amber-900"], on_track: ["On track", "bg-emerald-50 text-emerald-800"], no_frequency: ["No SLCM Frequency", "bg-slate-100 text-slate-700"] };

/** Monitor (Tasks M-2/M-3): SLCM reviews due per control from the effective SLCM Frequency. Strategy is defined in Select (S-5). */
export function SlcmDue({ sid }: { sid: string }) {
  const { data } = useApi<Row>(`/systems/${sid}/iscm/due`);
  const { data: strat } = useApi<Row>(`/systems/${sid}/iscm`);
  const [flt, setFlt] = useState("attention");
  if (!data) return null;
  const items = data.items.filter((i: Row) => flt === "all" || (flt === "attention" ? ["overdue", "never_monitored", "due_soon"].includes(i.status) : i.status === flt));
  return (
    <Panel title="SLCM due / overdue (Continuous Monitoring execution)" testId="slcm-due"
      actions={<Link className="text-[12px] text-blue-800 underline" to="/rmf/select#iscm" data-testid="slcm-edit-strategy">Edit strategy (Select · S-5) →</Link>}>
      {data.counts.no_frequency > 0 && <div className="mb-2 flex flex-wrap items-center gap-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] text-amber-900" data-testid="slcm-nofreq-fix">
        <span>{data.counts.no_frequency} controls have no monitoring frequency.</span>
        <Link className="btn-secondary !py-0.5 text-[12px]" to="/rmf/select#iscm" data-testid="slcm-nofreq-set">Set in Monitoring Strategy (Select · S-5)</Link>
        {strat?.strategy && <Link className="btn-secondary !py-0.5 text-[12px]" to="/rmf/select#iscm-defaults" title="Opens the strategy's system-default SLCM values; they take effect when the ISSM approves the strategy" data-testid="slcm-nofreq-defaults">Apply strategy defaults</Link>}</div>}
      <p className="text-[12px] text-slate-600">Next review = last assessment or evidence date + the control's effective <b>SLCM Frequency</b> (from its override or the Continuous Monitoring Strategy).</p>
      <div className="my-2 flex flex-wrap gap-2 text-[12px]" data-testid="slcm-counts">
        {[["attention", "Needs attention"], ["all", "All"], ...Object.entries(LABEL).map(([k, [l]]) => [k, `${l} (${data.counts[k]})`])].map(([k, l]) =>
          <button key={k} className={`rounded px-2 py-0.5 ${flt === k ? "bg-slate-800 text-white" : "bg-slate-100"}`} onClick={() => setFlt(k)} data-testid={`slcm-filter-${k}`}>{l}</button>)}</div>
      <div className="max-h-80 overflow-auto"><table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>Control</th><th>SLCM Frequency</th><th>SLCM Method</th><th>Source</th><th>Last monitored</th><th>Next due</th><th>Status</th></tr></thead>
        <tbody>{items.slice(0, 300).map((i: Row) => <tr key={i.control_id} className="border-t border-slate-100" data-testid={`slcm-row-${i.control_id}`}>
          <td><Link className="text-blue-800 underline" to={`/systems/${sid}/controls/${i.control_id}`}>{fmtControl(i.control_id)}</Link> <span className="text-slate-500">{i.title}</span></td>
          <td>{i.slcm_frequency || "—"}</td><td>{i.slcm_method || "—"}</td><td className="text-slate-500">{i.source || "—"}</td><td>{i.last_monitored || "—"}</td><td>{i.next_due || "—"}</td>
          <td><span className={`rounded px-1.5 py-0.5 ${LABEL[i.status][1]}`}>{LABEL[i.status][0]}</span></td></tr>)}</tbody></table>
        {!items.length && <p className="p-2 text-[12px] text-slate-500" data-testid="slcm-empty">Nothing in this view.</p>}</div>
    </Panel>);
}
