import { Fragment, useEffect, useState } from "react";
import { ApproveDialog } from "@/components/tr/ApproveDialog";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { useActiveSystemId } from "@/components/rmf/Stepper";
import { showNextStep } from "@/components/common/NextStep";
import { PROCESSING_STARTED } from "@/components/shell/Processing";
import { downloadFile } from "@/lib/download";

const STATE_TONE: Record<string, string> = { approved: "bg-emerald-100 text-emerald-800", edited: "bg-blue-100 text-blue-800", auto: "bg-slate-100 text-slate-800",
  missing: "bg-amber-100 text-amber-900", conflict: "bg-rose-100 text-rose-800" };
const STATE_LABEL: Record<string, string> = { auto: "Auto-suggested", edited: "Edited", approved: "Approved", missing: "Missing", conflict: "Conflict", needs_confirmation: "Needs tester/date confirmation" };
const ROLE_LABEL: Record<string, string> = { control_acronym: "Control Acronym", ap_acronym: "AP Acronym", cci: "CCI", cci_definition: "CCI Definition",
  implementation_guidance: "Implementation Guidance", assessment_procedures: "Assessment Procedures", compliance_status: "Compliance Status",
  date_tested: "Date Tested", tested_by: "Tested By", test_results: "Test Results" };

function Upload({ sid, onDone }: { sid: string; onDone: (id: string) => void }) {
  const [msg, setMsg] = useState("");
  const up = async (f: File) => {
    const fd = new FormData(); fd.append("file", f);
    try {
      const r = await api.post<Row>(`/systems/${sid}/tr/workbooks`, fd);
      setMsg(`“${f.name}” uploaded (v${r.data.version}, SHA-256 ${r.data.sha256.slice(0, 12)}…) – Queued: detecting sheets, header row and columns.`);
      window.dispatchEvent(new Event(PROCESSING_STARTED)); onDone(r.data.id);
    } catch (e) { setMsg(errorMessage(e)); }
  };
  return (<div className="rounded border border-dashed border-slate-300 p-4" data-testid="tr-upload">
    <div className="mb-2 text-sm font-medium">Import an eMASS Test Result workbook (.xlsx)</div>
    <input type="file" accept=".xlsx,.xlsm" onChange={(e) => e.target.files?.[0] && up(e.target.files[0])} data-testid="tr-upload-input" />
    {msg && <div className="mt-2 text-[12px]" role="status" data-testid="tr-upload-msg">{msg}</div>}
  </div>);
}

function Mapping({ wb, reload }: { wb: Row; reload: () => void }) {
  const det = wb.detection || {};
  const [roles, setRoles] = useState<Record<string, string>>(wb.definition?.roles || {});
  const [name, setName] = useState("eMASS TR template");
  const save = async () => { try { await api.put(`/tr/workbooks/${wb.id}/mapping`, { roles }); toast.success("Column roles saved – rows re-matched"); reload(); } catch (e) { toast.error(errorMessage(e)); } };
  const tpl = async () => { try { const r = await api.post<Row>(`/tr/workbooks/${wb.id}/template`, { name }); toast.success(`Saved template “${r.data.name}” v${r.data.version} – the next upload with this layout applies it automatically`); reload(); } catch (e) { toast.error(errorMessage(e)); } };
  return (<div className="rounded border border-slate-200 p-3" data-testid="tr-mapping">
    <div className="mb-1 text-sm font-medium">1 · Columns detected on sheet “{det.sheet}”, header row {det.header_row}</div>
    <div className="mb-2 text-[12px] text-slate-600">Results are written only to the “Enter Test Results Here” columns; read-only eMASS columns are never changed. Allowed Compliance Status values: <b>{(wb.definition?.vocabulary?.compliance_status || []).join(", ")}</b> <span className="text-slate-500">(from {wb.definition?.vocabulary?.source})</span>. Dates: {wb.definition?.date_format}.</div>
    <table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>Col</th><th>Header</th><th>Section</th><th>Role</th></tr></thead><tbody>
      {(det.columns || []).map((c: Row) => <tr key={c.col} className="border-t border-slate-100" data-testid={`tr-col-${c.col}`}><td className="font-mono">{c.col}</td><td>{c.header}</td>
        <td className={c.group === "readonly" ? "text-slate-500" : c.group === "editable" ? "text-emerald-700" : ""}>{c.group === "readonly" ? "read-only (eMASS)" : c.group === "editable" ? "results (editable)" : "–"}</td>
        <td>{(c.role || "").startsWith("latest_") ? <span className="text-slate-500">previous result (read-only)</span> :
          <select className="input py-0 text-[12px]" value={Object.keys(roles).find((k) => roles[k] === c.col) || ""} data-testid={`tr-role-${c.col}`}
            onChange={(e) => { const n = { ...roles }; Object.keys(n).forEach((k) => n[k] === c.col && delete n[k]); if (e.target.value) n[e.target.value] = c.col; setRoles(n); }}>
            <option value="">– not used –</option>{Object.keys(ROLE_LABEL).map((k) => <option key={k} value={k}>{ROLE_LABEL[k]}</option>)}</select>}</td></tr>)}
    </tbody></table>
    <div className="mt-2 flex flex-wrap items-center gap-2"><button className="btn-secondary" onClick={save} data-testid="tr-mapping-save">Apply column roles</button>
      <input className="input w-56" value={name} onChange={(e) => setName(e.target.value)} data-testid="tr-template-name" /><button className="btn-secondary" onClick={tpl} data-testid="tr-template-save">Save as reusable template</button>
      {wb.definition?.template && <span className="text-[11px] text-slate-600">Template “{wb.definition.template.name}” v{wb.definition.template.version} applied</span>}</div>
  </div>);
}

function Resolve({ wb, r, reload }: { wb: Row; r: Row; reload: () => void }) {
  const [q, setQ] = useState(r.control_id || "");
  const [opts, setOpts] = useState<Row | null>(null);
  const find = async () => setOpts((await api.get<Row>("/tr/lookup", { params: { q } })).data);
  const pick = async (control_id: string) => { try { await api.post(`/tr/workbooks/${wb.id}/rows/${r.id}/resolve`, { control_id, cci_id: r.cci_id }); toast.success(`Row ${r.row} confirmed as ${control_id.toUpperCase()}`); reload(); } catch (e) { toast.error(errorMessage(e)); } };
  return (<span className="inline-flex flex-wrap items-center gap-1"><input className="input w-24 py-0 text-[11px]" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ac-2" data-testid={`tr-resolve-q-${r.row}`} />
    <button className="btn-secondary px-1 py-0 text-[11px]" onClick={find} data-testid={`tr-resolve-find-${r.row}`}>Find</button>
    {r.control_id && <button className="btn-secondary px-1 py-0 text-[11px]" onClick={() => pick(r.control_id)} data-testid={`tr-resolve-confirm-${r.row}`}>Confirm {r.control_id.toUpperCase()}</button>}
    {opts?.controls?.slice(0, 6).map((c: string) => <button key={c} className="rounded bg-slate-100 px-1 text-[11px]" onClick={() => pick(c)}>{c.toUpperCase()}</button>)}</span>);
}

const VERDICT: Record<string, string> = { supports: "bg-emerald-100 text-emerald-800", contradicts: "bg-rose-100 text-rose-800", does_not_establish: "bg-slate-100 text-slate-700" };

function Analysis({ wb, r, onApplied }: { wb: Row; r: Row; onApplied: () => void }) {
  const [a, setA] = useState<Row | null>(null); const [busy, setBusy] = useState(false); const [text, setText] = useState("");
  const load = async () => { const d = (await api.get<Row>(`/tr/workbooks/${wb.id}/rows/${r.id}/analysis`)).data; setA(d.latest); if (d.latest) setText(d.latest.output.explanation); return d.latest; };
  useEffect(() => { load(); }, [r.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const run = async () => { setBusy(true); const prev = a?.id;
    try { await api.post(`/tr/workbooks/${wb.id}/analyze`, { row_ids: [r.id] });
      for (let i = 0; i < 60; i++) { await new Promise((ok) => setTimeout(ok, 1500)); const n = await load(); if (n && n.id !== prev) break; }
    } catch (e) { toast.error(errorMessage(e)); } setBusy(false); };
  const use = async () => { try { await api.post(`/tr/workbooks/${wb.id}/rows/${r.id}/use-analysis`, { analysis_id: a!.id, text });
    toast.success(`Row ${r.row}: text applied to Test Results (AI-assisted, audited)${r.state === "approved" ? " – SCA re-approval needed before export" : ""}`); onApplied(); } catch (e) { toast.error(errorMessage(e)); } };
  const rec: Record<string, Row> = Object.fromEntries((a?.records || []).map((x: Row) => [x.id, x]));
  const o = a?.output || {};
  return (<div className="rounded border border-indigo-200 bg-indigo-50/40 p-2 text-[12px]" data-testid={`tr-analysis-${r.row}`}>
    <div className="mb-1 flex flex-wrap items-center gap-2"><b>Evidence analysis</b>
      {a && <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${a.mode === "ai" ? "bg-indigo-600 text-white" : "bg-slate-600 text-white"}`} data-testid={`tr-analysis-badge-${r.row}`}>{a.label}</span>}
      {a?.mode === "ai" && <span className="text-[10px] text-slate-600">{a.provider} · {a.model} · {a.prompt_version}</span>}
      {a?.error && <span className="text-[10px] text-amber-800">{a.error}</span>}
      <button className="btn-secondary px-1.5 py-0 text-[11px]" disabled={busy} onClick={run} data-testid={`tr-analyze-${r.row}`}>{busy ? "Analyzing…" : a ? "Re-run analysis" : "Run analysis"}</button>
      <span className="text-[10px] text-slate-500">Analysis never sets Compliance Status, Tested By or Date Tested.</span></div>
    {!a && !busy && <div className="text-slate-600">No analysis yet.</div>}
    {a && <>
      <ul className="space-y-0.5">{(o.sources || []).map((s: Row) => <li key={s.id} data-testid={`tr-analysis-src-${r.row}-${s.id.slice(0, 8)}`}><span className={`mr-1 rounded px-1 text-[10px] font-semibold ${VERDICT[s.verdict]}`}>{s.verdict.replace(/_/g, " ")}</span>
        <span className="text-slate-700">{rec[s.id]?.text?.split(". ")[0]}</span> – {s.reason}{s.quote && <q className="ml-1 italic text-slate-600">{s.quote}</q>}</li>)}</ul>
      {[["Conflicts", (o.conflicts || []).map((c: Row) => c.reason)], ["Stale evidence", (o.stale || []).map((i: string) => rec[i]?.text?.split(" (")[0])], ["Missing", o.missing || []], ["Unsupported conclusions", o.unsupported || []]]
        .filter(([, v]) => (v as string[]).length).map(([k, v]) => <div key={k as string} className="mt-1 text-amber-900" data-testid={`tr-analysis-${(k as string).split(" ")[0].toLowerCase()}-${r.row}`}><b>{k as string}:</b> {(v as string[]).join("; ")}</div>)}
      {!!a.dropped?.length && <div className="mt-1 text-[10px] text-rose-700" data-testid={`tr-analysis-dropped-${r.row}`}>{a.dropped.length} unverifiable reference(s)/quote(s) removed by the server.</div>}
      <div className="mt-1 font-medium">Proposed Test Results explanation</div>
      <textarea className="input h-20 w-full text-[12px]" value={text} onChange={(e) => setText(e.target.value)} data-testid={`tr-analysis-text-${r.row}`} />
      {wb.can_edit !== false && <button className="btn-primary mt-1 px-2 py-0.5 text-[11px]" onClick={use} data-testid={`tr-use-text-${r.row}`}>Use this text</button>}
    </>}
  </div>);
}

function Badges({ r, v }: { r: Row; v: Row }) {
  return (<div className="mt-0.5 flex flex-wrap gap-1 text-[10px]">
    {(v.determination_source || "").startsWith("assessment:") && <span className="rounded bg-sky-100 px-1 text-sky-800" data-testid={`tr-badge-assessment-${r.row}`}>Recorded assessment</span>}
    {r.state === "approved" && <span className="rounded bg-emerald-600 px-1 text-white" data-testid={`tr-badge-approved-${r.row}`}>Approved SCA decision</span>}
    {v.ai_assisted && <span className="rounded bg-indigo-100 px-1 text-indigo-800" data-testid={`tr-badge-ai-${r.row}`}>AI suggestion applied{v.ai_assisted.mode === "deterministic" ? " (deterministic)" : ""}{v.ai_assisted.edited_by_user ? ", edited" : ""}</span>}
  </div>);
}

function Review({ wb, reload }: { wb: Row; reload: () => void }) {
  const [state, setState] = useState(""); const [fam, setFam] = useState(""); const [match, setMatch] = useState("");
  const rows = useApi<Row>(`/tr/workbooks/${wb.id}/rows`, { state: state || undefined, family: fam || undefined, match: match || undefined, size: 200 });
  const [sel, setSel] = useState<string[]>([]); const [just, setJust] = useState(""); const [useSug, setUseSug] = useState(false);
  const decide = async (body: Row) => {
    try { const r = await api.post<Row>(`/tr/workbooks/${wb.id}/decide`, body);
      toast.success(`${(r.data.approved || r.data.edited || []).length} row(s) ${body.action === "approve" ? "approved" : "edited"}${r.data.skipped?.length ? `, ${r.data.skipped.length} skipped (${r.data.skipped[0].reason})` : ""}`);
      setSel([]); rows.reload(); reload(); } catch (e) { toast.error(errorMessage(e)); }
  };
  const edit = (r: Row) => { const t = window.prompt("Test Results text", r.final?.test_results ?? r.proposed?.test_results ?? ""); if (t === null) return; const j = window.prompt("Justification (kept in the audit log)") || ""; decide({ action: "edit", row_ids: [r.id], values: { test_results: t }, justification: j }); };
  const items: Row[] = rows.data?.items || [];
  const [open, setOpen] = useState<string | null>(null);
  const [approving, setApproving] = useState<Row[] | null>(null);
  const bulk = async () => { try { const r = await api.post<Row>(`/tr/workbooks/${wb.id}/analyze`, sel.length ? { row_ids: sel } : { all_matched: true });
    toast.success(`Evidence analysis queued for ${r.data.rows} row(s) – open a row’s analysis to see the result`); } catch (e) { toast.error(errorMessage(e)); } };
  return (<div className="rounded border border-slate-200 p-3" data-testid="tr-review">
    <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]"><span className="text-sm font-medium">3 · Review ({rows.data?.total ?? 0} rows)</span>
      <select className="input py-0" value={state} onChange={(e) => setState(e.target.value)} data-testid="tr-filter-state"><option value="">Status: all</option>{Object.keys(STATE_LABEL).map((k) => <option key={k} value={k}>{STATE_LABEL[k]}</option>)}</select>
      <select className="input py-0" value={match} onChange={(e) => setMatch(e.target.value)} data-testid="tr-filter-match"><option value="">Mapping: all</option><option value="ambiguous,unmatched">Needs mapping review</option><option value="matched,resolved">Matched</option></select>
      <input className="input w-20 py-0" placeholder="Family" value={fam} onChange={(e) => setFam(e.target.value)} data-testid="tr-filter-family" />
      <button className="btn-secondary py-0" onClick={bulk} data-testid="tr-bulk-analyze">{sel.length ? `Analyze evidence for ${sel.length} selected` : "Analyze evidence for all mapped rows"}</button></div>
    {!wb.can_approve && <div className="mb-2 rounded bg-slate-100 p-2 text-[12px]" role="note" data-testid="tr-locked">Locked: only an assessor (SCA role) can approve or set a Compliance Status. You can review the proposals and edit the Test Results text.</div>}
    {wb.can_approve && <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]" data-testid="tr-bulk"><input className="input w-72" placeholder="Justification for the selected rows" value={just} onChange={(e) => setJust(e.target.value)} data-testid="tr-bulk-just" />
      <label className="flex items-center gap-1"><input type="checkbox" checked={useSug} onChange={(e) => setUseSug(e.target.checked)} data-testid="tr-bulk-use-suggestion" />Use the evidence suggestion as my determination</label>
      <button className="btn-primary" disabled={!sel.length} onClick={() => setApproving(items.filter((r) => sel.includes(r.id)))} data-testid="tr-bulk-approve">Approve {sel.length} selected…</button></div>}
    {approving && <ApproveDialog rows={approving} onClose={() => setApproving(null)}
      onSubmit={(extra) => { decide({ action: "approve", row_ids: approving.map((r) => r.id), justification: just, use_suggestion: useSug, ...extra }); setApproving(null); }} />}
    <table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th></th><th>Row</th><th>AP / CCI</th><th>Status</th><th>Compliance Status</th><th>Tested by / date</th><th>Test Results &amp; sources</th><th></th></tr></thead><tbody>
      {items.map((r) => { const v = { ...r.proposed, ...(r.final || {}) };
        return (<Fragment key={r.id}><tr className="border-t border-slate-100 align-top" data-testid={`tr-row-${r.row}`}>
          <td><input type="checkbox" disabled={!wb.can_approve} checked={sel.includes(r.id)} onChange={() => setSel(sel.includes(r.id) ? sel.filter((x) => x !== r.id) : [...sel, r.id])} data-testid={`tr-check-${r.row}`} /></td>
          <td className="font-mono">{r.row}</td>
          <td><div className="font-medium">{r.ap_acronym || "–"}</div><div className="text-slate-500">{r.cci_id || "no CCI"}</div>
            {["ambiguous", "unmatched"].includes(r.match_status) && <div className="text-amber-800" data-testid={`tr-match-${r.row}`}>{r.match_reason}<div><Resolve wb={wb} r={r} reload={rows.reload} /></div></div>}
            {(r.flags || []).includes("derived_ap") && <div className="text-[10px] text-slate-500">AP number derived – verify in eMASS</div>}</td>
          <td><span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${STATE_TONE[r.state]}`} data-testid={`tr-state-${r.row}`}>{STATE_LABEL[r.state]}</span>
            {(r.flags || []).filter((f: string) => f !== "derived_ap").map((f: string) => <div key={f} className="text-[10px] text-amber-800">{f.replace(/_/g, " ")}</div>)}</td>
          <td>{v.compliance_status ? <b data-testid={`tr-status-${r.row}`}>{v.compliance_status}</b> : <span className="text-slate-500">blank – assessor input required</span>}
            <Badges r={r} v={v} />
            {!v.compliance_status && v.suggestion && <div className="text-[10px] italic text-blue-800" data-testid={`tr-suggestion-${r.row}`}>Suggestion only: evidence indicates {v.suggestion}</div>}</td>
          <td>{v.tested_by || "–"}<div className="text-slate-500">{v.date_tested || ""}</div>{r.final?.tester_source && <div className="text-[10px] text-slate-500" data-testid={`tr-tester-source-${r.row}`}>{r.final.tester_source}</div>}
            {r.sod_lock && <div className="text-[10px] text-slate-700" role="note" data-testid={`tr-sod-lock-${r.row}`}>Approve locked: {r.sod_lock}</div>}
            {r.final?.sod_label && r.state === "approved" && <div className="text-[10px] text-amber-800" data-testid={`tr-sod-label-${r.row}`}>{r.final.sod_label}</div>}
            {r.state === "needs_confirmation" && <div className="text-[10px] text-amber-800" data-testid={`tr-needs-confirm-${r.row}`}>Approved before tester/date entry was required – excluded from export until the SCA confirms them.</div>}{r.final?.determined_by && <div className="text-[10px] text-slate-500">{r.final.determined_by}</div>}</td>
          <td className="max-w-[420px]"><div className="line-clamp-3">{v.test_results || <span className="text-slate-500">No data – stays blank</span>}</div>
            <div className="mt-0.5 flex flex-wrap gap-1">{(r.sources || []).slice(0, 6).map((s: Row) => <Link key={s.id + s.label} to={s.type === "finding" ? `/findings/${s.id}` : s.type === "policy" ? `/policy-auditor/${s.id}` : s.type === "poam" ? `/poams/${s.id}` : "/evidence-ledger"} className="rounded bg-slate-100 px-1 text-[10px]" title={s.label}>{s.type}</Link>)}</div>
            {r.justification && <div className="text-[10px] text-slate-500">{r.decided_by}: {r.justification}</div>}</td>
          <td className="whitespace-nowrap">{wb.can_approve && r.state !== "approved" && <button className="btn-primary px-1.5 py-0 text-[11px]" onClick={() => setApproving([r])} disabled={!!r.sod_lock} title={r.sod_lock || undefined} data-testid={`tr-approve-${r.row}`}>{r.state === "needs_confirmation" ? "Confirm tester/date…" : "Approve…"}</button>}
            <button className="btn-secondary ml-1 px-1.5 py-0 text-[11px]" onClick={() => edit(r)} data-testid={`tr-edit-${r.row}`}>Edit</button>
            <button className="btn-secondary ml-1 px-1.5 py-0 text-[11px]" disabled={!r.control_id} onClick={() => setOpen(open === r.id ? null : r.id)} data-testid={`tr-open-analysis-${r.row}`}>Evidence analysis</button></td></tr>
          {open === r.id && <tr><td colSpan={8} className="pb-2"><Analysis wb={wb} r={r} onApplied={() => { rows.reload(); reload(); }} /></td></tr>}</Fragment>); })}
    </tbody></table>
    {!items.length && <div className="p-3 text-[12px] text-slate-600" data-testid="tr-review-empty">No rows match these filters.</div>}
  </div>);
}

function Exports({ wb, reload }: { wb: Row; reload: () => void }) {
  const run = async () => {
    try { const r = await api.post<Row>(`/tr/workbooks/${wb.id}/export`);
      toast.success(`Exported v${r.data.version}: ${r.data.counts.written_rows} approved row(s) written, ${r.data.verification.changed_cells.length} cells changed – validation passed`);
      showNextStep({ message: `TR export v${r.data.version} is ready.`, label: "download it and the validation report below", to: "/test-results" }); reload();
    } catch (e) { toast.error(errorMessage(e)); }
  };
  const dl = (url: string, name: string, label: string) => downloadFile(url, name, label);
  return (<div className="rounded border border-slate-200 p-3" data-testid="tr-exports">
    <div className="mb-2 flex items-center gap-2"><span className="text-sm font-medium">4 · Export</span><button className="btn-primary" onClick={run} data-testid="tr-export">Export approved rows to the workbook</button>
      <span className="text-[11px] text-slate-600">Only approved rows are written; everything else in the workbook stays byte-identical.</span></div>
    <table className="w-full text-[12px]"><tbody>{(wb.exports || []).map((e: Row) => <tr key={e.id} className="border-t border-slate-100" data-testid={`tr-export-${e.version}`}>
      <td>v{e.version}</td><td>{new Date(e.created_at).toLocaleString()}</td><td>{e.exported_by}</td><td>{e.counts?.written_rows} rows · {e.changed_cells} cells</td>
      <td data-testid={`tr-export-mode-${e.version}`}>{e.mode === "blank" ? "Blank-template mode" : "Pre-populated mode"}{e.sandbox_same_person_rows ? ` · ${e.sandbox_same_person_rows} row(s) approved “Sandbox: same person”` : ""}</td>
      <td>{e.validation_ok ? <span className="text-emerald-700">validation passed</span> : <span className="text-rose-700">validation failed</span>}</td>
      <td><button className="underline" onClick={() => dl(`/tr/exports/${e.id}/download`, e.file_name, "TR workbook")} data-testid={`tr-download-${e.version}`}>Workbook</button> · <button className="underline" onClick={() => dl(`/tr/exports/${e.id}/validation-report`, e.file_name.replace(".xlsx", "_validation_report.json"), "Validation report")} data-testid={`tr-report-${e.version}`}>Validation report</button></td></tr>)}</tbody></table>
    <div className="mt-2 text-[11px] text-slate-600" data-testid="tr-human-required">HUMAN_REQUIRED before submitting: 1) open the file in Microsoft Excel (no repair prompt), 2) import it in eMASS (Assessment → Test Result Import), 3) spot-check three rows in eMASS.</div>
  </div>);
}

export default function TestResultsPage() {
  const sid = useActiveSystemId();
  const list = useApi<Row[]>(sid ? `/systems/${sid}/tr/workbooks` : null);
  const [wid, setWid] = useState<string | null>(null);
  const cur = wid || list.data?.[0]?.id || null;
  const wb = useApi<Row>(cur ? `/tr/workbooks/${cur}` : null);
  const reload = () => { wb.reload(); list.reload(); };
  const busy = ["queued", "processing", "generating"].includes(wb.data?.status) || (!!wid && !wb.data);
  useEffect(() => {  // poll while the background job runs, then the page updates by itself
    if (!busy) return;
    const t = setInterval(() => { wb.reload(); list.reload(); }, 2000);
    return () => clearInterval(t);
  }, [busy]);  // eslint-disable-line react-hooks/exhaustive-deps
  const gen = async (populate: boolean) => { try { await api.post(`/tr/workbooks/${cur}/generate`, { populate }); toast.success("Generating Test Results from approved assessments, STIG/ACAS, policy coverage, evidence and POA&Ms…"); window.dispatchEvent(new Event(PROCESSING_STARTED)); setTimeout(reload, 4000); } catch (e) { toast.error(errorMessage(e)); } };
  if (!sid) return <div className="p-6" data-testid="tr-no-system">Select a system first (top bar) – Test Results belong to one system.</div>;
  const w = wb.data;
  return (<div className="space-y-4 p-6" data-testid="tr-page">
    <div><div className="text-[11px] uppercase text-slate-500">5 · Assess → Templates → Test Results</div><h1 className="text-2xl font-semibold">eMASS Test Results</h1>
      <p className="text-sm text-slate-600">Import the eMASS Test Result template, map it, generate proposals from real data, have the SCA approve the determinations, and export into the same workbook.</p></div>
    <Upload sid={sid} onDone={(id) => { setWid(id); setTimeout(reload, 3000); }} />
    {!!list.data?.length && <select className="input" value={cur || ""} onChange={(e) => setWid(e.target.value)} data-testid="tr-workbook-select">{list.data.map((x) => <option key={x.id} value={x.id}>{`${x.file_name} v${x.version} – ${x.status}`}</option>)}</select>}
    {!list.data?.length && <div className="text-sm text-slate-600" data-testid="tr-empty">No Test Result workbook yet – upload the blank eMASS template above to start.</div>}
    {w && <>
      <div className="text-[12px] text-slate-700" data-testid="tr-status">Status: <b>{busy ? (w.status === "generating" ? "Processing… generating proposals" : "Processing… detecting columns") : w.status}</b>{w.error ? ` – ${w.error}` : ""} · rows {w.counts?.rows ?? 0} · matched {w.counts?.match?.matched ?? 0} · needs review {(w.counts?.match?.ambiguous ?? 0) + (w.counts?.match?.unmatched ?? 0)}
        {Object.entries(w.counts?.state || {}).map(([k, n]) => <span key={k}> · {STATE_LABEL[k] || k} {String(n)}</span>)}</div>
      {w.status === "generated" && <div className="text-[12px]" data-testid="tr-export-mode">Export mode: <b>{w.export_mode === "blank" ? "Blank-template mode" : "Pre-populated mode"}</b> – {w.export_mode === "blank"
        ? "the template had no data rows; added rows get Control Acronym, AP Acronym, CCI and CCI Definition plus the result columns. Columns B–E and I–L stay blank."
        : "rows came from eMASS; only the result columns M–P of approved rows are written. Everything else stays unchanged."}</div>}
      {w.detection && <Mapping wb={w} reload={reload} />}
      {w.detection && <div className="rounded border border-slate-200 p-3" data-testid="tr-generate"><div className="mb-1 text-sm font-medium">2 · Generate Test Results</div>
        {w.counts?.rows === 0 ? <><div className="mb-1 text-[12px] text-slate-600">This template has no AP rows (blank template). Add one row per CCI of this system's controls – AP numbers are derived and must be verified in eMASS.</div>
          <button className="btn-primary" onClick={() => gen(true)} data-testid="tr-generate-populate">Add rows from this system and generate</button></>
          : <button className="btn-primary" onClick={() => gen(false)} data-testid="tr-generate-btn">Generate Test Results</button>}
        <div className="mt-1 text-[11px] text-slate-600">Evidence only suggests a status. Compliance Status, Tested By and Date Tested come from an assessor determination.</div></div>}
      {w.status === "generated" && <Review wb={w} reload={reload} />}
      {w.status === "generated" && <Exports wb={w} reload={reload} />}
    </>}
  </div>);
}
