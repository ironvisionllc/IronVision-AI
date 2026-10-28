import { useEffect, useState } from "react";
import { CompletedNext } from "@/components/common/CompletedNext";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { downloadFile } from "@/lib/download";
import { ImportReview } from "@/components/workbench/emass/ImportReview";
import { ImportPrompt, TYPES } from "@/components/workbench/emass/ImportPrompt";
import { useSystems } from "@/context/SystemContext";
import { AiSettingsPanel, BatchUpload, ExportLinks, PpsmPanel } from "@/components/workbench/emass/ImportCenter";

const REVERTIBLE = ["slcm", "categorization", "ppsm"];

const LABEL = "eMASS report import – compatibility pending verification against a real eMASS export";
const List = ({ title, rows, render, testId }: { title: string; rows: Row[]; render: (r: Row) => string; testId: string }) => rows?.length ? (
  <details className="text-[12px]" data-testid={testId}><summary className="cursor-pointer font-medium">{title} ({rows.length})</summary>
    <ul className="ml-4 mt-1 list-disc">{rows.slice(0, 200).map((r, i) => <li key={i}>{render(r)}</li>)}</ul></details>) : null;

function StrategyPlan({ plan, mode, setMode, editable }: { plan: Row; mode: string; setMode: (m: "strategy" | "per_control") => void; editable: boolean }) {
  const used = plan.mode || mode;
  return (
    <Panel title="Continuous Monitoring Strategy from this worksheet" testId="import-strategy-plan">
      <p className="text-[13px] font-medium" data-testid="import-strategy-summary">{plan.summary}</p>
      <p className="mt-1 text-[12px] text-slate-600">From {plan.counts?.controls} controls{plan.counts?.no_slcm_skipped ? ` (${plan.counts.no_slcm_skipped} Inherited / Not Applicable controls skipped – no SLCM)` : ""}.
        {plan.kept_profiles ? ` ${plan.kept_profiles} existing profile(s) kept.` : ""}</p>
      <p className="mt-1 rounded bg-amber-50 px-2 py-1 text-[12px] text-amber-900" data-testid="import-strategy-note">{plan.note}</p>
      {plan.blocked && <p className="mt-1 text-[12px] text-rose-700" data-testid="import-strategy-blocked">{plan.blocked}</p>}
      {editable && !plan.blocked ? <div className="mt-2 flex flex-wrap gap-4 text-[12px]" role="radiogroup">
        <label className="flex items-center gap-1"><input type="radio" checked={mode === "strategy"} onChange={() => setMode("strategy")} data-testid="slcm-mode-strategy" />Save as strategy draft + per-control exceptions (recommended)</label>
        <label className="flex items-center gap-1"><input type="radio" checked={mode === "per_control"} onChange={() => setMode("per_control")} data-testid="slcm-mode-per-control" />Apply as per-control values now</label></div>
        : <p className="mt-2 text-[12px]" data-testid="import-strategy-mode">Applied as: <b>{used === "per_control" ? "per-control values" : "strategy draft + per-control exceptions"}</b></p>}
      <details className="mt-2 text-[12px]"><summary className="cursor-pointer">Defaults and family profiles</summary>
        <ul className="mt-1 list-disc pl-5">{Object.entries(plan.defaults || {}).map(([k, v]) => <li key={k}>Default {LABELS[k] || k}: {String(v)}</li>)}
          {(plan.profiles || []).map((p: Row) => <li key={p.name}>{p.name}: {Object.entries(p.values).map(([k, v]) => `${LABELS[k] || k} = ${v}`).join("; ")}</li>)}</ul></details>
    </Panel>);
}

function Report({ imp }: { imp: Row }) {
  const r = imp.report || {}, c = imp.counts || {}, d = imp.detection || {};
  return (
    <Panel title={`Import report – ${imp.report_type_label}`} testId="emass-import-report">
      <div className="grid gap-2 text-[12px] md:grid-cols-4" data-testid="import-counts">
        <div>Status: <b data-testid="import-status">{imp.status}</b> · {imp.detected?.confidence} confidence</div><div>Items: <b>{(imp.items || []).length}</b></div>
        <div>Changed fields: <b>{c.changed_fields}</b> (accepted {c.accepted}, rejected {c.rejected}, undecided {c.undecided})</div>
        <div>Invalid: <b>{c.invalid}</b> · blocked: <b>{c.blocked}</b>{c.applied_fields !== undefined && <> · applied: <b data-testid="import-applied-count">{c.applied_fields}</b></>}</div>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">{imp.label} · SHA-256 {imp.sha256?.slice(0, 16)}…{d.sheet ? ` · sheet "${d.sheet}", header row ${d.header_row}` : ""}</p>
      {r.summary && <div className="mt-2 flex flex-wrap gap-2 text-[12px]" data-testid="import-row-summary">
        <span className="rounded bg-slate-100 px-2 py-0.5">Rows read <b>{r.summary.rows_read}</b></span>
        <span className="rounded bg-emerald-50 px-2 py-0.5 text-emerald-900" data-testid="import-rows-to-apply">Would apply <b>{r.summary.rows_to_apply}</b></span>
        <span className="rounded bg-amber-50 px-2 py-0.5 text-amber-900" data-testid="import-rows-warnings">With warnings <b>{r.summary.rows_with_warnings}</b></span>
        <span className={`rounded px-2 py-0.5 ${r.summary.rows_with_errors ? "bg-rose-50 text-rose-800" : "bg-slate-100"}`} data-testid="import-rows-errors">With errors <b>{r.summary.rows_with_errors}</b></span>
        <span className="rounded bg-slate-100 px-2 py-0.5">Not in this system <b>{r.summary.rows_not_in_system}</b></span>
        <span className="rounded bg-slate-100 px-2 py-0.5">Placeholders ignored <b>{r.summary.placeholders_ignored}</b></span></div>}
      {imp.detected?.mismatch && <div className="mt-2 rounded border border-rose-300 bg-rose-50 px-3 py-1.5 text-[12px] text-rose-800" data-testid="import-mismatch-banner">System mismatch: {imp.detected.mismatch}</div>}
      <div className="mt-2 space-y-1">
        <List title="Not in this system" rows={r.not_in_system} render={(x) => `${x.control} (row ${x.row})`} testId="import-not-in-system" />
        <List title="Invalid values" rows={r.invalid} render={(x) => `Row ${x.row} ${x.control} – ${x.field}: ${x.error}`} testId="import-invalid" />
        <List title="Blocked by rules" rows={r.blocked} render={(x) => `Row ${x.row} ${x.control} – ${x.field}: ${x.reason}`} testId="import-blocked" />
        <List title="Required-field problems" rows={r.required_issues} render={(x) => `Row ${x.row} ${x.control}: ${x.issue}`} testId="import-required" />
        <List title="Implementation Status not applied (eMASS required fields missing)" rows={r.status_not_applied} render={(x) => `Row ${x.row} ${x.control}: ${x.status} needs ${x.missing.join(", ")}`} testId="import-status-not-applied" />
        <List title="Warnings – value not applied" rows={r.warnings} render={(x) => `Row ${x.row} ${x.control} – ${x.field} "${x.value}": ${x.reason}`} testId="import-warnings" />
        <List title="Info – placeholders ignored" rows={r.info} render={(x) => `Row ${x.row} ${x.control} – ${x.field} "${x.value}": ${x.note}`} testId="import-info" />
        <List title="Duplicate rows (first occurrence used)" rows={r.duplicates} render={(x) => `${x.control} row ${x.row} (first at row ${x.first_row})`} testId="import-duplicates" />
        <List title="System controls missing from the file" rows={(r.missing_from_file || []).map((x: string) => ({ x }))} render={(x) => x.x} testId="import-missing" />
        <List title="Exception queue" rows={r.exceptions} render={(x) => `${x.row ? `Row ${x.row} ` : ""}${x.control}: ${x.issue}`} testId="import-exceptions" />
        <List title="Not imported" rows={(r.not_imported || []).map((x: string) => ({ x }))} render={(x) => x.x} testId="import-not-imported" />
        {r.duplicate_of && <p className="text-[12px] text-amber-800" data-testid="import-duplicate-of">This exact file (same SHA-256) was already applied to this system – values that already match propose no change.</p>}
        {r.ai?.used && <p className="text-[12px] text-violet-800" data-testid="import-ai-used">Columns were mapped with AI suggestions (sheet “{r.ai.sheet}”) – every value needs your review; nothing is preselected.</p>}
        <List title="Apply results" rows={r.apply_results} render={(x) => `${x.control}: ${x.applied.length} field(s) applied${x.failed ? ` – ${x.failed}` : ""}${(r.reverted_keys || []).includes(x.key) ? " – reverted" : ""}`} testId="import-apply-results" />
      </div>
    </Panel>);
}

export default function EmassImportPage() {
  const { id, importId } = useParams();
  const nav = useNavigate();
  const { systems } = useSystems();
  const ctxSys = id ? systems.find((s: Row) => s.id === id) || { id } : undefined;
  const base = id ? `/systems/${id}/emass-import` : "/emass-import";
  const { data: hist, reload } = useApi<Row>(`/emass-imports${id ? `?system_id=${id}` : ""}`);
  const [imp, setImp] = useState<Row | null>(null);
  const [sample, setSample] = useState("slcm");
  const [busy, setBusy] = useState("");
  const [slcmMode, setSlcmMode] = useState<"strategy" | "per_control">("strategy");
  useEffect(() => { setImp(null); if (importId) api.get<Row>(`/emass-imports/${importId}`).then((r) => setImp(r.data)).catch((e) => toast.error(errorMessage(e))); }, [importId]);
  const revert = async () => {
    if (!window.confirm("Revert every change this import applied? The values from before the import are restored; each step is audited.")) return;
    setBusy("revert");
    try { const r = await api.post<Row>(`/emass-imports/${importId}/revert`, {}); setImp(r.data); reload(); toast.success(`Reverted ${r.data.reverted.length} item(s)`); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(""); }
  };
  const finish = async (what: "apply" | "discard") => {
    if (what === "apply" && !window.confirm(`Apply ${imp?.counts?.accepted ?? 0} accepted field(s)? Fields that break a rule are reported, not saved. Each change is audited.`)) return;
    setBusy(what);
    try { const r = await api.post<Row>(`/emass-imports/${importId}/${what}`, undefined, what === "apply" && imp?.report_type === "slcm" ? { params: { slcm_mode: slcmMode } } : undefined); setImp(what === "apply" ? r.data : { ...imp, ...r.data }); reload(); toast.success(what === "apply" ? `Applied ${r.data.counts?.applied_fields ?? 0} field(s)` : "Import discarded"); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(""); }
  };
  return (
    <div data-testid="emass-import-page">
      <PageHeader title="eMASS Import Center" subtitle={LABEL}>{id && <Link to={`/systems/${id}/controls`} className="btn-secondary" data-testid="import-back-workbench">Back to Control Workbench</Link>}</PageHeader>
      {!importId && <div className="space-y-5">
        <Panel title="Upload eMASS exports" testId="emass-import-upload">
          <p className="mb-2 text-[12px] text-slate-600">System Details, Categorization, Test Results, SLCM worksheet, Hardware/Software List or PPSM Boundaries – one file or several at once; the type is detected from sheet names and headers (you can override it). .xlsx, .xlsm or .csv, max 10 MB / 10,000 rows; macros and formulas are never run. Imported values are preselected, but nothing is saved until you review and apply.</p>
          <p className="mb-3 text-[11px] text-slate-500" data-testid="import-deferred-note">Control Information and POA&M imports are deferred for the migration – their existing importers still work but are not part of this flow yet.</p>
          <div className="mb-3"><AiSettingsPanel /></div>
          <BatchUpload systemId={id} base={base} onDone={reload} />
          <div className="mt-3 flex items-center gap-2 text-[12px]">SYNTHETIC samples:
            <select className="input w-auto" value={sample} onChange={(e) => setSample(e.target.value)} data-testid="import-sample-type">{Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}</select>
            <button className="text-blue-800 underline" onClick={() => downloadFile(`/emass-imports/samples/${sample}${id ? `?system_id=${id}` : ""}`, `SYNTHETIC_eMASS_${sample}_sample.${sample === "hwsw" ? "xlsm" : "xlsx"}`, "Synthetic sample")} data-testid="import-sample-download">Download sample</button></div>
        </Panel>
        {id && <ExportLinks systemId={id} />}
        {id && <PpsmPanel systemId={id} />}
        <Panel title="Import history" testId="emass-import-history">
          <table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>When</th><th>Type</th><th>File</th><th>System</th><th>Who</th><th>Status</th><th>Accepted / rejected / applied</th><th /></tr></thead>
            <tbody>{(hist?.items || []).map((h: Row) => <tr key={h.id} className="border-t border-slate-100" data-testid={`import-history-${h.id}`}>
              <td>{new Date(h.created_at).toLocaleString()}</td><td>{h.report_type_label}</td><td>{h.file_name}</td>
              <td>{h.system_id ? (systems.find((s: Row) => s.id === h.system_id)?.acronym || "system") : <i>unassigned</i>}</td><td>{h.uploaded_by}</td><td>{h.status}</td>
              <td>{h.counts?.accepted ?? 0} / {h.counts?.rejected ?? 0} / {h.counts?.applied_fields ?? "–"}</td>
              <td><Link className="text-blue-800 underline" to={`${base}/${h.id}`} data-testid={`import-open-${h.id}`}>{["review", "detected"].includes(h.status) ? "Resume" : "View"}</Link></td></tr>)}</tbody></table>
          {!hist?.items?.length && <p className="text-[12px] text-slate-500">No imports yet.</p>}
        </Panel></div>}
      {importId && imp && imp.status === "detected" && <ImportPrompt imp={imp} contextSystem={ctxSys} onTargeted={(d) => { setImp(d); if (!id && d.system_id) nav(`/systems/${d.system_id}/emass-import/${d.id}`, { replace: true }); }} />}
      {importId && imp && imp.status !== "detected" && <div className="space-y-5">
        <div className="flex items-center gap-3 text-[12px]"><Link to={base} className="text-blue-800 underline" data-testid="import-back-history">← Import history</Link>
          <span>{imp.file_name} · uploaded by {imp.uploaded_by}</span>
          {imp.can_apply && imp.status === "review" && <span className="ml-auto flex gap-2">
            <button className="btn-secondary" disabled={!!busy} onClick={() => finish("discard")} data-testid="import-discard-btn">Discard import</button>
            <button className="btn-primary" disabled={!!busy || !imp.counts?.accepted} onClick={() => finish("apply")} data-testid="import-apply-btn">Apply {imp.counts?.accepted ?? 0} accepted field(s)</button></span>}
          {imp.status !== "review" && imp.system_id && <span className="ml-auto flex gap-2">
            <Link className="btn-secondary" to={`/systems/${imp.system_id}/migration-report`} data-testid="import-completion-report">Completion report</Link>
            {imp.status === "applied" && REVERTIBLE.includes(imp.report_type) && imp.can_apply && <button className="btn-secondary" disabled={!!busy} onClick={revert} data-testid="import-revert-btn">Revert this import</button>}</span>}</div>
        {imp.report_type === "slcm" && imp.report?.strategy_plan && <StrategyPlan plan={imp.report.strategy_plan} mode={slcmMode} setMode={setSlcmMode} editable={imp.status === "review"} />}
        {imp.report_type === "categorization" && imp.report?.proposal && <p className="rounded border border-blue-200 bg-blue-50 px-3 py-2 text-[12px] text-blue-900" data-testid="import-categorization-proposal">{imp.report.proposal}.
          {(imp.report.apply_results || []).filter((x: Row) => x.revision).map((x: Row) => <span key={x.revision}> {x.summary}. <Link className="underline" to="/rmf/categorize">Open Categorize →</Link></span>)}</p>}
        {imp.status === "applied" && <CompletedNext kind={imp.report_type} counts={imp.counts} testId="import-completed-next" />}
        <Report imp={imp} />
        <ImportReview imp={{ ...imp, labels: LABELS }} onChange={setImp} />
      </div>}
    </div>);
}

const LABELS: Row = { implementation_status: "Implementation Status", control_designation: "Security Control Designation", estimated_completion_date: "Estimated Completion Date",
  responsible_entities: "Responsible Entities", slcm_criticality: "SLCM Criticality", slcm_frequency: "SLCM Frequency", slcm_method: "SLCM Method", slcm_reporting: "SLCM Reporting",
  slcm_tracking: "SLCM Tracking", slcm_comments: "SLCM Comments", na_justification: "N/A Justification", common_control_provider: "Common Control Provider",
  implementation_narrative: "Implementation Narrative", severity: "Severity", relevance_of_threat: "Relevance of Threat", likelihood: "Likelihood", impact: "Impact",
  residual_risk_level: "Residual Risk Level", impact_description: "Impact Description", vulnerability_summary: "Vulnerability Summary", recommendations: "Recommendations", mitigations: "Mitigations" };
