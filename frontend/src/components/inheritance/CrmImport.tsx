import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Modal } from "@/components/common/Workflow";
import { showNextStep } from "@/components/common/NextStep";

/** CRM import: pick file (CSV/XLSX) → map columns → preview changes + row errors → apply (audited). */
export function CrmImportModal({ provider, sid, onClose, onDone }: { provider: Row; sid: string; onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [pv, setPv] = useState<Row | null>(null);
  const [mapping, setMapping] = useState<Row>({});
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const form = (f: File, m: Row | null) => { const fd = new FormData(); fd.append("file", f); fd.append("system_id", sid); if (m) fd.append("mapping", JSON.stringify(m)); return fd; };
  const preview = async (f: File, m: Row | null) => {
    setErr(""); setBusy(true);
    try { const r = await api.post<Row>(`/providers/${provider.id}/crm/preview`, form(f, m)); setPv(r.data); setMapping(r.data.mapping); }
    catch (e) { setErr(errorMessage(e)); setPv(null); } finally { setBusy(false); }
  };
  const applyIt = async () => {
    setBusy(true);
    try { const r = await api.post<Row>(`/providers/${provider.id}/crm/apply`, form(file!, mapping));
      showNextStep({ message: `CRM applied for ${provider.name}: ${r.data.controls_updated} control(s) updated, ${r.data.matrix_rows} matrix rows stored${r.data.skipped_errors ? `, ${r.data.skipped_errors} row(s) with errors skipped` : ""}.`,
        label: "check the inherited and shared controls below", to: "/inheritance" });
      onDone(); onClose();
    } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  };
  const s = pv?.summary ?? {};
  return (
    <Modal title={`Import customer responsibility matrix – ${provider.name}`} onClose={onClose} testId="crm-modal">
      <div className="text-[13px]">
        <p className="text-slate-600">Upload the provider's CRM as CSV or Excel (.xlsx). You will map its columns, see exactly what changes for this system, then apply. <a className="text-blue-800 underline" href={`${process.env.REACT_APP_BACKEND_URL}/api/v1/crm/sample.csv`} onClick={async (e) => {
          e.preventDefault(); const r = await api.get("/crm/sample.csv", { responseType: "blob" });
          const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(r.data as Blob), download: "SAMPLE-customer-responsibility-matrix.csv" }); a.click(); }} data-testid="crm-sample">Download a SAMPLE template (synthetic)</a></p>
        <input type="file" accept=".csv,.xlsx" className="mt-2" onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); preview(f, null); } }} data-testid="crm-file" />
        {err && <div className="mt-2 rounded bg-rose-50 p-2 text-[12px] text-rose-800" role="alert" data-testid="crm-error">{err}</div>}
        {pv && <>
          <div className="mt-3 font-medium">1 · Map columns</div>
          <div className="mt-1 grid grid-cols-2 gap-2" data-testid="crm-mapping">{Object.entries(pv.fields as Row).map(([k, label]) => (
            <label key={k} className="text-[12px]">{label as string}{["control_id", "responsibility"].includes(k) && " *"}
              <select className="input mt-0.5" value={mapping[k] ?? ""} onChange={(e) => setMapping({ ...mapping, [k]: e.target.value })} data-testid={`crm-map-${k}`}>
                <option value="">— not in file —</option>{pv.headers.map((h: string) => <option key={h}>{h}</option>)}</select></label>))}</div>
          <button className="btn-secondary mt-2 text-[12px]" disabled={busy} onClick={() => preview(file!, mapping)} data-testid="crm-repreview">Update preview</button>
          {pv.missing_columns.length > 0 ? <p className="mt-2 text-[12px] text-amber-800" data-testid="crm-missing">Map these required columns: {pv.missing_columns.join(", ")}.</p> : <>
            <div className="mt-3 font-medium">2 · Preview</div>
            <div className="mt-1 flex flex-wrap gap-3 text-[12px]" data-testid="crm-summary"><span>Changes: <b>{s.changes ?? 0}</b></span><span>Unchanged: {s.unchanged ?? 0}</span>
              <span title="Rows for controls that are not selected for this system – stored in the provider matrix only">Not in this system: {s.not_in_system ?? 0}</span>
              <span className={s.errors ? "text-rose-700" : ""}>Row errors: <b>{s.errors ?? 0}</b></span></div>
            <div className="mt-1 max-h-60 overflow-auto"><table className="w-full text-[11px]"><thead><tr className="text-left text-slate-500"><th>Row</th><th>Control</th><th>Responsibility</th><th>Change for this system</th><th>Problems</th></tr></thead>
              <tbody>{pv.rows.map((r: Row) => <tr key={r.row} className={`border-t border-slate-100 ${r.errors.length ? "bg-rose-50" : ""}`} data-testid={`crm-row-${r.row}`}>
                <td>{r.row}</td><td className="font-mono">{r.control_id}</td><td>{r.responsibility}</td><td>{r.change}</td><td className="text-rose-700">{r.errors.join("; ")}</td></tr>)}</tbody></table></div>
            <div className="mt-3 font-medium">3 · Apply</div>
            <p className="text-[11px] text-slate-500">Rows with errors are skipped. The import is recorded in the audit log with the file name, mapping and changed controls.</p>
            <button className="btn-primary mt-1" disabled={busy || !(s.changes || s.unchanged || s.not_in_system)} onClick={applyIt} data-testid="crm-apply">Apply {s.changes ?? 0} change(s)</button></>}
        </>}
        <p className="mt-3 text-[11px] text-slate-500">Need to add the provider first? Close this and use <b>Add provider</b>. Inherited controls are listed under <Link className="underline" to="/inheritance">Inheritance</Link>.</p>
      </div>
    </Modal>);
}

/** Bulk: tick controls, choose Inherited / Shared / System and the provider, apply in one action. */
export function BulkInheritance({ sid, providers, onDone }: { sid: string; providers: Row[]; onDone: () => void }) {
  const [list, setList] = useState<Row[] | null>(null);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [f, setF] = useState<Row>({ responsibility: "inherited", provider_id: "", provider_responsibility_text: "", system_responsibility_text: "" });
  const [m, setM] = useState<{ ok?: string; err?: string }>({});
  const load = async () => setList((await api.get<Row[]>(`/systems/${sid}/traceability`)).data);
  const shown = (list ?? []).filter((r) => !q || r.control_id.startsWith(q.toLowerCase().replace("(", ".").replace(")", ""))).slice(0, 300);
  const go = async () => {
    try { const r = await api.post<Row>(`/systems/${sid}/inheritance/bulk`, { control_ids: picked, responsibility: f.responsibility, provider_id: f.provider_id || null,
        provider_responsibility_text: f.provider_responsibility_text || null, system_responsibility_text: f.system_responsibility_text || null });
      setM({ ok: `${r.data.updated.length} control(s) set to ${f.responsibility}.` }); setPicked([]); onDone(); load();
      showNextStep({ message: `${r.data.updated.length} control(s) set to ${f.responsibility}.`, label: "document the system part of shared controls in the Workbench", to: `/systems/${sid}/controls?responsibility=shared` });
    } catch (e) { setM({ err: errorMessage(e) }); }
  };
  if (!list) return <button className="btn-secondary" onClick={load} data-testid="bulk-inherit-open">Bulk-set inheritance…</button>;
  return (
    <div className="panel mb-5 p-4 text-[12px]" data-testid="bulk-inherit">
      <div className="mb-2 font-heading text-[14px] font-semibold">Bulk-set inheritance</div>
      {m.ok && <div className="mb-2 rounded bg-emerald-50 p-2 text-emerald-900" role="status" data-testid="bulk-ok">{m.ok}</div>}
      {m.err && <div className="mb-2 rounded bg-rose-50 p-2 text-rose-800" role="alert" data-testid="bulk-error">{m.err}</div>}
      <div className="grid gap-4 lg:grid-cols-2">
        <div><input className="input" placeholder="Filter, e.g. pe- or sc-28" value={q} onChange={(e) => setQ(e.target.value)} data-testid="bulk-filter" />
          <div className="mt-1 flex gap-2 text-[11px]"><button className="underline" onClick={() => setPicked(shown.map((r) => r.control_id))} data-testid="bulk-select-all">Select all shown ({shown.length})</button>
            <button className="underline" onClick={() => setPicked([])}>Clear</button><span>{picked.length} selected</span></div>
          <ul className="mt-1 max-h-56 overflow-y-auto rounded border border-slate-200">{shown.map((r) => <li key={r.control_id} className="border-b border-slate-100 px-2 py-0.5">
            <label className="flex items-center gap-2"><input type="checkbox" checked={picked.includes(r.control_id)} onChange={(e) => setPicked(e.target.checked ? [...picked, r.control_id] : picked.filter((x) => x !== r.control_id))}
              data-testid={`bulk-pick-${r.control_id}`} /><span className="font-mono">{r.control_id.toUpperCase()}</span><span className="text-slate-500">{r.responsibility}</span></label></li>)}</ul></div>
        <div className="grid content-start gap-2">
          <label className="font-medium">Set to<select className="input mt-0.5" value={f.responsibility} onChange={(e) => setF({ ...f, responsibility: e.target.value })} data-testid="bulk-resp">
            <option value="inherited">Inherited – the provider fully covers it</option><option value="shared">Shared – provider and system both have a part</option><option value="system">System-owned – no inheritance</option></select></label>
          {f.responsibility !== "system" && <label className="font-medium">From provider<select className="input mt-0.5" value={f.provider_id} onChange={(e) => setF({ ...f, provider_id: e.target.value })} data-testid="bulk-provider">
            <option value="">— choose a provider —</option>{providers.map((p) => <option key={p.id} value={p.id}>{p.name}{p.expiry?.status === "expired" ? " (authorization EXPIRED)" : ""}</option>)}</select></label>}
          {f.responsibility !== "system" && <textarea className="input" rows={2} placeholder="Provider responsibility (optional, applied to all selected)" value={f.provider_responsibility_text} onChange={(e) => setF({ ...f, provider_responsibility_text: e.target.value })} />}
          {f.responsibility === "shared" && <textarea className="input" rows={2} placeholder="System responsibility (optional)" value={f.system_responsibility_text} onChange={(e) => setF({ ...f, system_responsibility_text: e.target.value })} />}
          <button className="btn-primary" disabled={!picked.length} onClick={go} data-testid="bulk-apply">Apply to {picked.length} control(s)</button>
        </div>
      </div>
    </div>);
}
