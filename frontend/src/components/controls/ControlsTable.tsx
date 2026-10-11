import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { ControlList, Family } from "@/lib/types";
import { BaselinePill, StatusPill } from "@/components/common/StatusPill";
import { ControlDetailDrawer } from "@/components/controls/ControlDetailDrawer";

const PAGE = 50;

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function ControlsTable() {
  const [q, setQ] = useState("");
  const [family, setFamily] = useState("");
  const [baseline, setBaseline] = useState("");
  const [withdrawn, setWithdrawn] = useState(false);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<ControlList | null>(null);
  const [families, setFamilies] = useState<Family[]>([]);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const dq = useDebounced(q);

  useEffect(() => {
    api.get<Family[]>("/controls/families").then((r) => setFamilies(r.data)).catch(() => setFamilies([]));
  }, []);

  useEffect(() => setOffset(0), [dq, family, baseline, withdrawn]);

  useEffect(() => {
    const params = { q: dq || undefined, family: family || undefined, baseline: baseline || undefined, include_withdrawn: withdrawn, limit: PAGE, offset };
    api.get<ControlList>("/controls", { params }).then((r) => { setData(r.data); setError(""); }).catch((e) => setError(errorMessage(e)));
  }, [dq, family, baseline, withdrawn, offset]);

  const total = data?.total ?? 0;
  return (
    <div className="panel animate-fade-up" data-testid="controls-catalog">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3">
        <div className="relative min-w-[260px] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-slate-400" aria-hidden />
          <input className="input pl-8" placeholder="Search by control ID or title (e.g. ac-2, audit)" value={q}
            onChange={(e) => setQ(e.target.value)} data-testid="controls-search-input" aria-label="Search controls" />
        </div>
        <select className="input w-auto max-w-xs" value={family} onChange={(e) => setFamily(e.target.value)} data-testid="controls-family-filter" aria-label="Family filter">
          <option value="">All families</option>
          {families.map((f) => <option key={f.family_id} value={f.family_id}>{f.family_id.toUpperCase()} – {f.family_title} ({f.count})</option>)}
        </select>
        <select className="input w-auto" value={baseline} onChange={(e) => setBaseline(e.target.value)} data-testid="controls-baseline-filter" aria-label="Baseline filter">
          <option value="">All baselines</option>
          <option value="low">Low</option>
          <option value="moderate">Moderate</option>
          <option value="high">High</option>
          <option value="privacy">Privacy</option>
        </select>
        <label className="flex items-center gap-2 text-[13px] text-slate-700">
          <input type="checkbox" checked={withdrawn} onChange={(e) => setWithdrawn(e.target.checked)} data-testid="controls-withdrawn-toggle" className="h-4 w-4 accent-blue-700" />
          Include withdrawn
        </label>
      </div>
      {error && <div className="px-4 py-3 text-sm text-rose-700" role="alert" data-testid="controls-error">{error}</div>}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse" data-testid="controls-table">
          <thead>
            <tr><th className="th w-28">ID</th><th className="th">Title</th><th className="th w-56">Family</th><th className="th w-48">Baselines</th><th className="th w-28">Type</th></tr>
          </thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.control_id} onClick={() => setOpenId(c.control_id)} data-testid={`control-row-${c.control_id}`}
                className="cursor-pointer transition-colors duration-100 hover:bg-blue-50/60">
                <td className="td font-mono text-[12px] font-semibold text-blue-800">{c.label ?? c.control_id}</td>
                <td className="td">
                  {c.is_enhancement && <span className="mr-1 text-slate-400">↳</span>}
                  <span className={c.is_withdrawn ? "text-slate-400 line-through" : "text-slate-800"}>{c.title}</span>
                </td>
                <td className="td text-[12px] text-slate-600">{c.family_id.toUpperCase()} · {c.family_title}</td>
                <td className="td"><div className="flex flex-wrap gap-1">{c.baselines.map((b) => <BaselinePill key={b} baseline={b} />)}</div></td>
                <td className="td">
                  {c.is_withdrawn ? <StatusPill tone="neutral">Withdrawn</StatusPill> : c.is_enhancement ? <StatusPill tone="info">Enhancement</StatusPill> : <StatusPill tone="primary">Base</StatusPill>}
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr><td colSpan={5} className="td py-10 text-center text-slate-500" data-testid="controls-empty">No controls match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between px-4 py-2.5 text-[12px] text-slate-600">
        <span data-testid="controls-result-count">
          {total === 0 ? "0 results" : `${(offset + 1).toLocaleString()}–${Math.min(offset + PAGE, total).toLocaleString()} of ${total.toLocaleString()}`}
        </span>
        <div className="flex gap-1">
          <button className="btn-secondary px-2 py-1" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} data-testid="controls-prev-page" aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></button>
          <button className="btn-secondary px-2 py-1" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)} data-testid="controls-next-page" aria-label="Next page"><ChevronRight className="h-4 w-4" /></button>
        </div>
      </div>
      <ControlDetailDrawer controlId={openId} onClose={() => setOpenId(null)} onNavigate={setOpenId} />
    </div>
  );
}
