import type { QFile, QState } from "./queue";
import { STATES, TONE } from "./queue";

/** Sticky, live batch summary: totals per state (chips filter the list), overall progress, the next action. */
export function BatchSummary({ files, filter, setFilter, onNext, onImportAll, running, readyCount }: {
  files: QFile[]; filter: QState | ""; setFilter: (s: QState | "") => void; onNext: () => void; onImportAll: () => void; running: boolean; readyCount: number;
}) {
  const n = (s: QState) => files.filter((f) => f.state === s).length;
  const live = files.filter((f) => f.state !== "removed").length;
  const done = n("imported") + n("failed");
  const pct = live ? Math.round((done / live) * 100) : 0;
  const decide = n("needs_decision");
  return (
    <div className="sticky top-0 z-20 -mx-1 rounded-xl border px-3 py-2.5 shadow-sm" style={{ background: "var(--iv-surface-solid)", borderColor: "var(--iv-border-strong)" }}
      data-testid="ic-batch-summary" aria-live="polite">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12px]">
        <b data-testid="ic-batch-total">{files.length} file{files.length === 1 ? "" : "s"}</b>
        <span className="text-slate-600" data-testid="ic-batch-progress-label">{done} of {live} processed · {pct}%</span>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter files by state">
          <button type="button" onClick={() => setFilter("")} aria-pressed={!filter} data-testid="ic-chip-all"
            className={`rounded-full px-2 py-0.5 font-semibold ${!filter ? "ring-2 ring-blue-700" : ""} bg-slate-100 text-slate-800`}>All {files.length}</button>
          {STATES.map(([s, label]) => {
            const c = n(s);
            return <button key={s} type="button" disabled={!c && filter !== s} onClick={() => setFilter(filter === s ? "" : s)} aria-pressed={filter === s}
              className={`rounded-full px-2 py-0.5 font-semibold transition-opacity disabled:opacity-40 ${TONE[s]} ${filter === s ? "ring-2 ring-blue-700" : ""} ${!c && filter !== s ? "hidden sm:inline-block" : ""}`} data-testid={`ic-chip-${s}`}>
              {c} {s === "needs_decision" ? (c === 1 ? "needs your decision" : "need your decision") : label.toLowerCase()}</button>;
          })}
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          {decide > 0 && <button type="button" className="btn-secondary px-2 py-1 text-[12px]" onClick={onNext} data-testid="ic-next-decision">
            Next: review {decide} file{decide === 1 ? "" : "s"} needing a decision</button>}
          <button type="button" className="btn-primary px-2 py-1 text-[12px]" disabled={running || !readyCount} onClick={onImportAll} data-testid="ic-import-all">
            {running ? "Importing…" : `Import all ready (${readyCount})`}</button>
        </div>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label="Overall progress">
        <div className="h-full rounded-full bg-emerald-600 transition-[width] duration-500" style={{ width: `${pct}%` }} data-testid="ic-batch-progress" />
      </div>
    </div>);
}
