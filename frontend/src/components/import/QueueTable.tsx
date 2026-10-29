import { useState } from "react";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import type { Row } from "@/lib/useApi";
import type { QFile } from "./queue";
import { LABEL, removable, TONE } from "./queue";

function DecisionBox({ f, onResolve }: { f: QFile; onResolve: (value: string, all: boolean) => void }) {
  const d = f.decision!;
  const [v, setV] = useState("");  // explicit choice required (e.g. never default to an AI-spending option)
  const [all, setAll] = useState(false);
  return (
    <div className="mt-1 rounded border border-amber-300 bg-amber-50 p-2 text-[12px] text-amber-950" data-testid={`ic-decision-${f.key}`}>
      <div>{d.prompt}</div>
      {!!d.options.length && <div className="mt-1 flex flex-wrap items-center gap-2">
        <select className="input w-auto max-w-[18rem]" value={v} onChange={(e) => setV(e.target.value)} data-testid={`ic-decision-select-${f.key}`}>
          <option value="" disabled>Choose…</option>{d.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
        {d.batchSafe && <label className="flex items-center gap-1"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} data-testid={`ic-decision-all-${f.key}`} />
          Apply the same choice to all files with this question</label>}
        <button type="button" className="btn-primary px-2 py-0.5 text-[12px]" disabled={!v} onClick={() => onResolve(v, all)} data-testid={`ic-decision-apply-${f.key}`}>Continue</button>
      </div>}
    </div>);
}

export function QueueTable({ files, types, sid, sel, setSel, onType, onImport, onRemove, onResolve, busy }: {
  files: QFile[]; types: Row; sid: string; sel: string[]; setSel: (k: string[]) => void; onType: (k: string, t: string) => void; onImport: (k: string) => void;
  onRemove: (keys: string[]) => void; onResolve: (k: string, v: string, all: boolean) => void; busy: boolean;
}) {
  const toggle = (k: string) => setSel(sel.includes(k) ? sel.filter((x) => x !== k) : [...sel, k]);
  const pickable = files.filter(removable).map((f) => f.key);
  return (
    <div className="mt-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
        <label className="flex items-center gap-1"><input type="checkbox" checked={!!pickable.length && pickable.every((k) => sel.includes(k))}
          onChange={(e) => setSel(e.target.checked ? pickable : [])} data-testid="ic-select-all" />Select all removable</label>
        <button type="button" className="btn-secondary px-2 py-0.5 text-[12px]" disabled={!sel.length || busy} onClick={() => onRemove(sel)} data-testid="ic-remove-selected">Remove selected ({sel.length})</button>
        <button type="button" className="btn-ghost px-2 py-0.5 text-[12px] text-rose-700" disabled={!pickable.length || busy} onClick={() => onRemove(pickable)} data-testid="ic-clear-all">Clear all</button>
        <span className="text-slate-500">Removing deletes the uploaded file before anything is applied. Applied data is managed from Import history.</span>
      </div>
      <div className="space-y-2" style={{ scrollMarginTop: "14rem" }} data-testid="ic-files">
        {files.map((f) => {
          const t = types[f.type];
          const d = f.det || {};
          return (
            <div key={f.key} className={`rounded-lg border p-2 text-[12px] ${f.state === "removed" ? "opacity-60" : ""}`} style={{ borderColor: "var(--iv-border)" }} data-testid={`ic-file-${f.key}`}>
              <div className="flex flex-wrap items-start gap-2">
                <input type="checkbox" className="mt-1" disabled={!removable(f)} checked={sel.includes(f.key)} onChange={() => toggle(f.key)} aria-label={`Select ${f.file.name}`} data-testid={`ic-select-${f.key}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <b className="break-all">{f.file.name}</b>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${TONE[f.state]}`} data-testid={`ic-state-${f.key}`}>{LABEL[f.state]}{f.state === "imported" ? (f.emassId ? " – in review" : " – processing") : ""}</span>
                    {d.record_count != null && <span className="text-slate-500" data-testid={`ic-count-${f.key}`}>{d.record_count} record(s)</span>}
                    {d.confidence && d.confidence !== "none" && <span className="text-slate-500" data-testid={`ic-confidence-${f.key}`}>confidence {d.confidence}</span>}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2 text-slate-600">
                    {["ready", "needs_decision"].includes(f.state) && f.type && f.decision?.kind !== "type" ? (
                      <select className="input w-auto max-w-[16rem]" value={f.type} onChange={(e) => onType(f.key, e.target.value)} data-testid={`ic-type-${f.key}`}>
                        {Object.values(types).map((x: Row) => <option key={x.key} value={x.key} disabled={!x.allowed}>{x.label}{x.allowed ? "" : " (not permitted)"}</option>)}</select>)
                      : t && <span>{t.label}</span>}
                    {t && <span>→ <b>{t.step}</b> · {t.dest}</span>}
                  </div>
                  {f.decision && f.state === "needs_decision" && <DecisionBox f={f} onResolve={(v, all) => onResolve(f.key, v, all)} />}
                  {f.error && <div className="mt-1 text-rose-700" data-testid={`ic-error-${f.key}`}>{f.error}</div>}
                  {f.res?.link && <div className="mt-1" data-testid={`ic-result-${f.key}`}>{f.res.note} · <Link className="text-blue-800 underline" to={f.res.link} data-testid={`ic-open-${f.key}`}>Open review / results</Link>
                    <div className="mt-0.5 text-slate-600" data-testid={`ic-next-${f.key}`}>{f.emassId ? "Sent to review – nothing applied yet. Next: open the review, exclude rows you don't want, then apply." : "Sent – processing is queued; results appear in the linked run."}</div></div>}
                  {f.res?.preview && !!f.res.preview.counts?.accepted && <button type="button" className="mt-1 underline" data-testid={`ic-plan-import-${f.key}`} onClick={async () => {
                    const fd = new FormData(); fd.append("file", f.file);
                    try { const r = (await api.post<Row>(`/systems/${sid}/tr/test-plan/import`, fd)).data; toast.success(`Imported ${r.counts?.imported ?? r.counts?.accepted ?? ""} procedure(s)`); }
                    catch (e) { toast.error(errorMessage(e)); } }}>Import accepted procedures</button>}
                </div>
                <div className="flex items-center gap-1">
                  {f.state === "ready" && <button type="button" className="btn-primary px-2 py-0.5 text-[12px]" disabled={busy} onClick={() => onImport(f.key)} data-testid={`ic-import-${f.key}`}>Import</button>}
                  {removable(f) && <button type="button" className="rounded p-1 text-slate-500 hover:bg-rose-50 hover:text-rose-700" onClick={() => onRemove([f.key])}
                    aria-label={`Remove ${f.file.name}`} title="Remove before import" data-testid={`ic-remove-${f.key}`}><X className="h-4 w-4" /></button>}
                </div>
              </div>
            </div>);
        })}
      </div>
    </div>);
}
