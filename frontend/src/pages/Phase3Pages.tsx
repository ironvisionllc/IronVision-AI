import { FoundItHere, ReadingReport } from "@/components/policy/Reading";
import { useMemo, useRef, useState } from "react";
import { autosaveCall, useAutoSave } from "@/lib/useAutoSave";
import { AutoSaveStatus } from "@/components/common/AutoSaveStatus";
import { Link, useParams } from "react-router-dom";
import { ImportButton } from "@/components/import/ImportButton";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { ControlLink, NeedSystem, S, Stat, Table } from "@/components/common/Bits";
import { Modal } from "@/components/common/Workflow";
import { MapToControlModal, PolicyMappingsPanel } from "@/components/controls/PolicyMappings";
import { cn, fmtDate } from "@/lib/format";
import { RmfOverview } from "@/pages/RmfStepPages";
import { BulkInheritance, CrmImportModal } from "@/components/inheritance/CrmImport";
import { Gated } from "@/components/common/RoleGate";
import { downloadFile } from "@/lib/download";
import { CCI_TIP, CoverageChecklist } from "@/components/policy/Coverage";
import { useActiveSystemId } from "@/components/rmf/Stepper";
import { ProcessingList } from "@/components/shell/Processing";
import { AnalysisProgress, StageHistory, usePollWhile } from "@/components/policy/AnalysisProgress";

const PROV_FIELDS = ["name", "package", "authorization_type", "basis", "coverage_text", "last_validated_at", "package_expiration"];
const provVals = (p: Row) => Object.fromEntries(PROV_FIELDS.map((k) => [k, p[k] ?? ""]));

/** Editing an existing common-control provider auto-saves its fields (adding a provider stays explicit). */
function ProviderAutoSave({ prov, setProv }: { prov: Row; setProv: (p: Row) => void }) {
  const [init] = useState(() => provVals(prov));
  const val = useMemo(() => provVals(prov), [prov]);
  const as = useAutoSave<Row>({ id: `provider:${prov.id}`, initial: init, value: val, version: prov.updated_at, apply: (x) => setProv({ ...prov, ...x }),
    save: async (x, base) => {
      if (!String(x.name).trim()) throw { status: 422, detail: [{ loc: ["body", "name"] }] };
      return { version: (await autosaveCall<Row>("patch", `/providers/${prov.id}`, Object.fromEntries(Object.entries(x).map(([k, v]) => [k, v || null])), base)).updated_at };
    } });
  return <AutoSaveStatus a={as} testId="provider-autosave" />;
}

export function InheritancePage() {
  const { selectedId: sid } = useSystems();
  const { can, user } = useAuth();
  const { data, reload } = useApi<Row>(sid ? `/systems/${sid}/inheritance` : null);
  const [msg, setMsg] = useState("");
  const [hist, setHist] = useState<Row[] | null>(null);
  const [prov, setProv] = useState<Row | null>(null);
  const [assign, setAssign] = useState<Row | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [upFor, setUpFor] = useState("");
  const [crm, setCrm] = useState<Row | null>(null);
  if (!sid) return <NeedSystem />;
  if (!data) return null;
  const c = data.cards;
  const act = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); setMsg(ok); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  const upload = (f: File) => { const fd = new FormData(); fd.append("file", f); act(() => api.post(`/attestations/${upFor}/evidence`, fd), "Evidence stored in ledger (SHA-256 recorded)"); };
  return (
    <div data-testid="inheritance-page">
      <PageHeader title="Inheritance & Attestations" subtitle="Record which controls another authorized package covers for this system.">
        <Gated perm="system.write"><><button className="btn-secondary" onClick={() => setProv({ name: "" })} data-testid="add-provider-btn">Add provider</button>
          <button className="btn-secondary" onClick={() => setAssign({ control_id: "", responsibility: "shared" })} data-testid="assign-inheritance-btn">Assign inherited/shared control</button></></Gated>
      </PageHeader>
      {msg && <div className="panel mb-4 p-3 text-[13px]" role="alert" data-testid="inheritance-msg">{msg}</div>}
      <div className="panel mb-4 p-4 text-[13px] text-slate-700" data-testid="inheritance-explainer">
        <b>Inherited</b> = the control is fully satisfied by another authorized package or provider (e.g. a data center or a cloud platform); you rely on their authorization. <b>Shared</b> = both parties have responsibilities: the provider covers part and this system must implement and evidence the rest. <b>System-owned</b> = this system does it all.
        <span className="mt-1 block text-[11px] text-slate-500">{c.note} A provider's authorization must be current – expired or soon-expiring providers are flagged below.</span></div>
      {data.providers.filter((p: Row) => ["expired", "expiring"].includes(p.expiry?.status)).map((p: Row) => <div key={p.id} role="alert" data-testid={`provider-warning-${p.id}`}
        className={`mb-3 rounded border p-3 text-[13px] ${p.expiry.status === "expired" ? "border-rose-300 bg-rose-50 text-rose-900" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
        <b>{p.name}:</b> {p.expiry.message} {p.fully_inherited + p.shared} control(s) in this system depend on it.<Gated perm="system.write"><button className="ml-2 underline" onClick={() => setProv(p)}>Update the provider record</button></Gated></div>)}
      <Gated perm="system.write"><BulkInheritance sid={sid} providers={data.providers} onDone={reload} /></Gated>
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Fully inherited" value={c.fully_inherited} testId="inh-card-inherited" hint={`of ${c.assigned}`} />
        <Stat label="Shared" value={c.shared} testId="inh-card-shared" /><Stat label="System-owned" value={c.system_owned} testId="inh-card-system" />
        <Stat label="Manual attestation" value={c.manual_attestation} testId="inh-card-attest" hint={`${c.attestation_overdue} overdue · ${c.attestation_due_30d} due ≤30d (overlaps)`} />
        <Stat label="Reconciles" value={c.sum_check ? "Yes" : "No"} testId="inh-card-sum" hint={`${c.fully_inherited}+${c.shared}+${c.system_owned}=${c.assigned}`} />
      </div>
      <Panel title="Who covers what" className="mb-5" testId="providers-panel">
        <Table head={["Provider", "Package / system it comes from", "Authorization", "Coverage", "Inherited", "Shared", "Last validation", "Authorization expires", ""]}>
          {data.providers.map((p: Row) => <tr key={p.id} data-testid={`provider-${p.id}`}><td className="td text-[12px] font-medium">{p.name}</td><td className="td text-[12px]">{p.package}<div className="text-[10px] text-slate-500">{p.basis}</div></td>
            <td className="td text-[12px]">{p.authorization_type ?? "—"}</td><td className="td max-w-[260px] text-[12px]">{p.coverage_text}</td><td className="td font-mono">{p.fully_inherited}</td><td className="td font-mono">{p.shared}</td>
            <td className="td font-mono text-[11px]">{p.last_validated_at ?? "—"}</td><td className="td font-mono text-[11px]" data-testid={`provider-expiry-${p.id}`}>{p.package_expiration ?? "—"}<div className={p.expiry?.status === "expired" ? "text-rose-700" : p.expiry?.status === "expiring" ? "text-amber-700" : "text-slate-500"}>{p.expiry?.status}</div></td>
            <td className="td"><Gated perm="system.write"><><button className="text-[11px] text-blue-800 underline" onClick={() => setProv(p)} data-testid={`edit-provider-${p.id}`}>Edit</button>
              <button className="ml-2 text-[11px] text-blue-800 underline" onClick={() => setCrm(p)} data-testid={`crm-import-${p.id}`}>Import CRM (CSV / Excel)</button></></Gated></td></tr>)}
        </Table>
      </Panel>
      <Panel title="Shared & inherited controls – provider vs system responsibility" eyebrow="Seeded text is a synthetic demo responsibility matrix · CSV columns: control_id, responsibility, provider_responsibility, customer_responsibility" className="mb-5" testId="shared-panel">
        <Table head={["Control", "Type", "Provider responsibility", "System responsibility", "System part (this system's own evidence)"]}>
          {data.shared.map((x: Row) => <tr key={x.control_id} data-testid={`shared-${x.control_id}`}><td className="td"><ControlLink systemId={sid} controlId={x.control_id} /></td><td className="td text-[11px]">{x.responsibility}{x.provider_name && <div className={x.provider_expiry === "expired" ? "text-rose-700" : "text-slate-500"} data-testid={`shared-provider-${x.control_id}`}>from {x.provider_name}{x.provider_expiry === "expired" ? " (authorization expired)" : x.provider_expiry === "expiring" ? " (expiring soon)" : ""}</div>}</td>
            {x.split_missing ? <td colSpan={2} className="td text-[12px] text-amber-800" data-testid={`split-missing-${x.control_id}`}>Responsibility split not documented</td> : <>
            <td className="td max-w-[320px] text-[12px]">{x.provider_responsibility ?? "—"}</td><td className="td max-w-[320px] text-[12px]">{x.system_responsibility ?? "—"}</td></>}
            <td className="td text-[12px]"><S v={x.system_part.monitoring_status} label="monitoring" /> <S v={x.system_part.evidence_freshness_status} /> <span className="font-mono">{x.system_part.open_findings} open</span></td></tr>)}
        </Table>
        <div className="mt-2 text-[11px] text-slate-500">Provider passing never satisfies the system portion.</div>
      </Panel>
      <Panel title="Manual attestations" testId="attestations-panel">
        <input ref={fileRef} type="file" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} data-testid="attestation-file-input" />
        <Table head={["Control", "Statement", "Owner", "Evidence required", "Due", "Status", "Signature", "Expires", "Actions"]} testId="attestations-table">
          {data.attestations.filter((a: Row) => a.status !== "superseded").map((a: Row) => (
            <tr key={a.id} data-testid={`attestation-${a.control_id}`}>
              <td className="td"><ControlLink systemId={sid} controlId={a.control_id} /> <span className="text-[10px] text-slate-400">v{a.version}</span></td>
              <td className="td max-w-[260px] text-[12px]">{a.statement}</td><td className="td text-[12px]">{a.owner_name}</td><td className="td text-[11px]">{a.evidence_required}{a.evidence_id && <div className="text-emerald-700">evidence attached</div>}</td>
              <td className="td font-mono text-[11px]">{a.due_date}</td><td className="td"><S v={a.display_status} testId={`attestation-status-${a.control_id}`} /></td>
              <td className="td text-[10px]">{a.signature ? <>{a.signature}<div>{fmtDate(a.signed_at)}</div></> : "—"}</td><td className="td font-mono text-[11px]">{a.expires_at ?? "—"}</td>
              <td className="td"><div className="flex flex-wrap gap-1">
                {["pending", "expired"].includes(a.status) && <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => { setUpFor(a.id); fileRef.current?.click(); }} data-testid={`att-upload-${a.control_id}`}>Upload evidence</button>}
                {["pending", "expired"].includes(a.status) && <button className="btn-primary px-2 py-0.5 text-[11px]" disabled={!user || a.owner_id !== user.id} title={!user || a.owner_id !== user.id ? "Only the assigned owner can attest" : ""} onClick={() => act(() => api.post(`/attestations/${a.id}/attest`), "Attested (simulated signature – not CAC/PIV)")} data-testid={`att-attest-${a.control_id}`}>Attest</button>}
                <Gated perm="poam.manage"><button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act(() => api.post(`/attestations/${a.id}/remind`), "Reminder sent")} data-testid={`att-remind-${a.control_id}`}>Send reminder</button></Gated>
                {["signed", "expired"].includes(a.status) && <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act(() => api.post(`/attestations/${a.id}/renew`), "New attestation version created; prior record preserved")} data-testid={`att-renew-${a.control_id}`}>Renew</button>}
                <button className="text-[11px] text-blue-800 underline" onClick={async () => setHist((await api.get<Row[]>(`/attestations/${a.id}/history`)).data)} data-testid={`att-history-${a.control_id}`}>History</button>
                {can("demo.tools") && a.status === "signed" && <button className="btn-secondary px-2 py-0.5 text-[10px]" onClick={() => act(() => api.post(`/demo/attestations/${a.id}/expire`, { days_ago: 1 }), "Demo: attestation expired – cascade ran")} data-testid={`att-demo-expire-${a.control_id}`}>Demo: expire</button>}
              </div></td>
            </tr>))}
        </Table>
      </Panel>
      {hist && <Modal title="Attestation history (signed records preserved)" onClose={() => setHist(null)} testId="att-history-modal">
        {hist.map((h) => <div key={h.id} className="border-b border-slate-100 py-1 text-[12px]">v{h.version} · <S v={h.status} /> · signed {h.signed_at ? `${fmtDate(h.signed_at)} by ${h.signer_name}` : "—"} · expires {h.expires_at ?? "—"}</div>)}</Modal>}
      {prov && <Modal title={prov.id ? "Edit provider" : "Add provider"} onClose={() => setProv(null)} testId="provider-modal">
        {["name", "package", "authorization_type", "basis", "coverage_text", "last_validated_at", "package_expiration"].map((k) => <label key={k} className="block text-[13px]">{({ package: "Package / system it comes from", authorization_type: "Authorization type (e.g. ATO, FedRAMP P-ATO, DoD PA)", package_expiration: "Authorization expiration date", coverage_text: "What it covers" } as Record<string, string>)[k] ?? k.replace(/_/g, " ")}<input className="input" type={k.endsWith("_at") || k.endsWith("expiration") ? "date" : "text"} value={prov[k] ?? ""} onChange={(e) => setProv({ ...prov, [k]: e.target.value })} data-testid={`provider-${k}`} /></label>)}
        <div className="mt-3 flex flex-wrap items-center gap-3"><button className="btn-primary" onClick={() => { const b = Object.fromEntries(PROV_FIELDS.map((k) => [k, prov[k] || null])); act(() => prov.id ? api.patch(`/providers/${prov.id}`, b) : api.post("/providers", b), "Provider saved").then(() => setProv(null)); }} data-testid="provider-save">Save</button>
          {prov.id && <ProviderAutoSave prov={prov} setProv={setProv} />}</div></Modal>}
      {crm && <CrmImportModal provider={crm} sid={sid} onClose={() => setCrm(null)} onDone={reload} />}
      {assign && <Modal title="Assign inheritance" onClose={() => setAssign(null)} testId="assign-modal">
        <div className="grid gap-2 text-[13px]">
          <label>Control<input className="input" placeholder="sc-28" value={assign.control_id} onChange={(e) => setAssign({ ...assign, control_id: e.target.value })} data-testid="assign-control" /></label>
          <label>Responsibility<select className="input" value={assign.responsibility} onChange={(e) => setAssign({ ...assign, responsibility: e.target.value })} data-testid="assign-responsibility">{["inherited", "shared", "system"].map((x) => <option key={x}>{x}</option>)}</select></label>
          <label>Provider<select className="input" value={assign.provider_id ?? ""} onChange={(e) => setAssign({ ...assign, provider_id: e.target.value || null })} data-testid="assign-provider"><option value="">—</option>{data.providers.map((p: Row) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label>Provider responsibility<textarea className="input" value={assign.provider_responsibility_text ?? ""} onChange={(e) => setAssign({ ...assign, provider_responsibility_text: e.target.value })} data-testid="assign-provider-text" /></label>
          <label>System responsibility<textarea className="input" value={assign.system_responsibility_text ?? ""} onChange={(e) => setAssign({ ...assign, system_responsibility_text: e.target.value })} data-testid="assign-system-text" /></label>
        </div>
        <button className="btn-primary mt-3" onClick={() => act(() => api.put(`/systems/${sid}/inheritance`, assign), "Inheritance updated").then(() => setAssign(null))} data-testid="assign-save">Save</button></Modal>}
    </div>
  );
}

export function PolicyAuditorPage() {
  const { can } = useAuth();
  const { selectedId: sid } = useSystems();
  const { data, reload } = useApi<Row>("/policies");
  const [f, setF] = useState<Row>({ title: "", owner: "" });
  const fileRef = useRef<HTMLInputElement>(null);
  const [msg, setMsg] = useState("");
  const up = async (file: File) => {
    const fd = new FormData(); fd.append("file", file); fd.append("title", f.title || file.name); fd.append("owner", f.owner); if (sid) fd.append("system_ids", sid);
    try { const r = await api.post<Row>("/policies", fd); window.dispatchEvent(new Event("iv:processing-started")); if (r.data.duplicate) { setMsg(r.data.message); return; } setMsg(`Uploaded v${r.data.version} – Processing… a summary appears when the analysis finishes`); setTimeout(reload, 4000); reload(); } catch (e) { setMsg(errorMessage(e)); }
  };
  const running = !!data?.policies?.some((p: Row) => ["queued", "processing"].includes(p.analysis_status));
  usePollWhile(running, reload);
  if (!data) return null;
  const c = data.cards;
  return (
    <div data-testid="policy-auditor-page">
      <PageHeader title="Policy Auditor" subtitle="Findings are proposals until a human confirms. NIST organization-defined parameters have no universal threshold." />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Policies" value={c.total} testId="pol-card-total" /><Stat label="Audited" value={c.audited} testId="pol-card-audited" />
        <Stat label="Requirements w/o coverage" value={c.requirements_without_coverage} testId="pol-card-missing" /><Stat label="Policy/config disagreements" value={c.disagreements} testId="pol-card-disagree" />
        <Stat label="Overdue reviews" value={c.overdue_reviews} testId="pol-card-overdue" />
      </div>
      <Gated perm="implementation.write"><Panel title="Upload policy (PDF, DOCX, TXT)" className="mb-5" testId="policy-upload-panel">
        {sid && <ProcessingList sid={sid} />}
        <div className="flex gap-2"><input className="input" placeholder="Title" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="policy-title" />
          <input className="input" placeholder="Owner" value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} data-testid="policy-owner" />
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={(e) => e.target.files?.[0] && up(e.target.files[0])} data-testid="policy-file-input" />
          <button className="btn-secondary whitespace-nowrap" onClick={() => fileRef.current?.click()} data-testid="policy-upload-btn">Upload with title & owner</button>
          <ImportButton systemId={sid} type="policy" primary testId="policy-import-center-btn" /></div>
        {msg && <div className="mt-2 text-[12px]" data-testid="policy-upload-msg">{msg}</div>}
      </Panel></Gated>
      <Panel title="Policy library" testId="policy-library">
        <Table head={["Policy", "Version", "Status", "Owner", "Approved", "Review due", "Analysis", "Proposed / confirmed / dismissed"]}>
          {data.policies.map((p: Row) => <tr key={p.id} data-testid={`policy-row-${p.policy_key}-v${p.version}`} className={cn(p.status === "superseded" && "iv-dimmed")}>
            <td className="td"><Link className="text-blue-800 hover:underline" to={`/policy-auditor/${p.id}`}>{p.title}</Link>{p.metadata_only && <div className="text-[10px] text-slate-400">metadata only (no document loaded)</div>}</td>
            <td className="td font-mono">v{p.version}</td><td className="td"><S v={p.review_status ?? p.status} testId={`policy-review-status-${p.policy_key}-v${p.version}`} /></td><td className="td text-[12px]">{p.owner}</td><td className="td font-mono text-[11px]">{p.approval_date ?? "—"}</td>
            <td className="td font-mono text-[11px]">{p.review_due ?? "—"}</td><td className="td"><S v={p.analysis_status} />{["queued", "processing"].includes(p.analysis_status) && <AnalysisProgress p={p.analysis?.progress} testId={`policy-progress-${p.policy_key}-v${p.version}`} />}{p.analysis_status === "analyzed" && p.analysis?.progress?.phase === "done" && <div className="text-[10px] text-slate-500" data-testid={`policy-completed-${p.policy_key}-v${p.version}`}>{p.analysis.progress.stage}</div>}</td><td className="td font-mono">{p.proposed} / {p.confirmed} / {p.dismissed}</td></tr>)}
        </Table>
      </Panel>
    </div>
  );
}

const TYPES: Record<string, string> = { policy_vs_config_difference: "Policy vs configuration", odp_not_met: "ODP not met", missing_policy_requirement: "Missing requirement",
  possible_outdated_reference: "Possible outdated reference", ai_suggested_needs_validation: "AI suggestion – needs validation" };

/** Stored results from an older auditor version or keyword-only (no AI) rows: one-click re-analysis with the latest auditor (ISSO/ISSM, audited). */
function StaleAuditor({ a, id, canRun, reload, setMsg }: { a: Row; id: string; canRun: boolean; reload: () => void; setMsg: (m: string) => void }) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { await api.post(`/policies/${id}/reanalyze?latest=true`); setMsg("Re-analysis with the latest auditor queued – your Mapping Review decisions are kept."); reload(); }
    catch (e) { setMsg(errorMessage(e)); } finally { setBusy(false); }
  };
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] text-amber-900" data-testid="policy-stale-auditor">
      <span className="rounded bg-amber-200 px-1.5 py-0.5 font-semibold" data-testid="policy-stale-badge">Analyzed with an older auditor version</span>
      <span>{a.used_version !== a.current_version ? `${a.used_version || "unknown"} → current ${a.current_version}` : `${a.keyword_only_requirements} requirement(s) were checked by keyword only (AI unavailable) – they need manual review`}</span>
      <button className="btn-primary ml-auto !py-0.5 text-[12px]" disabled={!canRun || busy} title={canRun ? a.est_basis : "Only the ISSO or ISSM can re-analyse"} onClick={run} data-testid="policy-reanalyze-latest">
        Re-analyze with latest (est. ${Number(a.est_cost_usd).toFixed(2)})</button>
    </div>);
}


export function PolicyDetailPage() {
  const { id = "" } = useParams();
  const { can, user } = useAuth();
  const { data, reload } = useApi<Row>(`/policies/${id}`);
  const [msg, setMsg] = useState("");
  const [mapFor, setMapFor] = useState<string[] | null>(null);
  const active = useActiveSystemId();
  const analysing = ["queued", "processing"].includes(data?.policy?.analysis_status);
  usePollWhile(analysing, reload);
  if (!data) return null;
  const p = data.policy;
  const act = async (pf: Row, action: string) => {
    const body: Row = {};
    if (action === "dismiss") { const j = window.prompt("Dismissal justification (min 10 chars)"); if (!j) return; body.justification = j; }
    if (action === "link") { const c = window.prompt("Link to control (e.g. ac-2.3)", pf.control_id ?? ""); if (!c) return; body.control_id = c; }
    try { const r = await api.post<Row>(`/policy-findings/${pf.id}/${action}`, body); setMsg(action === "confirm" ? `Confirmed → canonical finding ${r.data.finding_id.slice(0, 8)} created` : `${action} recorded`); reload(); } catch (e) { setMsg(errorMessage(e)); }
  };
  return (
    <div data-testid="policy-detail-page">
      <PageHeader title={`${p.title} v${p.version}`} subtitle={`${p.status} · ${p.file_name ?? "metadata only"} · sha256 ${p.sha256?.slice(0, 16) ?? "—"} · ${p.analysis?.ai_note ?? ""}`}>
        <button className="btn-secondary" onClick={() => downloadFile(`/policies/${id}/parameters.csv`, "policy-parameters.csv", "Parameter comparison")} data-testid="export-params-btn">Export parameter comparison (CSV)</button>
      </PageHeader>
      {msg && <div className="panel mb-4 p-3 text-[13px]" role="alert" data-testid="policy-msg">{msg}</div>}
      {analysing && <div className="panel mb-4 p-3" data-testid="policy-detail-progress"><div className="text-[12px] font-semibold">Analysis {p.analysis_status === "queued" ? "queued" : "in progress"}</div>
        <AnalysisProgress p={p.analysis?.progress ?? { pct: 0, stage: "Queued – waiting for a worker" }} testId="policy-detail-progress-bar" /></div>}
      {!analysing && p.analysis?.progress?.phase === "done" && <div className="mb-3 text-[12px] text-slate-600" data-testid="policy-detail-completed">Analysis {p.analysis.progress.stage.toLowerCase()} · {p.analysis.progress.requirements_analyzed} requirements analysed · {p.analysis.progress.requirement_gaps} requirement gaps · {p.analysis.progress.audit_findings} audit findings stored{p.analysis.progress.audit_suggestions != null && ` (${p.analysis.progress.audit_suggestions} AI suggestions)`}
        {p.analysis.progress.audit_note && <div className="text-amber-800" data-testid="policy-detail-audit-note">{p.analysis.progress.audit_note}</div>}
        <StageHistory p={p.analysis.progress} testId="policy-detail-stage-history" /></div>}
      {data.auditor?.stale && <StaleAuditor a={data.auditor} id={id} canRun={can("ingest.upload") && ((user && user.roles) || []).some((r: Row) => ["isso", "issm", "admin"].includes(r.role))} reload={reload} setMsg={setMsg} />}
      {p.analysis?.text_refreshed && <div className="mb-3 text-[12px] text-slate-600" data-testid="policy-text-refreshed">Re-analysed with improved table extraction on {new Date(p.analysis.text_refreshed.at).toLocaleDateString()}{["queued", "processing"].includes(p.analysis_status) ? " (re-analysis in progress)" : ""}. Your earlier decisions are kept; differences show as “Re-analysis differs from approved”.</div>}
      <Panel title="Mapped controls (confidence · basis · matched text)" className="mb-5" testId="policy-control-mappings">
        <PolicyMappingsPanel policyId={id} data={data} canMap={can("finding.map")} reload={reload} setMsg={setMsg} />
      </Panel>
      <Panel title="Requirement coverage (DISA CCIs + SP 800-53A objectives)" eyebrow={CCI_TIP} className="mb-5" testId="policy-coverage">
        <CoverageChecklist policyId={id} data={data} systemId={(data.policy.system_ids || [])[0] || active || undefined} canMap={can("finding.map")} canPoam={can("poam.manage")} reload={reload} setMsg={setMsg} />
      </Panel>
      <Panel title="Values this policy sets" className="mb-5" testId="policy-values">
        <Table head={["Control", "Parameter", "Policy value & exact quote", "Approved ODP", "Observed / enforced", "Evidence age", "Result"]}>
          {data.values.map((v: Row, i: number) => <tr key={i} data-testid={`value-${v.control_id}`}><td className="td"><ControlLink systemId={v.system_id} controlId={v.control_id} /></td><td className="td text-[12px]">{v.parameter}</td>
            <td className="td"><span className="font-mono">{v.policy_value}</span>{v.quote && <blockquote className="mt-1 border-l-2 border-slate-300 pl-2 text-[11px] text-slate-700" data-testid={`value-quote-${v.control_id}`}>“{v.quote}”<div className="text-[10px] not-italic text-slate-500">{v.quote_location}{v.quote_status !== "verbatim" ? ` · ${v.quote_status}` : " · verbatim"}</div></blockquote>}</td><td className="td font-mono">{v.odp_value ?? "—"}</td><td className="td font-mono">{v.observed_value ?? "—"}<div className="text-[10px] text-slate-500">{v.observed_source}</div></td>
            <td className="td font-mono text-[11px]">{v.observed_age_days ?? "—"}d</td><td className="td">{v.result ? <S v={v.result === "Match" ? "current" : "failing"} label={v.result} testId={`value-result-${v.control_id}`} /> : "—"}</td></tr>)}
        </Table>
      </Panel>
      <Panel title="Proposed findings (needs human confirmation)" className="mb-5" testId="policy-findings">
        <Table head={["Type", "Control", "Description", "Quote", "Origin", "Status", "Actions"]}>
          {data.findings.map((pf: Row) => <tr key={pf.id} data-testid={`pf-${pf.finding_type}-${pf.control_id}`}>
            <td className="td text-[12px]">{TYPES[pf.finding_type]}</td><td className="td">{pf.control_id ? <ControlLink systemId={pf.system_id} controlId={pf.control_id} /> : "—"}</td>
            <td className="td max-w-[320px] text-[12px]">{pf.description}</td><td className="td max-w-[220px] text-[11px] text-slate-600" data-testid={`pf-quote-${pf.id}`}>{pf.quote ? (pf.quote.startsWith("[paraphrase") ? <span className="text-amber-700">{pf.quote}</span> : <>“{pf.quote}”</>) : "—"}</td><td className="td text-[11px]">{pf.origin}</td>
            <td className="td"><S v={pf.status} />{pf.justification && <div className="text-[10px] text-slate-500">{pf.reviewer_name}: {pf.justification}</div>}</td>
            <td className="td">{can("finding.map") && ["proposed", "in_review"].includes(pf.status) && <div className="flex flex-wrap gap-1">
              <button className="btn-primary px-2 py-0.5 text-[11px]" onClick={() => act(pf, "confirm")} data-testid={`pf-confirm-${pf.id}`}>Confirm</button>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act(pf, "dismiss")} data-testid={`pf-dismiss-${pf.id}`}>Dismiss</button>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act(pf, "request-review")} data-testid={`pf-review-${pf.id}`}>Request review</button>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act(pf, "link")} data-testid={`pf-link-${pf.id}`}>Link to control</button></div>}
              <Gated perm="finding.map"><button className="mt-1 btn-secondary px-2 py-0.5 text-[11px]" onClick={() => setMapFor(pf.control_id ? [pf.control_id] : [])} data-testid={`pf-map-control-${pf.id}`}>Map to control</button></Gated>
              {pf.finding_id && <Link className="text-[11px] text-blue-800 underline" to={`/findings/${pf.finding_id}`} data-testid={`pf-finding-link-${pf.id}`}>Finding → Add to POA&M</Link>}</td></tr>)}
        </Table>
      </Panel>
      {mapFor && <MapToControlModal policyId={id} initial={mapFor} onClose={() => setMapFor(null)} onDone={(m) => { setMapFor(null); setMsg(m); reload(); }} />}
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Versions" testId="policy-versions">{data.versions.map((v: Row) => <div key={v.id} className="text-[12px]"><Link className="text-blue-800 underline" to={`/policy-auditor/${v.id}`}>v{v.version}</Link> <S v={v.status} /> {v.approval_date}</div>)}</Panel>
        <Panel title="Extracted text (preview)" testId="policy-text"><pre className="max-h-72 overflow-y-auto whitespace-pre-wrap text-[11px]">{data.text_preview || "No document loaded (metadata-only policy)."}</pre>
          {data.text_preview && <FoundItHere policyId={id} canMap={can("implementation.write")} setMsg={setMsg} />}</Panel>
      </div>
      {data.reading && <ReadingReport r={data.reading} />}
    </div>
  );
}

export function RmfWorkflowPage() {
  const { selectedId: sid, systems, loaded } = useSystems();
  const { data } = useApi<Row[]>(sid ? `/systems/${sid}/rmf-workflow` : null);
  const empty = loaded && systems.length === 0;
  const tone: Record<string, string> = { completed: "border-emerald-300", in_progress: "border-sky-300", needs_attention: "border-amber-400", not_configured: "border-slate-300" };
  const ongoing = (data ?? []).filter((s) => s.stage.startsWith("Ongoing"));
  return (
    <div data-testid="rmf-workflow-page">
      <PageHeader title="Getting started · RMF overview" subtitle="IronVision follows the 7 steps of the Risk Management Framework (NIST SP 800-37 Rev. 2). Each step's status is computed from this system's real records – hover a step to see how it is decided." />
      <RmfOverview />
      {!empty && ongoing.length > 0 && <>
        <h2 className="mb-2 mt-6 font-heading text-[15px] font-semibold text-slate-900">Ongoing activities</h2>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {ongoing.map((s) => <Link key={s.stage} to={s.link} className={cn("panel card-interactive border-l-4 p-4", tone[s.state])} data-testid={`stage-${s.stage.replace(/[^a-zA-Z0-9]+/g, "-").toLowerCase()}`}>
            <div className="flex items-center justify-between"><span className="font-heading font-semibold text-slate-900">{s.stage.replace("Ongoing: ", "")}</span><S v={s.state} /></div><div className="mt-1 text-[12px] text-slate-600">{s.reason}</div></Link>)}
        </div></>}
    </div>
  );
}
