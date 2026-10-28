import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { downloadFile } from "@/lib/download";
import { useAuth } from "@/context/AuthContext";
import { TYPES } from "@/components/workbench/emass/ImportPrompt";
import { ImportedCheck, ImportedDeleteBar, ImportedMark, useImported, useSelection } from "@/components/common/Imported";

/** AI column assist: notice for everyone, toggle for eMASS admins (audited server-side). */
export function AiSettingsPanel() {
  const { can } = useAuth();
  const { data, reload } = useApi<Row>("/emass-import-settings/ai");
  const [busy, setBusy] = useState(false);
  if (!data) return null;
  const toggle = async () => {
    setBusy(true);
    try { await api.put("/emass-import-settings/ai", { enabled: !data.enabled }); reload(); toast.success(`AI column assist ${data.enabled ? "turned off" : "turned on"}`); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };
  return (
    <div className="rounded border border-violet-200 bg-violet-50 px-3 py-2 text-[12px] text-violet-950" data-testid="import-ai-notice">
      <div className="flex flex-wrap items-center gap-3"><b>AI column assist: <span data-testid="import-ai-state">{data.enabled ? "on" : "off"}</span></b>
        {!data.provider_configured && <span className="text-slate-600">(no AI provider configured – deterministic import only)</span>}
        {can("emass.admin") && <button className="btn-secondary ml-auto" disabled={busy} onClick={toggle} data-testid="import-ai-toggle">{data.enabled ? "Turn off" : "Turn on"}</button>}</div>
      <p className="mt-1">{data.notice}</p>
    </div>);
}

/** Several files at once: each is uploaded and detected separately; open each to confirm the type and review. */
export function BatchUpload({ systemId, base, onDone }: { systemId?: string; base: string; onDone: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [done, setDone] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    const out: Row[] = [];
    for (const f of files) {
      try {
        const fd = new FormData(); fd.append("file", f); if (systemId) fd.append("system_id", systemId);
        const r = await api.post<Row>("/emass-imports", fd);
        out.push({ name: f.name, id: r.data.id, type: r.data.detected?.type, confidence: r.data.detected?.confidence, ambiguous: r.data.detected?.ambiguous });
      } catch (e) { out.push({ name: f.name, error: errorMessage(e) }); }
      setDone([...out]);
    }
    setBusy(false); onDone();
  };
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <input type="file" multiple accept=".xlsx,.xlsm,.csv" onChange={(e) => { setFiles(Array.from(e.target.files || [])); setDone([]); }} data-testid="import-file-input" />
        <button className="btn-primary" disabled={!files.length || busy} onClick={run} data-testid="import-upload-btn">{busy ? "Detecting…" : files.length > 1 ? `Upload and detect ${files.length} files` : "Upload and detect"}</button>
      </div>
      {!!done.length && <table className="mt-3 w-full text-[12px]" data-testid="import-batch-results"><thead><tr className="text-left text-slate-500"><th>File</th><th>Detected</th><th>Confidence</th><th /></tr></thead>
        <tbody>{done.map((d, n) => <tr key={n} className="border-t border-slate-100" data-testid={`import-batch-row-${n}`}><td>{d.name}</td>
          <td>{d.error ? <span className="text-rose-700">{d.error}</span> : TYPES[d.type] || "unknown – choose the type"}</td><td>{d.confidence}{d.ambiguous ? " (confirm)" : ""}</td>
          <td>{d.id && <Link className="text-blue-800 underline" to={`${base}/${d.id}`} data-testid={`import-batch-open-${n}`}>Confirm type and review</Link>}</td></tr>)}</tbody></table>}
    </div>);
}

export function ExportLinks({ systemId }: { systemId: string }) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-[12px]" data-testid="import-export-links">eMASS-layout exports (round trip):
      <button className="text-blue-800 underline" onClick={() => downloadFile(`/systems/${systemId}/emass-exports/slcm`, "SLCM_Final_Results.xlsx", "SLCM export")} data-testid="import-export-slcm">SLCM worksheet</button>
      <button className="text-blue-800 underline" onClick={() => downloadFile(`/systems/${systemId}/emass-exports/ppsm`, "PPSMBoundariesInformationExport.xlsx", "PPSM export")} data-testid="import-export-ppsm">PPSM boundaries</button>
      <Link className="text-blue-800 underline" to="/test-results" data-testid="import-export-tr">Test Results export</Link>
      <Link className="text-blue-800 underline" to="/inventory" data-testid="import-export-hwsw">HW/SW export</Link>
      <Link className="btn-secondary ml-auto" to={`/systems/${systemId}/migration-report`} data-testid="import-open-migration-report">Migration completion report</Link>
    </div>);
}

export function PpsmPanel({ systemId }: { systemId: string }) {
  const { data, reload } = useApi<Row>(`/systems/${systemId}/ppsm`);
  const items: Row[] = data?.items || [];
  const imp = useImported(systemId, "ppsm"); const isel = useSelection();
  return (
    <Panel title={`PPSM boundary (${items.length})`} testId="ppsm-table">
      <div id="ppsm" />
      <ImportedDeleteBar selected={isel.sel} items={imp.items} onDone={() => { isel.clear(); imp.reload(); reload(); }} testId="ppsm-delete-imported" />
      {items.length ? <table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>Port</th><th>Protocol</th><th>Data service</th><th>Boundaries</th><th>FQDN</th><th>Purpose</th><th>Source</th></tr></thead>
        <tbody>{items.map((e) => <tr key={e.id} className="border-t border-slate-100 align-top" data-testid={`ppsm-row-${e.id}`}><td className="font-mono"><ImportedCheck id={e.id} info={imp.items[e.id]} checked={isel.sel.includes(e.id)} onChange={isel.toggle} />{e.port}</td><td>{e.protocol}</td><td>{e.data_service}</td>
          <td>{(e.boundaries || []).join("; ")}</td><td>{e.fqdn}</td><td>{e.purpose}</td><td className="text-slate-500">{e.source === "emass_import" ? `eMASS import · row ${e.source_row}` : e.source}<ImportedMark info={imp.items[e.id]} testId={`ppsm-imported-${e.id}`} /></td></tr>)}</tbody></table>
        : <p className="text-[12px] text-slate-500" data-testid="ppsm-empty">No PPSM rows yet – import the eMASS PPSM Boundaries template.</p>}
    </Panel>);
}
