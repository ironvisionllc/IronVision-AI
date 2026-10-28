import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { Panel } from "@/components/common/Panel";
import type { Row } from "@/lib/useApi";

/** What the auditor read: extraction %, characters/sections, tables, warnings, whole-document coverage guard and second-look counts. */
export function ReadingReport({ r }: { r: Row }) {
  const kv: [string, string | number | null | undefined][] = [
    ["Text extracted", r.pct_extracted != null ? `${r.pct_extracted}%` : "–"], ["Characters read", r.chars_read],
    ["Sections", r.sections], ["Tables included", r.tables_included ? "yes" : "no"],
    ["Whole-document check", r.whole_document == null ? "–" : r.whole_document ? `yes – ${r.chunks_covered} of ${r.chunks_total} sections available to every control` : "no (document too large – retrieval only)"],
    ["Second look", r.second_look_candidates == null ? "–" : `${r.second_look_candidates} with candidate passages · ${r.second_look_ai} re-asked · ${r.second_look_found} found · ${r.second_look_confirmed_absent} confirmed absent`],
    ["Prompt cache", r.tokens_in ? `${Math.round((100 * (r.tokens_cached || 0)) / r.tokens_in)}% of ${r.tokens_in} input tokens from cache` : "–"]];
  return (
    <Panel title="Reading report" testId="policy-reading-report">
      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-[12px] sm:grid-cols-2">
        {kv.map(([k, v]) => <div key={k} className="flex gap-2"><dt className="shrink-0 text-slate-600">{k}:</dt><dd className="font-medium" data-testid={`reading-${k.toLowerCase().replace(/[^a-z]+/g, "-")}`}>{v ?? "–"}</dd></div>)}
      </dl>
      {(r.warnings || []).length > 0 && <ul className="mt-2 list-disc pl-5 text-[12px] text-amber-900" data-testid="reading-warnings">
        {r.warnings.map((w: string) => <li key={w}>{w}</li>)}</ul>}
      {(r.uncovered_sections || []).length > 0 && <p className="mt-2 text-[12px] text-rose-700" data-testid="reading-uncovered">Sections not available to any control check: {r.uncovered_sections.join(", ")}</p>}
    </Panel>);
}

/** "Found it here": highlight text in the policy and link it to a control/requirement → human proposal in Mapping Review (never auto-approved). */
export function FoundItHere({ policyId, canMap, setMsg }: { policyId: string; canMap: boolean; setMsg: (m: string) => void }) {
  const [sel, setSel] = useState("");
  const [ctl, setCtl] = useState("");
  const [req, setReq] = useState("");
  const grab = () => setSel((window.getSelection()?.toString() || "").trim());
  const send = async () => {
    try {
      const r = await api.post<Row>(`/policies/${policyId}/found-it-here`, { control_id: ctl.trim().toLowerCase().replace(/\((\d+)\)/, ".$1"), requirement_id: req.trim() || null, text: sel });
      setMsg(r.data.message); setSel("");
    } catch (e) { setMsg(errorMessage(e)); }
  };
  if (!canMap) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px]" data-testid="found-it-here">
      <button className="btn-secondary !py-0.5" onMouseDown={(e) => e.preventDefault()} onClick={grab} data-testid="found-it-here-grab">Found it here (use highlighted text)</button>
      {sel && <>
        <span className="max-w-md truncate italic" title={sel} data-testid="found-it-here-selection">“{sel}”</span>
        <input className="input w-28" placeholder="Control e.g. RA-5" value={ctl} onChange={(e) => setCtl(e.target.value)} aria-label="Control" data-testid="found-it-here-control" />
        <input className="input w-36" placeholder="Requirement (optional)" value={req} onChange={(e) => setReq(e.target.value)} aria-label="Requirement" data-testid="found-it-here-req" />
        <button className="btn-primary !py-0.5" disabled={!/^[a-zA-Z]{2}-\d+/.test(ctl.trim()) || sel.length < 12} onClick={send} data-testid="found-it-here-send">Send to Mapping Review</button></>}
    </div>);
}

/** "Use this passage" on a candidate passage: same human-proposal path as Found it here. */
export function UseCandidate({ policyId, controlId, requirementId, text, setMsg }: { policyId: string; controlId: string; requirementId?: string; text: string; setMsg: (m: string) => void }) {
  const use = async () => {
    try { const r = await api.post<Row>(`/policies/${policyId}/found-it-here`, { control_id: controlId, requirement_id: requirementId || null, text, via: "use_candidate" }); setMsg(r.data.message); }
    catch (e) { setMsg(errorMessage(e)); }
  };
  return <button className="ml-2 text-[11px] text-blue-800 underline" onClick={use} data-testid={`use-candidate-${controlId}-${requirementId || "x"}`}>Use this passage</button>;
}
