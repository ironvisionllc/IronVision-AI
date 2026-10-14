import { ContentUpdatesPanel } from "@/pages/Phase4Pages";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Copy, Upload } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { ControlLink, NeedSystem, S, Sev, Table } from "@/components/common/Bits";
import { fmtDate } from "@/lib/format";
import { AddToPoamButton } from "@/components/common/Workflow";

export function SourcesPage() {
  const { selectedId: sid } = useSystems();
  const { can } = useAuth();
  const sources = useApi<Row[]>(sid ? `/systems/${sid}/sources` : null);
  const runs = useApi<Row[]>(sid ? `/systems/${sid}/ingest-runs` : null);
  const { data: types } = useApi<Row[]>("/source-types");
  const [msg, setMsg] = useState<Record<string, string>>({});
  const [form, setForm] = useState<Row | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadSrc, setUploadSrc] = useState("");
  if (!sid) return <NeedSystem />;
  const act = async (key: string, fn: () => Promise<{ data: Row }>) => {
    try { const r = await fn(); setMsg({ ...msg, [key]: r.data.message ?? `Status: ${r.data.status}` }); sources.reload(); runs.reload(); }
    catch (e) { setMsg({ ...msg, [key]: errorMessage(e) }); }
  };
  const upload = async (f: File) => {
    const fd = new FormData(); fd.append("file", f); if (uploadSrc) fd.append("source_id", uploadSrc);
    await act("upload", () => api.post(`/systems/${sid}/uploads`, fd));
    setTimeout(() => { runs.reload(); sources.reload(); }, 3000);
  };
  return (
    <div data-testid="sources-page">
      <PageHeader title="Evidence Sources" subtitle="All metrics computed from the database. Non-file connectors are MOCK/DEMO adapters.">
        {can("source.manage") && <button className="btn-secondary" onClick={() => setForm({ name: "", source_type: "manual_upload", credential: "" })} data-testid="add-source-btn">Add source</button>}
      </PageHeader>
      {sources.data && sources.data.length === 0 && !form && (
        <div className="panel mb-5 p-6" data-testid="sources-empty">
          <div className="t-title text-slate-900">Add a source or upload a scan</div>
          <p className="mt-1 text-[13px] text-slate-600">This system has no evidence yet. Add a source (file import or a MOCK connector), or upload a STIG checklist (.ckl/.cklb), ACAS export (.nessus/.csv), SCAP XCCDF or SARIF file below.</p>
        </div>
      )}
      {form && (
        <Panel title="Add evidence source" className="mb-5" testId="source-form">
          <div className="grid grid-cols-4 gap-2">
            <input className="input" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="source-name" />
            <select className="input" value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })} data-testid="source-type">{types?.map((t) => <option key={t.key} value={t.key}>{t.label} ({t.adapter_mode})</option>)}</select>
            <input className="input" type="password" placeholder="Credential / API token (stored encrypted server-side)" value={form.credential} onChange={(e) => setForm({ ...form, credential: e.target.value })} data-testid="source-credential" />
            <button className="btn-primary" onClick={() => act("form", () => api.post(`/systems/${sid}/sources`, { ...form, credential: form.credential || undefined })).then(() => setForm(null))} data-testid="source-save-btn">Save</button>
          </div>
        </Panel>
      )}
      <div className="mb-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {sources.data?.map((s) => (
          <div key={s.id} className="panel p-4" data-testid={`source-card-${s.source_type}`}>
            <div className="flex items-start justify-between"><div><div className="font-semibold text-slate-900">{s.name}</div><div className="text-[11px] text-slate-500">{s.type_label} · {s.adapter_mode === "mock" ? "MOCK/DEMO adapter" : "File import only"}</div></div><S v={s.enabled ? s.health : "disabled"} /></div>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
              {[["Results (latest run)", s.results_latest_run, "results"], ["Findings (failed)", s.findings_open, "open"], ["Passing checks", s.findings_passing, "passing"], ["Mapped findings", s.mapped, "mapped"], ["Unmapped findings", s.unmapped, "unmapped"], ["Assets", s.assets, "assets"], ["Evidence items", s.evidence_count, "evidence"]].map(([k, v, t]) => <div key={k}><dt className="text-slate-500">{k}</dt><dd className="font-mono text-[13px] text-slate-800" data-testid={`source-${s.source_type}-${t}`}>{String(v)}</dd></div>)}
              <div className="col-span-3 text-[10px] text-slate-400">Results = all records the source produced (checks, config snapshots, findings) · Mapped/Unmapped findings = canonical findings; the ingest table counts mapped/unmapped results per run ({s.findings_total}){s.dispositioned ? ` · unmapped incl. ${s.dispositioned} dispositioned` : ""} · freshness {s.freshness}</div>
            </dl>
            <div className="mt-2 text-[11px] text-slate-500">Last run {fmtDate(s.last_run_at)} · Next {s.next_run_at ? fmtDate(s.next_run_at) : "manual"} · {s.credential_set ? "credential set ✓" : "no credential"}</div>
            {can("source.manage") && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                <button className="btn-secondary px-2 py-1 text-xs" onClick={() => act(s.id, () => api.post(`/sources/${s.id}/test`))} data-testid={`source-test-${s.source_type}`}>Test connection</button>
                <button className="btn-secondary px-2 py-1 text-xs" disabled={!s.enabled} onClick={() => act(s.id, () => api.post(`/sources/${s.id}/run`))} data-testid={`source-run-${s.source_type}`}>Run collection</button>
                <button className="btn-secondary px-2 py-1 text-xs" onClick={() => act(s.id, () => api.patch(`/sources/${s.id}`, { enabled: !s.enabled }))}>{s.enabled ? "Disable" : "Enable"}</button>
                <Link className="btn-secondary px-2 py-1 text-xs" to="/evidence-ledger">View evidence</Link>
              </div>
            )}
            {s.last_error && <div className="mt-2 text-[11px] text-rose-700">Error: {s.last_error}</div>}
            {msg[s.id] && <div className="mt-2 rounded bg-slate-50 p-2 text-[11px] text-slate-700" data-testid={`source-msg-${s.source_type}`}>{msg[s.id]}</div>}
          </div>
        ))}
      </div>
      <Panel title="Latest ingest" testId="ingest-runs-panel" actions={can("ingest.upload") && (
        <div className="flex gap-2">
          <select className="input w-56" value={uploadSrc} onChange={(e) => setUploadSrc(e.target.value)} data-testid="upload-source-select"><option value="">(no source)</option>{sources.data?.filter((s) => s.adapter_mode === "file_import").map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          <input ref={fileRef} type="file" accept=".nessus,.csv,.ckl,.cklb" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} data-testid="upload-file-input" />
          <button className="btn-primary" onClick={() => fileRef.current?.click()} data-testid="upload-btn"><Upload className="h-4 w-4" />Upload .nessus / .csv / .ckl / .cklb</button>
        </div>)}>
        {msg.upload && <div className="mb-2 text-[12px] text-slate-700" data-testid="upload-msg">{msg.upload}</div>}
        <Table head={["Received", "Source", "File", "Status", "Results", "Mapped results", "Unmapped results", "Controls touched", "SHA-256"]} testId="ingest-runs-table">
          {runs.data?.map((r) => (
            <tr key={r.id} data-testid={`ingest-run-${r.id}`}>
              <td className="td font-mono text-[11px]"><Link className="text-blue-800 hover:underline" to={`/ingest-runs/${r.id}`}>{fmtDate(r.received_at)}</Link></td>
              <td className="td text-[12px]">{r.source_name ?? "—"}</td><td className="td text-[12px]">{r.file_name}</td><td className="td"><S v={r.status} /></td>
              <td className="td font-mono">{r.total}</td><td className="td font-mono">{r.mapped}</td><td className="td font-mono">{r.unmapped}</td><td className="td font-mono">{r.controls_touched}</td>
              <td className="td font-mono text-[11px]">{r.sha256?.slice(0, 12)}…</td>
            </tr>
          ))}
        </Table>
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
      <Panel title={`Unmapped (${unmapped.length})`} eyebrow="No authoritative/approved mapping – requires explicit mapping or disposition" className="mb-5" testId="unmapped-panel">
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
                  <button className="btn-secondary px-2 py-1 text-xs" onClick={() => send(f.id, "disposition")} data-testid={`disposition-btn-${f.id}`}>Disposition</button>
                </div>) : "—"}</td>
            </tr>
          ))}
        </Table>
      </Panel>
      <Panel title={`All findings in this run (${data.findings.length})`} testId="run-findings-panel">
        <Table head={["Rule / plugin", "Title", "Asset", "Severity", "State", "Mapping", "Controls (grouped, CCIs)", "Observations", ""]}>
          {data.findings.map((f: Row) => (
            <tr key={f.id}>
              <td className="td font-mono text-[11px]">{f.vuln_id ?? f.rule_id}</td><td className="td text-[12px]">{f.title}{f.is_kev && <> <S v="critical" label="KEV" /></>}</td><td className="td text-[12px]">{f.asset_name}</td>
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
        {can("evidence.verify") && <button className="btn-primary" onClick={verify} data-testid="verify-integrity-btn">Verify integrity</button>}
      </PageHeader>
      {job && <div className="panel mb-4 p-3 text-[13px]" data-testid="integrity-job-status">Integrity job <S v={job.status === "succeeded" ? "completed" : job.status} /> {job.result && `checked ${job.result.checked} · ok ${job.result.ok} · mismatched ${job.result.mismatched}`}</div>}
      {msg && <div className="panel mb-4 border-amber-300 bg-amber-50 p-3 text-[13px] text-amber-900" data-testid="ledger-msg">{msg}</div>}
      <ContentUpdatesPanel />
      <div className="mb-4 text-[11px] text-slate-500" data-testid="freshness-policies">Freshness windows: {pol?.map((p) => p.label).join(" · ")}</div>
      <Panel testId="ledger-table-panel">
        <Table head={["Evidence", "Source", "Controls", "Assets", "Collected", "SHA-256", "Window", "Integrity", "Signature", "Freshness", ""]} testId="ledger-table">
          {data?.map((e) => (
            <tr key={e.id} data-testid={`ledger-row-${e.file_name}`}>
              <td className="td text-[12px]">{e.name}<div className="text-[10px] text-slate-400">{e.evidence_type} · v{e.version}</div></td>
              <td className="td text-[12px]">{e.source_name ?? "—"}</td>
              <td className="td max-w-[180px] text-[11px]">{e.controls.slice(0, 6).map((c: string) => <span key={c} className="mr-1"><ControlLink systemId={sid} controlId={c} /></span>)}{e.controls.length > 6 && `+${e.controls.length - 6}`}</td>
              <td className="td max-w-[140px] truncate text-[11px]">{e.assets.join(", ") || "—"}</td>
              <td className="td font-mono text-[11px]">{fmtDate(e.collected_at)}</td>
              <td className="td font-mono text-[11px]">{e.sha256.slice(0, 12)}… <button aria-label="Copy hash" onClick={() => navigator.clipboard?.writeText(e.sha256)} data-testid={`copy-hash-${e.id}`}><Copy className="inline h-3 w-3" /></button></td>
              <td className="td font-mono text-[11px]">{e.freshness_window_days}d</td><td className="td"><S v={e.integrity_status} testId={`ledger-integrity-${e.id}`} /></td><td className="td"><S v={e.signature_status} testId={`ledger-signature-${e.id}`} /></td><td className="td"><S v={e.state} testId={`ledger-state-${e.id}`} /></td>
              <td className="td">{can("demo.tools") && <button className="btn-secondary px-2 py-0.5 text-[10px]" onClick={() => backdate(e.id)} data-testid={`demo-backdate-${e.id}`}>Demo: −45d</button>}</td>
            </tr>
          ))}
        </Table>
      </Panel>
    </div>
  );
}
