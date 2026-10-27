import { Fragment, useMemo, useState } from "react";
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
  const [open, setOpen] = useState<string | null>(null);
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
        <tbody>{rows.map((r: Row) => <Fragment key={r.finding_id + r.rule_id}><tr className="cursor-pointer border-t border-slate-100 align-top hover:bg-slate-50" onClick={() => setOpen(open === r.finding_id ? null : r.finding_id)} data-testid={`stig-rule-${r.vuln_id}`}>
          <td className="py-1 font-mono">{r.vuln_id}</td><td className="py-1 font-mono text-[11px]">{r.rule_id}</td><td className="py-1">{r.title}{(r.edited || []).length > 0 && <span className="ml-1 rounded bg-amber-100 px-1 text-[10px] text-amber-900" data-testid={`stig-edited-${r.vuln_id}`}>edited in app: {r.edited.join(", ")}</span>}</td><td className="py-1">{r.severity}</td>
          <td className="py-1" title={STATUS_TIP[r.status]}>{r.status}</td><td className="max-w-[260px] py-1 text-[11px]">{r.finding_details}</td><td className="max-w-[200px] py-1 text-[11px]">{r.comments}</td></tr>
          {open === r.finding_id && <tr data-testid={`stig-rule-detail-${r.vuln_id}`}><td colSpan={7} className="bg-slate-50 p-2 text-[11px]">
            {!r.source ? <div className="text-rose-700">The source file could not be re-read – only the stored record is shown.</div> : <div className="grid gap-2 md:grid-cols-2">
              <div><div className="font-semibold">From the uploaded checklist (original, read-only)</div>
                {[["STIG ID", r.source.stig_id], ["Group title", r.source.group_title], ["Rule version", r.source.rule_version], ["Legacy IDs", r.source.legacy_ids], ["Status", r.source.source_status ?? r.source.status],
                  ["Severity", r.source.source_severity ?? r.source.severity], ["Severity override", r.source.severity_override], ["Override justification", r.source.severity_justification], ["CCIs", (r.source.ccis || []).join(", ")]]
                  .filter(([, v]) => v).map(([k, v]) => <div key={k}><span className="text-slate-500">{k}:</span> {v}</div>)}
                {[["Discussion", r.source.discussion], ["Check text", r.source.check_content], ["Fix text", r.source.fix_text]].map(([k, v]) => <details key={k} className="mt-1"><summary className="cursor-pointer text-slate-600">{k}</summary><pre className="whitespace-pre-wrap">{v || "Not present in the source file"}</pre></details>)}
              </div>
              <div><div className="font-semibold">Current record in the app</div><div>Title: {r.title}</div><div>Severity: {r.severity}</div><div>Finding state: {r.current_state}</div>
                {(r.edited || []).length ? <div className="mt-1 text-amber-800">Differs from the source file: {r.edited.join(", ")}</div> : <div className="mt-1 text-emerald-700">Matches the source file.</div>}</div>
            </div>}</td></tr>}</Fragment>)}</tbody></table></div>
    </Panel>);
}
