import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { ControlLink, NeedSystem, S, Stat, Table } from "@/components/common/Bits";
import { Modal } from "@/components/common/Workflow";
import { cn, fmtDate } from "@/lib/format";

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
  if (!sid) return <NeedSystem />;
  if (!data) return null;
  const c = data.cards;
  const act = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); setMsg(ok); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  const upload = (f: File) => { const fd = new FormData(); fd.append("file", f); act(() => api.post(`/attestations/${upFor}/evidence`, fd), "Evidence stored in ledger (SHA-256 recorded)"); };
  return (
    <div data-testid="inheritance-page">
      <PageHeader title="Inheritance & Attestations" subtitle={c.note}>
        {can("system.write") && <><button className="btn-secondary" onClick={() => setProv({ name: "" })} data-testid="add-provider-btn">Add provider</button>
          <button className="btn-secondary" onClick={() => setAssign({ control_id: "", responsibility: "shared" })} data-testid="assign-inheritance-btn">Assign inherited/shared control</button></>}
      </PageHeader>
      {msg && <div className="panel mb-4 p-3 text-[13px]" role="alert" data-testid="inheritance-msg">{msg}</div>}
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Fully inherited" value={c.fully_inherited} testId="inh-card-inherited" hint={`of ${c.assigned}`} />
        <Stat label="Shared" value={c.shared} testId="inh-card-shared" /><Stat label="System-owned" value={c.system_owned} testId="inh-card-system" />
        <Stat label="Manual attestation" value={c.manual_attestation} testId="inh-card-attest" hint={`${c.attestation_overdue} overdue · ${c.attestation_due_30d} due ≤30d (overlaps)`} />
        <Stat label="Reconciles" value={c.sum_check ? "Yes" : "No"} testId="inh-card-sum" hint={`${c.fully_inherited}+${c.shared}+${c.system_owned}=${c.assigned}`} />
      </div>
      <Panel title="Who covers what" className="mb-5" testId="providers-panel">
        <Table head={["Provider", "Package / basis", "Coverage", "Inherited", "Shared", "Last validation", "Package expiration", "Evidence refs", ""]}>
          {data.providers.map((p: Row) => <tr key={p.id} data-testid={`provider-${p.id}`}><td className="td text-[12px] font-medium">{p.name}</td><td className="td text-[12px]">{p.package}<div className="text-[10px] text-slate-500">{p.basis}</div></td>
            <td className="td max-w-[260px] text-[12px]">{p.coverage_text}</td><td className="td font-mono">{p.fully_inherited}</td><td className="td font-mono">{p.shared}</td>
            <td className="td font-mono text-[11px]">{p.last_validated_at ?? "—"}</td><td className="td font-mono text-[11px]">{p.package_expiration ?? "—"}</td><td className="td text-[11px]">{(p.evidence_refs || []).join(", ")}</td>
            <td className="td">{can("system.write") && <button className="text-[11px] text-blue-800 underline" onClick={() => setProv(p)} data-testid={`edit-provider-${p.id}`}>Edit</button>}</td></tr>)}
        </Table>
      </Panel>
      <Panel title="Shared controls – provider vs system responsibility" className="mb-5" testId="shared-panel">
        <Table head={["Control", "Provider responsibility", "System responsibility", "System part (this system's own evidence)"]}>
          {data.shared.map((x: Row) => <tr key={x.control_id} data-testid={`shared-${x.control_id}`}><td className="td"><ControlLink systemId={sid} controlId={x.control_id} /></td>
            <td className="td max-w-[320px] text-[12px]">{x.provider_responsibility ?? "—"}</td><td className="td max-w-[320px] text-[12px]">{x.system_responsibility ?? "—"}</td>
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
                {can("poam.manage") && <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act(() => api.post(`/attestations/${a.id}/remind`), "Reminder sent")} data-testid={`att-remind-${a.control_id}`}>Send reminder</button>}
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
        {["name", "package", "basis", "coverage_text", "last_validated_at", "package_expiration"].map((k) => <label key={k} className="block text-[13px]">{k.replace(/_/g, " ")}<input className="input" type={k.endsWith("_at") || k.endsWith("expiration") ? "date" : "text"} value={prov[k] ?? ""} onChange={(e) => setProv({ ...prov, [k]: e.target.value })} data-testid={`provider-${k}`} /></label>)}
        <button className="btn-primary mt-3" onClick={() => { const b = Object.fromEntries(["name", "package", "basis", "coverage_text", "last_validated_at", "package_expiration"].map((k) => [k, prov[k] || null])); act(() => prov.id ? api.patch(`/providers/${prov.id}`, b) : api.post("/providers", b), "Provider saved").then(() => setProv(null)); }} data-testid="provider-save">Save</button></Modal>}
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
    try { const r = await api.post<Row>("/policies", fd); setMsg(`Uploaded v${r.data.version} – analysis job queued (worker)`); setTimeout(reload, 4000); reload(); } catch (e) { setMsg(errorMessage(e)); }
  };
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
      {can("implementation.write") && <Panel title="Upload policy (PDF, DOCX, TXT)" className="mb-5" testId="policy-upload-panel">
        <div className="flex gap-2"><input className="input" placeholder="Title" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="policy-title" />
          <input className="input" placeholder="Owner" value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} data-testid="policy-owner" />
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={(e) => e.target.files?.[0] && up(e.target.files[0])} data-testid="policy-file-input" />
          <button className="btn-primary whitespace-nowrap" onClick={() => fileRef.current?.click()} data-testid="policy-upload-btn">Upload & analyze</button></div>
        {msg && <div className="mt-2 text-[12px]" data-testid="policy-upload-msg">{msg}</div>}
      </Panel>}
      <Panel title="Policy library" testId="policy-library">
        <Table head={["Policy", "Version", "Status", "Owner", "Approved", "Review due", "Analysis", "Proposed / confirmed / dismissed"]}>
          {data.policies.map((p: Row) => <tr key={p.id} data-testid={`policy-row-${p.policy_key}-v${p.version}`} className={cn(p.status === "superseded" && "opacity-60")}>
            <td className="td"><Link className="text-blue-800 hover:underline" to={`/policy-auditor/${p.id}`}>{p.title}</Link>{p.metadata_only && <div className="text-[10px] text-slate-400">metadata only (no document loaded)</div>}</td>
            <td className="td font-mono">v{p.version}</td><td className="td"><S v={p.status} /></td><td className="td text-[12px]">{p.owner}</td><td className="td font-mono text-[11px]">{p.approval_date ?? "—"}</td>
            <td className="td font-mono text-[11px]">{p.review_due ?? "—"}</td><td className="td"><S v={p.analysis_status} /></td><td className="td font-mono">{p.proposed} / {p.confirmed} / {p.dismissed}</td></tr>)}
        </Table>
      </Panel>
    </div>
  );
}

const TYPES: Record<string, string> = { policy_vs_config_difference: "Policy vs configuration", odp_not_met: "ODP not met", missing_policy_requirement: "Missing requirement",
  possible_outdated_reference: "Possible outdated reference", ai_suggested_needs_validation: "AI suggestion – needs validation" };

export function PolicyDetailPage() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const { data, reload } = useApi<Row>(`/policies/${id}`);
  const [msg, setMsg] = useState("");
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
        <a className="btn-secondary" href={`${process.env.REACT_APP_BACKEND_URL}/api/v1/policies/${id}/parameters.csv`} onClick={async (e) => { e.preventDefault(); const r = await api.get(`/policies/${id}/parameters.csv`, { responseType: "blob" }); const u = URL.createObjectURL(r.data as Blob); const a = document.createElement("a"); a.href = u; a.download = "parameters.csv"; a.click(); }} data-testid="export-params-btn">Export parameter comparison (CSV – OSCAL in Phase 4)</a>
      </PageHeader>
      {msg && <div className="panel mb-4 p-3 text-[13px]" role="alert" data-testid="policy-msg">{msg}</div>}
      <Panel title="Values this policy sets" className="mb-5" testId="policy-values">
        <Table head={["Control", "Parameter", "Policy value", "Approved ODP", "Observed / enforced", "Evidence age", "Result"]}>
          {data.values.map((v: Row, i: number) => <tr key={i} data-testid={`value-${v.control_id}`}><td className="td"><ControlLink systemId={v.system_id} controlId={v.control_id} /></td><td className="td text-[12px]">{v.parameter}</td>
            <td className="td font-mono">{v.policy_value}</td><td className="td font-mono">{v.odp_value ?? "—"}</td><td className="td font-mono">{v.observed_value ?? "—"}<div className="text-[10px] text-slate-500">{v.observed_source}</div></td>
            <td className="td font-mono text-[11px]">{v.observed_age_days ?? "—"}d</td><td className="td">{v.result ? <S v={v.result === "Match" ? "current" : "failing"} label={v.result} testId={`value-result-${v.control_id}`} /> : "—"}</td></tr>)}
        </Table>
      </Panel>
      <Panel title="Proposed findings (needs human confirmation)" className="mb-5" testId="policy-findings">
        <Table head={["Type", "Control", "Description", "Quote", "Origin", "Status", "Actions"]}>
          {data.findings.map((pf: Row) => <tr key={pf.id} data-testid={`pf-${pf.finding_type}-${pf.control_id}`}>
            <td className="td text-[12px]">{TYPES[pf.finding_type]}</td><td className="td">{pf.control_id ? <ControlLink systemId={pf.system_id} controlId={pf.control_id} /> : "—"}</td>
            <td className="td max-w-[320px] text-[12px]">{pf.description}</td><td className="td max-w-[200px] text-[11px] italic text-slate-600">{pf.quote}</td><td className="td text-[11px]">{pf.origin}</td>
            <td className="td"><S v={pf.status} />{pf.justification && <div className="text-[10px] text-slate-500">{pf.reviewer_name}: {pf.justification}</div>}</td>
            <td className="td">{can("finding.map") && ["proposed", "in_review"].includes(pf.status) && <div className="flex flex-wrap gap-1">
              <button className="btn-primary px-2 py-0.5 text-[11px]" onClick={() => act(pf, "confirm")} data-testid={`pf-confirm-${pf.id}`}>Confirm</button>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act(pf, "dismiss")} data-testid={`pf-dismiss-${pf.id}`}>Dismiss</button>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act(pf, "request-review")} data-testid={`pf-review-${pf.id}`}>Request review</button>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act(pf, "link")} data-testid={`pf-link-${pf.id}`}>Link to control</button></div>}
              {pf.finding_id && <Link className="text-[11px] text-blue-800 underline" to={`/findings/${pf.finding_id}`} data-testid={`pf-finding-link-${pf.id}`}>Finding → Add to POA&M</Link>}</td></tr>)}
        </Table>
      </Panel>
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Versions" testId="policy-versions">{data.versions.map((v: Row) => <div key={v.id} className="text-[12px]"><Link className="text-blue-800 underline" to={`/policy-auditor/${v.id}`}>v{v.version}</Link> <S v={v.status} /> {v.approval_date}</div>)}</Panel>
        <Panel title="Extracted text (preview)" testId="policy-text"><pre className="max-h-72 overflow-y-auto whitespace-pre-wrap text-[11px]">{data.text_preview || "No document loaded (metadata-only policy)."}</pre></Panel>
      </div>
    </div>
  );
}

export function RmfWorkflowPage() {
  const { selectedId: sid } = useSystems();
  const { data } = useApi<Row[]>(sid ? `/systems/${sid}/rmf-workflow` : null);
  if (!sid) return <NeedSystem />;
  const tone: Record<string, string> = { completed: "border-emerald-300", in_progress: "border-sky-300", needs_attention: "border-amber-400", not_configured: "border-slate-300" };
  return (
    <div data-testid="rmf-workflow-page">
      <PageHeader title="RMF Workflow" subtitle="Live stage state derived from this system's records (rules documented in README)." />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {data?.map((s) => <Link key={s.stage} to={s.link} className={cn("panel card-interactive border-l-4 p-4", tone[s.state])} data-testid={`stage-${s.stage.replace(/[^a-zA-Z0-9]+/g, "-").toLowerCase()}`}>
          <div className="flex items-center justify-between"><span className="font-heading font-semibold text-slate-900">{s.stage}</span><S v={s.state} /></div><div className="mt-1 text-[12px] text-slate-600">{s.reason}</div></Link>)}
      </div>
    </div>
  );
}
