import { PoamImpactBanner } from "@/pages/Phase4Pages";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { ControlLink, S, Sev, Stat, Table } from "@/components/common/Bits";
import { Modal } from "@/components/common/Workflow";
import { fmtDate } from "@/lib/format";

const SEV: Record<string, string> = { critical: "failing", high: "failing", medium: "near_expiration", low: "neutral" };

export function PoamListPage() {
  const { selectedId: sid } = useSystems();
  const [all, setAll] = useState(false);
  const [p, setP] = useState({ q: "", status: "open", severity: "", sort: "human_id", desc: false, page: 1 });
  const { data } = useApi<Row>("/poams", { system_id: all ? undefined : sid || undefined, ...p, q: p.q || undefined, status: p.status || undefined, severity: p.severity || undefined });
  const sm = data?.summary;
  const sortBy = (k: string) => setP({ ...p, sort: k, desc: p.sort === k ? !p.desc : false });
  return (
    <div data-testid="poam-list-page">
      <PageHeader title="POA&M" subtitle={`Plan of Action & Milestones · all counts computed from the database · eMASS: ${sm?.emass_note ?? ""}`}>
        <label className="flex items-center gap-1 text-[12px]"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} data-testid="poam-all-systems" />All my systems</label>
      </PageHeader>
      {sm && (
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-6">
          <Stat label="Open" value={sm.open} testId="poam-card-open" /><Stat label="Overdue" value={sm.overdue} testId="poam-card-overdue" />
          <Stat label="Due ≤ 30 days" value={sm.due_30d} testId="poam-card-due30" /><Stat label="Pending ISSM review" value={sm.pending_issm_review} testId="poam-card-pending-issm" />
          <Stat label="CAT I / high+" value={sm.cat1} testId="poam-card-cat1" /><Stat label="Pending eMASS sync" value={sm.pending_emass_sync} testId="poam-card-emass" hint="open outbound changes in the eMASS queue" />
        </div>
      )}
      <Panel testId="poam-table-panel" actions={
        <div className="flex gap-2">
          <input className="input w-64" placeholder="Search ID, weakness, control, CVE/STIG" value={p.q} onChange={(e) => setP({ ...p, q: e.target.value, page: 1 })} data-testid="poam-search" />
          <select className="input w-44" value={p.status} onChange={(e) => setP({ ...p, status: e.target.value, page: 1 })} data-testid="poam-status-filter">
            <option value="">All statuses</option>{["open", "new", "in_progress", "overdue", "closure_eligible", "closure_review", "risk_acceptance_review", "closed", "risk_accepted"].map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select>
          <select className="input w-32" value={p.severity} onChange={(e) => setP({ ...p, severity: e.target.value, page: 1 })} data-testid="poam-severity-filter"><option value="">Any severity</option>{["critical", "high", "medium", "low"].map((s) => <option key={s}>{s}</option>)}</select>
        </div>}>
        <div className="overflow-x-auto">
          <table className="w-full" data-testid="poam-table">
            <thead><tr>{[["Item ID", "human_id"], ["Weakness"], ["Related control"], ["Severity", "severity"], ["Asset"], ["Source"], ["Owner"], ["Due", "due_date"], ["Milestones"], ["Status", "status"], ["eMASS"]].map(([h, k]) => (
              <th key={h} className="th">{k ? <button onClick={() => sortBy(k)} data-testid={`poam-sort-${k}`}>{h}{p.sort === k ? (p.desc ? " ▼" : " ▲") : ""}</button> : h}</th>))}</tr></thead>
            <tbody>
              {data?.items.map((r: Row) => (
                <tr key={r.id} data-testid={`poam-row-${r.human_id}`}>
                  <td className="td"><Link className="font-mono text-[12px] font-semibold text-blue-800 hover:underline" to={`/poams/${r.id}`}>{r.human_id}</Link></td>
                  <td className="td max-w-[320px] text-[12px]">{r.weakness}</td>
                  <td className="td">{r.control_ids.map((c: string) => <span key={c} className="mr-1"><ControlLink systemId={r.system_id} controlId={c} /></span>)}</td>
                  <td className="td"><S v={SEV[r.severity] ? r.severity : r.severity} /> {r.cat && <Sev v={r.cat} />}</td>
                  <td className="td text-[12px]">{r.asset_names.join(", ") || "—"}</td><td className="td text-[12px]">{r.source_label}</td>
                  <td className="td text-[12px]">{r.owner_name ?? "—"}</td><td className="td font-mono text-[11px]">{r.due_date ?? "—"}</td>
                  <td className="td font-mono text-[12px]">{r.milestones_done} of {r.milestones_total}</td>
                  <td className="td"><S v={r.display_status} testId={`poam-status-${r.human_id}`} /></td><td className="td text-[11px] text-slate-500" data-testid={`poam-emass-${r.human_id}`}>{r.emass_queue_status ? `queue: ${r.emass_queue_status.replace(/_/g, " ")}` : r.emass_status.replace(/_/g, " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-3 flex items-center gap-2 text-[12px]" data-testid="poam-pagination">
          <button className="btn-secondary px-2 py-1 text-xs" disabled={p.page <= 1} onClick={() => setP({ ...p, page: p.page - 1 })} data-testid="poam-prev">Prev</button>
          <span>Page {p.page} · {data?.total ?? 0} items</span>
          <button className="btn-secondary px-2 py-1 text-xs" disabled={!data || p.page * data.page_size >= data.total} onClick={() => setP({ ...p, page: p.page + 1 })} data-testid="poam-next">Next</button>
        </div>
      </Panel>
    </div>
  );
}

export function PoamDetailPage() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const { data, reload } = useApi<Row>(`/poams/${id}`);
  const [msg, setMsg] = useState("");
  const [modal, setModal] = useState<"" | "closure" | "risk" | "extension" | "edit">("");
  const [f, setF] = useState<Row>({ evidence_ids: [] });
  const [ms, setMs] = useState({ title: "", due_date: "" });
  if (!data) return null;
  const p = data.poam;
  const terminal = ["closed", "risk_accepted"].includes(p.status);
  const run = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); setMsg(ok); setModal(""); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  const field = (k: string, label: string, type = "text") => (
    <label className="text-[13px]">{label}<input type={type} className="input" value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`poam-${modal}-${k}`} /></label>);
  return (
    <div data-testid="poam-detail-page">
      <PageHeader title={`${p.human_id} · ${p.weakness}`} subtitle={`System ${p.system_id.slice(0, 8)} · created ${fmtDate(p.created_at)} · eMASS: ${p.emass_status.replace(/_/g, " ")}${p.emass_remote_id ? ` (${p.emass_remote_id})` : ""}`}>
        <div className="flex items-center gap-2">
          <S v={p.display_status} testId="poam-detail-status" />
          {p.display_status !== p.status && <span className="text-[12px] text-slate-500" data-testid="poam-detail-stored-status">· stored status: {p.status.replace(/_/g, " ")}</span>}
        </div>
      </PageHeader>
      {msg && <div className="panel mb-4 p-3 text-[13px]" data-testid="poam-msg">{msg}</div>}
      <PoamImpactBanner p={p} onDone={reload} />
      {p.status === "closure_eligible" && <div className="panel mb-4 border-emerald-300 bg-emerald-50 p-3 text-[13px] text-emerald-900" data-testid="closure-eligible-banner">A rescan observed every linked finding as fixed. This POA&M is NOT closed automatically – request closure with evidence for ISSM approval.</div>}
      {can("poam.manage") && !terminal && (
        <div className="mb-4 flex flex-wrap gap-2" data-testid="poam-actions">
          <button className="btn-secondary" onClick={() => { setF({ owner_id: p.owner_id ?? "", due_date: p.due_date ?? "", remediation_plan: p.remediation_plan ?? "", root_cause: p.root_cause ?? "", resources: p.resources ?? "" }); setModal("edit"); }} data-testid="poam-edit-btn">Edit / assign</button>
          <button className="btn-primary" disabled={!["new", "in_progress", "closure_eligible"].includes(p.status)} onClick={() => { setF({ evidence_ids: [] }); setModal("closure"); }} data-testid="poam-request-closure-btn">Request closure</button>
          <button className="btn-secondary" onClick={() => { setF({}); setModal("risk"); }} data-testid="poam-request-risk-btn">Request risk acceptance</button>
          <button className="btn-secondary" onClick={() => { setF({}); setModal("extension"); }} data-testid="poam-request-extension-btn">Request waiver / extension</button>
        </div>
      )}
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Weakness" testId="poam-weakness">
          <dl className="grid grid-cols-[150px_1fr] gap-y-1.5 text-[13px]">
            {[["Security impact", p.security_impact], ["Severity", `${p.severity ?? "—"} ${p.cat ?? ""}`], ["Source", p.source_label], ["Vuln IDs (CVE/STIG)", (p.vuln_ids || []).join(", ")],
              ["Affected assets", p.asset_names.join(", ") || "—"], ["Root cause", p.root_cause], ["Remediation plan", p.remediation_plan], ["Owner", p.owner_name], ["Resources", p.resources],
              ["Target completion", p.due_date], ["Actual completion", p.actual_completion], ["Risk acceptance", p.risk_acceptance_ref ? `${p.risk_acceptance_ref} (expires ${p.risk_acceptance_expiration})` : "—"]].map(([k, v]) => (
              <><dt key={`k${k}`} className="text-slate-500">{k}</dt><dd key={`v${k}`} data-testid={`poam-field-${String(k).toLowerCase().replace(/[^a-z]+/g, "-")}`}>{v || "—"}</dd></>))}
          </dl>
        </Panel>
        <Panel title="Related control requirements" testId="poam-controls">
          {data.controls.map((c: Row) => <div key={c.control_id} className="mb-2 text-[12px]"><ControlLink systemId={p.system_id} controlId={c.control_id} /> <b>{c.title}</b><div className="line-clamp-3 text-slate-600">{c.statement}</div></div>)}
        </Panel>
        <Panel title={`Linked findings (${data.findings.length})`} testId="poam-findings">
          <Table head={["Finding", "Asset", "State", "Remediation"]}>
            {data.findings.map((x: Row) => <tr key={x.id}><td className="td text-[12px]"><Link className="text-blue-800 hover:underline" to={`/findings/${x.id}`} data-testid={`finding-link-${x.id}`}>{x.vuln_id ?? x.plugin_id} {x.title}</Link></td>
              <td className="td text-[12px]">{x.asset_name}</td><td className="td"><S v={x.current_state} /></td><td className="td"><S v={x.remediation_status ?? "open"} testId={`finding-remediation-${x.id}`} /></td></tr>)}
          </Table>
        </Panel>
        <Panel title="Detection & closure evidence" testId="poam-evidence">
          {[["Detection", data.detection_evidence], ["Closure", data.closure_evidence]].map(([k, list]) => (
            <div key={k as string} className="mb-2 text-[12px]"><b>{k as string}:</b> {(list as Row[]).length === 0 ? "—" : (list as Row[]).map((e) => <Link key={e.id} to="/evidence-ledger" className="mr-2 text-blue-800 underline">{e.name} ({e.sha256.slice(0, 10)}…)</Link>)}</div>))}
        </Panel>
        <Panel title="Milestones" testId="poam-milestones">
          {data.milestones.map((m: Row) => (
            <div key={m.id} className="flex items-center justify-between border-b border-slate-100 py-1.5 text-[12px]" data-testid={`milestone-${m.id}`}>
              <span>{m.title} · due {m.due_date ?? "—"}</span>
              <span className="flex items-center gap-2"><S v={m.status} />{can("poam.manage") && !terminal && m.status !== "completed" &&
                <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => run(() => api.patch(`/poam-milestones/${m.id}`, { status: "completed" }), "Milestone completed")} data-testid={`milestone-complete-${m.id}`}>Complete</button>}</span>
            </div>))}
          {can("poam.manage") && !terminal && <div className="mt-2 flex gap-2">
            <input className="input" placeholder="New milestone" value={ms.title} onChange={(e) => setMs({ ...ms, title: e.target.value })} data-testid="milestone-title" />
            <input type="date" className="input w-40" value={ms.due_date} onChange={(e) => setMs({ ...ms, due_date: e.target.value })} data-testid="milestone-due" />
            <button className="btn-secondary" disabled={ms.title.length < 3} onClick={() => run(() => api.post(`/poams/${id}/milestones`, { title: ms.title, due_date: ms.due_date || undefined }).then(() => setMs({ title: "", due_date: "" })), "Milestone added")} data-testid="milestone-add">Add</button></div>}
        </Panel>
        <Panel title="Reviews & history" testId="poam-history">
          {data.requests.map((r: Row) => <div key={r.id} className="text-[12px]"><Link className="font-mono text-blue-800 underline" to={`/reviews/${r.id}`} data-testid={`poam-review-link-${r.human_id}`}>{r.human_id}</Link> {r.request_type.replace(/_/g, " ")} <S v={r.status} /></div>)}
          <ul className="mt-2 max-h-60 overflow-y-auto text-[11px] text-slate-600">{data.history.map((h: Row) => <li key={h.id}>{fmtDate(h.created_at)} · {h.actor_name ? `${h.actor_name} (${(h.actor_roles || []).map((x: string) => x.toUpperCase()).join("/")})` : h.actor_email} · <b>{h.action}</b> {h.details ? JSON.stringify(h.details).slice(0, 120) : ""}</li>)}</ul>
        </Panel>
      </div>
      {modal === "edit" && <Modal title="Edit / assign POA&M" onClose={() => setModal("")} testId="poam-edit-modal">
        <div className="grid gap-2"><OwnerSelect value={f.owner_id} onChange={(v) => setF({ ...f, owner_id: v })} />{field("due_date", "Due date", "date")}{field("root_cause", "Root cause")}{field("remediation_plan", "Remediation plan")}{field("resources", "Resources")}</div>
        <button className="btn-primary mt-3" onClick={() => run(() => api.patch(`/poams/${id}`, { ...f, owner_id: f.owner_id || null, due_date: f.due_date || null }), "Saved")} data-testid="poam-edit-save">Save</button></Modal>}
      {modal === "closure" && <Modal title="Request closure (routes to ISSM per decision rule)" onClose={() => setModal("")} testId="poam-closure-modal">
        {field("justification", "Justification (min 10 chars)")}
        <div className="mt-2 max-h-48 overflow-y-auto text-[12px]" data-testid="closure-evidence-list"><div className="font-medium">Closure evidence (required)</div>
          {data.system_evidence.map((e: Row) => <label key={e.id} className="flex gap-2"><input type="checkbox" checked={f.evidence_ids.includes(e.id)} data-testid={`closure-ev-${e.id}`}
            onChange={(x) => setF({ ...f, evidence_ids: x.target.checked ? [...f.evidence_ids, e.id] : f.evidence_ids.filter((i: string) => i !== e.id) })} />{e.name} · {fmtDate(e.collected_at)} · {e.state}</label>)}</div>
        <button className="btn-primary mt-3" onClick={() => run(() => api.post(`/poams/${id}/request-closure`, f), "Closure requested – routed to ISSM")} data-testid="poam-closure-submit">Submit closure request</button></Modal>}
      {modal === "risk" && <Modal title="Request risk acceptance (ISSM endorses → AO decides)" onClose={() => setModal("")} testId="poam-risk-modal">
        {field("justification", "Justification")}{field("expiration", "Acceptance expiration", "date")}
        <button className="btn-primary mt-3" onClick={() => run(() => api.post(`/poams/${id}/request-risk-acceptance`, f), "Risk acceptance requested")} data-testid="poam-risk-submit">Submit</button></Modal>}
      {modal === "extension" && <Modal title="Request waiver / extension (ISSM endorses → AO decides)" onClose={() => setModal("")} testId="poam-extension-modal">
        {field("justification", "Justification")}{field("new_due_date", "New due date", "date")}
        <button className="btn-primary mt-3" onClick={() => run(() => api.post(`/poams/${id}/request-extension`, f), "Extension requested")} data-testid="poam-extension-submit">Submit</button></Modal>}
    </div>
  );
}

function OwnerSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data } = useApi<Row>("/reference/registration");
  const users: Row[] = data?.users ?? [];
  return <label className="text-[13px]">Owner<select className="input" value={value ?? ""} onChange={(e) => onChange(e.target.value)} data-testid="poam-owner-select"><option value="">(unassigned)</option>{users.map((u) => <option key={u.id} value={u.id}>{u.display_name} ({u.email})</option>)}</select></label>;
}
