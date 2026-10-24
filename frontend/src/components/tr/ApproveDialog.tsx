import { useState } from "react";
import { Modal } from "@/components/common/Modal";
import { SimulatedSignatureNote } from "@/components/shell/Sandbox";
import { api } from "@/lib/api";
import { Row } from "@/lib/useApi";

const today = () => new Date().toISOString().slice(0, 10);
const fromAssessment = (r: Row) => (r.proposed?.determination_source || "").startsWith("assessment:") && r.proposed?.tested_by && r.proposed?.date_tested;

/** SCA enters (or explicitly confirms) the ACTUAL tester and test date. Nothing defaults to the approver or today. */
export function ApproveDialog({ rows, onSubmit, onClose }: { rows: Row[]; onSubmit: (extra: Row) => void; onClose: () => void }) {
  const one = rows.length === 1 ? rows[0] : null;
  const pre = one && fromAssessment(one) ? one.proposed : null;
  const [by, setBy] = useState<string>(pre?.tested_by || "");
  const [on, setOn] = useState<string>(pre?.date_tested || "");
  const [confirm, setConfirm] = useState(false);
  const allRecorded = rows.length > 1 && rows.every(fromAssessment);
  const [mode, setMode] = useState<"batch" | "recorded">("batch");
  const myName = async () => { const me = (await api.get<Row>("/auth/me")).data; setBy(me.display_name || me.email); };
  const future = on > today();
  const ready = mode === "recorded" || (by.trim() && on && !future && (rows.length === 1 || confirm));
  const submit = () => onSubmit(mode === "recorded"
    ? { per_row: Object.fromEntries(rows.map((r) => [r.id, { tested_by: r.proposed.tested_by, date_tested: r.proposed.date_tested }])) }
    : { tested_by: by.trim(), date_tested: on });
  return (<Modal title={`Approve ${rows.length} row(s) – actual tester and test date`} onClose={onClose} testId="tr-approve-dialog">
    <div className="space-y-2 text-[13px]">
      <SimulatedSignatureNote />
      <p className="text-slate-600">eMASS “Tested By” and “Date Tested” must be the person who performed the test and when – not the approver and not today’s date by default.</p>
      {pre && <div className="rounded bg-sky-50 p-2 text-[12px] text-sky-900" data-testid="tr-approve-prefill">Prefilled from the recorded assessment ({one!.proposed.determination_source}): {pre.tested_by}, {pre.date_tested}. Confirm or change.</div>}
      {allRecorded && <div className="flex gap-3 text-[12px]"><label><input type="radio" checked={mode === "batch"} onChange={() => setMode("batch")} /> One tester and date for all</label>
        <label><input type="radio" checked={mode === "recorded"} onChange={() => setMode("recorded")} data-testid="tr-approve-use-recorded" /> Each row’s recorded assessment tester/date</label></div>}
      {mode === "batch" && <>
        <label className="block">Date tested<input type="date" className="input mt-0.5 w-full" max={today()} value={on} onChange={(e) => setOn(e.target.value)} data-testid="tr-approve-date" /></label>
        {future && <div className="text-rose-700" role="alert">Date tested cannot be in the future.</div>}
        <label className="block">Tested by<div className="mt-0.5 flex gap-1"><input className="input w-full" placeholder="e.g. Brooks, Dana" value={by} onChange={(e) => setBy(e.target.value)} data-testid="tr-approve-tester" />
          <button type="button" className="btn-secondary whitespace-nowrap" onClick={myName} data-testid="tr-approve-my-name">Use my name</button></div></label>
        {rows.length > 1 && <label className="flex items-center gap-1 text-[12px]"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} data-testid="tr-approve-confirm-batch" />
          I confirm {by || "this tester"} tested all {rows.length} rows on {on || "this date"}.</label>}
      </>}
      <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={!ready} onClick={submit} data-testid="tr-approve-submit">Approve</button></div>
    </div>
  </Modal>);
}
