import { useState } from "react";
import { TableScroll } from "@/components/common/TableScroll";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { SimulatedSignatureNote } from "@/components/shell/Sandbox";

const STATUS: Record<string, string> = { draft: "Draft – awaiting approval", pending_reapproval: "Pending re-approval (inputs changed)", approved: "Approved",
  superseded: "Superseded", legacy_unreviewed: "Legacy – recorded before approvals, review and approve" };

/** Categorize · step 5 – rationale, approval by the AO (authorization.decide) and revision history. */
export function CategorizationApproval({ sid, version }: { sid: string; version: number }) {
  const { data, reload } = useApi<Row>(`/systems/${sid}/categorization/records?v=${version}`);
  const [why, setWhy] = useState("");
  const [err, setErr] = useState("");
  const cur = data?.current;
  const approve = async () => {
    try { await api.post(`/systems/${sid}/categorization/records/${cur.id}/approve`, { rationale: why }); setWhy(""); setErr(""); reload(); }
    catch (e) { setErr(errorMessage(e)); }
  };
  if (!data) return null;
  const impacts = (r: Row) => r.framework === "cnssi1253" ? `${(r.impacts?.c ?? "—")[0]}-${(r.impacts?.i ?? "—")[0]}-${(r.impacts?.a ?? "—")[0]} (kept separate)` : `${r.overall ?? "—"} (high-water mark)`;
  return (
    <Panel title="Categorization approval and history" eyebrow="Step 5 · rationale + approval" testId="cat-approval">
      {(data.review_flags ?? []).map((f: Row, i: number) => <p key={i} className="mb-2 rounded bg-amber-50 p-2 text-[11px] text-amber-900" data-testid={`cat-review-flag-${i}`}>{f.message} ({f.value})</p>)}
      {cur ? <div className="text-[12px]" data-testid="cat-current">
        <div>Revision {cur.revision}: <b data-testid="cat-current-status">{STATUS[cur.status] ?? cur.status}</b> · {cur.framework === "cnssi1253" ? "CNSSI 1253" : "FIPS 199"} · {impacts(cur)}</div>
        {cur.detail?.baseline_selection && <p className={`mt-1 rounded p-2 text-[11px] ${cur.detail.baseline_selection.startsWith("SME") ? "bg-amber-50 text-amber-900" : "bg-slate-50 text-slate-700"}`} data-testid="cat-sme-note">{cur.detail.baseline_selection}</p>}
        {data.approved && cur.status !== "approved" && <div className="mt-1 text-[11px] text-slate-600">In force until re-approved: revision {data.approved.revision}, approved by {data.approved.approved_by} on {String(data.approved.approved_at).slice(0, 10)}.</div>}
        {["draft", "pending_reapproval", "legacy_unreviewed"].includes(cur.status) && (data.can_approve
          ? <div className="mt-2 grid gap-1.5"><SimulatedSignatureNote />
            <textarea className="input" rows={2} placeholder="Approval rationale (required, min 10 characters)" value={why} onChange={(e) => setWhy(e.target.value)} data-testid="cat-approve-why" />
            {err && <div className="text-rose-700" role="alert">{err}</div>}
            <button className="btn-primary w-fit px-2 py-0.5 text-[11px]" disabled={why.trim().length < 10} onClick={approve} data-testid="cat-approve-btn">Approve categorization</button></div>
          : <p className="mt-2 text-[11px] text-slate-600" data-testid="cat-approve-locked">Approval needs the Authorizing Official (authorization decision permission).</p>)}
      </div> : <p className="text-[12px] text-slate-600">No categorization saved yet.</p>}
      <details className="mt-3 text-[11px]"><summary className="cursor-pointer text-blue-800" data-testid="cat-history-toggle">Revision history ({data.history.length})</summary>
        <TableScroll><table className="mt-1 w-full"><tbody>{data.history.map((r: Row) => <tr key={r.id}><td className="td">Rev {r.revision}</td><td className="td">{STATUS[r.status] ?? r.status}</td>
          <td className="td">{impacts(r)}</td><td className="td">{r.submitted_by}</td><td className="td">{r.approved_by ? `Approved by ${r.approved_by} – ${r.approval_rationale}` : "—"}</td></tr>)}</tbody></table></TableScroll></details>
    </Panel>);
}
