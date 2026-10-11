import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { NeedSystem, S, Stat, Table } from "@/components/common/Bits";
import { Modal } from "@/components/common/Workflow";
import { cn, fmtDate } from "@/lib/format";

const DIFF_TABS: [string, string][] = [["added", "Added"], ["removed", "Removed"], ["changed_requirement", "Changed requirement"], ["changed_severity", "Changed severity"]];

export function ContentUpdatesPanel() {
  const { can } = useAuth();
  const { data, reload } = useApi<Row>("/content-updates");
  const [up, setUp] = useState<Row | null>(null);
  const [tab, setTab] = useState("added");
  const [msg, setMsg] = useState("");
  if (!data) return null;
  const preview = async (vid: string) => { try { setUp((await api.post<Row>(`/content-versions/${vid}/preview`)).data); setTab("added"); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  const apply = async () => {
    const j = window.prompt("Approval justification for applying this content update (min 10 chars)"); if (!j || !up) return;
    try { const r = await api.post<Row>(`/content-updates/${up.id}/apply`, { justification: j }); const c = r.data.result || {}; setMsg(`Applied ${imp?.from ?? ""} → ${imp?.to ?? ""}: ${["assets", "findings", "controls", "poams"].filter((k) => c[k] != null).map((k) => `${c[k]} ${k === "poams" ? "POA&Ms" : k}`).join(" · ") || "no linked records"} affected. History preserved — see Application history.`); setUp(null); reload(); } catch (e) { setMsg(errorMessage(e)); }
  };
  const imp = up?.impact;
  return (
    <Panel title="Content updates (installed vs available)" className="mb-5" testId="content-updates-panel">
      {msg && <div className="mb-2 text-[12px]" role="alert" data-testid="content-msg">{msg}</div>}
      <Table head={["Content type", "Installed", "Effective", "Available", "Status", ""]} testId="content-types-table">
        {data.types.map((t: Row) => <tr key={t.content_type} data-testid={`content-type-${t.content_type}`}>
          <td className="td text-[12px] font-medium">{t.label}</td>
          <td className="td text-[12px]">{t.installed.map((v: Row) => <div key={v.id ?? v.title}>{v.title} <span className="font-mono">{v.version}</span>{v.synthetic && <span className="ml-1 text-[10px] text-amber-700">SYNTHETIC</span>}</div>)}{!t.installed.length && "—"}</td>
          <td className="td font-mono text-[11px]">{t.installed.map((v: Row) => <div key={v.id ?? v.title}>{v.effective_date ?? "—"}</div>)}</td>
          <td className="td text-[12px]">{t.available.map((v: Row) => <div key={v.id}><span className="font-mono">{v.version}</span> · {v.effective_date}</div>)}{!t.available.length && <span className="text-slate-400">{t.note ?? "none"}</span>}</td>
          <td className="td">{t.available.length ? <S v="needs_attention" label="update available" /> : t.installed.length ? <S v="current" label="up to date" /> : <S v="not_configured" />}</td>
          <td className="td">{t.available.map((v: Row) => <button key={v.id} className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => preview(v.id)} data-testid={`preview-${t.content_type}-${v.version}`}>Preview diff & impact</button>)}</td></tr>)}
      </Table>
      <div className="mt-3 text-[12px] font-medium">Application history</div>
      <Table head={["When", "Type", "From → To", "Status", "Counts", "By"]} testId="content-history">
        {data.history.map((h: Row) => <tr key={h.id}><td className="td font-mono text-[11px]">{fmtDate(h.applied_at ?? h.created_at)}</td><td className="td text-[11px]">{h.content_type}</td>
          <td className="td font-mono text-[11px]">{h.from_version} → {h.to_version}</td><td className="td"><S v={h.status} /></td><td className="td text-[11px]" data-testid={`history-summary-${h.id}`}><HistorySummary h={h} /></td>
          <td className="td text-[11px]">{h.applier_name ?? h.requester_name}{h.justification && <div className="text-slate-500">{h.justification}</div>}</td></tr>)}
      </Table>
      {up && <Modal title={`Update preview: ${imp.from ?? ""} → ${imp.to ?? ""}`} onClose={() => setUp(null)} testId="content-preview-modal" wide>
        <div className="mb-2 flex flex-wrap gap-2" data-testid="diff-summary">{DIFF_TABS.map(([k, l]) => <button key={k} className={cn("rounded px-2 py-0.5 text-[12px]", tab === k ? "bg-brand-700 text-white" : "bg-slate-100 text-slate-700 hover:bg-blue-50")} onClick={() => setTab(k)} data-testid={`diff-tab-${k}`}>{l} ({up.diff_summary?.[k] ?? 0})</button>)}</div>
        <div className="max-h-56 overflow-y-auto" data-testid="diff-list">{(imp.diff?.[tab] || []).map((r: Row, i: number) => <div key={i} className="border-b border-slate-100 py-1 text-[12px]">
          <span className="font-mono">{r.vuln_id ?? r}</span> {r.title}{r.old_severity && <b> {r.old_severity} → {r.new_severity}</b>}{r.old_title && r.old_title !== r.new_title && <div className="text-[11px] text-slate-500">was: {r.old_title}</div>}</div>)}</div>
        {imp.counts && <div className="my-3 grid grid-cols-4 gap-2">{Object.entries(imp.counts).map(([k, v]) => <Stat key={k} label={`Affected ${k}`} value={String(v)} testId={`impact-${k}`} />)}</div>}
        {imp.poams?.length > 0 && <div className="text-[12px]" data-testid="impact-poams"><b>POA&M impact:</b>{imp.poams.map((p: Row) => <div key={p.human_id}><Link className="font-mono text-blue-800 underline" to={`/poams/${p.poam_id}`}>{p.human_id}</Link> {p.weakness} – {p.impacts.join(", ")}</div>)}</div>}
        {imp.assets?.length > 0 && <div className="mt-2 max-h-24 overflow-y-auto text-[11px]" data-testid="impact-assets"><b>Assets needing a new checklist:</b> {imp.assets.map((a: Row) => `${a.asset} (${a.system})`).join(", ")}</div>}
        {imp.controls?.length > 0 && <div className="mt-1 text-[11px]" data-testid="impact-controls"><b>Controls:</b> {imp.controls.map((c: Row) => `${c.control_id.toUpperCase()}@${c.system}`).join(", ")}</div>}
        {imp.note && <div className="mt-1 text-[11px] text-slate-500">{imp.note}</div>}
        <div className="mt-3 flex items-center gap-2"><button className="btn-primary" disabled={!can("content.apply")} onClick={apply} data-testid="apply-content-btn">Apply approved update</button>
          <span className="text-[11px] text-slate-500">{can("content.apply") ? "Historical observations, assessments and mappings keep their original content version." : "Requires content.apply (ISSM or platform admin)."}</span></div>
      </Modal>}
    </Panel>
  );
}

function HistorySummary({ h }: { h: Row }) {
  const d = h.diff_summary || {};
  const c = h.counts || h.result || {};
  const diff = [["added", "added"], ["removed", "removed"], ["changed_requirement", "changed"], ["changed_severity", "severity"]]
    .filter(([k]) => d[k] != null).map(([k, l]) => `${d[k]} ${l}`).join(" / ");
  const imp = [["assets", "assets"], ["findings", "findings"], ["controls", "controls"], ["poams", "POA&Ms"], ["changed", "KEV flags changed"], ["remapped_mappings", "mappings re-mapped"]]
    .filter(([k]) => c[k] != null).map(([k, l]) => `${c[k]} ${l}`).join(" · ");
  return <><div className="font-medium">{diff || (d.added != null ? `${d.added} added / ${d.removed} removed` : "—")}</div>{imp && <div className="text-slate-500">Impact: {imp}{c.observations_rewritten === 0 ? " · history preserved (0 observations rewritten)" : ""}</div>}</>;
}

export function ScoreBreakdown({ findingId }: { findingId: string }) {
  const { data } = useApi<Row>(`/findings/${findingId}/score`);
  if (!data || data.score == null) return null;
  return (
    <Panel title={`Operational prioritization score: ${data.score}`} testId="finding-score">
      <div className="mb-1 text-[11px] text-amber-800">{data.label}</div>
      <Table head={["Factor", "Basis", "Value", "Weight", "Points"]}>
        {data.breakdown.map((x: Row) => <tr key={x.factor} data-testid={`score-${x.factor}`}><td className="td text-[12px]">{x.factor.replace("rf_", "").replace(/_/g, " ")}</td><td className="td text-[11px]">{String(x.basis)}</td>
          <td className="td font-mono text-[11px]">{x.value}</td><td className="td font-mono text-[11px]">{x.weight}</td><td className="td font-mono text-[11px]">{x.points}</td></tr>)}
        <tr><td className="td font-semibold" colSpan={4}>Total</td><td className="td font-mono font-semibold" data-testid="score-total">{data.score}</td></tr>
      </Table>
    </Panel>
  );
}

export function FindingMappingHistory({ findingId }: { findingId: string }) {
  const { can } = useAuth();
  const { data: cu } = useApi<Row>("/content-updates");
  const [asOf, setAsOf] = useState("");
  const { data, reload } = useApi<Row>(`/findings/${findingId}/mappings`, asOf ? { as_of: asOf } : undefined);
  const [msg, setMsg] = useState("");
  const versions = (cu?.types || []).filter((t: Row) => ["stig_benchmark", "cci_list"].includes(t.content_type))
    .flatMap((t: Row) => [...t.installed, ...(t.superseded || [])].map((v: Row) => ({ ...v, type: t.label })));
  const suggest = async () => { try { const r = await api.post<Row>(`/findings/${findingId}/suggest-mapping`); setMsg(`AI proposed: ${r.data.suggested.join(", ") || "none"} (needs human approval in Mapping review)`); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  return (
    <Panel title="Mappings by content version" testId="finding-mapping-history" actions={can("finding.map") ? <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={suggest} data-testid="ai-suggest-mapping-btn">AI: suggest mapping</button> : undefined}>
      <select className="input mb-2 w-72" value={asOf} onChange={(e) => setAsOf(e.target.value)} data-testid="mapping-as-of"><option value="">Current mappings</option>{versions.map((v: Row) => <option key={v.id} value={v.id}>As of {v.type} {v.version}</option>)}</select>
      {msg && <div className="mb-1 text-[12px]" role="alert" data-testid="mapping-msg">{msg}</div>}
      <div className="text-[11px] text-slate-500">Finding currently evaluated under: {data?.current_content_version ?? "—"}</div>
      {(data?.mappings || []).map((m: Row) => <div key={m.id} className="text-[12px]"><span className="font-mono">{m.control_id.toUpperCase()}</span> via {m.cci_id || m.mapping_source} · <S v={m.review_status} />{m.valid_to && <span className="text-[10px] text-slate-400"> superseded {fmtDate(m.valid_to)}</span>}</div>)}
    </Panel>
  );
}

export function MappingReviewPage() {
  const { selectedId: sid } = useSystems();
  const { can } = useAuth();
  const { data, reload } = useApi<Row>(sid ? "/mapping-review" : null, sid ? { system_id: sid } : undefined);
  const [msg, setMsg] = useState("");
  if (!sid) return <NeedSystem />;
  const act = async (id: string, action: string) => {
    const j = window.prompt(`${action} justification (min 10 chars)`); if (!j) return;
    try { await api.post(`/mappings/${id}/review`, { action, justification: j }); setMsg(`Mapping ${action}d`); reload(); } catch (e) { setMsg(errorMessage(e)); }
  };
  const suggest = async (fid: string) => { try { const r = await api.post<Row>(`/findings/${fid}/suggest-mapping`); setMsg(`AI proposed ${r.data.suggested.join(", ") || "nothing valid"}${r.data.dropped_invalid.length ? ` (dropped invalid: ${r.data.dropped_invalid.join(", ")})` : ""}`); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  return (
    <div data-testid="mapping-review-page">
      <PageHeader title="Mapping review" subtitle="Suggested and low-confidence mappings need a human decision with justification. AI suggestions are proposals only." />
      {msg && <div className="panel mb-4 p-3 text-[13px]" role="alert" data-testid="mapping-review-msg">{msg}</div>}
      <Panel title={`Pending review (${data?.pending.length ?? 0})`} className="mb-5" testId="mapping-pending">
        <Table head={["Finding", "Control", "Source", "Confidence", "Rationale", "Status", ""]}>
          {data?.pending.map((m: Row) => <tr key={m.id} data-testid={`pending-map-${m.id}`}><td className="td text-[12px]"><Link className="text-blue-800 underline" to={`/findings/${m.finding_id}`}>{m.vuln_id}</Link> {m.finding_title}</td>
            <td className="td font-mono">{m.control_id.toUpperCase()}</td><td className="td text-[11px]">{m.source}</td><td className="td"><S v={m.confidence} /></td><td className="td max-w-[260px] text-[11px]">{m.justification}</td><td className="td"><S v={m.review_status} /></td>
            <td className="td">{can("finding.map") && <div className="flex gap-1"><button className="btn-primary px-2 py-0.5 text-[11px]" onClick={() => act(m.id, "approve")} data-testid={`map-approve-${m.id}`}>Approve</button><button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act(m.id, "reject")} data-testid={`map-reject-${m.id}`}>Reject</button></div>}</td></tr>)}
        </Table>
      </Panel>
      <Panel title={`Unmapped findings (${data?.unmapped.length ?? 0})`} testId="mapping-unmapped">
        {data?.unmapped.map((f: Row) => <div key={f.id} className="flex items-center justify-between border-b border-slate-100 py-1 text-[12px]"><span><Link className="text-blue-800 underline" to={`/findings/${f.id}`}>{f.vuln_id}</Link> {f.title} <span className="text-slate-400">{(f.ccis || []).join(", ")}</span></span>
          {can("finding.map") && <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => suggest(f.id)} data-testid={`suggest-${f.id}`}>AI: suggest mapping</button>}</div>)}
      </Panel>
    </div>
  );
}

export function OscalPanel({ systemId }: { systemId: string }) {
  const { data, reload } = useApi<Row>(`/systems/${systemId}/oscal`);
  const [res, setRes] = useState<Row | null>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const gen = async (m: string) => { setBusy(m); try { setRes((await api.post<Row>(`/systems/${systemId}/oscal/${m}`)).data); reload(); } catch (e) { setMsg(errorMessage(e)); } setBusy(""); };
  const dl = async (eid: string, name: string) => { const r = await api.get(`/oscal-exports/${eid}/download`, { responseType: "blob" }); const a = document.createElement("a"); a.href = URL.createObjectURL(r.data as Blob); a.download = name; a.click(); };
  if (!data) return null;
  return (
    <Panel title={`OSCAL exports (JSON, OSCAL ${data.oscal_version}, validated against official NIST schemas)`} testId="oscal-panel">
      <div className="flex flex-wrap gap-2">{data.models.map((m: string) => <button key={m} className="btn-secondary" disabled={!!busy} onClick={() => gen(m)} data-testid={`oscal-gen-${m}`}>{busy === m ? "Generating…" : `Generate ${m}`}</button>)}</div>
      {msg && <div className="mt-2 text-[12px]" role="alert">{msg}</div>}
      {res && <div className="mt-3 rounded border border-slate-200 p-2 text-[12px]" data-testid="oscal-result">
        <S v={res.validation.valid ? "current" : "failing"} label={res.label} testId="oscal-validation-label" /> <span className="font-mono">{res.file_name}</span> · sha256 {res.sha256.slice(0, 16)}…
        <div className="text-[11px] text-slate-500">Validator: {res.validation.validator} · schema {res.validation.schema} ({res.validation.schema_sha256.slice(0, 12)}…) · {res.validation.error_count} errors</div>
        {res.validation.errors.map((e: Row, i: number) => <div key={i} className="font-mono text-[10px] text-rose-700">{e.path}: {e.message}</div>)}
        <pre className="mt-1 max-h-48 overflow-auto bg-slate-50 p-2 text-[10px]" data-testid="oscal-preview">{JSON.stringify(res.document, null, 1).slice(0, 5000)}</pre>
        <button className="btn-primary mt-1" onClick={() => dl(res.evidence_id, res.file_name)} data-testid="oscal-download-btn">Download</button></div>}
      <div className="mt-3 text-[12px] font-medium">Previous exports (stored as hashed evidence)</div>
      {data.exports.map((e: Row) => <div key={e.evidence_id} className="flex items-center gap-2 text-[11px]"><S v={e.validation?.valid ? "current" : "failing"} label={e.validation?.valid ? "valid" : "invalid"} /><button className="text-blue-800 underline" onClick={() => dl(e.evidence_id, e.file_name)}>{e.file_name}</button> {fmtDate(e.collected_at)}</div>)}
      <div className="mt-3 text-[11px] text-slate-600" data-testid="oscal-unsupported"><b>Not supported:</b> {data.unsupported.map((u: Row) => `${u.model} – ${u.reason}`).join(" · ")}</div>
      <ul className="mt-1 list-disc pl-4 text-[11px] text-slate-600" data-testid="oscal-limitations">{data.limitations.map((l: string) => <li key={l}>{l}</li>)}</ul>
    </Panel>
  );
}

export function EmassStatusBanner({ st }: { st: Row }) {
  return <div className={cn("panel mb-4 p-3 text-[13px]", st.mode === "mock" ? "border-amber-300 bg-amber-50" : st.mode === "oscal_export_only" ? "border-slate-400 bg-slate-50" : "")} data-testid="emass-mode-banner">
    <b>eMASS mode: {st.mode_label}</b>{st.notice && <div data-testid="emass-notice">{st.notice}</div>}
    <div className="text-[11px]">Last sync {st.last_sync_at ? fmtDate(st.last_sync_at) : "never"}{st.last_error && <span className="text-rose-700"> · last error: {st.last_error}</span>}</div></div>;
}

export function EmassPage() {
  const { selectedId: sid } = useSystems();
  const { can } = useAuth();
  const { data, reload } = useApi<Row>(sid ? `/systems/${sid}/emass` : null);
  const [cmp, setCmp] = useState<Row | null>(null);
  const [msg, setMsg] = useState("");
  const [sel, setSel] = useState<Row | null>(null);
  if (!sid) return <NeedSystem />;
  if (!data) return null;
  const run = async (fn: () => Promise<{ data: Row }>, ok: (d: Row) => string) => { try { const r = await fn(); setMsg(ok(r.data)); reload(); return r.data; } catch (e) { setMsg(errorMessage(e)); } };
  const live = data.status.capabilities.live_sync;
  const sm = data.summary;
  return (
    <div data-testid="emass-page">
      <PageHeader title="eMASS sync" subtitle="Outbound changes need approval. Remote changes are never overwritten blindly – conflicts need a human choice.">
        {can("emass.queue") && live && <><button className="btn-secondary" onClick={async () => setCmp(await run(() => api.post(`/systems/${sid}/emass/compare`), () => "Compared local vs remote") ?? null)} data-testid="emass-compare-btn">Compare local vs remote</button>
          <button className="btn-secondary" onClick={() => run(() => api.post(`/systems/${sid}/emass/import`), (d) => `Imported (only empty local fields filled): ${d.filled.join(", ") || "nothing to fill"}`)} data-testid="emass-import-btn">Import metadata</button></>}
      </PageHeader>
      <EmassStatusBanner st={data.status} />
      {msg && <div className="panel mb-4 p-3 text-[13px]" role="alert" data-testid="emass-msg">{msg}</div>}
      <div className="mb-5 grid grid-cols-3 gap-3 md:grid-cols-7">{Object.entries(sm).map(([k, v]) => <Stat key={k} label={k.replace(/_/g, " ")} value={String(v)} testId={`emass-sum-${k}`} />)}</div>
      {cmp && <Panel title={`Local vs remote${cmp.mock ? " (MOCK remote)" : ""}`} className="mb-5" testId="emass-compare">
        <div className="mb-1 text-[12px]">{Object.entries(cmp.summary).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ")} · remote controls: {cmp.controls_remote}</div>
        <Table head={["POA&M", "Remote ID", "State", "Differences", ""]}>{cmp.poams.map((r: Row, i: number) => <tr key={i} data-testid={`cmp-${r.human_id ?? r.remote_id}`}><td className="td font-mono text-[12px]">{r.human_id ?? "—"}</td><td className="td font-mono text-[11px]">{r.remote_id ?? "—"}</td><td className="td"><S v={r.state === "in_sync" ? "current" : r.state === "different" ? "needs_attention" : "not_configured"} label={r.state} /></td>
          <td className="td text-[11px]">{r.differences.map((d: Row) => `${d.field}: local ${d.local} / remote ${d.remote}`).join("; ") || (r.state === "remote_only" ? r.remote?.weakness : "")}</td>
          <td className="td">{r.poam_id && r.state !== "in_sync" && can("emass.queue") && <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => run(() => api.post(`/systems/${sid}/emass/changes`, { entity_type: "poam", entity_id: r.poam_id }), () => "Outbound change queued (proposed)")} data-testid={`queue-${r.human_id}`}>Queue local → eMASS</button>}</td></tr>)}</Table>
      </Panel>}
      <Panel title="Outbound change queue" className="mb-5" testId="emass-queue">
        <Table head={["Entity", "Op", "Trigger", "Requested by", "Approval", "Status", "Attempts", "Submitted", "Actions"]}>
          {data.changes.map((c: Row) => <tr key={c.id} data-testid={`change-${c.id}`}><td className="td text-[12px]">{c.entity_label}<div className="text-[10px] text-slate-500">{c.entity_type} {c.remote_id ?? "(new)"}</div></td>
            <td className="td text-[11px]">{c.operation}</td><td className="td text-[11px]">{c.trigger}</td><td className="td text-[11px]">{c.requester_name ?? "system (auto-queued)"}</td><td className="td"><S v={c.approval_status} /></td>
            <td className="td"><S v={c.status === "succeeded" ? "current" : ["failed", "conflict"].includes(c.status) ? "failing" : "needs_attention"} label={c.status} testId={`change-status-${c.id}`} />{c.next_retry_at && c.status === "pending_retry" && <div className="text-[10px]">retry {fmtDate(c.next_retry_at)}</div>}</td>
            <td className="td font-mono text-[11px]">{c.attempts}</td><td className="td font-mono text-[10px]">{c.submitted_at ? fmtDate(c.submitted_at) : "—"}</td>
            <td className="td"><div className="flex flex-wrap gap-1">
              <button className="text-[11px] text-blue-800 underline" onClick={() => setSel(c)} data-testid={`change-detail-${c.id}`}>Diff & history</button>
              {can("emass.queue") && c.status === "proposed" && <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => { const j = window.prompt("Justification (min 10 chars)"); if (j) run(() => api.post(`/emass/changes/${c.id}/request-approval`, { justification: j }), (d) => `Approval requested (${d.human_id}) – ISSM decides in Reviews`); }} data-testid={`change-request-${c.id}`}>Request approval</button>}
              {can("emass.queue") && ["approved", "pending_retry", "failed"].includes(c.status) && <button className="btn-primary px-2 py-0.5 text-[11px]" disabled={!live} title={!live ? "No live synchronization in this mode" : ""} onClick={() => run(() => api.post(`/emass/changes/${c.id}/submit`), (d) => d.status === "succeeded" ? "eMASS accepted the change" : `Not synced – status ${d.status}: ${d.response?.message ?? ""}`)} data-testid={`change-submit-${c.id}`}>{c.status === "approved" ? "Submit" : "Retry now"}</button>}
              {can("emass.queue") && c.status === "conflict" && ["keep_local", "accept_remote"].map((ch) => <button key={ch} className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => { const j = window.prompt(`Rationale for ${ch} (min 10 chars)`); if (j) run(() => api.post(`/emass/changes/${c.id}/resolve`, { choice: ch, rationale: j }), (d) => `Conflict resolved: ${d.status}`); }} data-testid={`change-${ch}-${c.id}`}>{ch === "keep_local" ? "Keep local (rebase)" : "Accept remote"}</button>)}
            </div></td></tr>)}
        </Table>
      </Panel>
      <Panel title="Sync history" testId="emass-runs">{data.runs.map((r: Row) => <div key={r.id} className="text-[11px]">{fmtDate(r.created_at)} · {r.kind} · {r.mode} · <S v={r.status === "succeeded" ? "current" : "failing"} label={r.status} /> {r.error ?? JSON.stringify(r.summary)}</div>)}</Panel>
      {sel && <Modal title={`${sel.entity_label} – before / after`} onClose={() => setSel(null)} testId="change-modal" wide>
        <div className="grid grid-cols-2 gap-2 text-[11px]"><pre className="bg-slate-50 p-2">{JSON.stringify(sel.before, null, 1)}</pre><pre className="bg-blue-50 p-2">{JSON.stringify(sel.after, null, 1)}</pre></div>
        <div className="mt-2 text-[11px]"><b>API response:</b> {JSON.stringify(sel.response)}</div>
        {(sel.history || []).map((h: Row, i: number) => <div key={i} className="font-mono text-[10px]">{h.at} {h.event} {h.message ?? h.error ?? ""}</div>)}
      </Modal>}
    </div>
  );
}

export function EmassSubmitButton({ systemId, controlId }: { systemId: string; controlId: string }) {
  const { can } = useAuth();
  const [msg, setMsg] = useState("");
  if (!can("emass.queue")) return null;
  const q = async () => { try { await api.post(`/systems/${systemId}/emass/changes`, { entity_type: "control", entity_id: controlId }); setMsg("Queued – request approval on the eMASS page"); } catch (e) { setMsg(errorMessage(e)); } };
  return <><button className="btn-secondary" onClick={q} data-testid="wb-emass-submit">Submit for eMASS sync</button>{msg && <Link to="/emass" className="text-[11px] text-blue-800 underline" data-testid="wb-emass-msg">{msg}</Link>}</>;
}

export function PoamImpactBanner({ p, onDone }: { p: Row; onDone: () => void }) {
  const [msg, setMsg] = useState("");
  if (!p.content_impact) return null;
  const ci = p.content_impact;
  const ack = async (apply: boolean) => { const j = window.prompt("Impact review rationale (min 10 chars)"); if (!j) return; try { await api.post(`/poams/${p.id}/content-impact/ack`, { rationale: j, apply_new_cat: apply }); onDone(); } catch (e) { setMsg(errorMessage(e)); } };
  return <div className={cn("panel mb-4 p-3 text-[13px]", ci.status === "pending_review" ? "border-amber-400 bg-amber-50" : "")} data-testid="poam-content-impact">
    <b>Content update {ci.version}:</b> {ci.impacts.join(", ")} – {ci.status === "pending_review" ? "impact review needed" : `reviewed by ${ci.reviewed_by}: ${ci.rationale}`}
    {ci.status === "pending_review" && <div className="mt-1 flex gap-2">{ci.new_cat && <button className="btn-primary px-2 py-0.5 text-[11px]" onClick={() => ack(true)} data-testid="impact-apply-cat">Accept {ci.new_cat}</button>}<button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => ack(false)} data-testid="impact-ack">Mark reviewed (keep {p.cat})</button></div>}
    {msg && <div className="text-[12px] text-rose-700">{msg}</div>}</div>;
}

export function AdminPhase4Panels() {
  const { can } = useAuth();
  const { data: w, reload: rw } = useApi<Row>("/risk/weights");
  const { data: jobs, reload: rj } = useApi<Row[]>("/scheduled-jobs");
  const { data: st, reload: rs } = useApi<Row>("/emass/status");
  const [cfg, setCfg] = useState<Row>({});
  const [msg, setMsg] = useState("");
  const run = async (fn: () => Promise<{ data: Row }>, ok: (d: Row) => string) => { try { const r = await fn(); setMsg(ok(r.data)); rw(); rj(); rs(); } catch (e) { setMsg(errorMessage(e)); } };
  return (
    <div className="space-y-5" data-testid="admin-phase4">
      {msg && <div className="panel p-3 text-[13px]" role="alert" data-testid="admin4-msg">{msg}</div>}
      <Panel title="Continuous monitoring jobs" testId="jobs-panel" actions={can("admin.content.load") ? <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => run(() => api.post("/content-updates/register"), (d) => `Registered staged content: ${JSON.stringify(d)}`)} data-testid="register-content-btn">Register staged content</button> : undefined}>
        <Table head={["Job", "Every (min)", "Enabled", "Last run", "Status", "Next run", "Runs", ""]}>
          {jobs?.map((j) => <tr key={j.id} data-testid={`job-${j.job_type}`}><td className="td text-[12px]">{j.label}<div className="font-mono text-[10px] text-slate-500">{j.job_type}</div></td>
            <td className="td"><input type="number" className="input w-20" defaultValue={j.interval_minutes} disabled={!can("risk.admin")} onBlur={(e) => Number(e.target.value) !== j.interval_minutes && run(() => api.put(`/scheduled-jobs/${j.id}`, { interval_minutes: Number(e.target.value), enabled: j.enabled }), () => "Schedule updated")} data-testid={`job-interval-${j.job_type}`} /></td>
            <td className="td"><input type="checkbox" checked={j.enabled} disabled={!can("risk.admin")} onChange={(e) => run(() => api.put(`/scheduled-jobs/${j.id}`, { interval_minutes: j.interval_minutes, enabled: e.target.checked }), () => "Schedule updated")} data-testid={`job-enabled-${j.job_type}`} /></td>
            <td className="td font-mono text-[10px]">{j.last_run_at ? fmtDate(j.last_run_at) : "never"}</td><td className="td"><S v={j.last_status === "succeeded" ? "current" : j.last_status === "failed" ? "failing" : "needs_attention"} label={j.last_status ?? "—"} />{j.last_error && <div className="text-[10px] text-rose-700">{j.last_error.slice(0, 80)}</div>}</td>
            <td className="td font-mono text-[10px]" data-testid={`job-next-${j.job_type}`}>{fmtDate(j.next_run_at)}</td><td className="td font-mono text-[11px]">{j.run_count}</td>
            <td className="td">{can("risk.admin") && <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => run(() => api.post(`/scheduled-jobs/${j.id}/run`), () => `${j.job_type} queued for the worker`)} data-testid={`job-run-${j.job_type}`}>Run now</button>}</td></tr>)}
        </Table>
      </Panel>
      {w && <Panel title="Operational prioritization weights" testId="weights-panel">
        <div className="mb-1 text-[11px] text-amber-800">{w.label} · {w.formula}</div>
        {w.weights.map((x: Row) => <label key={x.reason_code} className="flex items-center justify-between border-b border-slate-100 py-1 text-[12px]"><span><span className="font-mono">{x.reason_code}</span> – {x.description}</span>
          <input type="number" className="input w-20" defaultValue={x.weight} disabled={!can("risk.admin")} onBlur={(e) => Number(e.target.value) !== x.weight && run(() => api.put("/risk/weights", { weights: { [x.reason_code]: Number(e.target.value) } }), (d) => `Weights saved – ${d.findings_rescored} findings re-scored`)} data-testid={`weight-${x.reason_code}`} /></label>)}
      </Panel>}
      {st && <Panel title="eMASS connector setup" testId="emass-setup-panel">
        <EmassStatusBanner st={st} />
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[12px]">{Object.entries(st.checks).map(([k, v]) => <div key={k} className="flex justify-between" data-testid={`emass-check-${k}`}><span>{k.replace(/_/g, " ")}</span><S v={v ? "current" : "not_configured"} label={v ? "configured" : "not configured"} /></div>)}
          {Object.entries(st.capabilities).map(([k, v]) => <div key={k} className="flex justify-between" data-testid={`emass-cap-${k}`}><span>capability: {k.replace(/_/g, " ")}</span><span>{v ? "yes" : "no"}</span></div>)}</div>
        {st.last_connectivity && <div className="mt-1 text-[11px]" data-testid="emass-connectivity">Connectivity test: {st.last_connectivity.ok ? "OK" : "FAILED"} – {st.last_connectivity.message}</div>}
        {can("emass.admin") && <div className="mt-3 grid grid-cols-3 gap-2 text-[12px]">
          <select className="input" value={cfg.mode ?? st.mode} onChange={(e) => setCfg({ ...cfg, mode: e.target.value })} data-testid="emass-mode-select">{["mock", "read", "write", "oscal_export_only"].map((m) => <option key={m}>{m}</option>)}</select>
          {["base_url", "app_registration_id", "api_user_uid", "client_cert_path"].map((k) => <input key={k} className="input" placeholder={k} value={cfg[k] ?? ""} onChange={(e) => setCfg({ ...cfg, [k]: e.target.value })} data-testid={`emass-${k}`} />)}
          <input className="input" type="password" placeholder="API key (write-only, stored encrypted)" value={cfg.api_key ?? ""} onChange={(e) => setCfg({ ...cfg, api_key: e.target.value })} data-testid="emass-api-key" />
          <button className="btn-primary" onClick={() => run(() => api.put("/emass/config", { mode: st.mode, ...cfg }), () => "eMASS configuration saved")} data-testid="emass-save-btn">Save</button>
          <button className="btn-secondary" onClick={() => run(() => api.post("/emass/test"), (d) => `Connectivity: ${d.ok ? "OK" : "FAILED"} – ${d.message}`)} data-testid="emass-test-btn">Test connectivity</button>
        </div>}
        {can("emass.admin") && st.mode === "mock" && <div className="mt-3 flex items-center gap-2 text-[12px]" data-testid="failure-sim">
          <b>MOCK failure simulation:</b> {st.failure_simulation.mode} ({st.failure_simulation.remaining} remaining)
          {[["500", "Fail next 2 (500)"], ["timeout", "Timeout next 1"], ["409", "409 conflict next 1"], ["off", "Off"]].map(([m, l]) => <button key={m} className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => run(() => api.put("/emass/failure-sim", { mode: m, remaining: m === "off" ? 0 : m === "500" ? 2 : 1 }), () => `Failure simulation: ${l}`)} data-testid={`failsim-${m}`}>{l}</button>)}
        </div>}
      </Panel>}
    </div>
  );
}
