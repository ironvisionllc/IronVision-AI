import { Link, useSearchParams } from "react-router-dom";
import { Row, useApi } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { usePaged } from "@/components/common/PageSize";
import { useActiveSystemId } from "@/components/rmf/Stepper";
import { downloadFile } from "@/lib/download";
import { CCI_TIP, CovBadge } from "@/components/policy/Coverage";

const KEYS = ["mapped", "coverage", "policy", "control", "family", "q"];
const fmt = (c: string) => c.toUpperCase().replace(/\.(\d+)$/, "($1)");

/** CCI view: every DISA CCI of the system's assigned controls with policy coverage; filters live in the URL. */
export default function CciPage() {
  const sid = useActiveSystemId();
  const [params, setParams] = useSearchParams();
  const f = Object.fromEntries(KEYS.filter((k) => params.get(k)).map((k) => [k, params.get(k) as string]));
  const { data } = useApi<Row>(sid ? `/systems/${sid}/ccis` : null, f);
  const { data: facets } = useApi<Row>(sid ? `/systems/${sid}/workbench/policy-facets` : null);
  const pg = usePaged<Row>("ccis", data?.items);
  const set = (k: string, v: string) => setParams((prev) => { const p = new URLSearchParams(prev); if (v) p.set(k, v); else p.delete(k); return p; }, { replace: true });
  if (!sid) return <div className="panel p-4 text-[13px]">Pick a system in the header first – the CCI view lists the CCIs of that system's controls.</div>;
  const qs = new URLSearchParams({ ...f, fmt: "csv" }).toString();
  return (
    <div data-testid="cci-page">
      <PageHeader title="CCI view" subtitle="Each DISA CCI of this system's assigned controls, with whether a policy covers it (MET / PARTIAL / MISSING) and the matched text.">
        <button className="btn-secondary" onClick={() => downloadFile(`/systems/${sid}/ccis?${qs}`, "ccis.csv", "CCI list")} data-testid="cci-export">Export CSV (current filters)</button>
      </PageHeader>
      <Panel testId="cci-panel" title="CCIs" actions={<span className="flex items-center gap-2"><span className="text-[11px] text-slate-500" title={CCI_TIP} data-testid="cci-tip">What is a CCI? ⓘ</span>{pg.select}</span>}>
        <div className="mb-2 grid grid-cols-2 gap-2 md:grid-cols-6" data-testid="cci-filters">
          <select className="input" value={f.mapped || ""} onChange={(e) => set("mapped", e.target.value)} data-testid="cci-filter-mapped"><option value="">Mapped: all</option><option value="yes">Mapped to a policy</option><option value="no">Not mapped</option></select>
          <select className="input" value={f.coverage || ""} onChange={(e) => set("coverage", e.target.value)} data-testid="cci-filter-coverage"><option value="">Coverage: all</option>{["met", "partial", "missing"].map((v) => <option key={v} value={v}>{v.toUpperCase()}</option>)}</select>
          <select className="input" value={f.policy || ""} onChange={(e) => set("policy", e.target.value)} data-testid="cci-filter-policy"><option value="">Policy: all</option>{(facets?.policy || []).map((p: Row) => <option key={p.id} value={p.id}>{p.title} v{p.version}</option>)}</select>
          <input className="input" placeholder="Control, e.g. ra-1" value={f.control || ""} onChange={(e) => set("control", e.target.value.trim())} data-testid="cci-filter-control" />
          <input className="input" placeholder="Family, e.g. ra" value={f.family || ""} onChange={(e) => set("family", e.target.value.trim())} data-testid="cci-filter-family" />
          <input className="input" placeholder="Search CCI text" value={f.q || ""} onChange={(e) => set("q", e.target.value)} data-testid="cci-filter-q" />
        </div>
        <div className="mb-2 text-[12px] text-slate-600" data-testid="cci-count">{data ? `${data.total.toLocaleString()} CCIs · ${data.counts.mapped} mapped · ${data.counts.met} met · ${data.counts.partial} partial · ${data.counts.missing} missing` : "Loading…"}</div>
        {data && data.total === 0 && <p className="text-[12px] text-slate-600" data-testid="cci-empty">No CCIs match. Clear a filter, or upload a policy in the <Link className="underline" to="/policy-auditor">Policy Auditor</Link> to map CCIs.</p>}
        <table className="w-full text-[12px]"><thead><tr className="text-left text-[11px] text-slate-500"><th>CCI</th><th>Definition</th><th>Control</th><th>Implementation</th><th>Coverage</th><th>Policy · matched text</th></tr></thead><tbody>
          {pg.rows.map((r) => <tr key={`${r.cci_id}-${r.control_id}`} className="border-t border-slate-100 align-top [content-visibility:auto]" data-testid={`cci-row-${r.cci_id}`}>
            <td className="py-1 font-mono">{r.cci_id}</td><td className="py-1 pr-2 text-[11px]">{r.definition}</td>
            <td className="py-1"><Link className="font-mono text-blue-800 underline" to={`/systems/${sid}/controls/${r.control_id}`}>{fmt(r.control_id)}</Link></td>
            <td className="py-1">{r.implementation_status.replace(/_/g, " ")}</td><td className="py-1">{r.coverage ? <CovBadge s={r.coverage} /> : <span className="text-slate-400">not mapped</span>}{r.covered_elsewhere && <div className="text-[10px] text-slate-500">covered elsewhere</div>}</td>
            <td className="py-1 text-[11px]">{r.policy_ids.map((p: string, i: number) => <Link key={p} className="text-blue-800 underline" to={`/policy-auditor/${p}`}>{r.policies[i] || "policy"}</Link>)}
              {r.snippet && <div className="text-slate-600">“{r.snippet.text.slice(0, 160)}” <span className="text-[10px] text-slate-500">{r.snippet.location}</span></div>}</td></tr>)}
        </tbody></table>
        <div className="mt-2 flex justify-end">{pg.pager}</div>
      </Panel>
    </div>);
}
