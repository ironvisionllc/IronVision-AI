import { useState } from "react";
import { useApi, Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { downloadFile } from "@/lib/download";

/** On-screen ODP comparison; the CSV export uses the same endpoint rows and the same filters. */
export function ParameterComparison({ sid }: { sid: string }) {
  const [f, setF] = useState<Record<string, string>>({ family: "", status: "", q: "" });
  const [page, setPage] = useState(0);
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(f).filter(([, v]) => v))).toString();
  const { data } = useApi<Row>(`/systems/${sid}/parameter-comparison?${qs}&limit=50&offset=${page * 50}`);
  const set = (k: string, v: string) => { setF({ ...f, [k]: v }); setPage(0); };
  return (
    <Panel title="Parameter comparison (organization-defined parameters)" testId="param-compare"
      actions={<button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => downloadFile(`/systems/${sid}/parameters.csv?${qs}`, "parameter-comparison.csv", "Parameter comparison")}
        data-testid="param-compare-export">Export these rows (CSV)</button>}>
      <div className="mb-2 flex flex-wrap gap-2 text-[12px]">
        <input className="input w-28" placeholder="Family (AC)" value={f.family} onChange={(e) => set("family", e.target.value)} data-testid="param-filter-family" />
        <select className="input w-64" value={f.status} onChange={(e) => set("status", e.target.value)} data-testid="param-filter-status">
          <option value="">All statuses</option>{Object.entries(data?.statuses ?? {}).map(([k, v]) => <option key={k} value={k}>{String(v)} ({data?.counts?.[k] ?? 0})</option>)}</select>
        <input className="input w-56" placeholder="Search control / parameter" value={f.q} onChange={(e) => set("q", e.target.value)} data-testid="param-filter-q" />
        <span className="self-center text-slate-600" data-testid="param-compare-total">{data?.total ?? 0} row(s)</span>
      </div>
      {data && !data.total ? <p className="rounded border border-dashed border-slate-300 p-3 text-[12px] text-slate-600" data-testid="param-compare-empty">No parameter rows match. Assign controls (baseline/overlays) or clear the filters.</p>
        : <div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr>{(data?.columns ?? []).map((c: Row) => <th key={c.key} className="th">{c.label}</th>)}</tr></thead>
          <tbody>{(data?.items ?? []).map((r: Row, i: number) => <tr key={i} data-testid={`param-row-${i}`} data-status={r.status}>{data!.columns.map((c: Row) => <td key={c.key} className="td align-top">{r[c.key] ?? "—"}</td>)}</tr>)}</tbody></table></div>}
      {data && data.total > 50 && <div className="mt-2 flex gap-2 text-[11px]"><button className="btn-secondary px-2 py-0.5" disabled={!page} onClick={() => setPage(page - 1)}>Previous</button>
        <span className="self-center">{page * 50 + 1}–{Math.min((page + 1) * 50, data.total)} of {data.total}</span>
        <button className="btn-secondary px-2 py-0.5" disabled={(page + 1) * 50 >= data.total} onClick={() => setPage(page + 1)}>Next</button></div>}
      <p className="mt-2 text-[11px] text-slate-500" data-testid="param-compare-omitted">{Object.entries(data?.omitted_columns ?? {}).map(([k, v]) => `Not shown – ${k}: ${v}`).join(" ")}</p>
    </Panel>);
}
