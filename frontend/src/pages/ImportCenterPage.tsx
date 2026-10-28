import { useCallback, useState } from "react";
import { TableScroll } from "@/components/common/TableScroll";
import { CompletedNext } from "@/components/common/CompletedNext";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Upload } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { useSystems } from "@/context/SystemContext";

const SCANS = ["ckl", "cklb", "xccdf", "nessus_xml", "nessus_csv", "sarif"];
const GENERIC_EMASS = ["system_details", "categorization", "slcm", "ppsm", "poam"];
const STATUS_TONE: Row = { applied: "text-emerald-800", failed: "text-rose-700", "needs review": "text-amber-800", queued: "text-slate-600", processing: "text-blue-800", reverted: "text-violet-800" };

/** Sends the file to the type's EXISTING pipeline endpoint and returns the link to its existing review screen. */
async function route(type: string, sid: string, file: File): Promise<{ link: string; note: string; preview?: Row }> {
  const fd = new FormData();
  fd.append("file", file);
  if (type === "policy") {
    fd.append("title", file.name.replace(/\.[^.]+$/, "")); fd.append("system_ids", sid);
    const r = (await api.post<Row>("/policies", fd)).data;
    return { link: `/policy-auditor/${r.id}`, note: r.duplicate ? r.message : "Queued for Policy Auditor analysis – mappings go to Mapping Review" };
  }
  if (SCANS.includes(type)) {
    const r = (await api.post<Row>(`/systems/${sid}/uploads`, fd)).data;
    return { link: `/ingest-runs/${r.id}`, note: "Received – evidence processing queued" };
  }
  if (type === "control_information") {
    const r = (await api.post<Row>(`/systems/${sid}/emass-imports`, fd)).data;
    return { link: `/systems/${sid}/emass-import/${r.id}`, note: `${r.report?.summary?.rows_to_apply ?? r.counts?.controls ?? 0} row(s) ready for review` };
  }
  if (GENERIC_EMASS.includes(type)) {
    fd.append("system_id", sid);
    const up = (await api.post<Row>("/emass-imports", fd)).data;
    const r = (await api.post<Row>(`/emass-imports/${up.id}/target`, { action: "update", system_id: sid, report_type: type })).data;
    return { link: `/systems/${sid}/emass-import/${r.id}`, note: `${(r.items || []).length} item(s) ready for review` };
  }
  if (type === "test_results") {
    await api.post<Row>(`/systems/${sid}/tr/workbooks`, fd);
    return { link: "/test-results", note: "Workbook received – column detection queued (Test Results)" };
  }
  if (type === "test_plan") {
    const p = (await api.post<Row>(`/systems/${sid}/tr/test-plan/preview`, fd)).data;
    return { link: "/test-results#test-plan", note: `Preview: ${p.counts?.accepted ?? 0} procedure(s) can be imported`, preview: p };
  }
  if (type === "hwsw") {
    const r = (await api.post<Row>(`/systems/${sid}/inventory/imports`, fd)).data;
    return { link: "/inventory", note: `Inventory import v${r.version} queued – differences become proposals` };
  }
  throw new Error("Unsupported type");
}

function FileRow({ f, n, sid, types, preset, onDone }: { f: Row; n: number; sid: string; types: Row; preset?: string; onDone: () => void }) {
  const [type, setType] = useState<string>((preset && f.candidates?.includes(preset) ? preset : f.type) || "");
  const [forced, setForced] = useState(false);
  const [res, setRes] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const t = types[type];
  const go = async () => {
    setBusy(true);
    try { setRes(await route(type, sid, f.file)); onDone(); } catch (e) { toast.error(`${f.file_name}: ${errorMessage(e)}`); } finally { setBusy(false); }
  };
  const importPlan = async () => {
    const fd = new FormData(); fd.append("file", f.file);
    try { const r = (await api.post<Row>(`/systems/${sid}/tr/test-plan/import`, fd)).data; toast.success(`Imported ${r.counts?.imported ?? r.counts?.accepted ?? ""} procedure(s)`); onDone(); }
    catch (e) { toast.error(errorMessage(e)); }
  };
  return (
    <tr className="border-t border-slate-100 align-top" data-testid={`ic-file-${n}`}>
      <td className="min-w-[180px] break-all py-2 pr-2 font-medium">{f.file_name}</td>
      <td className="pr-2">{f.type || f.candidates?.length || forced ? (
        <select className="input w-auto" value={type} onChange={(e) => setType(e.target.value)} data-testid={`ic-type-${n}`}>
          {Object.values(types).map((x: Row) => <option key={x.key} value={x.key} disabled={!x.allowed}>{x.label}{x.allowed ? "" : " (not permitted)"}</option>)}</select>)
        : <span className="text-rose-700" data-testid={`ic-unknown-${n}`}>{f.message}
          {f.override && <button className="ml-2 text-blue-800 underline" onClick={() => { setForced(true); setType(f.override); }} data-testid={`ic-force-${n}`}>{f.override_label}</button>}</span>}</td>
      <td className="pr-2" data-testid={`ic-confidence-${n}`}>{f.confidence}{f.ambiguous ? " – confirm" : ""}</td>
      <td className="pr-2">{t ? <><b>{t.step}</b><div className="text-[11px] text-slate-500">{t.dest}</div></> : "–"}</td>
      <td className="pr-2" data-testid={`ic-count-${n}`}>{f.record_count ?? "–"}</td>
      <td className="whitespace-nowrap">{res ? <div className="text-[12px]" data-testid={`ic-result-${n}`}>{res.note}<br /><Link className="text-blue-800 underline" to={res.link} data-testid={`ic-open-${n}`}>Open review / results</Link><CompletedNext kind={type} counts={res.counts} next={res.link.includes("emass-import") ? { label: "Review the preview and apply the changes", link: res.link } : undefined} testId={`ic-next-${n}`} />
          {res.preview && !!res.preview.counts?.accepted && <button className="ml-2 underline" onClick={importPlan} data-testid={`ic-plan-import-${n}`}>Import accepted procedures</button>}</div>
        : t && (t.allowed ? <button className="btn-primary" disabled={busy || !sid} onClick={go} data-testid={`ic-import-${n}`}>{busy ? "Sending…" : sid ? "Import" : "Choose a system"}</button>
          : <span className="text-[12px] text-slate-500" data-testid={`ic-denied-${n}`}>{t.reason}</span>)}</td>
    </tr>);
}

function History({ sid }: { sid?: string }) {
  const { data, reload } = useApi<Row>("/import-center/history", sid ? { system_id: sid } : undefined);
  const retry = async (r: Row) => {
    try { await api.post(`/import-center/retry/${r.kind}/${r.id}`); toast.success("Re-queued on its pipeline"); reload(); } catch (e) { toast.error(errorMessage(e)); }
  };
  const items: Row[] = data?.items || [];
  return (
    <Panel title={`Import history (${items.length})`} testId="ic-history">
      <div className="overflow-x-auto"><table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>When</th><th>Type</th><th>System</th><th>File · SHA-256</th><th>User</th><th>Status</th><th>Counts</th><th /></tr></thead>
        <tbody>{items.slice(0, 200).map((r) => <tr key={`${r.kind}-${r.id}`} className="border-t border-slate-100" data-testid={`ic-hist-${r.kind}-${r.id}`}>
          <td className="whitespace-nowrap">{r.at ? new Date(r.at).toLocaleString() : ""}</td><td>{r.label}</td><td>{r.system || "–"}</td>
          <td>{r.file_name} <span className="font-mono text-slate-400">{(r.sha256 || "").slice(0, 10)}…</span></td><td>{r.user || "–"}</td>
          <td className={STATUS_TONE[r.status] || ""} title={r.error || r.raw_status}>{r.status}</td>
          <td className="text-slate-600">{Object.entries(r.counts || {}).filter(([, v]) => typeof v === "number").slice(0, 3).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ")}</td>
          <td className="whitespace-nowrap"><Link className="text-blue-800 underline" to={r.link}>Open</Link>
            {r.kind === "emass" && ["applied", "reverted"].includes(r.raw_status) && <Link className="ml-2 text-blue-800 underline" to={`/import-center/manage/${r.id}`} data-testid={`ic-manage-${r.id}`}>Manage imported data</Link>}
            {r.retry && <button className="ml-2 underline" onClick={() => retry(r)} data-testid={`ic-retry-${r.id}`}>Retry</button>}</td></tr>)}</tbody></table></div>
      {!items.length && <p className="text-[12px] text-slate-500">No imports yet.</p>}
    </Panel>);
}

/** ONE Import Center: drop any number of files; each is detected, then routed to its existing pipeline and review screen. */
export default function ImportCenterPage() {
  const { id } = useParams();
  const [q] = useSearchParams();
  const preset = q.get("type") || undefined;
  const { systems, selectedId } = useSystems();
  const [pick, setPick] = useState(id || selectedId || "");  // default: the selected system
  const sid = id || pick;
  const { data: tdata } = useApi<Row>("/import-center/types", sid ? { system_id: sid } : undefined);
  const types: Row = Object.fromEntries((tdata?.types || []).map((t: Row) => [t.key, t]));
  const [files, setFiles] = useState<Row[]>([]);
  const [drag, setDrag] = useState(false);
  const [tick, setTick] = useState(0);
  const add = useCallback(async (list: FileList | File[]) => {
    const out: Row[] = [];
    for (const file of Array.from(list)) {
      const fd = new FormData(); fd.append("file", file); if (sid) fd.append("system_id", sid);
      try { out.push({ ...(await api.post<Row>("/import-center/detect", fd)).data, file }); }
      catch (e) { out.push({ file, file_name: file.name, type: null, message: errorMessage(e) }); }
    }
    setFiles((f) => [...f, ...out]);
  }, [sid]);
  const sysName = systems.find((s: Row) => s.id === sid);
  return (
    <div data-testid="import-center-page">
      <PageHeader title="Import Center" subtitle="One place for every system data import. Files are detected, then sent to the existing pipeline and its review screen – nothing is applied without review." />
      <div className="space-y-5">
        <Panel title="Drop files" testId="ic-dropzone-panel">
          <div className="mb-3 flex flex-wrap items-center gap-3 text-[12px]">
            {id ? <span data-testid="ic-system">Target system: <b>{sysName?.acronym || sysName?.name || id}</b></span>
              : <label>Target system <select className="input ml-1 w-auto" value={pick} onChange={(e) => setPick(e.target.value)} data-testid="ic-system-select">
                <option value="">Choose…</option>{systems.map((s: Row) => <option key={s.id} value={s.id}>{s.acronym} – {s.name}</option>)}</select></label>}
            {preset && <span className="rounded bg-blue-50 px-2 py-0.5 text-blue-900" data-testid="ic-preset">Pre-set type: {types[preset]?.label || preset}</span>}
          </div>
          <label onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors ${drag ? "border-blue-600 bg-blue-50" : "border-slate-300 hover:border-blue-400"}`} data-testid="ic-dropzone">
            <Upload className="mb-2 h-6 w-6 text-slate-500" aria-hidden /><b>Drop one or more files here, or click to choose</b>
            <span className="mt-1 text-[12px] text-slate-600">{tdata?.supported}</span>
            <input type="file" multiple className="hidden" onChange={(e) => { if (e.target.files) add(e.target.files); e.target.value = ""; }} data-testid="ic-file-input" />
          </label>
          <p className="mt-2 text-[11px] text-slate-500" data-testid="ic-reference-note">{tdata?.reference_data_note} Control Information and POA&M are importable here; they are deferred only in the eMASS migration wizard.</p>
          {!!files.length && <table className="mt-3 w-full text-[12px]" data-testid="ic-files"><thead><tr className="text-left text-slate-500"><th>File</th><th>Detected type (override)</th><th>Confidence</th><th>RMF step → destination</th><th>Records</th><th /></tr></thead>
            <tbody>{files.map((f, n) => <FileRow key={n} f={f} n={n} sid={sid} types={types} preset={preset} onDone={() => setTick(tick + 1)} />)}</tbody></table>}
        </Panel>
        <Panel title="Supported import types" testId="ic-types">
          <TableScroll><table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>Type</th><th>RMF step</th><th>Destination</th><th>Your access</th></tr></thead>
            <tbody>{Object.values(types).map((t: Row) => <tr key={t.key} className={`border-t border-slate-100 ${t.allowed ? "" : "text-slate-400"}`} data-testid={`ic-typerow-${t.key}`}>
              <td>{t.label}</td><td>{t.step}</td><td>{t.dest}</td><td>{t.allowed ? "Can import" : t.reason}</td></tr>)}</tbody></table></TableScroll>
        </Panel>
        <History key={`${sid}-${tick}`} sid={id} />
      </div>
    </div>);
}
