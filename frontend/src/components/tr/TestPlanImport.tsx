import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { TestPlanExport } from "@/components/tr/TestPlanExport";

const detail = (e: unknown): Row | null => (e as { response?: { data?: { detail?: Row } } })?.response?.data?.detail ?? null;

export function TestPlanImport({ sid, onDone }: { sid: string; onDone: (id: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [p, setP] = useState<Row | null>(null);
  const [err, setErr] = useState<Row | string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  const send = async (step: "preview" | "import") => {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file); setBusy(true); setErr(null);
    try { const r = await api.post<Row>(`/systems/${sid}/tr/test-plan/${step}`, fd);
      if (step === "preview") setP(r.data); else { setP(null); setFile(null); setDone(`Imported ${r.data.preview.counts.accepted} procedure(s) into “${r.data.file_name}” v${r.data.version} – select it below to review. ${r.data.preview.counts.rejected} row(s) were not imported.`); onDone(r.data.id); }
    } catch (e) { const d = detail(e); setErr(d && typeof d === "object" ? d : errorMessage(e)); if (step === "preview") setP(null); } finally { setBusy(false); }
  };
  const e = typeof err === "object" && err ? err : null;
  return (<div id="test-plan" className="rounded border border-blue-200 bg-blue-50/30 p-4" data-testid="tp-import">
    <div className="text-sm font-medium">Test Plan – import or export (eMASS Test Results / Assessment Procedures)</div>
    <p className="mb-2 text-[12px] text-slate-600">RMF Task A-2/A-3 · Upload the eMASS Test Result Import template (.xlsx) or a CSV with the same columns. Required: AP Acronym, CCI. Preview first – nothing is saved until you click Import.</p>
    <div className="flex flex-wrap items-center gap-2">
      <input type="file" accept=".xlsx,.xlsm,.csv" onChange={(x) => { setFile(x.target.files?.[0] || null); setP(null); setErr(null); setDone(""); }} data-testid="tp-file" />
      <button className="btn-secondary" disabled={!file || busy} onClick={() => send("preview")} data-testid="tp-preview-btn">Preview</button>
      {p && <button className="btn-primary" disabled={busy || !p.counts.accepted} onClick={() => send("import")} data-testid="tp-import-btn">Import {p.counts.accepted} procedure(s)</button>}
    </div>
    <TestPlanExport sid={sid} />
    {done && <div className="mt-2 rounded bg-emerald-50 p-2 text-[12px] text-emerald-800" data-testid="tp-done">{done}</div>}
    {err && <div className="mt-2 rounded bg-rose-50 p-2 text-[12px] text-rose-800" role="alert" data-testid="tp-error">
      {e ? <>{e.message}{e.missing_columns && <div>Found columns: {(e.found_columns || []).join(", ") || "none"}</div>}
        {e.rejected && <ul>{e.rejected.map((r: Row) => <li key={r.row}>Row {r.row}: {r.reason}</li>)}</ul>}</> : String(err)}</div>}
    {p && <div className="mt-3 text-[12px]" data-testid="tp-preview">
      <div data-testid="tp-summary">Recognised: <b>{p.format}</b> · sheet “{p.sheet}”, header row {p.header_row} · {p.counts.rows} rows: <b className="text-emerald-700">{p.counts.accepted} accepted</b>, <b className="text-rose-700">{p.counts.rejected} rejected</b>{p.counts.unchanged ? <>, <b className="text-slate-700" data-testid="tp-unchanged">{p.counts.unchanged} already present (unchanged)</b></> : ""}{p.counts.needs_mapping_review ? `, ${p.counts.needs_mapping_review} need mapping review` : ""}</div>
      {!p.counts.accepted && !p.counts.rejected && !!p.counts.unchanged && <div className="text-[12px] text-slate-700" data-testid="tp-nothing">Nothing to import – every procedure is already in Test Results.</div>}
      <div className="text-[11px] text-slate-500">{p.detected.label}</div>
      {!!p.rejected.length && <table className="mt-2 w-full" data-testid="tp-rejected"><thead><tr className="text-left text-slate-500"><th>Row</th><th>AP Acronym</th><th>CCI</th><th>Why it is rejected</th></tr></thead>
        <tbody>{p.rejected.map((r: Row) => <tr key={r.row} className="border-t border-rose-100 text-rose-900" data-testid={`tp-rejected-${r.row}`}><td>{r.row}</td><td>{r.ap_acronym || "—"}</td><td>{r.cci || "—"}</td><td>{r.reason}</td></tr>)}</tbody></table>}
      {!!p.accepted.length && <table className="mt-2 w-full" data-testid="tp-accepted"><thead><tr className="text-left text-slate-500"><th>Row</th><th>AP Acronym</th><th>CCI</th><th>Control</th><th>Mapping</th></tr></thead>
        <tbody>{p.accepted.slice(0, 200).map((r: Row) => <tr key={r.row} className="border-t border-slate-100" data-testid={`tp-accepted-${r.row}`}><td>{r.row}</td><td>{r.ap_acronym}</td><td>{r.cci}</td><td>{r.control}</td>
          <td className={r.match_status === "ambiguous" ? "text-amber-800" : "text-emerald-700"}>{r.match_status === "ambiguous" ? r.note : "matched"}</td></tr>)}</tbody></table>}
      <div className="mt-1 text-[11px] text-slate-600">Imported rows become Test Results proposals. Compliance Status, Tested By and Date Tested stay blank until the SCA approves them.</div>
    </div>}
  </div>);
}
