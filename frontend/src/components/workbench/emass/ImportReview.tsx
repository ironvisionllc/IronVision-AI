import { useState } from "react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";

const val = (v: unknown) => (v === null || v === undefined || v === "" ? <span className="text-slate-400">(empty)</span> : String(v).length > 160 ? `${String(v).slice(0, 160)}…` : String(v));
const ORDER = ["System details", "Categorization", "Roles", "Controls", "SLCM", "PPSM", "Test Results", "POA&M", "Inventory"];
const tid = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-");

/** Unified review: sections → items → fields (current vs imported). Accept/reject per field, item or section; nothing saved until Apply. */
export function ImportReview({ imp, onChange }: { imp: Row; onChange: (d: Row) => void }) {
  const [showSame, setShowSame] = useState(false);
  const [busy, setBusy] = useState(false);
  const open = imp.status === "review";
  const labels: Row = imp.labels || {};
  const send = async (body: Row) => {
    setBusy(true);
    try { const r = await api.put<Row>(`/emass-imports/${imp.id}/decisions`, body); onChange(r.data); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };
  const dec = (items: Row[], field: string, decision: string | null) => send({ decisions: items.map((i) => ({ key: i.key, field, decision })) });
  const ok = (f: Row) => f.change && !f.error && !f.blocked;
  const sections = ORDER.filter((s) => (imp.items || []).some((i: Row) => (i.section || "Controls") === s));
  return (
    <Panel title="Review imported values" testId="emass-import-review" actions={open && imp.can_apply && <div className="flex gap-2">
      <button className="btn-secondary" disabled={busy} onClick={() => send({ bulk: "use_imported" })} data-testid="import-use-imported-all">Use imported everywhere</button>
      <button className="btn-secondary" disabled={busy} onClick={() => send({ bulk: "keep_existing" })} data-testid="import-keep-existing-all">Keep existing everywhere</button>
      <button className="btn-secondary" disabled={busy} onClick={() => send({ bulk: "accept_safe" })} data-testid="import-accept-safe">Accept all conflict-free changes</button>
      <button className="btn-secondary" disabled={busy} onClick={() => send({ bulk: "reject_all" })} data-testid="import-reject-all">Reject all</button>
      <button className="btn-secondary" disabled={busy} onClick={() => send({ bulk: "reset" })} data-testid="import-reset">Reset</button></div>}>
      <label className="mb-3 flex items-center gap-2 text-[12px]"><input type="checkbox" checked={showSame} onChange={(e) => setShowSame(e.target.checked)} data-testid="import-show-unchanged" />Show unchanged fields</label>
      {sections.map((sec) => {
        const all: Row[] = (imp.items || []).filter((i: Row) => (i.section || "Controls") === sec);
        const items = all.filter((i) => showSame || i.create || Object.values(i.fields).some((f: any) => f.change || f.error));
        const ro = !open || !(imp.allowed_sections || []).includes(sec);
        return (
          <section key={sec} className="mb-5" data-testid={`import-section-${tid(sec)}`}>
            <div className="mb-2 flex items-center gap-3"><h3 className="text-[13px] font-semibold">{sec}</h3><span className="text-[11px] text-slate-500">{all.length} item(s)</span>
              {ro && open && <span className="rounded bg-amber-50 px-1.5 text-[11px] text-amber-900" data-testid={`import-section-readonly-${tid(sec)}`}>Read-only: {imp.read_only_sections?.[sec]}</span>}
              {!ro && <span className="ml-auto flex gap-2 text-[12px]"><button className="underline" onClick={() => send({ bulk: "use_imported", section: sec })} data-testid={`import-accept-section-${tid(sec)}`}>Use imported (section)</button>
                <button className="underline" onClick={() => send({ bulk: "keep_existing", section: sec })} data-testid={`import-reject-section-${tid(sec)}`}>Keep existing (section)</button></span>}</div>
            <div className="space-y-2">{items.map((i) => {
              const fs = Object.entries(i.fields as Row).filter(([, f]: [string, any]) => showSame || f.change || f.error);
              return (
                <div key={i.key} className="rounded border border-slate-200" data-testid={`import-item-${tid(i.key)}`}>
                  <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 bg-slate-50 px-3 py-1.5 text-[12px]">
                    <b>{i.label}</b>{i.row && <span className="text-slate-500">row {i.row}</span>}
                    {i.create && <span className="rounded bg-emerald-50 px-1.5 text-emerald-800" data-testid={`import-will-create-${tid(i.key)}`}>will be created</span>}
                    {i.required_issue && <span className="rounded bg-rose-50 px-1.5 text-rose-800" data-testid={`import-required-${tid(i.key)}`}>{i.required_issue} – flagged, not saved</span>}
                    {i.note && <span className="text-slate-600" data-testid={`import-note-${tid(i.key)}`}>{i.note}</span>}
                    {!ro && <span className="ml-auto flex gap-2"><button className="underline" onClick={() => dec([i], "*", "accept")} data-testid={`import-accept-item-${tid(i.key)}`}>Accept item</button>
                      <button className="underline" onClick={() => dec([i], "*", "reject")} data-testid={`import-reject-item-${tid(i.key)}`}>Reject item</button></span>}
                  </div>
                  <table className="w-full text-[12px]"><tbody>{fs.map(([k, f]: [string, any]) => (
                    <tr key={k} className={f.error ? "bg-rose-50/60" : f.blocked ? "bg-amber-50/60" : f.change ? "bg-blue-50/50" : ""} data-testid={`import-field-${tid(i.key)}-${k}`}>
                      <td className="w-52 px-3 py-1 font-medium">{f.label || labels[k] || k}
                        {f.src?.sheet && <div className="text-[10px] font-normal text-slate-500" data-testid={`import-src-${tid(i.key)}-${k}`}>{f.src.sheet}{f.src.row ? ` · row ${f.src.row}` : ""}{f.src.col ? ` · col ${f.src.col}` : ""}</div>}
                        {f.ai && <div className="text-[10px] font-normal text-violet-800" data-testid={`import-ai-${tid(i.key)}-${k}`}>AI-suggested column ({f.ai.confidence}): {f.ai.reason} – review</div>}</td>
                      <td className="w-1/3 px-3 py-1 text-slate-600">{val(Array.isArray(f.current) ? f.current.join(", ") : f.current)}</td>
                      <td className={`w-1/3 px-3 py-1 ${f.change ? "font-semibold text-blue-900" : ""}`}>{val(Array.isArray(f.imported) ? f.imported.join(", ") : f.imported)}
                        {f.error && <div className="text-rose-700" data-testid={`import-error-${tid(i.key)}-${k}`}>{f.error}</div>}
                        {f.blocked && <div className="text-amber-800" data-testid={`import-blocked-${tid(i.key)}-${k}`}>{f.blocked}</div>}</td>
                      <td className="w-44 px-3 py-1 text-right">{ok(f) ? (ro ? <span>{f.decision || "undecided"}</span> : <span className="flex justify-end gap-1">
                        <button className={`rounded px-2 py-0.5 ${f.decision === "accept" ? "bg-emerald-700 text-white" : "border border-slate-300"}`} onClick={() => dec([i], k, f.decision === "accept" ? null : "accept")} data-testid={`import-accept-${tid(i.key)}-${k}`}>Use imported</button>
                        <button className={`rounded px-2 py-0.5 ${f.decision === "reject" ? "bg-slate-700 text-white" : "border border-slate-300"}`} onClick={() => dec([i], k, f.decision === "reject" ? null : "reject")} data-testid={`import-reject-${tid(i.key)}-${k}`}>Keep existing</button></span>)
                        : !f.error && !f.blocked && <span className="text-slate-400">unchanged</span>}</td>
                    </tr>))}</tbody></table>
                </div>);
            })}</div>
          </section>);
      })}
      {!sections.length && <p className="text-[12px] text-slate-500" data-testid="import-no-changes">Nothing to review.</p>}
    </Panel>);
}
