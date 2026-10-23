import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { useActiveSystemId } from "@/components/rmf/Stepper";
import { downloadFile } from "@/lib/download";

function poll(reload: () => void) { let n = 0; const t = setInterval(() => { reload(); if (++n >= 15) clearInterval(t); }, 3000); }

const STATUS_TONE: Record<string, string> = { open: "bg-amber-100 text-amber-900", pending_approval: "bg-blue-100 text-blue-800", applied: "bg-emerald-100 text-emerald-800",
  ignored: "bg-slate-100 text-slate-600", resolved: "bg-slate-100 text-slate-600" };

function SourceBadge({ label }: { label: string }) {
  const mocked = label === "MOCKED source";
  return <span className={`rounded px-1 text-[10px] font-semibold ${mocked ? "bg-rose-600 text-white" : "bg-slate-100 text-slate-700"}`} data-testid={mocked ? "mocked-badge" : undefined}>{label}</span>;
}

function AiBox({ ai, testId }: { ai: Row | null; testId: string }) {
  if (!ai) return null;
  return (<div className="mt-1 rounded border border-indigo-200 bg-indigo-50/50 p-1.5 text-[11px]" data-testid={testId}>
    <span className={`mr-1 rounded px-1 text-[10px] font-semibold text-white ${ai.mode === "ai" ? "bg-indigo-600" : "bg-slate-600"}`}>{ai.label}</span>
    {ai.mode === "ai" && <span className="text-slate-500">{ai.provider} · {ai.model} · {ai.prompt_version} </span>}
    {ai.summary || ai.explanation}
    {(ai.ranking || []).map((r: Row) => <div key={r.asset_id || r.record_id}>→ {r.name || (r.asset_id || r.record_id).slice(0, 8)}: confidence {r.confidence ?? r.score} – {r.explanation || r.reason}{r.identifiers?.length ? ` (identifiers: ${r.identifiers.join(", ")})` : ""}</div>)}
    {!!ai.dropped?.length && <div className="text-rose-700">{ai.dropped.length} unverifiable reference(s) removed by the server.</div>}
    {ai.error && <div className="text-amber-800">{ai.error}</div>}
    <div className="text-slate-500">Suggestion only – a person decides. AI never links assets or creates findings.</div>
  </div>);
}

function Imports({ sid, o, reload }: { sid: string; o: Row; reload: () => void }) {
  const [msg, setMsg] = useState("");
  const up = async (f: File) => { const fd = new FormData(); fd.append("file", f);
    try { const r = await api.post<Row>(`/systems/${sid}/inventory/imports`, fd); setMsg(`“${f.name}” uploaded (v${r.data.version}) – Queued: reading Hardware and Software sheets.`); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  const exp = async () => { try { const r = await api.post<Row>(`/systems/${sid}/inventory/export`); toast.success(`Exported v${r.data.version}: ${r.data.counts.hardware} hardware, ${r.data.counts.software} software – validation passed, VBA unchanged`); reload(); } catch (e) { toast.error(errorMessage(e)); } };
  return (<div className="grid gap-3 md:grid-cols-2">
    <div className="rounded border border-dashed border-slate-300 p-3" data-testid="inv-upload"><div className="mb-1 text-sm font-medium">1 · Import the eMASS HW/SW List (.xlsm)</div>
      <input type="file" accept=".xlsm,.xlsx" onChange={(e) => e.target.files?.[0] && up(e.target.files[0])} data-testid="inv-upload-input" />
      <div className="mt-1 text-[11px] text-slate-600">Macros are never run. Existing inventory is never overwritten – differences become proposals you approve.</div>
      {msg && <div className="mt-1 text-[12px]" role="status" data-testid="inv-upload-msg">{msg}</div>}
      {(o.imports || []).slice(0, 3).map((i: Row) => <div key={i.id} className="mt-1 text-[11px]" data-testid={`inv-import-${i.version}`}>v{i.version} {i.file_name} – <b>{i.status}</b>{i.error ? ` (${i.error})` : ""}
        {i.counts && ` · ${i.counts.created} created, ${i.counts.unchanged} unchanged, ${i.counts.proposed_changes} proposed changes, ${i.counts.linked_scan_assets} scan hosts linked${i.counts.errors?.length ? `, ${i.counts.errors.length} row errors` : ""}`}</div>)}</div>
    <div className="rounded border border-slate-200 p-3" data-testid="inv-export"><div className="mb-1 text-sm font-medium">4 · Export to the same template</div>
      <button className="btn-primary" onClick={exp} data-testid="inv-export-btn">Export HW/SW list</button>
      <div className="mt-1 text-[11px] text-slate-600">Only Hardware/Software data rows and the export header cells are written; the VBA project and its signatures stay byte-identical.</div>
      {(o.exports || []).slice(0, 3).map((e: Row) => <div key={e.id} className="mt-1 text-[11px]" data-testid={`inv-export-${e.version}`}>v{e.version} · {e.counts?.hardware} HW / {e.counts?.software} SW · {e.changed} cells · {e.ok ? "validation passed" : "FAILED"} ·
        <button className="ml-1 underline" onClick={() => downloadFile(`/inventory/exports/${e.id}/download`, e.file_name, "Workbook")}>Workbook</button> ·
        <button className="ml-1 underline" onClick={() => downloadFile(`/inventory/exports/${e.id}/validation-report`, `${e.file_name}.validation.json`, "Validation report")}>Validation report</button></div>)}
      {!!o.exports?.length && <div className="mt-1 text-[11px] text-amber-900">HUMAN_REQUIRED: open in Microsoft Excel (no repair prompt), import in eMASS, spot-check three rows.</div>}</div>
  </div>);
}

function Correlations({ sid, reload }: { sid: string; reload: () => void }) {
  const list = useApi<Row[]>(`/systems/${sid}/inventory/correlations`);
  const decide = async (c: Row, action: string, asset_id?: string) => {
    if (action === "explain") { await api.post(`/inventory/correlations/${c.id}`, { action }); toast.success("Ranking queued – the result appears here in a few seconds"); poll(list.reload); return; }
    const j = window.prompt("Justification (min 10 characters, kept in the audit log)"); if (!j) return;
    try { await api.post(`/inventory/correlations/${c.id}`, { action, asset_id, justification: j }); toast.success(action === "confirm" ? "Linked – findings now show on the inventory asset (finding records unchanged)" : "Kept separate"); list.reload(); reload(); } catch (e) { toast.error(errorMessage(e)); }
  };
  return (<div className="rounded border border-slate-200 p-3" id="correlations" data-testid="inv-correlations"><div className="mb-1 text-sm font-medium">2 · Scan → asset correlation needing review ({list.data?.length ?? 0})</div>
    {(list.data || []).map((c) => <div key={c.id} className="border-t border-slate-100 py-1.5 text-[12px]" data-testid={`inv-corr-${c.observed_asset?.name}`}>
      <b>{c.observed_asset?.name}</b> <SourceBadge label={c.observed_asset?.source_label} /> <span className="text-amber-800">{c.reason}</span>
      <div className="text-[11px] text-slate-600">Observed: {Object.entries(c.facts).filter(([k]) => ["host", "fqdn", "ips", "macs"].includes(k)).map(([k, v]) => `${k} ${Array.isArray(v) ? v.join(", ") : v}`).join(" · ")} ({c.source_format})</div>
      <div className="mt-0.5 flex flex-wrap gap-1">{c.candidates.map((x: Row) => <button key={x.asset_id} className="btn-secondary px-1.5 py-0 text-[11px]" onClick={() => decide(c, "confirm", x.asset_id)} data-testid={`inv-corr-confirm-${c.observed_asset?.name}-${x.name}`}>
        Confirm {x.name} (matches {x.matched.join(", ")}{x.conflicts.length ? `; conflicts ${x.conflicts.join(", ")}` : ""})</button>)}
        <button className="btn-secondary px-1.5 py-0 text-[11px]" onClick={() => decide(c, "reject")} data-testid={`inv-corr-reject-${c.observed_asset?.name}`}>Keep separate</button>
        <button className="btn-secondary px-1.5 py-0 text-[11px]" onClick={() => decide(c, "explain")} data-testid={`inv-corr-ai-${c.observed_asset?.name}`}>Rank candidates (AI)</button></div>
      <AiBox ai={c.ai && { ...c.ai, ranking: (c.ai.ranking || []).map((r: Row) => ({ ...r, name: c.candidates.find((x: Row) => x.asset_id === r.asset_id)?.name })) }} testId={`inv-corr-aibox-${c.observed_asset?.name}`} />
    </div>)}
    {!list.data?.length && <div className="text-[12px] text-slate-600">Nothing ambiguous – every scanned host matched on a reliable identifier or is new.</div>}
  </div>);
}

function Discrepancies({ sid, canWrite, reload }: { sid: string; canWrite: boolean; reload: () => void }) {
  const [kind, setKind] = useState("");
  const list = useApi<Row[]>(`/systems/${sid}/inventory/discrepancies`);
  const act = async (d: Row, action: string) => {
    const reason = action === "ignore" ? window.prompt("Why ignore? (min 10 characters, audited)") : "";
    if (action === "ignore" && !reason) return;
    try { await api.post(`/inventory/discrepancies/${d.id}`, { action, reason });
      toast.success({ accept: "Resolution proposed – awaiting approval (nothing changed yet)", approve: "Change applied and audited", reject: "Proposal withdrawn", ignore: "Ignored (reason audited)", explain: "Explanation queued" }[action] || "Done");
      if (action === "explain") poll(list.reload); else list.reload(); reload(); } catch (e) { toast.error(errorMessage(e)); }
  };
  const run = async () => { await api.post(`/systems/${sid}/inventory/check`); toast.success("Consistency checks queued"); setTimeout(list.reload, 4000); };
  const items = (list.data || []).filter((d) => !kind || d.kind === kind);
  const kinds = Array.from(new Set((list.data || []).map((d) => d.kind)));
  return (<div className="rounded border border-slate-200 p-3" data-testid="inv-discrepancies">
    <div className="mb-1 flex flex-wrap items-center gap-2"><span className="text-sm font-medium">3 · Consistency checks ({list.data?.length ?? 0} open)</span>
      <select className="input py-0 text-[12px]" value={kind} onChange={(e) => setKind(e.target.value)} data-testid="inv-disc-filter"><option value="">All kinds</option>{kinds.map((k) => <option key={k} value={k}>{(list.data || []).find((d) => d.kind === k)?.kind_label}</option>)}</select>
      <button className="btn-secondary py-0 text-[12px]" onClick={run} data-testid="inv-run-checks">Re-run checks</button></div>
    {items.map((d) => <div key={d.id} className="border-t border-slate-100 py-1.5 text-[12px]" data-testid={`inv-disc-${d.kind}`}>
      <span className={`mr-1 rounded px-1 text-[10px] font-semibold ${STATUS_TONE[d.status]}`}>{d.status.replace("_", " ")}</span><span className="mr-1 rounded bg-slate-200 px-1 text-[10px]">{d.kind_label}</span><b>{d.title}</b>
      <div className="mt-0.5 flex flex-wrap gap-1">{d.records.map((r: Row) => <span key={r.type + r.id} className="rounded border border-slate-200 px-1 text-[10px]">{r.type}: {r.label} <SourceBadge label={r.source_label} /> {r.timestamp ? new Date(r.timestamp).toLocaleDateString() : ""}</span>)}</div>
      <div className="text-[11px] text-slate-700">Recommended: {d.recommendation}{d.details?.correlation_id && <> <a className="underline" href="#correlations">Review the match</a></>}</div>
      {d.proposed_change && <div className="text-[11px] text-blue-900">Proposed change: {d.proposed_change.type === "create_asset" ? "create an inventory asset from the scanned host" : d.proposed_change.type === "add_ip" ? `add IP ${d.proposed_change.value}` : `${d.proposed_change.field}: “${d.proposed_change.from ?? "–"}” → “${d.proposed_change.to}”`}</div>}
      {canWrite && <div className="mt-0.5 flex flex-wrap gap-1">
        {d.status === "open" && d.proposed_change && <button className="btn-primary px-1.5 py-0 text-[11px]" onClick={() => act(d, "accept")} data-testid={`inv-accept-${d.id.slice(0, 8)}`}>{d.proposed_change.type === "create_asset" ? "Create asset (propose)" : "Accept resolution"}</button>}
        {d.status === "pending_approval" && <><button className="btn-primary px-1.5 py-0 text-[11px]" onClick={() => act(d, "approve")} data-testid={`inv-approve-${d.id.slice(0, 8)}`}>Approve change</button>
          <button className="btn-secondary px-1.5 py-0 text-[11px]" onClick={() => act(d, "reject")}>Withdraw</button></>}
        <button className="btn-secondary px-1.5 py-0 text-[11px]" onClick={() => act(d, "ignore")} data-testid={`inv-ignore-${d.id.slice(0, 8)}`}>Ignore…</button>
        <button className="btn-secondary px-1.5 py-0 text-[11px]" onClick={() => act(d, "explain")} data-testid={`inv-explain-${d.id.slice(0, 8)}`}>Explain (AI)</button></div>}
      <AiBox ai={d.ai} testId={`inv-disc-ai-${d.id.slice(0, 8)}`} />
    </div>)}
  </div>);
}

function Tables({ o }: { o: Row }) {
  return (<div className="grid gap-3 lg:grid-cols-2">
    <div className="rounded border border-slate-200 p-3" data-testid="inv-hardware"><div className="mb-1 text-sm font-medium">Hardware ({o.hardware.length}) · scan-only hosts ({o.scan_observed.length})</div>
      <table className="w-full text-[11px]"><thead><tr className="text-left text-slate-500"><th>Machine</th><th>IP</th><th>Serial / MAC</th><th>OS</th><th>Source</th><th>Findings</th></tr></thead><tbody>
        {[...o.hardware, ...o.scan_observed].map((a: Row) => <tr key={a.id} className={`border-t border-slate-100 ${a.is_inventory ? "" : "text-slate-500"}`} data-testid={`inv-asset-${a.name}`}>
          <td>{a.name}{!a.is_inventory && (a.correlated_asset_id ? " (linked)" : " (scan only)")}</td><td>{[a.ip_address, ...a.ip_addresses.filter((x: string) => x !== a.ip_address)].filter(Boolean).join(", ")}</td>
          <td>{a.serial_number || "–"}{a.mac_address ? ` / ${a.mac_address}` : ""}</td><td>{a.os || "–"}</td><td><SourceBadge label={a.source_label} /></td><td>{a.findings ? <Link className="underline" to={`/findings?asset=${a.id}`}>{a.findings}</Link> : 0}</td></tr>)}
      </tbody></table></div>
    <div className="rounded border border-slate-200 p-3" data-testid="inv-software"><div className="mb-1 text-sm font-medium">Software ({o.software.length})</div>
      <table className="w-full text-[11px]"><thead><tr className="text-left text-slate-500"><th>Vendor</th><th>Name</th><th>Version</th><th>Type</th><th>Source</th></tr></thead><tbody>
        {o.software.map((s: Row) => <tr key={s.id} className="border-t border-slate-100"><td>{s.vendor}</td><td>{s.name}</td><td>{s.version}</td><td>{s.sw_type}</td><td><SourceBadge label={s.source_label} /></td></tr>)}
      </tbody></table></div>
  </div>);
}

export default function InventoryPage() {
  const sid = useActiveSystemId();
  const o = useApi<Row>(sid ? `/systems/${sid}/inventory` : null);
  const busy = (o.data?.imports || []).some((i: Row) => ["queued", "processing"].includes(i.status));
  useEffect(() => { if (!busy) return; const t = setInterval(o.reload, 2000); return () => clearInterval(t); }, [busy]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!sid) return <div className="p-6" data-testid="inv-no-system">Select a system first (top bar).</div>;
  return (<div className="space-y-4 p-6" data-testid="inventory-page">
    <div><div className="text-[11px] uppercase text-slate-500">System boundary → HW/SW Inventory</div><h1 className="text-2xl font-semibold">Hardware &amp; software inventory</h1>
      <p className="text-sm text-slate-600">Import the eMASS HW/SW List, correlate STIG checklists and ACAS scans to assets, resolve discrepancies by proposal and approval, and export back into the same template.</p></div>
    {o.data && <><Imports sid={sid} o={o.data} reload={o.reload} /><Correlations sid={sid} reload={o.reload} /><Discrepancies sid={sid} canWrite={o.data.can_write} reload={o.reload} /><Tables o={o.data} /></>}
  </div>);
}
