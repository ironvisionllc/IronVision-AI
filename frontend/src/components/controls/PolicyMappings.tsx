import { useEffect, useState } from "react";
import { TableScroll } from "@/components/common/TableScroll";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Modal } from "@/components/common/Modal";
import { showNextStep } from "@/components/common/NextStep";
import { ConfidenceBadge, SideBySideReview } from "@/components/controls/SideBySideReview";

/** Searchable multi-select of catalog controls (ID, title, enhancements) → POST /policies/{id}/control-mappings. */
export function MapToControlModal({ policyId, initial = [], onClose, onDone }: { policyId: string; initial?: string[]; onClose: () => void; onDone: (m: string, ids: string[]) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Row[]>([]);
  const [sel, setSel] = useState<string[]>(initial);
  const [just, setJust] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    if (q.trim().length < 2) { setHits([]); return; }
    const t = setTimeout(() => api.get<Row>("/controls", { params: { q, limit: 25 } }).then((r) => setHits(r.data.items)).catch(() => setHits([])), 250);
    return () => clearTimeout(t);
  }, [q]);
  const toggle = (id: string) => setSel(sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id]);
  const save = async () => {
    try { const r = await api.post<Row>(`/policies/${policyId}/control-mappings`, { control_ids: sel, justification: just }); onDone(`Policy mapped to ${r.data.mapped.map((c: string) => fmtId(c)).join(", ")}.`, r.data.mapped); }
    catch (e) { setErr(`Could not save the mapping: ${errorMessage(e)}`); }
  };
  return (
    <Modal title="Map this policy to controls" onClose={onClose} testId="map-control-modal">
      <p className="mb-2 text-[12px] text-slate-600">Search the NIST 800-53 Rev 5 catalog by ID or name, tick every control this policy supports, then save.</p>
      <input className="input" autoFocus placeholder="Search control ID or title (e.g. ra-1, risk, ac-2(1))" value={q} onChange={(e) => setQ(e.target.value)} data-testid="map-control-search" />
      <div className="mt-2 max-h-56 overflow-y-auto" data-testid="map-control-results">
        {hits.map((c) => <label key={c.control_id} className="flex items-center gap-2 border-b border-slate-100 py-1 text-[12px]">
          <input type="checkbox" checked={sel.includes(c.control_id)} onChange={() => toggle(c.control_id)} data-testid={`map-control-option-${c.control_id}`} />
          <span className="font-mono font-semibold">{c.label}</span> {c.title}{c.is_enhancement && <span className="text-[10px] text-slate-500">enhancement</span>}</label>)}
      </div>
      <div className="mt-2 flex flex-wrap gap-1" data-testid="map-control-selected">{sel.map((s) => <button key={s} className="rounded bg-blue-100 px-1.5 text-[11px] font-mono" onClick={() => toggle(s)}>{s.toUpperCase()} ×</button>)}</div>
      <textarea className="input mt-2" rows={2} placeholder="Note (optional)" value={just} onChange={(e) => setJust(e.target.value)} data-testid="map-control-note" />
      {err && <div className="mt-1 text-[12px] text-rose-700" role="alert" data-testid="map-control-error">{err}</div>}
      <div className="mt-3 flex justify-end gap-2"><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={!sel.length} onClick={save} data-testid="map-control-save">Map {sel.length || ""} control(s)</button></div>
    </Modal>);
}

export function PolicyMappingsPanel({ policyId, data, canMap, reload, setMsg }: { policyId: string; data: Row; canMap: boolean; reload: () => void; setMsg: (m: string) => void }) {
  const [open, setOpen] = useState<string[] | null>(null);
  const [reject, setReject] = useState<Row | null>(null);
  const [sbs, setSbs] = useState<string | null>(null);
  const [just, setJust] = useState("");
  const [err, setErr] = useState("");
  const sid = (data.policy?.system_ids || [])[0];
  const next = (message: string, cid: string) => showNextStep(sid ? { message, label: `review ${fmtId(cid)} in the Control Workbench`, to: `/systems/${sid}/controls/${cid}` }
    : { message, label: "register the system this policy applies to", to: "/systems/new" });
  const doReject = async () => {
    if (just.trim().length < 10) { setErr("Please explain why (at least 10 characters) – the reason is kept in the audit history."); return; }
    try { await api.post(`/policies/${policyId}/control-mappings/reject`, { control_id: reject?.control_id, justification: just }); setMsg(`Mapping to ${fmtId(reject?.control_id)} rejected. It stays in the history with your reason.`); setReject(null); setJust(""); reload(); }
    catch (e) { setErr(`Could not reject the mapping: ${errorMessage(e)}`); }
  };
  const confirm = async (cid: string) => {
    try { await api.post(`/policies/${policyId}/control-mappings`, { control_ids: [cid] }); setMsg(`Mapping to ${fmtId(cid)} confirmed.`); next(`Policy mapped to ${fmtId(cid)}.`, cid); reload(); }
    catch (e) { setMsg(`Could not confirm the mapping: ${errorMessage(e)}`); }
  };
  const rows: Row[] = data.control_mappings || [];
  return (
    <div data-testid="policy-mappings">
      <p className="mb-2 text-[12px] text-slate-600">Controls this policy supports. <b>Confirm</b> the suggestions you agree with, <b>reject</b> the rest, or <b>map</b> more controls yourself. Confirmed mappings show on each control in the Control Workbench.</p>
      {canMap && <button className="btn-primary mb-2 px-3 py-1 text-[12px]" onClick={() => setOpen([])} data-testid="map-to-control-btn">Map to control</button>}
      {rows.length === 0 && <div className="text-[12px] text-slate-500" data-testid="policy-mappings-empty">No controls suggested yet. If the policy is still being analysed this fills in shortly – or use “Map to control”.</div>}
      {rows.length > 0 && <TableScroll><table className="w-full text-[12px]"><thead><tr className="text-left text-[11px] text-slate-500"><th>Control</th><th title="High = explicit control ID + requirement language · Medium = requirement language only (or ID without requirement language) · Low = inferred relevance · Requires manual review = no supporting text">Confidence <span className="cursor-help underline decoration-dotted">ⓘ</span></th><th>Why it was suggested</th><th>Matching text in the policy</th><th>Status</th><th /></tr></thead><tbody>
        {rows.map((m) => <tr key={m.id} className="border-t border-slate-100 align-top" data-testid={`policy-mapping-${m.control_id}`}>
          <td className="py-1"><span className="font-mono font-semibold">{fmtId(m.control_id)}</span>{m.control_title && <div className="text-[11px] text-slate-700">{m.control_title}</div>}{(m.parts || []).length > 0 && <div className="text-[10px] text-slate-500">parts: {m.parts.join(", ")}</div>}</td>
          <td className="py-1"><span className="sr-only" data-testid={`mapping-confidence-${m.control_id}`}>{m.confidence}</span><ConfidenceBadge m={m} /></td>
          <td className="max-w-[260px] py-1 text-[11px] text-slate-600" data-testid={`mapping-basis-${m.control_id}`}>{basisText(m.source)}</td>
          <td className="max-w-[340px] py-1 text-[11px] text-slate-700">{m.no_supporting_text ? <b className="text-rose-700" data-testid={`mapping-no-text-${m.control_id}`}>No supporting text found – manual review required</b>
            : (m.excerpts || []).slice(0, 2).map((e: Row, i: number) => <div key={i}>“{e.text}”<span className="block text-[10px] text-slate-500">{e.section ? `§ ${e.section}` : ""}{e.page ? ` · p. ${e.page}` : ""}</span></div>)}
            {m.reanalysis && <div className="text-[10px] text-amber-800">Re-analysis differs from approved</div>}{m.review_flag && <div className="text-[10px] text-rose-700">Flagged for manual review</div>}</td>
          <td className="py-1" data-testid={`mapping-status-${m.control_id}`}>{STATUS[m.status] ?? m.status}{m.decider_name && <div className="text-[10px] text-slate-500">{m.decider_name} · {new Date(m.decided_at).toLocaleString()}</div>}{m.justification && <div className="text-[10px] text-slate-500">Reason: {m.justification}</div>}</td>
          <td className="py-1"><button className="mb-1 text-[11px] text-blue-800 underline" onClick={() => setSbs(m.control_id)} data-testid={`mapping-sbs-${m.control_id}`}>Review side by side</button>{canMap && m.status !== "rejected" && <div className="flex gap-1">
            {m.status === "proposed" && <button className="btn-primary px-2 py-0.5 text-[11px]" onClick={() => confirm(m.control_id)} data-testid={`mapping-confirm-${m.control_id}`}>Confirm</button>}
            <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => { setReject(m); setErr(""); }} data-testid={`mapping-reject-${m.control_id}`}>Reject mapping</button></div>}</td></tr>)}
      </tbody></table></TableScroll>}
      <details className="mt-2 text-[11px]" data-testid="mapping-history"><summary className="cursor-pointer text-slate-600">Mapping history ({(data.mapping_history || []).length} entries – every decision is kept)</summary>
        {(data.mapping_history || []).map((h: Row) => <div key={h.id}>{new Date(h.created_at).toLocaleString()} · {fmtId(h.control_id)} · {STATUS[h.status] ?? h.status} · {basisText(h.source)}{h.decider_name ? ` · ${h.decider_name}` : ""}{h.valid_to ? " (replaced by a later decision)" : ""}</div>)}</details>
      {sbs && <SideBySideReview policyId={policyId} controlId={sbs} canDecide={canMap} onClose={() => setSbs(null)} onChanged={reload} />}
      {open && <MapToControlModal policyId={policyId} initial={open} onClose={() => setOpen(null)} onDone={(m, ids) => { setOpen(null); setMsg(m); if (ids[0]) next(m, ids[0]); reload(); }} />}
      {reject && <Modal title={`Reject the mapping to ${fmtId(reject.control_id)}?`} onClose={() => setReject(null)} testId="reject-mapping-modal">
        <p className="mb-2 text-[12px] text-slate-600">The suggestion is removed from this policy but kept in the history with your reason, so assessors can see why.</p>
        <textarea className="input" rows={3} placeholder="Why doesn't this policy support the control? (required, at least 10 characters)" value={just} onChange={(e) => setJust(e.target.value)} data-testid="reject-mapping-justification" />
        {err && <div className="mt-1 text-[12px] text-rose-700" role="alert" data-testid="reject-mapping-error">{err}</div>}
        <div className="mt-3 flex justify-end gap-2"><button className="btn-secondary" onClick={() => setReject(null)}>Cancel</button><button className="btn-primary" onClick={doReject} data-testid="reject-mapping-confirm">Reject mapping</button></div>
      </Modal>}
    </div>);
}

const STATUS: Record<string, string> = { proposed: "Suggested – needs your review", mapped: "Mapped", rejected: "Rejected" };
const BASIS: Record<string, string> = { explicit_id: "the policy quotes this control ID", statement_language: "the policy's wording matches this control's requirement",
  title_language: "this control's name appears in the policy", ai: "suggested by the AI assistant", manual: "mapped by a reviewer" };
const fmtId = (c?: string) => (c ?? "").toUpperCase().replace(/\.(\d+)$/, "($1)");
const basisText = (s: string) => { const t = (s || "").split("+").map((x) => BASIS[x] ?? x.replace(/_/g, " ")).join("; and "); return t.charAt(0).toUpperCase() + t.slice(1); };
