import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { Modal } from "@/components/common/Modal";
import { clip } from "@/lib/format";

const fmtId = (c?: string) => (c ?? "").toUpperCase().replace(/\.(\d+)$/, "($1)");
const CONF_CLS: Record<string, string> = { High: "bg-emerald-100 text-emerald-800", Medium: "bg-amber-100 text-amber-800", Low: "bg-slate-100 text-slate-700",
  "Requires manual review": "bg-rose-100 text-rose-800" };

export function ConfidenceBadge({ m }: { m: Row }) {
  const c = m.evidence_confidence ?? m.confidence;
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${CONF_CLS[c] ?? ""}`} title={m.confidence_explanation} data-testid={`evidence-confidence-${m.control_id}`}>
    {c}{m.evidence_kind && m.evidence_kind !== "none" ? ` · ${m.evidence_kind === "direct" ? "direct evidence" : "inferred relevance"}` : ""}</span>;
}

/** Side-by-side mapping review: control requirement (left, sticky) vs located policy excerpts, confidence, coverage and gaps (right). */
export function SideBySideReview({ policyId, controlId, canDecide, onClose, onChanged }: { policyId: string; controlId: string; canDecide: boolean; onClose: () => void; onChanged?: () => void }) {
  const { data, reload } = useApi<Row>(`/policies/${policyId}/mappings/${controlId}/review`);
  const [comment, setComment] = useState("");
  const [edit, setEdit] = useState("");
  const [cov, setCov] = useState("");
  const [msg, setMsg] = useState<{ ok?: string; err?: string }>({});
  const act = async (action: string) => {
    try { await api.post(`/policies/${policyId}/mappings/${controlId}/decision`, { action, comment, edit_control_id: edit || null, coverage_outcome: cov || null });
      setMsg({ ok: `${action.replace("_", " ")} saved.` }); setComment(""); reload(); onChanged?.(); }
    catch (e) { setMsg({ err: errorMessage(e) }); }
  };
  return (
    <Modal title={`Mapping review – ${fmtId(controlId)}`} onClose={onClose} testId="sbs-review" wide>
      {!data ? <p className="text-[12px]">Loading…</p> : <div className="grid gap-4 text-[12px] lg:grid-cols-2">
        <section className="self-start lg:sticky lg:top-0" aria-label="Control requirement" data-testid="sbs-left">
          <div className="text-[11px] uppercase text-slate-500">{data.control.framework} · {data.control.family}</div>
          <h3 className="font-heading text-[14px] font-semibold">{fmtId(data.control.control_id)} {data.control.title}</h3>
          <p className="mt-2 whitespace-pre-line rounded border border-slate-200 bg-white p-2" data-testid="sbs-statement">{data.control.statement}</p>
          {data.control.odps.length > 0 && <div className="mt-2"><b>Organization-defined parameters</b>{data.control.odps.map((p: Row) => <div key={p.id} className="text-[11px]">{p.id}: {p.label}</div>)}</div>}
          {data.control.enhancements.length > 0 && <div className="mt-2"><b>Enhancements</b> <span className="text-[11px]">{data.control.enhancements.map((e: Row) => `${fmtId(e.control_id)} ${e.title}`).join(" · ")}</span></div>}
          <details className="mt-2"><summary className="cursor-pointer font-semibold">CCIs and assessment objectives ({data.control.requirements.length})</summary>
            {data.control.requirements.map((q: Row) => <div key={q.id} className="text-[11px]"><b>{q.label}</b> {q.text}</div>)}</details>
          {data.control.guidance && <details className="mt-2 rounded bg-slate-50 p-2" data-testid="sbs-guidance"><summary className="cursor-pointer text-slate-600">Supplemental guidance (not a requirement)</summary>
            <p className="mt-1 whitespace-pre-line text-[11px] text-slate-600">{data.control.guidance}</p></details>}
        </section>
        <section aria-label="Policy evidence" data-testid="sbs-right">
          <div className="text-[11px] uppercase text-slate-500">Policy</div>
          <h3 className="font-heading text-[14px] font-semibold">{data.policy.title} · v{data.policy.version}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-2"><ConfidenceBadge m={{ ...data.mapping, control_id: controlId }} /><span className="text-[11px] text-slate-600">{data.mapping.confidence_explanation}</span></div>
          <div className="mt-1 text-[11px] text-slate-600">Rationale: {data.mapping.rationale}</div>
          {data.mapping.no_supporting_text ? <p className="mt-2 rounded bg-rose-50 p-2 font-semibold text-rose-800" data-testid="sbs-no-text">No supporting text found – manual review required</p>
            : data.mapping.excerpts.map((e: Row, i: number) => <blockquote key={i} className="mt-2 rounded border-l-4 border-blue-400 bg-slate-50 p-2 text-[11px]" data-testid={`sbs-excerpt-${i}`}>
              <span className="text-slate-500">…{e.context_before?.slice(-120)}</span><mark className="bg-yellow-200">{e.text}</mark><span className="text-slate-500">{e.context_after?.slice(0, 120)}…</span>
              <div className="mt-1 text-[10px] text-slate-500">{e.page ? `Page ${e.page}` : "Page not available (text extracted without page breaks)"} · {e.section ? `Section “${e.section}”` : "Section not identified"} · exact match verified</div></blockquote>)}
          {data.mapping.reanalysis && <p className="mt-2 rounded bg-amber-50 p-2 text-[11px] text-amber-900" data-testid="sbs-reanalysis">Re-analysis proposal – differs from approved: {data.mapping.reanalysis.confidence} · {(data.mapping.reanalysis.snippets || [])[0]}</p>}
          <div className="mt-3"><b>Coverage:</b> <span data-testid="sbs-coverage">{data.coverage.outcome}</span>{data.coverage.model_status && <span className="text-slate-500"> ({data.coverage.model_status})</span>}
            {data.coverage.overridden && <span className="text-[11px] text-slate-600"> – reviewer override by {data.coverage.by}: {data.coverage.justification}</span>}</div>
          {data.coverage.note && <div className="text-[10px] text-slate-500">{data.coverage.note}</div>}
          <div className="mt-2"><b>Gap analysis</b>{data.gaps.length ? data.gaps.map((g: Row, i: number) => <div key={i} className="text-[11px]" data-testid={`sbs-gap-${i}`} title={g.text}><span className="font-semibold">{g.type}:</span> {clip(g.text, 400)}</div>) : <div className="text-[11px]">No gaps found.</div>}</div>
          <details className="mt-2 text-[11px]"><summary className="cursor-pointer text-blue-800" data-testid="sbs-legend">Confidence legend</summary>{Object.entries(data.legend).map(([k, v]) => <div key={k}><b>{k}:</b> {String(v)}</div>)}</details>
          {canDecide && <div className="mt-3 grid gap-1.5 rounded border border-slate-200 p-2" data-testid="sbs-actions">
            <textarea className="input" rows={2} placeholder="Comment (required for reject, edit, flag and coverage override)" value={comment} onChange={(e) => setComment(e.target.value)} data-testid="sbs-comment" />
            <div className="flex flex-wrap gap-1.5">
              <button className="btn-primary px-2 py-0.5 text-[11px]" onClick={() => act("accept")} data-testid="sbs-accept">Accept</button>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act("reject")} data-testid="sbs-reject">Reject</button>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act("reanalyze")} data-testid="sbs-reanalyze">Request reanalysis</button>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => act("flag")} data-testid="sbs-flag">Flag for manual review</button></div>
            <div className="flex flex-wrap gap-1.5"><input className="input w-36" placeholder="Other control (AC-2(1))" value={edit} onChange={(e) => setEdit(e.target.value)} data-testid="sbs-edit-target" />
              <button className="btn-secondary px-2 py-0.5 text-[11px]" disabled={!edit} onClick={() => act("edit")} data-testid="sbs-edit">Edit mapping</button>
              <select className="input w-52" value={cov} onChange={(e) => setCov(e.target.value)} data-testid="sbs-cov-select"><option value="">Override coverage…</option>
                {["Fully Addressed", "Partially Addressed", "Not Addressed", "Requires Manual Review"].map((o) => <option key={o}>{o}</option>)}</select>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" disabled={!cov} onClick={() => act("override_coverage")} data-testid="sbs-override">Save override</button></div>
            {msg.ok && <div className="text-emerald-700" role="status">{msg.ok}</div>}{msg.err && <div className="text-rose-700" role="alert">{msg.err}</div>}
            {(data.mapping.comments || []).length > 0 && <div className="text-[10px] text-slate-500">{data.mapping.comments.map((c: Row, i: number) => <div key={i}>{String(c.at).slice(0, 16)} · {c.by} · {c.action}{c.comment ? `: ${c.comment}` : ""}</div>)}</div>}
          </div>}
        </section>
      </div>}
    </Modal>);
}
