import { useEffect, useState } from "react";
import { TableScroll } from "@/components/common/TableScroll";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { useAuth } from "@/context/AuthContext";
import { Panel } from "@/components/common/Panel";
import { showNextStep } from "@/components/common/NextStep";
import { PageSizeSelect, Pager, usePageSize } from "@/components/common/PageSize";
import { SideBySideReview } from "@/components/controls/SideBySideReview";
import { BulkJobProgress } from "@/components/evidence/BulkJobProgress";

const KIND: Record<string, string> = { policy_status: "Policy coverage → status", status: "Status suggestion", policy_map: "Policy → control", finding_map: "STIG rule → control" };
const fmt = (c: string) => c.toUpperCase().replace(/\.(\d+)$/, "($1)");
const SCA_MSG = "Implementation set to Implemented. Assessment status needs SCA confirmation";

/** Unified review queue: approve / reject / edit, one at a time or in bulk, with one shared justification. */
const APPROVER = "ISSO or ISSM";

/** Low-confidence policy coverage: shown for review, never turned into a status suggestion. */
function ReviewNeeded({ items }: { items: Row[] }) {
  if (!items.length) return null;
  return (<div className="mb-3 rounded border border-amber-200 bg-amber-50 p-2 text-[12px] text-amber-900" data-testid="queue-review-needed">
    <b>Review needed ({items.length})</b> – low-confidence policy matches. No status is suggested until someone checks the coverage.
    <ul className="mt-1 list-disc pl-5">{items.map((r) => <li key={`${r.policy_id}-${r.control_id}`}><Link className="underline" to={`/policy-auditor/${r.policy_id}`}>{r.message}</Link> <span className="text-[11px]">({r.policy})</span></li>)}</ul></div>);
}

/** Why a mapped control has no status suggestion (mapping still proposed, already at that status, low confidence …). */
function StatusNotes({ notes }: { notes: string[] }) {
  if (!notes.length) return null;
  return (<details className="mb-3 rounded border border-slate-200 bg-slate-50 p-2 text-[12px] text-slate-700" data-testid="queue-status-notes">
    <summary className="cursor-pointer font-medium">Why some policy-mapped controls have no status suggestion ({notes.length})</summary>
    <ul className="mt-1 list-disc pl-5">{notes.map((n) => <li key={n}>{n}</li>)}</ul></details>);
}

export function ReviewQueue({ sid, queue, counts, canMap, reload, setMsg, reviewNeeded = [], statusNotes = [] }: { sid: string; queue: Row[]; counts: Row; canMap: boolean; reload: () => void; setMsg: (m: string) => void; reviewNeeded?: Row[]; statusNotes?: string[] }) {
  const { can } = useAuth();
  const canApprove = (q: Row) => q.awaiting_sca ? can("assessment.perform") : canMap && (!["status", "policy_status"].includes(q.kind) || can("implementation.write"));
  const denyWhy = `Approving needs the ${APPROVER} role – your current role can view this item but not approve it.`;
  const [sel, setSel] = useState<string[]>([]);
  const [sbs, setSbs] = useState<{ p: string; c: string } | null>(null);
  const [kind, setKind] = useState(() => new URLSearchParams(window.location.search).get("tab") || "");
  const [just, setJust] = useState("");
  const [editTo, setEditTo] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [size, setSize] = usePageSize("mapping-review");
  const [page, setPage] = useState(0);
  const waiting = queue.filter((q) => q.awaiting_sca);
  const open = queue.filter((q) => !q.awaiting_sca);
  const all = kind === "sca" ? waiting : open.filter((q) => !kind || q.kind === kind);
  const rows = size ? all.slice(page * size, page * size + size) : all;
  useEffect(() => setPage(0), [kind, size, queue.length]);
  const toggle = (k: string) => { setAllMatching(false); setSel(sel.includes(k) ? sel.filter((x) => x !== k) : [...sel, k]); };
  const [allMatching, setAllMatching] = useState(false);
  const [job, setJob] = useState<Row | null>(null);
  const bulk = async (action: string, keys: string[] | null) => {
    setBusy(true);
    try {
      const r = await api.post<Row>("/mapping-review/bulk-jobs", { system_id: sid, action, justification: just, edit_control_ids: editTo.split(/[,\s]+/).filter(Boolean),
        item_keys: keys, kind: kind === "sca" ? "" : kind, awaiting_sca: kind === "sca", idempotency_key: crypto.randomUUID() });
      setJob(r.data); setSel([]); setAllMatching(false);
    } catch (e) { setErr(`Nothing was changed: ${errorMessage(e)}`); } finally { setBusy(false); }
  };
  const decide = async (action: string, keys: string[]) => {
    setErr("");
    if (action !== "approve" && just.trim().length < 10) { setErr("Write a reason (at least 10 characters) in the box above – it is required to reject or edit and is kept in the audit history."); return; }
    if (action === "edit" && !editTo.trim()) { setErr("Enter the control(s) the mapping should point to instead, e.g. AC-17(2)."); return; }
    if (allMatching || keys.length > 50) { await bulk(action, allMatching ? null : keys); return; }
    const items = queue.filter((q) => keys.includes(q.key)).map((q) => ({ kind: q.kind, ids: q.ids, control_id: q.control_id, evidence_fp: q.evidence_fp }));
    setBusy(true);
    try {
      const r = await api.post<Row>("/mapping-review/decide", { system_id: sid, items, action, justification: just, edit_control_ids: editTo.split(/[,\s]+/).filter(Boolean) });
      const n = r.data.approved + r.data.rejected + r.data.edited;
      const part = r.data.partial.length ? ` ${SCA_MSG} (${r.data.partial.map(fmt).join(", ")}) – they moved to “Awaiting assessor (SCA)”.` : "";
      const also = (r.data.also_approved || []).length ? ` Also approved: ${r.data.also_approved.join("; ")}.` : "";
      setMsg(`${n} item(s) ${action === "approve" ? "approved" : action === "reject" ? "rejected" : "edited"}.${part}${also}`);
      if (also) toast.success(`Also approved: ${r.data.also_approved.join("; ")}`, { duration: 10000 });
      if (r.data.partial.length) showNextStep({ message: `${SCA_MSG}.`, label: "SCA: confirm the assessment result in “Awaiting assessor (SCA)”", to: `/mapping-review?tab=sca` });
      else showNextStep({ message: `${n} review item(s) ${action}d.`, label: "review the updated controls in the Workbench", to: `/systems/${sid}/controls` });
      setSel([]); setJust(""); setEditTo(""); reload();
    } catch (e) { setErr(`Nothing was changed: ${errorMessage(e)}`); } finally { setBusy(false); }
  };
  const tabs: [string, string][] = [["", `All open (${open.length})`], ["status", `Status suggestions (${open.filter((q) => q.kind === "status").length})`], ["policy_status", `Policy coverage (${open.filter((q) => q.kind === "policy_status").length})`], ["policy_map", `Policy mappings (${counts.policy_map})`],
    ["finding_map", `STIG mappings (${counts.finding_map})`], ["sca", `Awaiting assessor (SCA) (${waiting.length})`]];
  return (
    <>{sbs && <SideBySideReview policyId={sbs.p} controlId={sbs.c} canDecide={canMap} onClose={() => setSbs(null)} onChanged={reload} />}
    <Panel title={`Review queue (${open.length} open${waiting.length ? `, ${waiting.length} awaiting SCA` : ""})`} className="mb-5" testId="review-queue">
      <ReviewNeeded items={reviewNeeded} />
      <StatusNotes notes={statusNotes} />
      {!canMap && open.length > 0 && <div className="mb-2 rounded bg-slate-100 p-2 text-[12px] text-slate-700" role="note" data-testid="queue-view-only">You can view these items. {denyWhy}</div>}
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
        {tabs.map(([k, l]) => <button key={k} className={`rounded px-2 py-0.5 ${kind === k ? "bg-brand-700 text-white" : k === "sca" && waiting.length ? "bg-amber-100 text-amber-900" : "bg-slate-100"}`} onClick={() => setKind(k)} data-testid={`queue-tab-${k || "all"}`}>{l}</button>)}
        <span className="ml-auto"><PageSizeSelect value={size} onChange={setSize} testId="queue-page-size" /></span>
      </div>
      {kind === "sca" && <div className="mb-2 rounded bg-amber-50 p-2 text-[12px] text-amber-900" data-testid="queue-sca-explainer">
        These were approved: implementation is already <b>Implemented</b>. Only the assessor (SCA) can confirm the assessment result (separation of duties).
        {can("assessment.perform") ? " Select them and press Approve to set Assessment → Satisfied." : " Ask your SCA to open this tab, or switch role to SCA in a sandbox."}</div>}
      {all.length === 0 ? <div className="text-[13px] text-slate-600" data-testid="queue-empty">{kind === "sca" ? "Nothing is waiting for the assessor." : <>Nothing to review. New items appear here after you upload STIG/scan results or a policy. <Link className="text-blue-800 underline" to="/evidence-sources">Upload evidence →</Link></>}</div> : <>
        {job && <BulkJobProgress job={job} onDone={reload} onRetry={setJob} />}
        {(canMap || (kind === "sca" && can("assessment.perform"))) && <div className="mb-3 rounded bg-slate-50 p-2" data-testid="queue-bulk-bar">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-[12px]"><input type="checkbox" checked={rows.length > 0 && rows.every((r) => sel.includes(r.key))} onChange={(e) => { setAllMatching(false); setSel(e.target.checked ? rows.map((r) => r.key) : []); }} data-testid="queue-select-all" /> Select all shown</label>
            {all.length > rows.length || all.length > 50 ? <button className={`rounded px-2 py-0.5 text-[12px] ${allMatching ? "bg-brand-700 text-white" : "bg-white underline"}`} onClick={() => { setAllMatching(!allMatching); setSel([]); }} data-testid="queue-select-all-matching"
              title="Selects every item matching this tab on the server – not only the rows loaded on this page">{allMatching ? `All ${all.length} matching selected (server-side)` : `Select all ${all.length} matching`}</button> : null}
            <span className="text-[12px] text-slate-600" data-testid="queue-selected-count">{allMatching ? `${all.length} selected (all matching this tab)` : `${sel.length} selected`}</span>
            <button className="btn-primary px-2 py-0.5 text-[12px]" disabled={(!sel.length && !allMatching) || busy || (!!job && !["succeeded", "failed"].includes(job.status))} onClick={() => decide("approve", sel)} data-testid="queue-bulk-approve">Approve selected</button>
            <button className="btn-secondary px-2 py-0.5 text-[12px]" disabled={(!sel.length && !allMatching) || busy} onClick={() => decide("reject", sel)} data-testid="queue-bulk-reject">Reject selected</button>
            <input className="input w-40" placeholder="Edit to control, e.g. AC-17(2)" value={editTo} onChange={(e) => setEditTo(e.target.value)} data-testid="queue-edit-to" />
            <button className="btn-secondary px-2 py-0.5 text-[12px]" disabled={!sel.length || busy} onClick={() => decide("edit", sel)} data-testid="queue-bulk-edit" title="Replace the suggested control with the one you enter (reason required)">Edit selected</button>
          </div>
          <input className="input mt-2" placeholder="Reason / justification – shared by all selected items (required to reject or edit)" value={just} onChange={(e) => setJust(e.target.value)} data-testid="queue-justification" />
          {err && <div className="mt-1 text-[12px] text-rose-700" role="alert" data-testid="queue-error">{err}</div>}
        </div>}
        <TableScroll><table className="w-full text-[12px]"><thead><tr className="text-left text-[11px] text-slate-500"><th /><th>Type</th><th>Control</th><th>What was found</th><th>Why it was suggested</th><th>Evidence</th><th /></tr></thead><tbody>
          {rows.map((q) => <tr key={q.key} className="border-t border-slate-100 align-top [content-visibility:auto]" data-testid={`queue-item-${q.key}`}>
            <td className="py-1"><input type="checkbox" disabled={!canApprove(q)} checked={sel.includes(q.key)} onChange={() => toggle(q.key)} title={canApprove(q) ? "" : denyWhy} data-testid={`queue-check-${q.key}`} /></td>
            <td className="py-1 whitespace-nowrap">{KIND[q.kind]}{q.awaiting_sca && <div className="text-[10px] font-medium text-amber-800">awaiting SCA</div>}</td><td className="py-1 font-mono font-semibold">{fmt(q.control_id)}</td>
            <td className="py-1">{q.downgrade && <div className="text-[10px] font-semibold uppercase text-rose-700" data-testid={`queue-downgrade-${q.key}`}>Downgrade suggested – policy gap</div>}
              {q.policy_id ? <Link className="text-blue-800 underline" to={`/policy-auditor/${q.policy_id}`}>{q.title}</Link> : q.title}
              {q.kind === "policy_map" && q.policy_id && <button className="ml-1 text-[11px] text-blue-800 underline" onClick={() => setSbs({ p: q.policy_id, c: q.control_id })} data-testid={`queue-sbs-${q.key}`}>Review side by side</button>}
              {q.mapping_note && <div className="text-[10px] text-blue-800" data-testid={`queue-mapping-note-${q.key}`}>{q.mapping_note}</div>}
              {q.why_new && <div className="text-[10px] font-medium text-amber-800" data-testid={`queue-why-new-${q.key}`}>{q.why_new}</div>}
              {q.next_actor && <div className="text-[10px] text-slate-600" data-testid={`queue-next-actor-${q.key}`}>Next: {q.next_actor}</div>}
              {(q.tech_needed || []).length > 0 && <div className="text-[10px] text-amber-800" data-testid={`queue-tech-needed-${q.key}`}>Policy alone cannot prove these – technical evidence (scan/STIG/config) still needed: {q.tech_needed.slice(0, 4).join(", ")}{q.tech_needed.length > 4 ? "…" : ""}</div>}{q.coverage && <div className="text-[10px] text-slate-600" data-testid={`queue-coverage-${q.key}`}>{q.coverage.met} of {q.coverage.total} requirements met{q.coverage.gaps.length ? ` – missing: ${q.coverage.gaps.join("; ")}` : ""}</div>}{q.current && <div className="text-[10px] text-slate-500">now: {q.current.implementation.replace(/_/g, " ")} · {q.current.assessment.replace(/_/g, " ")}</div>}</td>
            <td className="max-w-[320px] py-1 text-[11px] text-slate-600">{q.source}: {q.reasoning}{(q.snippets || []).slice(0, 1).map((s: string) => <div key={s}>“{s}”</div>)}</td>
            <td className="py-1 text-[11px]">{(q.evidence || []).map((e: Row) => <div key={e.id}><Link className="text-blue-800 underline" to={`/evidence-ledger?evidence=${e.id}`}>{e.file_name}</Link></div>)}</td>
            <td className="py-1"><button className="btn-primary px-2 py-0.5 text-[11px] disabled:cursor-not-allowed disabled:opacity-50" disabled={busy || !canApprove(q)} title={canApprove(q) ? "" : denyWhy} onClick={() => decide("approve", [q.key])} data-testid={`queue-approve-${q.key}`}>Approve</button>
              {!canApprove(q) && <div className="mt-0.5 max-w-[140px] text-[10px] text-slate-600" data-testid={`queue-approve-denied-${q.key}`}>Needs {APPROVER}</div>}</td></tr>)}
        </tbody></table></TableScroll>
        <div className="mt-2 flex justify-end"><Pager size={size} page={page} total={all.length} setPage={setPage} testId="queue-pager" /></div></>}
    </Panel></>);
}
