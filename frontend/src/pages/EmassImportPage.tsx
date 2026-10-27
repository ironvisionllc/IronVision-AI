import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { downloadFile } from "@/lib/download";
import { ImportReview } from "@/components/workbench/emass/ImportReview";

const LABEL = "eMASS Control Information import – compatibility pending verification against a real eMASS export";
const List = ({ title, rows, render, testId }: { title: string; rows: Row[]; render: (r: Row) => string; testId: string }) => rows?.length ? (
  <details className="text-[12px]" data-testid={testId}><summary className="cursor-pointer font-medium">{title} ({rows.length})</summary>
    <ul className="ml-4 mt-1 list-disc">{rows.slice(0, 200).map((r, i) => <li key={i}>{render(r)}</li>)}</ul></details>) : null;

function Report({ imp }: { imp: Row }) {
  const r = imp.report || {}, d = imp.detection || {}, c = imp.counts || {};
  return (
    <Panel title="Import report" testId="emass-import-report">
      <div className="grid gap-2 text-[12px] md:grid-cols-4" data-testid="import-counts">
        <div>Status: <b data-testid="import-status">{imp.status}</b></div><div>Matched controls: <b>{r.matched}</b></div>
        <div>Changed fields: <b>{c.changed_fields}</b> (accepted {c.accepted}, rejected {c.rejected}, undecided {c.undecided})</div>
        <div>Invalid: <b>{c.invalid}</b> · blocked: <b>{c.blocked}</b>{c.applied_fields !== undefined && <> · applied: <b data-testid="import-applied-count">{c.applied_fields}</b></>}</div>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">Sheet "{d.sheet}", header row {d.header_row}, {d.data_rows} data rows · columns: {Object.entries(d.columns || {}).map(([f, x]: [string, any]) => `${x.header} (${x.col}) → ${f}`).join(", ")}
        {d.unknown_headers?.length ? ` · unknown headers ignored: ${d.unknown_headers.join(", ")}` : ""}{d.ignored_headers?.length ? ` · not importable: ${d.ignored_headers.join(", ")}` : ""} · SHA-256 {imp.sha256?.slice(0, 16)}…</p>
      <div className="mt-2 space-y-1">
        <List title="Controls in the file but not in this system" rows={r.not_in_system} render={(x) => `${x.control} (row ${x.row})`} testId="import-not-in-system" />
        <List title="Invalid values" rows={r.invalid} render={(x) => `Row ${x.row} ${x.control} – ${x.field}: ${x.error}`} testId="import-invalid" />
        <List title="Blocked by eMASS rules" rows={r.blocked} render={(x) => `Row ${x.row} ${x.control} – ${x.field}: ${x.reason}`} testId="import-blocked" />
        <List title="Required-field problems" rows={r.required_issues} render={(x) => `Row ${x.row} ${x.control}: ${x.issue}`} testId="import-required" />
        <List title="Duplicate rows (first occurrence used)" rows={r.duplicates} render={(x) => `${x.control} row ${x.row} (first at row ${x.first_row})`} testId="import-duplicates" />
        <List title="Unreadable Control Acronyms" rows={r.unparseable} render={(x) => `Row ${x.row}: ${x.value}`} testId="import-unparseable" />
        <List title="System controls missing from the file" rows={(r.missing_from_file || []).map((x: string) => ({ x }))} render={(x) => x.x} testId="import-missing" />
        <List title="Apply results" rows={r.apply_results} render={(x) => `${x.control}: ${x.applied.length} field(s) applied${x.failed ? ` – ${x.failed}` : ""}`} testId="import-apply-results" />
      </div>
    </Panel>);
}

export default function EmassImportPage() {
  const { id = "", importId } = useParams();
  const nav = useNavigate();
  const { data: hist, reload } = useApi<Row>(`/systems/${id}/emass-imports`);
  const [imp, setImp] = useState<Row | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState("");
  useEffect(() => { setImp(null); if (importId) api.get<Row>(`/systems/${id}/emass-imports/${importId}`).then((r) => setImp(r.data)).catch((e) => toast.error(errorMessage(e))); }, [id, importId]);
  const upload = async () => {
    setBusy("upload");
    try { const fd = new FormData(); fd.append("file", file!); const r = await api.post<Row>(`/systems/${id}/emass-imports`, fd); toast.success("File parsed – review the changes; nothing has been saved"); reload(); nav(`/systems/${id}/emass-import/${r.data.id}`); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(""); }
  };
  const finish = async (what: "apply" | "discard") => {
    if (what === "apply" && !window.confirm(`Apply ${imp?.counts?.accepted ?? 0} accepted field(s)? Each change is audited.`)) return;
    setBusy(what);
    try { const r = await api.post<Row>(`/systems/${id}/emass-imports/${importId}/${what}`); setImp({ ...r.data, can_apply: imp?.can_apply }); reload(); toast.success(what === "apply" ? `Applied ${r.data.counts?.applied_fields ?? 0} field(s)` : "Import discarded"); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(""); }
  };
  return (
    <div data-testid="emass-import-page">
      <PageHeader title="Import from eMASS" subtitle={LABEL}><Link to={`/systems/${id}/controls`} className="btn-secondary" data-testid="import-back-workbench">Back to Control Workbench</Link></PageHeader>
      {!importId && <div className="space-y-5">
        <Panel title="Upload an eMASS Control Information export" testId="emass-import-upload">
          <p className="mb-2 text-[12px] text-slate-600">.xlsx or .xlsm, max 10 MB / 10,000 rows. Macros are never run. The header row and columns are detected by header name; our own eMASS-formatted Implementation Plan export is accepted too. Nothing is saved until you review and apply.</p>
          {hist?.can_apply ? <div className="flex flex-wrap items-center gap-3">
            <input type="file" accept=".xlsx,.xlsm" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="import-file-input" />
            <button className="btn-primary" disabled={!file || !!busy} onClick={upload} data-testid="import-upload-btn">{busy === "upload" ? "Parsing…" : "Upload and review"}</button>
          </div> : <div className="text-[12px] text-amber-900" data-testid="import-upload-readonly">Only the ISSO or System Owner can upload an eMASS import. You can view import results below.</div>}
          <button className="mt-3 text-[12px] text-blue-800 underline" onClick={() => downloadFile(`/systems/${id}/emass-imports/sample.xlsx`, "SYNTHETIC_ControlInfoExport_sample.xlsx", "Synthetic sample")} data-testid="import-sample-download">Download a SYNTHETIC sample Control Information export for this system</button>
        </Panel>
        <Panel title="Import history" testId="emass-import-history">
          <table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>When</th><th>File</th><th>Who</th><th>Status</th><th>Accepted / rejected / undecided</th><th /></tr></thead>
            <tbody>{(hist?.items || []).map((h: Row) => <tr key={h.id} className="border-t border-slate-100" data-testid={`import-history-${h.id}`}>
              <td>{new Date(h.created_at).toLocaleString()}</td><td>{h.file_name}</td><td>{h.uploaded_by}</td><td>{h.status}</td>
              <td>{h.counts?.accepted ?? 0} / {h.counts?.rejected ?? 0} / {h.counts?.undecided ?? 0}</td>
              <td><Link className="text-blue-800 underline" to={`/systems/${id}/emass-import/${h.id}`} data-testid={`import-open-${h.id}`}>{h.status === "review" ? "Resume review" : "View"}</Link></td></tr>)}</tbody></table>
          {!hist?.items?.length && <p className="text-[12px] text-slate-500">No imports yet.</p>}
        </Panel></div>}
      {importId && imp && <div className="space-y-5">
        <div className="flex items-center gap-3 text-[12px]"><Link to={`/systems/${id}/emass-import`} className="text-blue-800 underline" data-testid="import-back-history">← Import history</Link>
          <span>{imp.file_name} · uploaded by {imp.uploaded_by}</span>
          {imp.can_apply && imp.status === "review" && <span className="ml-auto flex gap-2">
            <button className="btn-secondary" disabled={!!busy} onClick={() => finish("discard")} data-testid="import-discard-btn">Discard import</button>
            <button className="btn-primary" disabled={!!busy || !imp.counts?.accepted} onClick={() => finish("apply")} data-testid="import-apply-btn">Apply {imp.counts?.accepted ?? 0} accepted field(s)</button></span>}</div>
        <Report imp={imp} />
        <ImportReview systemId={id} imp={{ ...imp, labels: LABELS }} onChange={(d) => setImp({ ...d, can_apply: imp.can_apply })} />
      </div>}
    </div>);
}

const LABELS: Row = { implementation_status: "Implementation Status", control_designation: "Security Control Designation", estimated_completion_date: "Estimated Completion Date",
  responsible_entities: "Responsible Entities", slcm_criticality: "SLCM Criticality", slcm_frequency: "SLCM Frequency", slcm_method: "SLCM Method", slcm_reporting: "SLCM Reporting",
  slcm_tracking: "SLCM Tracking", slcm_comments: "SLCM Comments", na_justification: "N/A Justification", common_control_provider: "Common Control Provider",
  implementation_narrative: "Implementation Narrative", severity: "Severity", relevance_of_threat: "Relevance of Threat", likelihood: "Likelihood", impact: "Impact",
  residual_risk_level: "Residual Risk Level", impact_description: "Impact Description", vulnerability_summary: "Vulnerability Summary", recommendations: "Recommendations", mitigations: "Mitigations" };
