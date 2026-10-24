import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { fmtControl } from "@/lib/format";

const List = ({ ids, testId }: { ids: string[]; testId: string }) =>
  ids.length ? <div className="mt-1 max-h-24 overflow-auto font-mono text-[11px] text-slate-700" data-testid={testId}>{ids.map(fmtControl).join(", ")}</div> : null;

/** CNSSI 1253 Appendix D baseline for NSS systems: trigraph selection, pending proposal (review + accept), source and SME items. */
export function CnssiBaseline({ sid, d, reload }: { sid: string; d: Row; reload: () => void }) {
  const c = d.cnssi, n = d.counts.cnssi, p = c.proposal;
  const [m, setM] = useState<{ ok?: string; err?: string }>({});
  const accept = async () => {
    try {
      const r = await api.post<Row>(`/systems/${sid}/select/cnssi-baseline`, { to: p.to });
      setM({ ok: `CNSSI 1253 ${r.data.applied} baseline applied: ${r.data.added} added, ${r.data.removed} removed, ${r.data.kept_with_work} kept (have work). ${r.data.counts.labels.reconciliation}.` });
      reload();
    } catch (e) { setM({ err: errorMessage(e) }); }
  };
  return (
    <Panel title="Baseline" eyebrow="CNSSI 1253 Appendix D (NSS)" testId="select-cnssi-baseline">
      {m.ok && <p className="mb-2 text-[12px] text-emerald-800" data-testid="cnssi-msg-ok">{m.ok}</p>}
      {m.err && <p className="mb-2 text-[12px] text-rose-700" role="alert" data-testid="cnssi-msg-err">{m.err}</p>}
      <div className="grid gap-3 text-[12px] md:grid-cols-3">
        <div>Security categorization (trigraph)<div className="text-[15px] font-semibold" data-testid="cnssi-trigraph">{c.trigraph ?? "— (set C, I and A)"}</div></div>
        <div>Applied CNSSI baseline<div className="text-[15px] font-semibold" data-testid="cnssi-applied">{c.applied ?? "not yet applied"}</div>
          {c.applied && <div className={`text-[11px] ${c.categorization_status.startsWith("Pending") ? "text-amber-800" : "text-emerald-800"}`} data-testid="cnssi-cat-status">{c.categorization_status}</div>}</div>
        {n && <div data-testid="cnssi-breakdown">C: {n.c} · I: {n.i} · A: {n.a} · union {n.security_union} + privacy {n.privacy_baseline} = <b>{n.union}</b></div>}
      </div>
      {p && <div className="mt-3 rounded border border-amber-300 bg-amber-50 p-3 text-[12px] text-amber-900" data-testid="cnssi-proposal">
        <b data-testid="cnssi-proposal-message">{p.message}</b> <span className="text-amber-800">(from {p.from} to {p.to})</span>
        <div className="mt-2">Add {p.add.length}:</div><List ids={p.add} testId="cnssi-proposal-add" />
        <div className="mt-2">Remove {p.remove.length} (baseline controls with no statement, evidence or assessment work):</div><List ids={p.remove} testId="cnssi-proposal-remove" />
        {p.keep_with_work.length > 0 && <><div className="mt-2">Keep {p.keep_with_work.length} as tailored in (they already have work):</div><List ids={p.keep_with_work} testId="cnssi-proposal-keep" /></>}
        {p.tailored_out_kept_out.length > 0 && <div className="mt-2">{p.tailored_out_kept_out.length} previously tailored out stay out.</div>}
        <button className="btn-primary mt-3" onClick={accept} disabled={!!p.blocked_reason} title={p.blocked_reason ?? undefined} data-testid="cnssi-accept">Accept CNSSI 1253 {p.to} baseline</button>
        {p.blocked_reason && <p className="mt-1 text-[12px]" data-testid="cnssi-accept-blocked">{p.blocked_reason}. <Link className="font-medium underline" to={p.approval_link} data-testid="cnssi-approval-link">Go to the categorization approval</Link></p>}
      </div>}
      <p className="mt-3 text-[11px] text-slate-600" data-testid="cnssi-rule">{c.rule.text.join(" ")} – {c.rule.ref}. Applied as: {c.rule.implemented_as}</p>
      <p className="mt-1 text-[11px] text-slate-500" data-testid="cnssi-source">Source: {c.source}</p>
      {c.sme_review.map((x: string) => <p key={x} className="mt-1 rounded bg-amber-50 p-2 text-[11px] text-amber-900" data-testid="cnssi-sme">{x}</p>)}
    </Panel>);
}
