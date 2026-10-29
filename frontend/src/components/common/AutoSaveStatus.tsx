import { useContext, useEffect, useState } from "react";
import { UNSAFE_NavigationContext } from "react-router-dom";
import { Modal } from "@/components/common/Modal";
import { AutoSave } from "@/lib/useAutoSave";
import { anyDirty, anyFailed, flushAll } from "@/lib/autosave";

const ago = (t: number) => { const s = Math.round((Date.now() - t) / 1000); return s < 10 ? "just now" : s < 60 ? `${s} s ago` : `${Math.round(s / 60)} min ago`; };
const show = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));

/** Status line for an auto-saved form: Saving… / Saved just now / Not saved – retry, Undo, Retry now, conflict dialog, restore prompt, on/off. */
export function AutoSaveStatus<T>({ a, testId = "autosave", manual }: { a: AutoSave<T>; testId?: string; manual?: React.ReactNode }) {
  const [, tick] = useState(0);
  useEffect(() => { const i = setInterval(() => tick((x) => x + 1), 15000); return () => clearInterval(i); }, []);
  const s = a.snap, sv = a.saver;
  const label = !s ? "" : s.state === "saving" ? "Saving…" : s.state === "pending" ? "Unsaved changes…" : s.state === "error" ? "Not saved – retry"
    : s.state === "conflict" ? "Not saved – someone else changed this" : s.state === "locked" ? "Auto-save paused" : s.state === "confirm" ? "Not saved – confirm first"
      : s.state === "invalid" ? "Not saved – check the highlighted fields" : s.savedAt ? `Saved ${ago(s.savedAt)}` : "Auto-save on";
  const bad = s && ["error", "conflict", "confirm", "invalid"].includes(s.state);
  const mine = (sv?.value || {}) as Record<string, unknown>, theirs = (s?.theirs || {}) as Record<string, unknown>;
  const keys = s?.theirs && typeof s.theirs === "object" ? Object.keys({ ...mine }).filter((k) => k in theirs && show(mine[k]) !== show(theirs[k])) : [];
  return (<div className="flex flex-wrap items-center gap-2 text-[12px]" data-testid={testId}>
    <label className="flex items-center gap-1 text-slate-600"><input type="checkbox" checked={a.on} onChange={(e) => a.setOn(e.target.checked)} data-testid={`${testId}-toggle`} />Auto-save</label>
    {!a.on && manual}
    {a.on && s && <>
      <span className={bad ? "font-semibold text-rose-700" : s.state === "locked" ? "text-amber-800" : "text-slate-600"} role="status" aria-live="polite" data-testid={`${testId}-state`}>{label}</span>
      {s.state === "error" && <span className="text-slate-500" data-testid={`${testId}-retry-info`}>(attempt {s.failures}, next in {Math.round((s.nextRetryMs || 0) / 1000)} s · kept in this browser)</span>}
      {(s.state === "error" || s.state === "invalid") && <button type="button" className="btn-secondary px-2 py-0 text-[11px]" onClick={() => sv?.retryNow()} data-testid={`${testId}-retry`}>Retry now</button>}
      {s.canUndo && ["saved", "invalid"].includes(s.state) && <button type="button" className="text-blue-800 underline" onClick={() => { const v = sv?.undo(); if (v !== undefined) a.apply(v); }} data-testid={`${testId}-undo`}>Undo</button>}
      {(s.state === "locked" || s.state === "invalid" || s.state === "error") && s.message && <span className="text-slate-600" data-testid={`${testId}-message`}>{s.message}</span>}
      {s.state === "locked" && manual}
      {s.state === "confirm" && <span className="text-amber-900" data-testid={`${testId}-sod`}>{s.message} <button type="button" className="btn-secondary ml-1 px-2 py-0 text-[11px]" onClick={() => sv?.confirmSod()} data-testid={`${testId}-sod-confirm`}>I understand – save my edit</button></span>}
      {s.restore !== null && <span className="rounded bg-amber-50 px-2 py-0.5 text-amber-900" data-testid={`${testId}-restore`}>Restore unsaved changes?
        <button type="button" className="ml-1 underline" onClick={() => { const v = sv?.acceptRestore(); if (v !== null && v !== undefined) a.apply(v); }} data-testid={`${testId}-restore-yes`}>Restore</button>
        <button type="button" className="ml-1 underline" onClick={() => sv?.discardRestore()} data-testid={`${testId}-restore-no`}>Discard</button></span>}
    </>}
    {a.on && s?.state === "conflict" && <Modal title="Someone else changed this record" onClose={() => undefined} testId={`${testId}-conflict`}>
      <p className="text-[12px] text-slate-600">Your change was not saved. Choose which version to keep – nothing is overwritten until you decide.</p>
      <table className="mt-2 w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>Field</th><th>Mine</th><th>Theirs (saved)</th></tr></thead>
        <tbody>{(keys.length ? keys : ["value"]).map((k) => <tr key={k} className="border-t border-slate-200 align-top"><td className="pr-2 font-medium">{k}</td>
          <td className="max-w-xs whitespace-pre-wrap break-words pr-2" data-testid={`${testId}-mine-${k}`}>{show(keys.length ? mine[k] : sv?.value)}</td>
          <td className="max-w-xs whitespace-pre-wrap break-words" data-testid={`${testId}-theirs-${k}`}>{show(keys.length ? theirs[k] : s.theirs)}</td></tr>)}</tbody></table>
      <div className="mt-3 flex gap-2"><button type="button" className="btn-primary" onClick={() => sv?.keepMine()} data-testid={`${testId}-keep-mine`}>Keep mine</button>
        <button type="button" className="btn-secondary" onClick={() => { const v = sv?.useTheirs(); if (v !== null && v !== undefined) a.apply(v); }} data-testid={`${testId}-use-theirs`}>Use theirs</button></div>
    </Modal>}
  </div>);
}

/** App-wide: Ctrl/Cmd+S saves now, beforeunload + in-app navigation guard while changes are unsaved or failed. */
export function AutoSaveGuard() {
  const { navigator } = useContext(UNSAFE_NavigationContext);
  useEffect(() => {  // every in-app route change (links and navigate()) goes through navigator.push/replace
    const nav = navigator as unknown as { push: (...a: unknown[]) => void; replace: (...a: unknown[]) => void };
    const push = nav.push, replace = nav.replace;
    const guard = (orig: (...a: unknown[]) => void) => (...a: unknown[]) => {
      if (anyFailed() && !window.confirm("Some changes are not saved. Leave this page anyway? They stay in this browser and are offered again when you come back.")) return;
      if (anyDirty()) void flushAll();
      orig.apply(navigator, a);
    };
    nav.push = guard(push); nav.replace = guard(replace);
    return () => { nav.push = push; nav.replace = replace; };
  }, [navigator]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); void flushAll(); } };
    const unload = (e: BeforeUnloadEvent) => { if (anyDirty()) { void flushAll(); e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("keydown", key); window.addEventListener("beforeunload", unload);
    return () => { window.removeEventListener("keydown", key); window.removeEventListener("beforeunload", unload); };
  }, []);
  return null;
}
