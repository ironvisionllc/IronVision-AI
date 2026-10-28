import { CompletedNext } from "@/components/common/CompletedNext";
import { usePaged } from "@/components/common/PageSize";
import { EvidenceActions } from "@/components/evidence/EvidenceActions";
import { ContentUpdatesPanel } from "@/pages/Phase4Pages";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ImportButton } from "@/components/import/ImportButton";
import { Copy, Upload } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { ControlLink, NeedSystem, S, Sev, Table } from "@/components/common/Bits";
import { fmtDate } from "@/lib/format";
import { AddToPoamButton } from "@/components/common/Workflow";
import { PROCESSING_STARTED, ProcessingList } from "@/components/shell/Processing";
import { showNextStep } from "@/components/common/NextStep";
import { StigDetail } from "@/components/evidence/StigDetail";
import { SampleFilesLink } from "@/components/shell/Sandbox";
import { ImportedCheck, ImportedDeleteBar, ImportedMark, useImported, useSelection } from "@/components/common/Imported";
import { Gated } from "@/components/common/RoleGate";

/** Upload rejection in plain language: what happened · how to fix it · accepted formats. */
function UploadError({ e, onClose }: { e: { file: string; text: string }; onClose: () => void }) {
  const [what, rest] = e.text.split(/Supported scan formats:/);
  const [supported, note] = (rest || "").split(/\.\s+(?=Policy documents)/);
  const reason = what.replace(`${e.file}: `, "").trim();
  return (
    <div className="mb-3 rounded border border-rose-200 bg-rose-50 p-3 text-[12px] text-rose-900" role="alert" data-testid="upload-error">
      <div className="font-semibold">“{e.file}” was not imported</div>
      <div className="mt-1"><b>What happened:</b> <span data-testid="upload-error-reason">{reason}</span></div>
      <div className="mt-1"><b>How to fix it:</b> export the results from your scanner or STIG Viewer in one of the accepted formats{supported ? ":" : "."}</div>
      {supported && <ul className="ml-5 mt-1 list-disc" data-testid="upload-error-formats">{supported.replace(/\.\s*$/, "").split(";").map((s) => <li key={s}>{s.trim()}</li>)}</ul>}
      {note && <div className="mt-1">{note}</div>}
      <button className="mt-2 text-[11px] underline" onClick={onClose} data-testid="upload-error-dismiss">Dismiss</button>
    </div>);
}

const sourceKey = (all: { source_type?: unknown }[], i: number) => { const n = all.slice(0, i).filter((x) => x.source_type === all[i].source_type).length; return n ? `${String(all[i].source_type)}-${n + 1}` : String(all[i].source_type); };

const UPLOAD_KINDS: [string, string][] = [
  ["DISA STIG checklist (.ckl, .cklb)", "After a STIG Viewer review of a host or application."],
  ["SCAP / XCCDF results (.xml, incl. ARF)", "Automated SCAP Compliance Checker or OpenSCAP benchmark scans."],
  ["ACAS / Nessus (.nessus or CSV export)", "Vulnerability scans exported from ACAS / Tenable.sc / Nessus."],
  ["SARIF (.sarif / .json)", "Static code or container scans exported from a pipeline."],
  ["Policy or procedure (.docx, .pdf)", "Sent to the Policy Auditor and mapped to the policy (-1) controls of each family."],
];

function UploadFilePanel({ sid, sources, types, onUploaded }: { sid: string; sources: Row[]; types: Row[]; onUploaded: () => void }) {
  const { can } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [src, setSrc] = useState("");
  const [err, setErr] = useState<{ file: string; text: string } | null>(null);
  const [msg, setMsg] = useState("");
  const [newSrc, setNewSrc] = useState<Row | null>(null);
  const fileTypes = types.filter((t) => t.adapter_mode === "file_import");
  const upload = async (f: File) => {
    setErr(null); setMsg("");
    try {
      if (/\.(docx|pdf)$/i.test(f.name)) {
        const fd = new FormData(); fd.append("file", f); fd.append("title", f.name.replace(/\.[^.]+$/, "")); fd.append("owner", ""); fd.append("system_ids", sid);
        const r = await api.post<Row>("/policies", fd);
        setMsg(r.data.duplicate ? r.data.message : `Policy “${f.name}” uploaded (version ${r.data.version}) – Queued for analysis. You will get a summary when it finishes.`);
      } else {
        const fd = new FormData(); fd.append("file", f); if (src) fd.append("source_id", src);
        const r = await api.post<Row>(`/systems/${sid}/uploads`, fd);
        setMsg(r.data.status === "duplicate" ? `“${f.name}” is identical to a file already processed – not double-counted.` : `“${f.name}” received – Queued for processing. Next: the evidence appears on each matching control's “Evidence & Policies” tab when processing finishes.`);
      }
      window.dispatchEvent(new Event(PROCESSING_STARTED));
    } catch (e) { setErr({ file: f.name, text: errorMessage(e) }); }
    setTimeout(onUploaded, 3000);
  };
  const createSrc = async () => {
    try { await api.post(`/systems/${sid}/sources`, newSrc); setNewSrc(null); onUploaded(); setMsg(`Source “${newSrc?.name}” created – pick it below when you upload its files.`); }
    catch (e) { setErr({ file: newSrc?.name ?? "source", text: errorMessage(e) }); }
  };
  return (
    <Panel title="Upload a file" eyebrow="Manual or air-gapped – never asks for credentials" testId="upload-panel">
      <ul className="mb-3 text-[12px]" data-testid="upload-kinds">{UPLOAD_KINDS.map(([k, w]) => <li key={k} className="border-b border-slate-100 py-1"><b className="font-medium">{k}</b> – <span className="text-slate-600">{w}</span></li>)}</ul>
      <p className="mb-2 text-[11px] text-slate-500">The format is detected from the file content, not just its extension.</p>
      {err && <UploadError e={err} onClose={() => setErr(null)} />}
      {msg && <div className="mb-2 rounded bg-emerald-50 p-2 text-[12px] text-emerald-900" role="status" data-testid="upload-msg">{msg}</div>}
      {can("ingest.upload") ? <div className="flex flex-wrap items-end gap-2">
        <label className="text-[12px] font-medium text-slate-700">Link to a source (optional)
          <select className="input mt-1 w-72" value={src} onChange={(e) => setSrc(e.target.value)} data-testid="upload-source-select"
            title="Linking groups repeated uploads (e.g. monthly ACAS exports) under one source so its history and freshness are tracked">
            <option value="">One-off file – don't link to a source</option>
            {sources.filter((s) => s.adapter_mode === "file_import").map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <input ref={fileRef} type="file" accept=".ckl,.cklb,.xml,.nessus,.csv,.sarif,.json,.docx,.pdf" className="hidden" onChange={(e) => { if (e.target.files?.[0]) upload(e.target.files[0]); e.target.value = ""; }} data-testid="upload-file-input" />
        <ImportButton systemId={sid} testId="upload-import-center-btn" primary label="Import… (Import Center)" />
        <button className="btn-secondary" title={src ? "Upload and link to the selected source" : "One-off upload – no source needed"} onClick={() => fileRef.current?.click()} data-testid="upload-btn"><Upload className="h-4 w-4" />{src ? "Upload to the linked source" : "Upload a file"}</button>
      </div> : <p className="text-[12px] text-slate-600" data-testid="upload-denied">Uploading needs the “ingest.upload” permission (ISSO, System Owner or DevSecOps).</p>}
      <p className="mt-2 text-[11px] text-slate-500">“One-off file” = upload without linking to a source – use it for single files. For files you upload regularly, create a file source so they are grouped:
        <Gated perm="source.manage"><button className="ml-1 underline" onClick={() => setNewSrc({ name: "", source_type: "stig_checklist" })} data-testid="create-file-source-btn">create a file source</button></Gated></p>
      {newSrc && <div className="mt-2 flex flex-wrap gap-2" data-testid="file-source-form">
        <input className="input w-48" placeholder="Name, e.g. Monthly ACAS" value={newSrc.name} onChange={(e) => setNewSrc({ ...newSrc, name: e.target.value })} data-testid="file-source-name" />
        <select className="input w-56" value={newSrc.source_type} onChange={(e) => setNewSrc({ ...newSrc, source_type: e.target.value })} data-testid="file-source-type">
          {fileTypes.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select>
        <button className="btn-primary" onClick={createSrc} data-testid="file-source-save">Create</button>
        <span className="w-full text-[11px] text-slate-500">{fileTypes.find((t) => t.key === newSrc.source_type)?.when}</span></div>}
      <ProcessingList sid={sid} />
      <div className="mt-3"><SampleFilesLink /></div>
    </Panel>);
}

function ConnectToolPanel({ sid, types, onSaved }: { sid: string; types: Row[]; onSaved: () => void }) {
  const { can } = useAuth();
  const live = types.filter((t) => t.adapter_mode !== "file_import");
  const [f, setF] = useState<Row>({ name: "", source_type: "", credential: "" });
  const [m, setM] = useState<{ ok?: string; err?: string }>({});
  const type = live.find((t) => t.key === (f.source_type || live[0]?.key));
  const save = async () => {
    try { await api.post(`/systems/${sid}/sources`, { name: f.name, source_type: type?.key, credential: f.credential || undefined });
      setF({ name: "", source_type: "", credential: "" }); onSaved(); setM({ ok: `Connected “${f.name}”. Use “Test connection”, then “Run collection” on its card below.` });
    } catch (e) { setM({ err: errorMessage(e) }); }
  };
  return (
    <Panel title="Connect a tool" eyebrow="Live API sources – the only place that asks for a token" testId="source-form">
      <ul className="mb-3 text-[12px]">{live.map((t) => <li key={t.key} className="border-b border-slate-100 py-1"><b className="font-medium">{t.label}</b> – <span className="text-slate-600">{t.when}</span></li>)}</ul>
      {m.ok && <div className="mb-2 rounded bg-emerald-50 p-2 text-[12px] text-emerald-900" role="status" data-testid="connect-ok">{m.ok}</div>}
      {m.err && <div className="mb-2 rounded bg-rose-50 p-2 text-[12px] text-rose-800" role="alert" data-testid="connect-error">{m.err}</div>}
      {can("source.manage") ? <div className="grid gap-2 md:grid-cols-2">
        <select className="input" value={type?.key ?? ""} onChange={(e) => setF({ ...f, source_type: e.target.value })} data-testid="source-type">{live.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select>
        <input className="input" placeholder="Name, e.g. Prod GovCloud account" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="source-name" />
        <input className="input md:col-span-2" type="password" placeholder="API token / credential (stored encrypted, never shown again)" value={f.credential} onChange={(e) => setF({ ...f, credential: e.target.value })} data-testid="source-credential" />
        <button className="btn-primary md:col-span-2" onClick={save} disabled={!f.name} data-testid="source-save-btn">Connect</button>
        <p className="text-[11px] text-slate-500 md:col-span-2">In this deployment these connectors are MOCK/DEMO adapters: they generate synthetic results and make no network calls.</p>
      </div> : <p className="text-[12px] text-slate-600">Connecting tools needs the “source.manage” permission (ISSO or System Owner).</p>}
    </Panel>);
}


export function SourcesPage() {
  const { selectedId: sid } = useSystems();
  const { can } = useAuth();
  const sources = useApi<Row[]>(sid ? `/systems/${sid}/sources` : null);
  const runs = useApi<Row[]>(sid ? `/systems/${sid}/ingest-runs` : null);
  const runsPg = usePaged("ingest-runs", runs.data);
  const { data: types } = useApi<Row[]>("/source-types");
  const [msg, setMsg] = useState<Record<string, string>>({});
  if (!sid) return <NeedSystem />;
  const act = async (key: string, fn: () => Promise<{ data: Row }>) => {
    try { const r = await fn(); setMsg({ ...msg, [key]: r.data.message ?? `Status: ${r.data.status}` }); sources.reload(); runs.reload(); }
    catch (e) { setMsg({ ...msg, [key]: errorMessage(e) }); }
  };
  return (
    <div data-testid="sources-page">
      <PageHeader title="Evidence Sources" subtitle="Add evidence for this system: upload exported files, or connect a tool that sends results automatically. All counts are computed from the database; live API connectors are MOCK/DEMO adapters in this deployment.">
        <a className="btn-secondary" href="#add-evidence" data-testid="add-source-btn">Add evidence</a>
      </PageHeader>
      {sources.data && sources.data.length === 0 && runs.data?.length === 0 && (
        <div className="panel mb-5 p-6" data-testid="sources-empty">
          <div className="t-title text-slate-900">This system has no evidence yet</div>
          <p className="mt-1 text-[13px] text-slate-600">Most teams start by uploading a STIG checklist or an ACAS scan with <b>Upload a file</b> below. Use <b>Connect a tool</b> only for tools that can send results over an API.</p>
        </div>
      )}
      <div id="add-evidence" className="mb-5 grid gap-5 xl:grid-cols-2" data-testid="add-evidence">
        <UploadFilePanel sid={sid} sources={sources.data ?? []} types={types ?? []} onUploaded={() => { runs.reload(); sources.reload(); }} />
        <ConnectToolPanel sid={sid} types={types ?? []} onSaved={sources.reload} />
      </div>
      <div className="mb-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {sources.data?.map((s, i, all) => { const tk = sourceKey(all, i); return (
          <div key={s.id} className="panel p-4" data-testid={`source-card-${tk}`}>
            <div className="flex items-start justify-between"><div><div className="font-semibold text-slate-900">{s.name}</div><div className="text-[11px] text-slate-500">{s.type_label} · {s.adapter_mode === "mock" ? "MOCK/DEMO adapter" : "File import only"}</div></div><S v={s.enabled ? s.health : "disabled"} /></div>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
              {[["Results (latest run)", s.results_latest_run, "results"], ["Findings total", s.findings_total, "findings-total"], ["Failed (of total)", s.findings_open, "open"], ["Passing (of total)", s.findings_passing, "passing"], ["Mapped (of total)", s.mapped, "mapped"], ["Unmapped (of total)", s.unmapped, "unmapped"], ["Assets", s.assets, "assets"], ["Evidence items", s.evidence_count, "evidence"]].map(([k, v, t]) => <div key={k}><dt className="text-slate-500">{k}</dt><dd className="font-mono text-[13px] text-slate-800" data-testid={`source-${tk}-${t}`}>{String(v)}</dd></div>)}
              <div className="col-span-3 text-[10px] text-slate-400">Results = all records the source produced (checks, config snapshots, findings) · Findings total = Failed + Passing{s.findings_total - s.findings_open - s.findings_passing > 0 ? ` + ${s.findings_total - s.findings_open - s.findings_passing} in other states (e.g. closed)` : ""} = Mapped + Unmapped{s.dispositioned ? ` (unmapped incl. ${s.dispositioned} dispositioned)` : ""} · the ingest table counts mapped/unmapped results per run · freshness {s.freshness}</div>
            </dl>
            <div className="mt-2 text-[11px] text-slate-500">Last run {fmtDate(s.last_run_at)} · Next {s.next_run_at ? fmtDate(s.next_run_at) : "manual"} · {s.credential_set ? "credential set ✓" : "no credential"}</div>
            {can("source.manage") && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                <button className="btn-secondary px-2 py-1 text-xs" onClick={() => act(s.id, () => api.post(`/sources/${s.id}/test`))} data-testid={`source-test-${tk}`}>Test connection</button>
                <button className="btn-secondary px-2 py-1 text-xs" disabled={!s.enabled} onClick={() => act(s.id, () => api.post(`/sources/${s.id}/run`))} data-testid={`source-run-${tk}`}>Run collection</button>
                <button className="btn-secondary px-2 py-1 text-xs" onClick={() => act(s.id, () => api.patch(`/sources/${s.id}`, { enabled: !s.enabled }))}>{s.enabled ? "Disable" : "Enable"}</button>
                <Link className="btn-secondary px-2 py-1 text-xs" to="/evidence-ledger">View evidence</Link>
              </div>
            )}
            {s.last_error && <div className="mt-2 text-[11px] text-rose-700">Error: {s.last_error}</div>}
            {msg[s.id] && <div className="mt-2 rounded bg-slate-50 p-2 text-[11px] text-slate-700" data-testid={`source-msg-${tk}`}>{msg[s.id]}</div>}
          </div>
        ); })}
      </div>
      <Panel title="Latest ingest" testId="ingest-runs-panel">
        <p className="mb-2 text-[12px] text-slate-600">Every uploaded or collected file appears here. Open a row to see its rules / findings and how they mapped to controls.</p>
        <div className="mb-2 flex justify-end">{runsPg.select}</div>
        <Table head={["Received", "Source", "File", "Status", "Results", "Mapped results", "Unmapped results", "Controls touched", "SHA-256"]} testId="ingest-runs-table">
          {runsPg.rows.map((r) => (
            <tr key={r.id} data-testid={`ingest-run-${r.id}`}>
              <td className="td font-mono text-[11px]"><Link className="text-blue-800 hover:underline" to={`/ingest-runs/${r.id}`}>{fmtDate(r.received_at)}</Link></td>
              <td className="td text-[12px]">{r.source_name ?? "—"}</td><td className="td text-[12px]">{r.file_name}</td><td className="td"><S v={r.status} /></td>
              <td className="td font-mono">{r.total}</td><td className="td font-mono">{r.mapped}</td><td className="td font-mono">{r.unmapped}</td><td className="td font-mono">{r.controls_touched}</td>
              <td className="td font-mono text-[11px]">{r.sha256?.slice(0, 12)}…</td>
            </tr>
          ))}
        </Table>
        <div className="mt-2 flex justify-end">{runsPg.pager}</div>
      </Panel>
    </div>
  );
}

export function IngestRunPage() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const { data, reload } = useApi<Row>(`/ingest-runs/${id}`);
  const [edit, setEdit] = useState<Row>({});
  const [err, setErr] = useState("");
  const imp = useImported(data?.run?.system_id, "finding"); const isel = useSelection();
  if (!data) return null;
  const r = data.run;
  const unmapped = data.findings.filter((f: Row) => f.mapping_status === "unmapped");
  const send = async (fid: string, kind: "map" | "disposition") => {
    try {
      const res = await api.post(`/findings/${fid}/${kind}`, kind === "map" ? { control_id: edit[fid]?.control_id, justification: edit[fid]?.justification } : { disposition: "no_control_mapping", justification: edit[fid]?.justification });
      setErr(res?.data?.message ?? ""); reload();
    }
    catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <div data-testid="ingest-run-page">
      <PageHeader title={`Ingest run · ${r.file_name}`} subtitle={`Status ${r.status} · ${r.total} records · ${r.mapped} mapped · ${r.unmapped} unmapped · ${r.controls_touched} controls touched`} />
      {r.status === "duplicate" && <div className="panel mb-4 border-sky-300 bg-sky-50 p-3 text-sm text-sky-900" data-testid="duplicate-notice">Duplicate upload: identical SHA-256 already ingested. Not re-processed or double-counted. Showing results of the original run.</div>}
      {data.evidence && <div className="mb-4 font-mono text-[11px] text-slate-600" data-testid="run-evidence-hash">evidence sha256 {data.evidence.sha256} · signature {data.evidence.signature_status} · integrity {data.evidence.integrity_status}</div>}
      {err && <div className="mb-3 text-sm text-rose-700" role="alert">{err}</div>}
      {r.status !== "failed" && <CompletedNext kind="scan" next={data.findings.some((f: Row) => !f.poam_id && f.current_state === "open") ? { label: "Create POA&Ms for the open findings below", link: "#run-create-poam" } : { label: "Review the findings in Mapping review", link: "/mapping-review" }} testId="run-completed-next" />}
      {data.findings.some((f: Row) => !f.poam_id && f.current_state === "open") && <Panel title="Create POA&M" eyebrow="Open findings from this run without a POA&M – nothing is created until you confirm each one" className="mb-4" testId="run-create-poam">
        <div id="run-create-poam" className="space-y-1 text-[12px]">{data.findings.filter((f: Row) => !f.poam_id && f.current_state === "open").slice(0, 25).map((f: Row) => <div key={f.id} className="flex items-center gap-2">
          <Link className="flex-1 truncate text-blue-800 underline" to={`/findings/${f.id}`}>{f.title || f.rule_id || f.id}</Link><AddToPoamButton findingId={f.id} onDone={reload} /></div>)}</div></Panel>}
      {["ckl", "cklb", "xccdf"].includes(r.file_format) && <StigDetail runId={r.duplicate_of_run_id ?? r.id} />}
      <Panel title={`Unmapped (${unmapped.length})`} eyebrow="These results are not linked to any NIST 800-53 control yet" className="mb-5" testId="unmapped-panel">
        {unmapped.length > 0 && <div className="mb-3 rounded bg-slate-50 p-3 text-[12px] text-slate-700" data-testid="unmapped-explainer">
          <b>What this means:</b> the app links a result to a control through DISA's CCI list (STIG rule → CCI → NIST 800-53 Rev 5 control). A result lands here when its CCI has <b>no Rev 5 mapping</b> in that list (some CCIs map only to Rev 4 or were retired), or when it names no CCI at all (e.g. vulnerability scan results).
          <div className="mt-1"><b>What to do:</b> either <b>Map</b> it to the control it supports (vulnerabilities usually belong to RA-5 Vulnerability Monitoring or SI-2 Flaw Remediation), or choose <b>No control needed</b> with a reason if it doesn&apos;t affect any control in your 800-53 ATO. Both are recorded with your reason.</div></div>}
        <Table head={["Finding", "Asset", "State", "CCIs / CVEs", "Map to control / disposition (justification required)"]}>
          {unmapped.map((f: Row) => (
            <tr key={f.id} data-testid={`unmapped-${f.rule_id}-${f.asset_name}`}>
              <td className="td text-[12px]"><span className="font-mono">{f.vuln_id ?? f.rule_id}</span> {f.title}</td><td className="td text-[12px]">{f.asset_name}{f.asset_unmatched && <div><S v="unmatched" label="asset" /></div>}</td><td className="td"><S v={f.current_state} /></td>
              <td className="td font-mono text-[11px]">{[...(f.ccis || []), ...(f.cves || [])].join(", ") || "—"}</td>
              <td className="td">{can("finding.map") ? (
                <div className="flex gap-1">
                  <input className="input w-24" placeholder="ra-5" onChange={(e) => setEdit({ ...edit, [f.id]: { ...edit[f.id], control_id: e.target.value } })} data-testid={`map-control-${f.id}`} />
                  <input className="input" placeholder="Justification (min 10 chars)" onChange={(e) => setEdit({ ...edit, [f.id]: { ...edit[f.id], justification: e.target.value } })} data-testid={`map-justification-${f.id}`} />
                  <button className="btn-primary px-2 py-1 text-xs" onClick={() => send(f.id, "map")} data-testid={`map-btn-${f.id}`}>Map</button>
                  <button className="btn-secondary px-2 py-1 text-xs" onClick={() => send(f.id, "disposition")} data-testid={`disposition-btn-${f.id}`} title="Record that this result does not need a control mapping (reason required)">No control needed</button>
                </div>) : "—"}</td>
            </tr>
          ))}
        </Table>
      </Panel>
      <Panel title={`All findings in this run (${data.findings.length})`} testId="run-findings-panel">
        <ImportedDeleteBar selected={isel.sel} items={imp.items} onDone={() => { isel.clear(); imp.reload(); reload(); }} testId="run-delete-imported" />
        <Table head={["Rule / plugin", "Title", "Asset", "Severity", "State", "Mapping", "Controls (grouped, CCIs)", "Observations", ""]}>
          {data.findings.map((f: Row) => (
            <tr key={f.id} data-testid={`run-finding-${f.id}`}>
              <td className="td font-mono text-[11px]"><ImportedCheck id={f.id} info={imp.items[f.id]} checked={isel.sel.includes(f.id)} onChange={isel.toggle} />{f.vuln_id ?? f.rule_id}<ImportedMark info={imp.items[f.id]} testId={`run-imported-${f.id}`} /></td><td className="td text-[12px]">{f.title}{f.is_kev && <> <S v="critical" label="KEV" /></>}</td><td className="td text-[12px]">{f.asset_name}</td>
              <td className="td text-[12px]"><Sev v={f.cat ?? f.severity} /></td><td className="td"><S v={f.current_state} /></td><td className="td"><S v={f.mapping_status} /></td>
              <td className="td text-[11px]">{f.controls.map((m: Row) => <div key={m.control_id}><ControlLink systemId={r.system_id} controlId={m.control_id} /> {m.ccis.length > 0 && <span className="font-mono">via {m.ccis.join(", ")}</span>} <span className="text-slate-500">{m.review_status}</span></div>)}</td>
              <td className="td font-mono">{f.observation_count}</td>
              <td className="td"><Link className="mr-1 text-[11px] text-blue-800 underline" to={`/findings/${f.id}`} data-testid={`run-finding-link-${f.id}`}>view</Link>{f.current_state === "open" && <AddToPoamButton findingId={f.id} onDone={reload} />}</td>
            </tr>
          ))}
        </Table>
      </Panel>
    </div>
  );
}

export function LedgerPage() {
  const { selectedId: sid } = useSystems();
  const { can } = useAuth();
  const { data, reload } = useApi<Row[]>(sid ? `/systems/${sid}/evidence` : null);
  const { data: pol } = useApi<Row[]>("/freshness-policies");
  const ledgerPg = usePaged("evidence-ledger", data);
  const [job, setJob] = useState<Row | null>(null);
  const [msg, setMsg] = useState("");
  if (!sid) return <NeedSystem />;
  const verify = async () => {
    const r = await api.post<Row>(`/systems/${sid}/evidence/verify`);
    const poll = async () => { const j = await api.get<Row>(`/jobs/${r.data.job_id}`); setJob(j.data); if (["queued", "running"].includes(j.data.status)) setTimeout(poll, 1500); else reload(); };
    poll();
  };
  const backdate = async (eid: string) => {
    try { const r = await api.post<Row>(`/demo/evidence/${eid}/collected-at`, { days_ago: 45 }); setMsg(`Demo tool: collected_at moved 45 days back → state ${r.data.state}`); reload(); } catch (e) { setMsg(errorMessage(e)); }
  };
  return (
    <div data-testid="ledger-page">
      <PageHeader title="Evidence Ledger" subtitle="Immutable originals, SHA-256 at receipt, re-verifiable integrity, policy-driven freshness.">
        <Gated perm="evidence.verify"><button className="btn-primary" onClick={verify} data-testid="verify-integrity-btn">Verify integrity</button></Gated>
      </PageHeader>
      {job && <div className="panel mb-4 p-3 text-[13px]" data-testid="integrity-job-status">Integrity job <S v={job.status === "succeeded" ? "completed" : job.status} /> {job.result && `checked ${job.result.checked} · ok ${job.result.ok} · mismatched ${job.result.mismatched}`}</div>}
      {msg && <div className="panel mb-4 border-amber-300 bg-amber-50 p-3 text-[13px] text-amber-900" data-testid="ledger-msg">{msg}</div>}
      <ContentUpdatesPanel />
      <div className="mb-4 text-[11px] text-slate-500" data-testid="freshness-policies">Freshness windows: {pol?.map((p) => p.label).join(" · ")}</div>
      <Panel testId="ledger-table-panel">
        <div className="mb-2 flex justify-end">{ledgerPg.select}</div>
        <Table head={["Evidence", "Source", "Controls", "Assets", "Collected", "SHA-256", "Window", "Integrity", "Signature", "Freshness", ""]} testId="ledger-table">
          {ledgerPg.rows.map((e) => (
            <tr key={e.id} data-testid={`ledger-row-${e.file_name}`}>
              <td className="td text-[12px]">{e.name}<div className="text-[10px] text-slate-400">{e.evidence_type} · v{e.version}</div></td>
              <td className="td text-[12px]">{e.source_name ?? "—"}</td>
              <td className="td max-w-[180px] text-[11px]">{e.controls.slice(0, 6).map((c: string) => <span key={c} className="mr-1"><ControlLink systemId={sid} controlId={c} /></span>)}{e.controls.length > 6 && `+${e.controls.length - 6}`}</td>
              <td className="td max-w-[140px] truncate text-[11px]">{e.assets.join(", ") || "—"}</td>
              <td className="td font-mono text-[11px]">{fmtDate(e.collected_at)}</td>
              <td className="td font-mono text-[11px]">{e.sha256.slice(0, 12)}… <button aria-label="Copy hash" onClick={() => navigator.clipboard?.writeText(e.sha256)} data-testid={`copy-hash-${e.id}`}><Copy className="inline h-3 w-3" /></button></td>
              <td className="td font-mono text-[11px]">{e.freshness_window_days}d</td><td className="td"><S v={e.integrity_status} testId={`ledger-integrity-${e.id}`} /></td><td className="td"><S v={e.signature_status} testId={`ledger-signature-${e.id}`} /></td><td className="td"><S v={e.state} testId={`ledger-state-${e.id}`} /></td>
              <td className="td whitespace-nowrap"><EvidenceActions ev={e} systemId={sid!} onChanged={reload} /> <Gated perm="demo.tools"><button className="btn-secondary px-2 py-0.5 text-[10px]" onClick={() => backdate(e.id)} data-testid={`demo-backdate-${e.id}`}>Demo: −45d</button></Gated></td>
            </tr>
          ))}
        </Table>
        <div className="mt-2 flex justify-end">{ledgerPg.pager}</div>
      </Panel>
    </div>
  );
}
