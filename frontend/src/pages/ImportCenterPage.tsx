import { useCallback, useEffect, useMemo, useState } from "react";
import { TableScroll } from "@/components/common/TableScroll";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Upload } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { useSystems } from "@/context/SystemContext";
import { useAuth } from "@/context/AuthContext";
import { BatchSummary } from "@/components/import/BatchSummary";
import { QueueTable } from "@/components/import/QueueTable";
import { useImportQueue } from "@/components/import/useImportQueue";
import { LABEL, sortByState } from "@/components/import/queue";
import type { QState } from "@/components/import/queue";

const STATUS_TONE: Row = { applied: "text-emerald-800", failed: "text-rose-700", "needs review": "text-amber-800", queued: "text-slate-600", processing: "text-blue-800", reverted: "text-violet-800" };

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
            {(r.status === "applied" || r.raw_status === "reverted" || r.raw_status === "registered") && <Link className="ml-2 text-blue-800 underline" to={`/import-center/manage/${r.kind}/${r.id}`} data-testid={`ic-manage-${r.id}`}>Manage imported data</Link>}
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
  useEffect(() => { if (!id && !pick && selectedId) setPick(selectedId); }, [id, pick, selectedId]);
  const { data: tdata } = useApi<Row>("/import-center/types", sid ? { system_id: sid } : undefined);
  const types: Row = useMemo(() => Object.fromEntries((tdata?.types || []).map((t: Row) => [t.key, t])), [tdata]);
  const [drag, setDrag] = useState(false);
  const [tick, setTick] = useState(0);
  const { can } = useAuth();
  const bump = useCallback(() => setTick((t) => t + 1), []);
  const qu = useImportQueue(sid, types, preset, can("system.register"), bump);
  const add = qu.add;
  const [filter, setFilter] = useState<QState | "">("");
  const [sel, setSel] = useState<string[]>([]);
  const shown = sortByState(qu.files).filter((f) => !filter || f.state === filter);
  const ready = qu.files.filter((f) => f.state === "ready").length;
  const next = () => { setFilter("needs_decision"); document.querySelector('[data-testid="ic-files"]')?.scrollIntoView({ behavior: "smooth", block: "start" }); };
  const removeKeys = async (keys: string[]) => { await qu.remove(keys); setSel((s) => s.filter((k) => !keys.includes(k))); };
  const sysName = systems.find((s: Row) => s.id === sid);
  return (
    <div data-testid="import-center-page">
      <PageHeader title="Import Center" subtitle="One place for every system data import. Files are detected, then sent to the existing pipeline and its review screen – nothing is applied without review." />
      <div className="space-y-5">
        {!!qu.files.length && <BatchSummary files={qu.files} filter={filter} setFilter={setFilter} onNext={next} onImportAll={qu.importAll} running={qu.running} readyCount={sid ? ready : 0} />}
        {qu.summary && <Panel title="Import all – results" testId="ic-run-summary" actions={<button className="text-[12px] underline" onClick={qu.closeSummary} data-testid="ic-run-summary-close">Close</button>}>
          <p className="text-[12px] text-slate-600">Each file went to its existing pipeline. Nothing was applied: open each review to check, exclude rows and apply.</p>
          <ul className="mt-2 space-y-1 text-[12px]">{qu.summary.map((f) => <li key={f.key} data-testid={`ic-run-row-${f.key}`}><b className="break-all">{f.file.name}</b> – {LABEL[f.state]}
            {f.res?.note ? ` · ${f.res.note}` : ""}{f.error ? ` · ${f.error}` : ""}{f.res?.link && <> · <Link className="text-blue-800 underline" to={f.res.link}>Open review</Link></>}</li>)}</ul>
        </Panel>}
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
          {!sid && !!qu.files.length && <p className="mt-2 text-[12px] font-medium text-amber-800" data-testid="ic-need-system">Choose a target system to import.</p>}
          {!!qu.files.length && <QueueTable files={shown} types={types} sid={sid} sel={sel} setSel={setSel} onType={qu.setType} onImport={qu.runOne} onRemove={removeKeys} onResolve={qu.resolve} busy={qu.running} />}
          {!!qu.files.length && filter && <button className="mt-2 text-[12px] underline" onClick={() => setFilter("")} data-testid="ic-filter-clear">Show all files</button>}
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
