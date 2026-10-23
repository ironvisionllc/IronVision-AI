import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { Gated } from "@/components/common/RoleGate";

const STATUSES = ["planned", "partially_implemented", "implemented", "not_applicable", "inherited", "not_implemented"];

/** Implementation status on its own, with an explicit Save – independent of the narrative/policy draft. */
export function StatusSection({ systemId, controlId, d, reload }: { systemId: string; controlId: string; d: Row; reload: () => void }) {
  const { can } = useAuth();
  const [v, setV] = useState(d.assignment.implementation_status);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setV(d.assignment.implementation_status); setErr(""); }, [d.assignment.id, d.assignment.implementation_status]); // eslint-disable-line react-hooks/exhaustive-deps
  const last = d.status_last_changed;
  const save = async () => {
    setBusy(true); setErr("");
    try { await api.put(`/systems/${systemId}/workbench/controls/${controlId}/status`, { implementation_status: v });
      toast.success(`Implementation status saved: ${v.replace(/_/g, " ")}`, { description: "Next step: describe how this control is implemented in the Implementation statement below, then attach evidence.",
        action: { label: "Go to statement", onClick: () => document.getElementById("wb-narrative")?.scrollIntoView({ behavior: "smooth" }) } });
      reload(); }
    catch (e) { setErr(`The status was not saved: ${errorMessage(e)}. ${/permission|forbidden|403/i.test(errorMessage(e)) ? "Your current role can't change it – switch to ISSO or System Owner in “Acting as”." : "Please try again."}`); } finally { setBusy(false); }
  };
  return (
    <Panel title="Status" testId="wb-status-section">
      <p className="mb-2 text-[12px] text-slate-600">Record where this control stands. Change the implementation status and press <b>Save status</b> – it is saved on its own, separate from the statement drafts below.</p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-[12px] font-medium" title="Implementation status (RMF Implement step): how far your organization has put this control in place – planned, partially implemented, implemented, inherited from a common control provider, or not applicable.">Implementation status <span className="cursor-help text-slate-400">ⓘ</span>
          <select className="input mt-1 w-56" value={v} onChange={(e) => setV(e.target.value)} disabled={!can("implementation.write")} data-testid="wb-impl-status">{STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select></label>
        <Gated perm="implementation.write"><button className="btn-primary" disabled={busy || v === d.assignment.implementation_status} onClick={save} data-testid="wb-status-save" title={v === d.assignment.implementation_status ? "Choose a different status first" : undefined}>{busy ? "Saving…" : "Save status"}</button></Gated>
        <div className="text-[12px]" title="Assessment status (RMF Assess step): the Security Control Assessor's (SCA) result – satisfied or other than satisfied. Only the SCA can set it.">Assessment status <span className="cursor-help text-slate-400">ⓘ</span>: <b data-testid="wb-assessment-status">{d.assignment.assessment_status.replace(/_/g, " ")}</b> <span className="text-[11px] text-slate-500">(set by the assessor in “SCA assessment” below)</span></div>
      </div>
      {err && <div className="mt-2 text-[12px] text-rose-700" role="alert" data-testid="wb-status-error">{err}</div>}
      <div className="mt-2 text-[11px] text-slate-500" data-testid="wb-status-last-changed">{last ? `Last changed by ${last.by} at ${new Date(last.at).toLocaleString()}` : "Not changed since the system was registered"}</div>
    </Panel>);
}

export function MappedPoliciesPanel({ d }: { d: Row }) {
  const rows: Row[] = d.policy_mappings || [];
  return (
    <Panel title={`Mapped policies (${rows.length})`} testId="wb-mapped-policies">
      {rows.length === 0 ? <div className="text-[12px] text-slate-500">No policy is mapped to this control yet (Policy Auditor → Map to control).</div>
        : rows.map((m) => <div key={m.id} className="border-b border-slate-100 py-1 text-[12px]" data-testid={`wb-mapped-policy-${m.policy_id}`}>
          <Link className="font-medium text-blue-800 underline" to={`/policy-auditor/${m.policy_id}`}>{m.policy_title} v{m.policy_version}</Link> · {m.status} · {m.confidence} · {m.source.replace(/_/g, " ")}
          <div className="text-[10px] text-slate-500">{m.decider_name ? `${m.decider_name} at ${new Date(m.decided_at).toLocaleString()}` : `proposed by the parser at ${new Date(m.created_at).toLocaleString()}`}</div></div>)}
    </Panel>);
}
