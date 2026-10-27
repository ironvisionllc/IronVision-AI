import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { fmtControl } from "@/lib/format";

export const SELECT_STEPS = ["Categorization summary", "Initial baseline", "Overlays", "Tailoring & parameters", "Review & approve"];

export function SelectStepper({ step, setStep, done }: { step: number; setStep: (n: number) => void; done: boolean[] }) {
  return <ol className="flex flex-wrap gap-2" data-testid="select-stepper">{SELECT_STEPS.map((t, i) =>
    <li key={t}><button onClick={() => setStep(i)} className={`rounded-full px-3 py-1 text-[12px] ${step === i ? "bg-slate-900 text-white" : done[i] ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-700"}`}
      data-testid={`select-step-${i + 1}`} aria-current={step === i ? "step" : undefined}>{i + 1}. {t}{done[i] && step !== i ? " ✓" : ""}</button></li>)}</ol>;
}

/** Result of a dry-run (nothing saved) – shown before every Apply. */
export function PreviewBox({ p, onConfirm, onCancel, label, testId }: { p: Row; onConfirm: () => void; onCancel: () => void; label: string; testId: string }) {
  const ids = (xs: string[]) => xs.slice(0, 40).map(fmtControl).join(", ") + (xs.length > 40 ? ` … +${xs.length - 40}` : "");
  return <div className="mt-2 rounded border border-blue-300 bg-blue-50/60 p-3 text-[12px]" data-testid={testId}>
    <div className="font-medium">Preview – nothing has been saved yet</div>
    <div className="mt-1" data-testid={`${testId}-summary`}>Controls: {p.counts_before.assigned} → <b>{p.counts_after.assigned}</b> · <span className="text-emerald-800">+{p.added.length} added</span> · <span className="text-rose-800">−{p.removed.length} removed</span> · {p.parameters_changed.length} parameter value(s) changed</div>
    {!!p.added.length && <div className="mt-1 text-slate-700">Added: {ids(p.added)}</div>}
    {!!p.removed.length && <div className="mt-1 text-rose-900" data-testid={`${testId}-removed`}>Removed: {ids(p.removed)} – this deletes {p.would_delete.statements} implementation statement(s) and {p.would_delete.evidence_links} evidence link(s) for this system (kept in the audit history).</div>}
    {!!p.parameters_changed.length && <div className="mt-1 text-slate-700">Parameters: {p.parameters_changed.slice(0, 12).join("; ")}{p.parameters_changed.length > 12 ? " …" : ""}</div>}
    <div className="mt-2 flex gap-2"><button className="btn-primary" onClick={onConfirm} data-testid={`${testId}-confirm`}>{label}</button><button className="btn-secondary" onClick={onCancel} data-testid={`${testId}-cancel`}>Cancel</button></div>
  </div>;
}

export function CategorizationSummary({ sid, d, next }: { sid: string; d: Row; next: () => void }) {
  const { data: s } = useApi<Row>(`/systems/${sid}`);
  if (!s) return null;
  const cn = d.framework === "cnssi1253";
  return <Panel title="Step 1 · Categorization summary" eyebrow={cn ? "CNSSI 1253 (National Security System)" : "FIPS 199 / NIST SP 800-60"} testId="select-cat-summary">
    <p className="text-[12px] text-slate-600">What the baseline is generated from. Change it in Categorize (Task C-2); a change needs AO approval before a new baseline is accepted.</p>
    <div className="mt-2 grid gap-3 text-[12px] md:grid-cols-5">
      <div>Framework<div className="text-[14px] font-semibold" data-testid="select-cat-framework">{cn ? "CNSSI 1253" : "FIPS 199"}</div></div>
      {[["Confidentiality", s.confidentiality_impact], ["Integrity", s.integrity_impact], ["Availability", s.availability_impact]].map(([l, v]) =>
        <div key={l}>{l}<div className="text-[14px] font-semibold capitalize" data-testid={`select-cat-${String(l).toLowerCase()}`}>{v || "—"}</div></div>)}
      <div>{cn ? "Trigraph / approval" : "Overall (high-water mark)"}<div className="text-[14px] font-semibold capitalize" data-testid="select-cat-overall">{cn ? (d.cnssi?.applied?.trigraph || d.cnssi?.trigraph || "—") : (s.categorization || "—")}</div>
        {cn && d.cnssi?.approval && <div className="text-[11px] text-slate-500">{d.cnssi.approval.label || d.cnssi.approval.status}</div>}</div>
    </div>
    <div className="mt-3 flex gap-3"><Link className="btn-secondary" to="/rmf/categorize" data-testid="select-cat-edit">Edit in Categorize</Link>
      <button className="btn-primary" onClick={next} data-testid="select-next-1">Next: initial baseline</button></div>
  </Panel>;
}

export function SelectionReview({ sid, canSubmit }: { sid: string; canSubmit: boolean }) {
  const { data: r, reload } = useApi<Row>(`/systems/${sid}/select/review`);
  const [why, setWhy] = useState("");
  const [show, setShow] = useState<"added" | "removed" | "">("");
  if (!r) return null;
  const submit = async () => {
    try { await api.post(`/systems/${sid}/select/submit`, { justification: why }); toast.success("Selection submitted – the ISSM endorses, then the AO approves (Reviews)"); setWhy(""); reload(); }
    catch (e) { toast.error(errorMessage(e)); }
  };
  const c = r.counts, ap = r.approval;
  const list = (xs: Row[]) => <table className="mt-2 w-full text-[11px]"><thead><tr className="text-left text-slate-500"><th>Control</th><th>Why</th><th>Rationale</th></tr></thead><tbody>
    {xs.map((x: Row) => <tr key={x.control_id} className="border-t border-slate-100"><td className="font-mono">{fmtControl(x.control_id)}</td>
      <td>{x.decision?.by || x.origin || "baseline change"}{x.detail ? ` (${x.detail})` : ""}{x.decision?.applicability ? ` · ${x.decision.applicability}` : ""}{x.decision?.compensating_control_id ? ` → ${fmtControl(x.decision.compensating_control_id)}` : ""}</td>
      <td className="text-slate-600">{x.decision?.justification || (x.origin === "overlay" ? "defined by the overlay" : <span className="text-amber-800">no rationale recorded</span>)}</td></tr>)}</tbody></table>;
  return <Panel title="Step 5 · Review & approve" eyebrow="SP 800-37 Task S-6 – selection approved as part of the security plan" testId="select-review">
    <div className="grid gap-3 text-[12px] md:grid-cols-4" data-testid="select-review-diff">
      <div>Original baseline<div className="text-[18px] font-semibold" data-testid="select-review-original">{r.original.count.toLocaleString()}</div><div className="text-[11px] text-slate-500">{r.original.source}</div></div>
      <div>Added<div className="text-[18px] font-semibold text-emerald-800">+{r.added.length}</div><div className="text-[11px] text-slate-500">{c.added_by_overlays} by overlays · {c.tailored_in} tailored in</div></div>
      <div>Removed<div className="text-[18px] font-semibold text-rose-800">−{r.removed.length}</div><div className="text-[11px] text-slate-500">{c.removed_by_overlays} by overlays · {c.tailored_out} tailored out</div></div>
      <div>Final selection<div className="text-[18px] font-semibold" data-testid="select-review-final">{r.final.count.toLocaleString()}</div><div className="text-[11px] text-slate-500">{c.overlays_applied} overlay(s) · {c.parameters_set} parameter value(s) set</div></div>
    </div>
    <p className="mt-2 text-[11px] text-slate-500" data-testid="select-review-reconciliation">{r.reconciliation}</p>
    <div className="mt-2 flex gap-3 text-[12px]"><button className="underline" onClick={() => setShow(show === "added" ? "" : "added")} data-testid="select-review-show-added">{show === "added" ? "Hide" : "Show"} added</button>
      <button className="underline" onClick={() => setShow(show === "removed" ? "" : "removed")} data-testid="select-review-show-removed">{show === "removed" ? "Hide" : "Show"} removed</button></div>
    {show === "added" && list(r.added)}{show === "removed" && list(r.removed)}
    <div className="mt-3 text-[12px]" data-testid="select-review-needs"><b>Needs a decision:</b> {r.needs_decision.length ? <ul className="list-disc pl-5">{r.needs_decision.map((n: Row, i: number) => <li key={i}>{n.item} – {n.why} (step {n.step})</li>)}</ul> : "nothing – ready to submit"}</div>
    <div className="mt-3 rounded bg-slate-50 p-2 text-[12px]" data-testid="select-review-approval">Approval: {ap ? <><b>{ap.human_id}</b> · {ap.status}{ap.status === "pending" ? ` – waiting for the ${ap.assigned_role.toUpperCase()}` : ""} · <Link className="underline" to={`/reviews/${ap.id}`}>open in Reviews</Link></> : "not submitted yet"}</div>
    {canSubmit && ap?.status !== "pending" && <div className="mt-3 flex flex-wrap items-end gap-2"><label className="flex-1 text-[12px]"><span className="font-medium">Note to the ISSM / AO</span>
      <input className="input mt-1 w-full" value={why} onChange={(e) => setWhy(e.target.value)} placeholder="e.g. Moderate baseline + privacy, 2 controls tailored out with rationale" data-testid="select-submit-note" /></label>
      <button className="btn-primary" disabled={why.trim().length < 10} onClick={submit} data-testid="select-submit-approval">Submit selection for approval</button></div>}
  </Panel>;
}
