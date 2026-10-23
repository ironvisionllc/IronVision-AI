import { useMemo, useState } from "react";
import { useApi, Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";

const STATUS_TIP: Record<string, string> = { "Open": "The check failed – this is a finding to fix or track in a POA&M.", "Not a Finding": "The check passed.",
  "Not Applicable": "The rule does not apply to this asset.", "Not Reviewed": "Nobody has evaluated this rule yet." };

/** Every rule of a STIG checklist (.ckl/.cklb) or XCCDF result, with totals and a check against the source file. */
export function StigDetail({ runId }: { runId: string }) {
  const { data } = useApi<Row>(`/ingest-runs/${runId}/stig`);
  const [q, setQ] = useState("");
  const [st, setSt] = useState("");
  const [sev, setSev] = useState("");
  const [sort, setSort] = useState("status");
  const rows = useMemo(() => {
    const r = (data?.rules || []).filter((x: Row) => (!st || x.status === st) && (!sev || x.severity === sev)
      && (!q || `${x.vuln_id} ${x.rule_id} ${x.title} ${x.finding_details} ${x.comments}`.toLowerCase().includes(q.toLowerCase())));
    return [...r].sort((a: Row, b: Row) => String(a[sort] ?? "").localeCompare(String(b[sort] ?? "")));
  }, [data, q, st, sev, sort]);
  if (!data) return null;
  const h = data.header || {}, pc = data.parse_check, t = data.totals;
  return (
    <Panel title="STIG checklist detail" className="mb-5" testId="stig-detail">
      <div className="mb-2 text-[13px]" data-testid="stig-header"><b>{h.title || "STIG"}</b> · Version {h.version ?? "—"} · Release {h.release ?? "—"} · Benchmark date {h.date ?? "—"}</div>
      <div className="mb-2 flex flex-wrap gap-2 text-[12px]" data-testid="stig-totals">
        {Object.entries(t.by_status).map(([k, v]) => <span key={k} className="rounded bg-slate-100 px-2 py-0.5" title={STATUS_TIP[k]}>{k}: <b>{String(v)}</b></span>)}
        {Object.entries(t.by_severity).map(([k, v]) => <span key={k} className="rounded bg-amber-50 px-2 py-0.5" title="CAT I = high, CAT II = medium, CAT III = low severity (DISA categories)">{k}: <b>{String(v)}</b></span>)}
      </div>
      <div className={`mb-3 text-[12px] ${pc.match === false ? "text-rose-700" : "text-emerald-700"}`} data-testid="stig-parse-check">
        {pc.match === null ? `${pc.stored_rules} rules stored (source file could not be re-read for comparison)` : pc.match
          ? `✓ Matches the source file: ${pc.source_rules} rules parsed, ${pc.stored_rules} stored` : `✗ Source file has ${pc.source_rules} rules but ${pc.stored_rules} were stored – re-upload the file`}</div>
      <div className="mb-2 flex flex-wrap gap-2">
        <input className="input w-64" placeholder="Search Vuln ID, rule, title, details…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="stig-search" />
        <select className="input w-44" value={st} onChange={(e) => setSt(e.target.value)} data-testid="stig-filter-status"><option value="">All statuses</option>{Object.keys(STATUS_TIP).map((s) => <option key={s}>{s}</option>)}</select>
        <select className="input w-36" value={sev} onChange={(e) => setSev(e.target.value)} data-testid="stig-filter-severity"><option value="">All severities</option>{["CAT I", "CAT II", "CAT III"].map((s) => <option key={s}>{s}</option>)}</select>
        <select className="input w-44" value={sort} onChange={(e) => setSort(e.target.value)} data-testid="stig-sort"><option value="status">Sort: status</option><option value="severity">Sort: severity</option><option value="vuln_id">Sort: Vuln ID</option><option value="title">Sort: title</option></select>
        <span className="self-center text-[12px] text-slate-500" data-testid="stig-row-count">{rows.length} of {data.rules.length} rules</span>
      </div>
      <div className="max-h-[520px] overflow-y-auto"><table className="w-full text-[12px]"><thead className="sticky top-0 bg-white"><tr className="text-left text-[11px] text-slate-500"><th>Vuln ID</th><th>Rule ID</th><th>Title</th><th>Severity</th><th>Status</th><th>Finding details</th><th>Comments</th></tr></thead>
        <tbody>{rows.map((r: Row) => <tr key={r.finding_id + r.rule_id} className="border-t border-slate-100 align-top" data-testid={`stig-rule-${r.vuln_id}`}>
          <td className="py-1 font-mono">{r.vuln_id}</td><td className="py-1 font-mono text-[11px]">{r.rule_id}</td><td className="py-1">{r.title}</td><td className="py-1">{r.severity}</td>
          <td className="py-1" title={STATUS_TIP[r.status]}>{r.status}</td><td className="max-w-[260px] py-1 text-[11px]">{r.finding_details}</td><td className="max-w-[200px] py-1 text-[11px]">{r.comments}</td></tr>)}</tbody></table></div>
    </Panel>);
}
