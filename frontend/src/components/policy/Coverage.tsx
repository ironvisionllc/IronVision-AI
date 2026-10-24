import { ReactElement, useState } from "react";
import { TableScroll } from "@/components/common/TableScroll";
import { Link } from "react-router-dom";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { showNextStep } from "@/components/common/NextStep";

export const CCI_TIP = "A CCI (Control Correlation Identifier) is DISA's ID for one testable requirement inside a NIST control – e.g. RA-1 is split into 21 CCIs such as “define the review frequency”. Assessment objectives (SP 800-53A) are NIST's own per-requirement checks.";
export const TECH_TIP = "Policy vs implementation: a policy can show that this requirement is defined and documented, but not that the system does it. Implemented is only suggested when current, passing technical evidence (scan, STIG checklist or configuration) is also linked.";
const TONE: Record<string, string> = { met: "bg-emerald-100 text-emerald-800", partial: "bg-amber-100 text-amber-900", missing: "bg-rose-100 text-rose-800" };
const fmt = (c: string) => c.toUpperCase().replace(/\.(\d+)$/, "($1)");

export function CovBadge({ s, testId }: { s: string; testId?: string }) {
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${TONE[s] || "bg-slate-100"}`} data-testid={testId}>{s}</span>;
}

/** One requirement row: status, CCI/objective text, matched snippets with location, extracted value, and what would satisfy it. */
export function RequirementRow({ r, actions }: { r: Row; actions?: ReactElement | null }) {
  const st = r.effective || r.status;
  return (
    <tr className="border-t border-slate-100 align-top" data-testid={`req-${r.requirement_id || r.label}`}>
      <td className="py-1 pr-2"><CovBadge s={st} />{r.override && <div className="text-[10px] text-slate-500" title={r.override.reason} data-testid={`req-covered-elsewhere-${r.requirement_id || r.label}`}>covered elsewhere (not policy text): {r.override.reason}</div>}
        {r.confidence && <div className={`text-[10px] ${r.confidence === "Low" && st !== "missing" ? "font-semibold text-amber-800" : "text-slate-500"}`} data-testid={`req-confidence-${r.requirement_id || r.label}`}>{r.confidence}{r.confidence === "Low" && st !== "missing" ? " – review needed" : ""}</div>}
        {r.basis && <div className="text-[10px] text-slate-500" title="How the match was made">{r.basis}</div>}
        {r.kind === "technical" && <div className="text-[10px] text-amber-800" title={TECH_TIP} data-testid={`req-technical-${r.requirement_id || r.label}`}>needs technical evidence</div>}</td>
      <td className="py-1 pr-2 font-mono text-[11px]" title={r.requirement_type === "cci" || r.type === "cci" ? CCI_TIP : "SP 800-53A assessment objective"}>{r.label}</td>
      <td className="py-1 pr-2 text-[11px]">{r.text}{r.parameter && <div className="mt-0.5 text-slate-600">{r.parameter}: <b className="font-mono">{r.parameter_value || r.value || "—"}</b></div>}</td>
      <td className="py-1 pr-2 text-[11px] text-slate-700">{r.reason}
        {(r.snippets || []).slice(0, 2).map((s: Row, i: number) => <blockquote key={i} className="mt-1 border-l-2 border-slate-300 pl-2 text-slate-600">“{s.text}”<div className="text-[10px] text-slate-500">{s.location}</div></blockquote>)}
        {st !== "met" && r.needs && <div className="mt-1 text-[10px] text-rose-800">Would satisfy it: {r.needs}</div>}
        {r.linked && <div className="mt-1 text-[10px] text-emerald-800">Linked as evidence by {r.linked.by} · {String(r.linked.at).slice(0, 10)}</div>}</td>
      <td className="py-1 text-right">{actions}</td>
    </tr>);
}

/** Policy detail: per-control expandable CCI / objective checklist with gap actions. */
export function CoverageChecklist({ policyId, data, systemId, canMap, canPoam, reload, setMsg }: { policyId: string; data: Row; systemId?: string; canMap: boolean; canPoam: boolean; reload: () => void; setMsg: (m: string) => void }) {
  const [onlyMapped, setOnlyMapped] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const status = Object.fromEntries((data.control_mappings || []).map((m: Row) => [m.control_id, m.status]));
  const rows = (data.coverage || []).filter((c: Row) => !onlyMapped || status[c.control_id] === "mapped");
  const elsewhere = async (r: Row) => {
    const reason = window.prompt(`Why is ${r.label} covered elsewhere? Name the other document or evidence (min 10 characters).`);
    if (!reason) return;
    try { await api.post(`/policies/${policyId}/coverage/${r.id}/covered-elsewhere`, { reason }); setMsg(`${r.label} marked as covered elsewhere – recorded separately; the policy-text result and status suggestions are unchanged (reason kept in the audit log).`); reload(); }
    catch (e) { setMsg(errorMessage(e)); }
  };
  const poam = async (r: Row) => {
    if (!systemId) { setMsg("Link this policy to a system first – a POA&M belongs to a system."); return; }
    try { const x = await api.post<Row>(`/policies/${policyId}/coverage/${r.id}/poam`, { system_id: systemId }); setMsg(`POA&M ${x.data.human_id} created for ${r.label}.`);
      showNextStep({ message: `POA&M ${x.data.human_id} created (prefilled with the gap).`, label: "add milestones in the POA&M", to: `/poams/${x.data.poam_id}` }); }
    catch (e) { setMsg(errorMessage(e)); }
  };
  return (
    <div data-testid="coverage-checklist">
      <div className="mb-2 flex flex-wrap items-center gap-3 text-[12px]">
        <label><input type="checkbox" checked={onlyMapped} onChange={(e) => setOnlyMapped(e.target.checked)} data-testid="coverage-only-mapped" /> Show only mapped (approved) controls</label>
        {systemId && rows.length > 0 && <Link className="text-blue-800 underline" to={`/systems/${systemId}/controls?policy=${policyId}`} data-testid="coverage-view-in-workbench">View these {rows.length} controls in the Workbench →</Link>}
        {systemId && <Link className="text-blue-800 underline" to={`/ccis?policy=${policyId}&mapped=yes`} data-testid="coverage-view-ccis">View the CCIs →</Link>}
        <span className="text-slate-500" title={CCI_TIP}>What is a CCI? ⓘ</span>
        <span className="text-slate-500" title={TECH_TIP} data-testid="coverage-policy-vs-impl">Policy vs implementation ⓘ</span>
      </div>
      {data.superseded_by && <div className="mb-2 rounded bg-amber-50 p-2 text-[12px] text-amber-900" data-testid="coverage-superseded">This version is superseded by <Link className="underline" to={`/policy-auditor/${data.superseded_by.id}`}>v{data.superseded_by.version}</Link> – coverage, filters and status suggestions use the current version only.</div>}
      {rows.length === 0 && <p className="text-[12px] text-slate-600" data-testid="coverage-empty">No requirement checklist yet. It is built for each control this policy maps to (approved, or proposed with High/Medium confidence) when the policy is analysed.</p>}
      {rows.map((c: Row) => (
        <div key={c.control_id} className="border-t border-slate-100 py-2" data-testid={`coverage-${c.control_id}`}>
          <button className="flex w-full items-center gap-2 text-left text-[12px]" onClick={() => setOpen(open === c.control_id ? null : c.control_id)} data-testid={`coverage-toggle-${c.control_id}`}>
            <CovBadge s={c.summary.state === "gaps" ? "missing" : c.summary.state || "missing"} /><b className="font-mono">{fmt(c.control_id)}</b><span>{c.line}</span>
            <span className="ml-auto text-[11px] text-slate-500">{status[c.control_id] || ""} · {open === c.control_id ? "hide" : "show"} checklist</span></button>
          {open === c.control_id && <TableScroll><table className="mt-2 w-full"><thead><tr className="text-left text-[10px] text-slate-500"><th>Status</th><th>ID</th><th>Requirement</th><th>Evidence in the policy</th><th /></tr></thead><tbody>
            {c.requirements.map((r: Row) => <RequirementRow key={r.id} r={r} actions={r.effective !== "met" ? <div className="flex flex-col gap-1">
              {canPoam && <button className="btn-secondary px-1.5 py-0.5 text-[10px]" onClick={() => poam(r)} data-testid={`gap-poam-${r.requirement_id}`}>Add to POA&M</button>}
              {canMap && <button className="btn-secondary px-1.5 py-0.5 text-[10px]" onClick={() => elsewhere(r)} data-testid={`gap-elsewhere-${r.requirement_id}`}>Mark as covered elsewhere</button>}</div> : null} />)}
          </tbody></table></TableScroll>}
        </div>))}
    </div>);
}

/** Workbench control detail: policy coverage per CCI / objective. */
export function ControlPolicyCoverage({ items }: { items: Row[] }) {
  const [open, setOpen] = useState(false);
  if (!items?.length) return null;
  return (
    <div className="mt-2 rounded bg-slate-50 px-2 py-1 text-[11px]" data-testid="wb-policy-coverage">
      {items.map((p) => <div key={p.policy_id}><CovBadge s={p.summary.state === "gaps" ? "missing" : p.summary.state || "missing"} /> <Link className="text-blue-800 underline" to={`/policy-auditor/${p.policy_id}`}>{p.policy_title}</Link>: {p.line}</div>)}
      <button className="text-blue-800 underline" onClick={() => setOpen(!open)} data-testid="wb-policy-coverage-toggle" title={CCI_TIP}>{open ? "Hide" : "Show"} coverage per CCI</button>
      {open && items.map((p) => <TableScroll key={p.policy_id}><table className="mt-1 w-full"><tbody>{p.requirements.map((r: Row) => <RequirementRow key={r.id} r={{ ...r, requirement_type: r.type }} />)}</tbody></table></TableScroll>)}
    </div>);
}
