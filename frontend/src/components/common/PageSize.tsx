import { useState } from "react";
import { useAuth } from "@/context/AuthContext";

export const PAGE_SIZES = [50, 100, 250, 0];

/** Page size per table, remembered per user (localStorage). 0 = All. */
export function usePageSize(table: string, fallback = 50): [number, (n: number) => void] {
  const { user } = useAuth();
  const key = `iv.pagesize.${user ? user.id : "anon"}.${table}`;
  const [n, setN] = useState<number>(() => { const v = localStorage.getItem(key); return v === null ? fallback : Number(v); });
  return [n, (v: number) => { localStorage.setItem(key, String(v)); setN(v); }];
}

export function PageSizeSelect({ value, onChange, testId }: { value: number; onChange: (n: number) => void; testId: string }) {
  return (
    <label className="flex items-center gap-1 whitespace-nowrap text-[12px] text-slate-600" title="Rows per page – remembered for you on this table">Rows
      <select className="input w-auto py-0.5 text-[12px]" value={value} onChange={(e) => onChange(Number(e.target.value))} data-testid={testId}>
        {PAGE_SIZES.map((s) => <option key={s} value={s}>{s === 0 ? "All" : s}</option>)}</select></label>);
}

export function Pager({ total, size, page, setPage, testId }: { total: number; size: number; page: number; setPage: (p: number) => void; testId: string }) {
  if (!size || total <= size) return null;
  const last = Math.ceil(total / size) - 1;
  return (
    <span className="flex items-center gap-1 text-[12px]" data-testid={testId}>
      <button className="btn-secondary px-2 py-0.5" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Previous page">‹</button>
      <span>{page * size + 1}–{Math.min((page + 1) * size, total)} of {total.toLocaleString()}</span>
      <button className="btn-secondary px-2 py-0.5" disabled={page >= last} onClick={() => setPage(page + 1)} aria-label="Next page">›</button>
    </span>);
}
