import { PackageDocuments } from "@/components/rmf/PackageDocuments";
import { PageSizeSelect, usePageSize } from "@/components/common/PageSize";
import { SimulatedSignatureNote } from "@/components/shell/Sandbox";
import { OscalPanel } from "@/pages/Phase4Pages";
import { AiModelSettings } from "@/components/admin/AiModelSettings";
import { IdentityMappings } from "@/components/admin/IdentityMappings";
import { useEffect, useState, Fragment } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Search } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { S, Table } from "@/components/common/Bits";
import { AccessDenied } from "@/components/common/AccessDenied";
import { fmtDate } from "@/lib/format";

export function GlobalSearch() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<Row[] | null>(null);
  const nav = useNavigate();
  useEffect(() => {
    if (q.trim().length < 2) { setRes(null); return; }
    const t = setTimeout(async () => setRes((await api.get<Row[]>("/search", { params: { q, system_id: localStorage.getItem("aegis.selected_system") || undefined } })).data), 250);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-500" aria-hidden />
      <input aria-label="Global search" className="input w-72 !py-1 !pl-8 text-[12px]" placeholder="Search systems, controls, findings, POA&Ms…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="global-search-input" />
      {res && <div className="iv-popover absolute z-50 mt-1.5 max-h-96 w-[28rem] overflow-y-auto" data-testid="global-search-results" onKeyDown={(e) => e.key === "Escape" && setRes(null)}>
        {res.length === 0 && <div className="p-3 text-[12px] text-slate-500">No authorized results</div>}
        {res.map((r, i) => <button key={i} className="block w-full border-b border-slate-100 px-3 py-1.5 text-left text-[12px] hover:bg-blue-50" onClick={() => { setRes(null); setQ(""); if (r.system_id) localStorage.setItem("aegis.selected_system", r.system_id); nav(r.link); }} data-testid={`search-result-${i}`}>
          <span className="mr-2 rounded-md bg-blue-50 px-1.5 text-[10px] font-semibold uppercase text-blue-800">{r.type}</span>{r.label}{r.group && <span className="ml-1 text-[10px] text-slate-500">[{r.group}]</span>}</button>)}
      </div>}
    </div>
  );
}

export function AuthorizationPage() {
  const { id = "" } = useParams();
  const { can, user } = useAuth();
  const { data, reload } = useApi<Row>(`/systems/${id}/authorization`);
  const [msg, setMsg] = useState("");
  const [f, setF] = useState<Row>({ decision: "ATO", conditions: "", expiration: "", rationale: "" });
  if (!data) return null;
  const pk = data.package;
  const pending = data.requests.find((r: Row) => r.status === "pending");
  const isAo = !!user && user.roles.some((r) => r.role === "ao");
  const submit = async () => { const j = window.prompt("Package submission note (min 10 chars)"); if (!j) return; try { await api.post(`/systems/${id}/authorization/submit`, { justification: j }); setMsg("Package submitted – ISSM endorses, then AO decides"); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  const decide = async () => { try { await api.post(`/systems/${id}/authorization-decision`, { ...f, request_id: pending.id, expiration: f.expiration || null, conditions: f.conditions || null }); setMsg("Authorization decision recorded"); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  return (
    <div data-testid="authorization-page">
      <PageHeader title={`Authorization package · ${pk.system.acronym}`} subtitle={`${pk.system.authorization_status} · expires ${pk.system.authorization_expiration ?? "—"}`}>
        {can("implementation.write") && !pending && <button className="btn-primary" onClick={submit} data-testid="submit-package-btn">Submit package for review</button>}
      </PageHeader>
      {msg && <div className="panel mb-4 p-3 text-[13px]" role="alert" data-testid="authz-msg">{msg}</div>}
      <div className="mb-5"><PackageDocuments systemId={id} acronym={pk.system.acronym} /></div>
      <div className="mb-5"><OscalPanel systemId={id} /></div>
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="SSP summary" testId="package-ssp"><div className="text-[13px]">{pk.ssp.assigned} controls · {pk.ssp.with_any_narrative} with statements · {pk.ssp.approved_narratives} approved</div></Panel>
        <Panel title="Assessment results (SCA)" testId="package-assessment"><div className="flex flex-wrap gap-2">{Object.entries(pk.assessment).map(([k, v]) => <S key={k} v={k} label={`${k.replace(/_/g, " ")}: ${v}`} />)}</div></Panel>
        <Panel title={`Open POA&Ms (${pk.open_poams.length})`} testId="package-poams">{pk.open_poams.slice(0, 12).map((p: Row) => <div key={p.id} className="text-[12px]"><Link className="font-mono text-blue-800 underline" to={`/poams/${p.id}`}>{p.human_id}</Link> {p.weakness} · {p.severity} · due {p.due_date}</div>)}</Panel>
        <Panel title="Risk acceptances" testId="package-risk">{pk.risk_acceptances.length === 0 ? "None" : pk.risk_acceptances.map((p: Row) => <div key={p.id} className="text-[12px]">{p.human_id} expires {p.expires}</div>)}</Panel>
        <Panel title="Authorization decision (AO only)" testId="authz-decision-panel">
          {!pending ? <div className="text-[12px] text-slate-500">No pending package review.</div> : pending.assigned_role !== "ao" ? <div className="text-[12px] text-slate-600" data-testid="authz-awaiting-issm">Awaiting ISSM endorsement (<Link className="text-blue-800 underline" to={`/reviews/${pending.id}`}>{pending.human_id}</Link>).</div>
            : !isAo ? <div className="text-[12px] text-slate-600" data-testid="authz-not-ao">Only the Authorizing Official can record this decision (decision rule).</div>
              : <div className="grid gap-2 text-[13px]">
                <select className="input" value={f.decision} onChange={(e) => setF({ ...f, decision: e.target.value })} data-testid="authz-decision-select">{[["ATO", "ATO"], ["ATO_with_conditions", "ATO with conditions"], ["IATT", "IATT"], ["DATO", "DATO (denial)"]].map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
                <input className="input" type="date" value={f.expiration} onChange={(e) => setF({ ...f, expiration: e.target.value })} data-testid="authz-expiration" />
                <textarea className="input" placeholder="Conditions" value={f.conditions} onChange={(e) => setF({ ...f, conditions: e.target.value })} data-testid="authz-conditions" />
                <textarea className="input" placeholder="Rationale (required)" value={f.rationale} onChange={(e) => setF({ ...f, rationale: e.target.value })} data-testid="authz-rationale" />
                <SimulatedSignatureNote />
                <button className="btn-primary" onClick={decide} data-testid="authz-record-btn">Record decision (simulated signature – not CAC/PIV)</button></div>}
        </Panel>
        <Panel title="Decision history" testId="authz-history">{data.decisions.map((d: Row) => <div key={d.id} className="border-b border-slate-100 py-1 text-[12px]"><b>{d.decision}</b> by {d.decider_name} · {fmtDate(d.created_at)} · expires {d.expiration ?? "—"}<div className="text-slate-600">{d.rationale}</div>{d.conditions && <div>Conditions: {d.conditions}</div>}</div>)}</Panel>
      </div>
    </div>
  );
}

export function AssessmentPanel({ systemId, controlId, objectives, onDone }: { systemId: string; controlId: string; objectives: Row[]; onDone: () => void }) {
  const { can } = useAuth();
  const { data, reload } = useApi<Row[]>(`/systems/${systemId}/controls/${controlId}/assessments`);
  const [f, setF] = useState<Row>({ objectives: [], methods: [], result: "satisfied", findings_text: "" });
  const [msg, setMsg] = useState("");
  const tog = (k: string, v: string) => setF({ ...f, [k]: f[k].includes(v) ? f[k].filter((x: string) => x !== v) : [...f[k], v] });
  const save = async () => { try { await api.post(`/systems/${systemId}/controls/${controlId}/assessments`, f); setMsg("Assessment recorded"); reload(); onDone(); } catch (e) { setMsg(errorMessage(e)); } };
  return (
    <div data-testid="wb-assessment">
      {(data || []).map((a) => <div key={a.id} className="border-b border-slate-100 py-1 text-[12px]"><S v={a.result} /> by {a.assessor_name} · {a.methods.join(", ")} · {fmtDate(a.created_at)}<div className="text-slate-600">{a.findings_text}</div></div>)}
      {can("assessment.perform") ? <div className="mt-2 text-[12px]">
        <div className="font-medium">Objectives assessed (800-53A)</div>
        <div className="max-h-32 overflow-y-auto">{objectives.filter((o) => o.prose).slice(0, 20).map((o) => <label key={o.id ?? o.label} className="flex gap-1"><input type="checkbox" checked={f.objectives.includes(o.label ?? o.id)} onChange={() => tog("objectives", o.label ?? o.id)} data-testid={`obj-${o.label ?? o.id}`} />{o.label ?? o.id}: {String(o.prose).slice(0, 90)}</label>)}</div>
        <div className="mt-1 flex gap-3">{["examine", "interview", "test"].map((m) => <label key={m}><input type="checkbox" checked={f.methods.includes(m)} onChange={() => tog("methods", m)} data-testid={`method-${m}`} /> {m}</label>)}</div>
        <textarea className="input mt-1" placeholder="Assessment findings" value={f.findings_text} onChange={(e) => setF({ ...f, findings_text: e.target.value })} data-testid="assessment-findings" />
        <div className="mt-1 flex gap-2"><select className="input w-56" value={f.result} onChange={(e) => setF({ ...f, result: e.target.value })} data-testid="assessment-result"><option value="satisfied">Satisfied</option><option value="other_than_satisfied">Other than satisfied</option></select>
          <button className="btn-primary" disabled={!f.objectives.length || !f.methods.length} onClick={save} data-testid="assessment-save">Record assessment</button></div>
      </div> : <div className="text-[11px] text-slate-500">Only an independent SCA can record assessment results (the only path that sets assessment status).</div>}
      {msg && <div className="mt-1 text-[12px]" role="alert" data-testid="assessment-msg">{msg}</div>}
    </div>
  );
}

export function NotificationPrefsPage() {
  const { data, reload } = useApi<Row>("/notification-prefs");
  if (!data) return null;
  return (
    <div data-testid="notification-prefs-page">
      <PageHeader title="Notification preferences" subtitle={data.email.note} />
      <Panel testId="prefs-panel">{data.kinds.map((k: Row) => <label key={k.kind} className="flex items-center justify-between border-b border-slate-100 py-2 text-[13px]">{k.label}
        <input type="checkbox" checked={k.enabled} onChange={async (e) => { await api.put("/notification-prefs", { kind: k.kind, enabled: e.target.checked }); reload(); }} data-testid={`pref-${k.kind}`} /></label>)}</Panel>
    </div>
  );
}

export function AuditLogPage() {
  const [f, setF] = useState<Row>({ actor: "", action: "", entity_type: "", outcome: "", date_from: "", date_to: "", page: 1, include_system: false });
  const [size, setSize] = usePageSize("audit-log");
  const params = { ...Object.fromEntries(Object.entries(f).filter(([, v]) => v !== "" && v !== false)), page_size: size || 1000 };
  const { data, error, denied } = useApi<Row>("/audit-log", params);
  const exp = async (fmt: string) => { const r = await api.get("/audit-log", { params: { ...params, fmt }, responseType: "blob" }); const a = document.createElement("a"); a.href = URL.createObjectURL(r.data as Blob); a.download = `audit.${fmt}`; a.click(); };
  if (denied) return <AccessDenied denied={denied} area="the Audit Log" />;
  if (error) return <div className="panel p-6 text-sm text-rose-700" data-testid="audit-log-error">{error}</div>;
  return (
    <div data-testid="audit-log-page">
      <PageHeader title="Audit log" subtitle={data ? `Hash chain: ${data.chain.valid ? "VALID" : "BROKEN at " + data.chain.first_invalid_seq} (${data.chain.checked} events)` : ""}>
        <button className="btn-secondary" onClick={() => exp("csv")} data-testid="audit-export-csv">Export CSV</button><button className="btn-secondary" onClick={() => exp("json")} data-testid="audit-export-json">Export JSON</button>
      </PageHeader>
      <div className="mb-3 flex flex-wrap gap-2">
        {[["actor", "Actor email"], ["action", "Action prefix (e.g. authz, poam)"], ["entity_type", "Entity type"]].map(([k, l]) => <input key={k} className="input w-52" placeholder={l} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value, page: 1 })} data-testid={`audit-filter-${k}`} />)}
        <label className="flex items-center gap-1 text-[12px]" data-testid="audit-include-system"><input type="checkbox" checked={!!f.include_system} onChange={(e) => setF({ ...f, include_system: e.target.checked, page: 1 })} />Include system events</label>
        <span className="self-center text-[11px] text-slate-500">{f.include_system ? "All events" : "Human actions"}</span>
        <select className="input w-36" value={f.outcome} onChange={(e) => setF({ ...f, outcome: e.target.value, page: 1 })} data-testid="audit-filter-outcome"><option value="">Any outcome</option><option value="success">success</option><option value="denied">denied</option><option value="failure">failure</option></select>
        <input type="date" className="input w-40" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value, page: 1 })} data-testid="audit-filter-from" />
        <input type="date" className="input w-40" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value, page: 1 })} data-testid="audit-filter-to" />
      </div>
      {data && <div className="mb-2 flex flex-wrap gap-1 text-[10px]" data-testid="audit-categories">{Object.entries(data.categories).map(([k, v]) => <button key={k} className="rounded bg-slate-100 px-1.5" onClick={() => setF({ ...f, action: k, page: 1 })}>{k} {String(v)}</button>)}</div>}
      <Panel testId="audit-table-panel">
        <Table head={["#", "When", "Actor", "Action", "Outcome", "Entity", "Details"]} testId="audit-table">
          {data?.items.map((e: Row) => <tr key={e.seq}><td className="td font-mono text-[11px]">{e.seq}</td><td className="td font-mono text-[11px]">{fmtDate(e.occurred_at)}</td>
            <td className="td text-[12px]">{e.actor_name ?? e.actor_email}<div className="text-[10px] text-slate-500">{(e.actor_roles || []).join("/")}</div></td><td className="td font-mono text-[11px]">{e.action}</td>
            <td className="td"><S v={e.outcome === "denied" ? "failing" : "current"} label={e.outcome} /></td><td className="td text-[11px]">{e.entity_type} {String(e.entity_id ?? "").slice(0, 8)}</td>
            <td className="td max-w-[300px] truncate font-mono text-[10px]">{JSON.stringify(e.details ?? e.after ?? {})}</td></tr>)}
        </Table>
        <div className="mt-2 flex items-center gap-2 text-[12px]"><PageSizeSelect value={size} onChange={(n) => { setSize(n); setF({ ...f, page: 1 }); }} testId="audit-log-page-size" /><button className="btn-secondary px-2 py-1 text-xs" disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })} data-testid="audit-prev">Prev</button>
          Page {f.page} · {data ? data.total : "…"} events<button className="btn-secondary px-2 py-1 text-xs" disabled={!data || f.page * data.page_size >= data.total} onClick={() => setF({ ...f, page: f.page + 1 })} data-testid="audit-next">Next</button></div>
      </Panel>
    </div>
  );
}

export function AdminPhase3Panels() {
  const { data: users, reload } = useApi<Row[]>("/admin/users");
  const { data: sec } = useApi<Row>("/admin/security");
  const { data: ai, reload: reloadAi } = useApi<Row>("/admin/ai-settings");
  const { data: rules, reload: reloadRules } = useApi<Row[]>("/decision-rules");
  const [inv, setInv] = useState<Row>({ email: "", display_name: "", role: "isso" });
  const [msg, setMsg] = useState("");
  const [hist, setHist] = useState<Row[] | null>(null);
  const run = async (fn: () => Promise<{ data: Row }>, ok: (d: Row) => string) => { try { const r = await fn(); setMsg(ok(r.data)); reload(); reloadAi(); reloadRules(); } catch (e) { setMsg(errorMessage(e)); } };
  return (
    <div className="space-y-5" data-testid="admin-phase3">
      {msg && <div className="panel p-3 text-[13px]" role="alert" data-testid="admin3-msg">{msg}</div>}
      <Panel title="Application security (truthful status)" testId="security-panel">
        {sec && <dl className="grid grid-cols-[180px_1fr] gap-y-1 text-[13px]">{[["Sign-in", sec.sign_in], ["Cryptography", sec.cryptography], ["Session timeout", `${sec.session_timeout_minutes} min – ${sec.session_timeout_note}`], ["Markings banner", sec.markings_banner], ["Tenant separation", sec.tenant_separation], ["Secrets", sec.secrets]].map(([k, v]) => <Fragment key={String(k)}><dt className="text-slate-500">{k}</dt><dd data-testid={`sec-${String(k).toLowerCase().replace(/\s+/g, "-")}`}>{v}</dd></Fragment>)}</dl>}
        <button className="btn-secondary mt-2" onClick={() => { const t = window.prompt("Markings banner text", sec?.markings_banner); if (t) run(() => api.put("/admin/banner", { text: t }), () => "Banner updated"); }} data-testid="edit-banner-btn">Edit banner</button>
      </Panel>
      <Panel title="Users & roles" testId="users-panel" actions={<div className="flex gap-1">
        <input className="input w-48" placeholder="email@x.demo" value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} data-testid="invite-email" />
        <input className="input w-40" placeholder="Display name" value={inv.display_name} onChange={(e) => setInv({ ...inv, display_name: e.target.value })} data-testid="invite-name" />
        <select className="input w-36" value={inv.role} onChange={(e) => setInv({ ...inv, role: e.target.value })} data-testid="invite-role">{["system_owner", "isso", "issm", "sca", "ao", "devsecops", "leadership_viewer"].map((r) => <option key={r}>{r}</option>)}</select>
        <button className="btn-primary" onClick={() => run(() => api.post("/admin/users", inv), (d) => `DEV ONLY – user created; temporary password (shown once): ${d.temporary_password}`)} data-testid="invite-btn">Invite (dev)</button></div>}>
        <Table head={["User", "Roles & scopes", "Privileged permissions", ""]}>
          {users?.map((u) => <tr key={u.id} data-testid={`user-row-${u.email}`}><td className="td text-[12px]">{u.display_name}<div className="text-[10px] text-slate-500">{u.email}</div></td>
            <td className="td text-[11px]">{u.roles.map((r: Row) => `${r.role}@${r.scope_type}`).join(", ")}</td><td className="td text-[11px]">{u.privileged_permissions.join(", ") || "—"}</td>
            <td className="td"><button className="text-[11px] text-blue-800 underline" onClick={async () => setHist((await api.get<Row[]>(`/admin/users/${u.id}/access-history`)).data)} data-testid={`access-history-${u.email}`}>Access history</button></td></tr>)}
        </Table>
        <div className="mt-1 text-[11px] text-slate-500">System-specific roles: assign/revoke on each System page (audited).</div>
        {hist && <div className="mt-2 max-h-48 overflow-y-auto rounded bg-slate-50 p-2 text-[11px]" data-testid="access-history">{hist.map((h) => <div key={h.seq}>{fmtDate(h.occurred_at)} {h.action} {h.outcome}</div>)}</div>}
      </Panel>
      <IdentityMappings />
      <Panel title="AI administration" testId="ai-admin-panel">
        {ai && <div className="text-[13px]">
          <AiModelSettings ai={ai} onSave={(m) => run(() => api.put("/admin/ai-settings", { model: m }), () => (m ? `AI model set to ${m}` : "AI model override cleared"))} />
          <div className="mt-2 text-[12px] text-slate-500">{ai.provider_note}</div>
          <div>Logging: {ai.logging_policy} · Retrieval: {ai.retrieval_restrictions}</div>
          <div className="mt-1">Human approval required: <b>always on (locked)</b></div>
          <div className="mt-2 flex flex-wrap gap-3">{Object.entries(ai.use_cases).map(([k, v]) => <label key={k} className="flex items-center gap-1"><input type="checkbox" checked={!!v} onChange={(e) => run(() => api.put("/admin/ai-settings", { use_cases: { [k]: e.target.checked } }), () => `AI use case ${k} ${e.target.checked ? "enabled" : "disabled"}`)} data-testid={`ai-usecase-${k}`} />{k}</label>)}</div>
        </div>}
      </Panel>
      <Panel title="Decision rules (versioned)" testId="rules-admin-panel">
        {rules?.map((r) => <div key={r.id} className="flex items-center justify-between border-b border-slate-100 py-1 text-[12px]" data-testid={`rule-admin-${r.request_type}`}>
          <span>{r.type_label} v{r.version}: {r.steps.map((s: Row) => `${s.role}:${s.action}`).join(" → ")}</span>
          <button className="text-blue-800 underline" onClick={() => { const v = window.prompt("Steps as role:action,… (e.g. issm:endorse,ao:decide)", r.steps.map((s: Row) => `${s.role}:${s.action}`).join(",")); if (!v) return; const steps = v.split(",").map((x) => { const [role, action] = x.trim().split(":"); return { role, action }; }); run(() => api.put(`/decision-rules/${r.request_type}`, { steps, label: r.label }), (d) => `Rule saved as v${d.version}`); }} data-testid={`rule-edit-${r.request_type}`}>Edit</button></div>)}
      </Panel>
    </div>
  );
}
