import { useState } from "react";
import { useApi, Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";

/** One counting rule (base control only vs including assigned enhancements), drillable to each CCI / objective. */
export function RequirementCounts({ systemId, controlId }: { systemId: string; controlId: string }) {
  const { data } = useApi<Row>(`/systems/${systemId}/workbench/controls/${controlId}/requirement-counts`);
  const [open, setOpen] = useState<string | null>(null);
  if (!data) return null;
  const b = data.base_only, inc = data.including_assigned_enhancements;
  return <Panel title="Requirement counts" testId="requirement-counts">
    <p className="text-[11px] text-slate-500" data-testid="requirement-counts-rule">{data.rules}</p>
    <table className="mt-2 w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>Scope</th><th>CCIs</th><th>Objectives</th><th>Requirements</th><th>Met (approved policies)</th></tr></thead>
      <tbody>
        <tr data-testid="requirement-counts-base"><td>{controlId.toUpperCase()} – base control only</td><td>{b.ccis}</td><td>{b.objectives}</td><td>{b.requirements}</td><td>{b.met}</td></tr>
        <tr data-testid="requirement-counts-incl"><td>Including assigned enhancements ({inc.controls.length} controls)</td><td>{inc.ccis_unique} unique</td><td>{inc.objectives}</td><td>{inc.requirements}</td><td>{inc.met}</td></tr>
      </tbody></table>
    <div className="mt-2 space-y-1">{data.per_control.map((p: Row) => <div key={p.control_id} className="text-[12px]">
      <button className="text-blue-700 underline" onClick={() => setOpen(open === p.control_id ? null : p.control_id)} data-testid={`requirement-counts-drill-${p.control_id}`}>
        {p.control_id.toUpperCase()}: {p.met.length} of {p.requirements} met · {p.policies.length} approved policy link(s){p.proposed_policies.length ? `, ${p.proposed_policies.length} proposed (not counted)` : ""}</button>
      {open === p.control_id && <div className="ml-3 text-[11px] text-slate-700" data-testid={`requirement-counts-detail-${p.control_id}`}>
        <div>CCIs: {p.ccis.map((c: string) => <span key={c} className={p.met.includes(c) ? "mr-1 text-emerald-700" : "mr-1"}>{c}</span>)}</div>
        <div>Objectives: {p.objectives.map((c: string) => <span key={c} className={p.met.includes(c) ? "mr-1 text-emerald-700" : "mr-1"}>{c}</span>)}</div>
      </div>}
    </div>)}</div>
  </Panel>;
}
