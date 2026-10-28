import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";

const ACTIONS: [string, string][] = [["restore", "Restore previous value"], ["clear", "Clear field"], ["delete", "Delete imported data"]];
const show = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : typeof v === "object" ? JSON.stringify(v).slice(0, 120) : String(v));
const slug = (s: string) => s.replace(/\W+/g, "-").toLowerCase();

/** Manage imported data (any import type): everything one import populated, grouped by section; restore / clear / delete with a 30-day undo. */
export default function ManageImportPage() {
  const { importId, kind = "emass" } = useParams();
  const base = `/imported-data/${kind}/${importId}`;
  const { data, reload, error } = useApi<Row>(importId ? base : null);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Row[]>([]);
  const all: Row[] = data?.entries || [];
  const entries = useMemo(() => all.filter((e) => !q || `${e.record} ${e.label} ${e.destination} ${show(e.imported)}`.toLowerCase().includes(q.toLowerCase())), [all, q]);
  const groups = useMemo(() => entries.reduce((m: Record<string, Row[]>, e) => ({ ...m, [e.destination]: [...(m[e.destination] || []), e] }), {}), [entries]);
  const toggle = (ids: string[], on: boolean) => setSel((s) => { const n = new Set(s); ids.forEach((i) => (on ? n.add(i) : n.delete(i))); return n; });
  const post = async (body: Row) => (await api.post<Row>(base, body)).data;
  const finish = (rs: Row[]) => {
    setResults(rs); setSel(new Set()); reload();
    const ok = rs.filter((r) => r.ok).length, bad = rs.length - ok;
    toast.success(`${ok} done${bad ? `, ${bad} need attention` : ""}`, { duration: 10000 });
  };
  const run = async (action: string, ids: string[], extra: Row = {}) => {
    const label = ACTIONS.find(([k]) => k === action)?.[1];
    if (!window.confirm(`${label} for ${ids.length} item(s)? You can undo it for ${data?.undo_days || 30} days.`)) return;
    setBusy(true);
    try { finish((await post({ action, ids, ...extra })).results || []); } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };
  const deleteEverything = async () => {
    const live = all.filter((e) => e.actions?.length && e.state === "applied");
    if (!live.length) { toast.info("Nothing left to remove"); return; }
    if (!window.confirm(`Delete everything this import created (${live.length} item(s))? The system itself is kept – deleting the whole system is the separate system-delete action. Approved decisions are kept and flagged for re-review. Evidence files stay (remove them separately). Undo for ${data?.undo_days || 30} days.`)) return;
    const pick = (e: Row) => (e.destination === "Registration (System Details)" ? (e.actions.includes("clear") ? "clear" : null)
      : e.actions.includes("delete") && (kind !== "emass" || e.created) ? "delete" : e.actions.includes("restore") ? "restore" : null);
    const by: Record<string, string[]> = {};
    live.filter((e) => !e.needs_file_confirm).forEach((e) => { const a = pick(e); if (a) by[a] = [...(by[a] || []), e.id]; });
    setBusy(true);
    try {
      const rs: Row[] = [];
      for (const [action, ids] of Object.entries(by)) rs.push(...((await post({ action, ids, force: true })).results || []));
      finish(rs);
    } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };
  const undo = async (op: string) => {
    try { await api.post(`${base}/undo/${op}`); toast.success("Undone"); reload(); } catch (e) { toast.error(errorMessage(e)); }
  };
  if (error) return <p className="text-sm text-rose-700" data-testid="mid-error">{error}</p>;
  if (!data) return <p className="text-sm text-slate-500">Loading…</p>;
  const imp = data.import || {};
  const ids = [...sel];
  const fileSel = ids.some((i) => i.startsWith("evidence_file|"));
  return (
    <div data-testid="manage-import-page">
      <PageHeader title="Manage imported data" subtitle={`${imp.kind_label || "eMASS workbook"} · ${imp.file_name} · SHA-256 ${(imp.sha256 || "").slice(0, 12)}… · ${imp.status}`}>
        <Link className="text-[12px] text-blue-800 underline" to="/import-center" data-testid="mid-back">Back to Import Center</Link>
      </PageHeader>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input className="w-full min-w-0 rounded border border-slate-300 px-2 py-1 text-[13px] sm:w-auto sm:flex-1" placeholder="Filter by control, field or value" value={q} onChange={(e) => setQ(e.target.value)} data-testid="mid-filter" aria-label="Filter imported data" />
        {ACTIONS.map(([k, label]) => <button key={k} disabled={busy || !ids.length} className="rounded border border-slate-300 px-2 py-1 text-[12px] disabled:opacity-40"
          onClick={() => (k === "delete" && fileSel && !window.confirm("The selection includes an evidence FILE. Remove the file itself (logical removal, kept for retention)? Cancel removes the links only.")
            ? run(k, ids.filter((i) => !i.startsWith("evidence_file|"))) : run(k, ids, k === "delete" && fileSel ? { confirm_file: true } : {}))} data-testid={`mid-${k}-selected`}>{label} ({ids.length})</button>)}
        <button disabled={busy} className="rounded bg-rose-700 px-2 py-1 text-[12px] font-semibold text-white disabled:opacity-40" onClick={deleteEverything} data-testid="mid-delete-everything">Delete everything this import created</button>
      </div>
      {!!(data.flags || []).length && <Panel title={`Needs re-review (${data.flags.length})`} testId="mid-flags">
        <ul className="text-[12px]">{data.flags.map((f: Row) => <li key={f.id} className="py-0.5" data-testid={`mid-flag-${f.id}`}><b>{f.label}</b> – {f.reason}</li>)}</ul>
        <p className="mt-1 text-[11px] text-slate-500">The decisions were not removed. The decision owner re-reviews and resolves each flag.</p></Panel>}
      {!!results.filter((r) => !r.ok).length && <Panel title="Needs attention" testId="mid-failures"><ul className="text-[12px]">{results.filter((r) => !r.ok).map((r) => <li key={r.id} data-testid={`mid-fail-${r.id}`}>{r.id}: {r.error}
        {r.needs_confirm && <button className="ml-1 underline" onClick={() => run(all.find((e) => e.id === r.id)?.actions.includes("delete") ? "delete" : "restore", [r.id], { force: true })} data-testid={`mid-force-${r.id}`}>Confirm anyway</button>}
        {r.needs_file_confirm && <button className="ml-1 underline" onClick={() => run("delete", [r.id], { confirm_file: true })} data-testid={`mid-file-${r.id}`}>Remove the file</button>}</li>)}</ul></Panel>}
      {(Object.entries(groups) as [string, Row[]][]).map(([dest, es]) => <Panel key={dest} title={`${dest} (${es.length})`} testId={`mid-group-${slug(dest)}`}>
        <label className="mb-1 flex items-center gap-1 text-[12px]"><input type="checkbox" onChange={(e) => toggle(es.filter((x) => x.actions.length).map((x) => x.id), e.target.checked)} data-testid={`mid-all-${slug(dest)}`} /> Select all in section</label>
        <ul className="divide-y divide-slate-100">{es.map((e) => <li key={e.id} className="flex flex-wrap items-start gap-2 py-1.5 text-[12px]" data-testid={`mid-entry-${e.id}`}>
          <input type="checkbox" disabled={!e.actions.length} checked={sel.has(e.id)} onChange={(ev) => toggle([e.id], ev.target.checked)} aria-label={`Select ${e.record} ${e.label}`} data-testid={`mid-select-${e.id}`} />
          <span className="font-semibold">{e.record}</span><span className="text-slate-600">{e.label}</span>
          <span className="min-w-0 basis-full [overflow-wrap:anywhere] sm:basis-auto">{e.field !== "*" && <>before: <b>{show(e.prior)}</b> → </>}imported: <b>{show(e.imported)}</b> · now: <b>{show(e.current)}</b></span>
          <span className={`rounded px-1 text-[11px] ${e.state === "applied" ? "bg-sky-50 text-sky-900" : "bg-slate-100 text-slate-700"}`} data-testid={`mid-state-${e.id}`}>{e.state === "applied" ? `Imported from ${imp.file_name}` : e.state}</span>
          {e.decision && <span className="text-[11px] text-amber-800">{e.decision}</span>}
          {e.changed_since_import && <span className="text-[11px] text-amber-800">changed after the import</span>}
          {e.read_only && <span className="text-[11px] text-slate-500">{e.read_only}</span>}</li>)}</ul></Panel>)}
      {!entries.length && <p className="text-[12px] text-slate-500" data-testid="mid-empty">Nothing from this import matches.</p>}
      <Panel title={`History – undo within ${data.undo_days} days`} testId="mid-log">
        <ul className="text-[12px]">{(data.log || []).slice().reverse().map((o: Row) => <li key={o.op_id} className="py-0.5" data-testid={`mid-op-${o.op_id}`}>{new Date(o.at).toLocaleString()} · {o.by} · {o.action} · {o.entries.length} item(s) {o.undone ? <span className="text-slate-500">(undone)</span> : <button className="ml-1 underline" onClick={() => undo(o.op_id)} data-testid={`mid-undo-${o.op_id}`}>Undo</button>}</li>)}</ul>
        {!(data.log || []).length && <p className="text-[12px] text-slate-500">No changes yet. The audit history is never deleted.</p>}
      </Panel>
    </div>);
}
