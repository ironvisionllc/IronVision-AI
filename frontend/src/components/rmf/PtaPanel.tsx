import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { useAuth } from "@/context/AuthContext";
import { Panel } from "@/components/common/Panel";
import { SimulatedSignatureNote } from "@/components/shell/Sandbox";

const ANS: [string, string][] = [["yes", "Yes"], ["no", "No"], ["not_sure", "Not sure – requires review"]];
const visible = (q: Row, a: Row) => Object.entries(q.show_if ?? {}).every(([k, v]) => a[k]?.answer === v);

/** Privacy Threshold Analysis: configurable questions, conditional follow-ups, privacy official review. Outcome is a recommendation only. */
export function PtaPanel({ sid }: { sid: string }) {
  const { can } = useAuth();
  const { data, reload } = useApi<Row>(`/systems/${sid}/pta`);
  const [a, setA] = useState<Row>({});
  const [rev, setRev] = useState<Row>({ rationale: "", determination: "" });
  const [m, setM] = useState<{ ok?: string; err?: string }>({});
  useEffect(() => { if (data?.latest) setA(data.latest.answers); }, [data]);
  if (!data) return null;
  const qs = data.question_set, last = data.latest;
  const submit = async () => { try { await api.post(`/systems/${sid}/pta`, { answers: a }); setM({ ok: "PTA submitted for privacy review." }); reload(); } catch (e) { setM({ err: errorMessage(e) }); } };
  const review = async (decision: string) => {
    try { await api.post(`/systems/${sid}/pta/${last.id}/review`, { decision, rationale: rev.rationale, determination: rev.determination || null }); setM({ ok: `PTA ${decision === "approve" ? "approved" : "returned"}.` }); reload(); }
    catch (e) { setM({ err: errorMessage(e) }); }
  };
  return (
    <Panel title={qs.title} eyebrow={qs.label} testId="pta-panel">
      <div className="grid gap-3 text-[12px]">
        {qs.questions.filter((q: Row) => visible(q, a)).map((q: Row) => (
          <div key={q.id} data-testid={`pta-q-${q.id}`}>
            <div className="font-medium text-slate-800">{q.text}{q.required && <span className="text-rose-700"> *</span>}</div>
            <div className="mt-1 flex flex-wrap gap-4" role="radiogroup" aria-label={q.text}>{ANS.map(([k, l]) => (
              <label key={k} className="flex items-center gap-1.5"><input type="radio" name={`pta-${q.id}`} checked={a[q.id]?.answer === k} disabled={!can("system.write")}
                onChange={() => setA({ ...a, [q.id]: { ...a[q.id], answer: k } })} data-testid={`pta-${q.id}-${k}`} />{l}</label>))}
              {!a[q.id]?.answer && <span className="text-[11px] text-amber-800">Not answered</span>}</div>
            <input className="input mt-1" placeholder="Explanation (optional)" value={a[q.id]?.explanation ?? ""} disabled={!can("system.write")}
              onChange={(e) => setA({ ...a, [q.id]: { ...a[q.id], explanation: e.target.value } })} data-testid={`pta-${q.id}-why`} />
          </div>))}
        {can("system.write") && <button className="btn-primary w-fit px-2 py-0.5 text-[11px]" onClick={submit} data-testid="pta-submit">Submit PTA for privacy review</button>}
        {m.ok && <div className="text-emerald-700" role="status">{m.ok}</div>}{m.err && <div className="text-rose-700" role="alert">{m.err}</div>}
        {last && <div className="rounded border border-slate-200 p-2" data-testid="pta-latest">
          <div>Revision {last.revision} · <b data-testid="pta-status">{last.status}</b>{last.reviewer && <> · reviewed by {last.reviewer} on {String(last.reviewed_at).slice(0, 10)} – {last.review_rationale}</>}</div>
          <p className="mt-1 rounded bg-blue-50 p-2 text-[11px] text-blue-900" data-testid="pta-recommendation">{last.recommendation}</p>
          {(last.flags ?? []).map((f: Row, i: number) => <div key={i} className="text-[11px] text-amber-800" data-testid={`pta-flag-${i}`}>⚑ {f.flag}</div>)}
          {last.status === "submitted" && (can("privacy.review") ? <div className="mt-2 grid gap-1.5" data-testid="pta-review">
            <SimulatedSignatureNote />
            <select className="input w-64" value={rev.determination} onChange={(e) => setRev({ ...rev, determination: e.target.value })} data-testid="pta-determination">
              <option value="">Determination (needed to approve)</option><option value="pii">PII present – privacy controls apply</option><option value="no_pii">No PII – confirmed by privacy official</option></select>
            <textarea className="input" rows={2} placeholder="Review rationale (required)" value={rev.rationale} onChange={(e) => setRev({ ...rev, rationale: e.target.value })} data-testid="pta-review-why" />
            <div className="flex gap-2"><button className="btn-primary px-2 py-0.5 text-[11px]" onClick={() => review("approve")} data-testid="pta-approve">Approve</button>
              <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => review("return")} data-testid="pta-return">Return for changes</button></div></div>
            : <p className="mt-1 text-[11px] text-slate-600" data-testid="pta-review-locked">Awaiting a Privacy Official's review – only they can make the privacy determination.</p>)}
        </div>}
        <p className="text-[11px] text-slate-500">{data.note} Any AI suggestion about privacy is suggestion-only and never a determination.</p>
      </div>
    </Panel>);
}
