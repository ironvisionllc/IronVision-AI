import { Link } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { S, Stat, Table } from "@/components/common/Bits";

export default function LeadershipPage() {
  const { data, error } = useApi<Row>("/dashboard/leadership");
  if (error) return <div className="panel p-6 text-sm text-rose-700" role="alert" data-testid="leadership-error">{error}</div>;
  if (!data) return null;
  const c = data.cards;
  const trend = data.trend.map((t: Row) => ({ ...t, label: new Date(t.taken_at).toISOString().slice(5, 10) }));
  return (
    <div data-testid="leadership-page">
      <PageHeader title="Portfolio / Leadership" subtitle={data.note} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <Stat label="Systems authorized" value={`${c.systems_authorized} / ${c.systems_total}`} testId="card-systems-authorized" />
        <Stat label="In assessment" value={c.systems_in_assessment} testId="card-in-assessment" />
        <Stat label="ATO exp. ≤ 90d" value={c.auth_expiring_90d} testId="card-expiring" />
        <Stat label="Open CAT I / critical" value={c.open_cat1} testId="card-open-cat1" />
        <Stat label="Open KEV" value={c.kev_open} testId="card-kev" />
        <Stat label="Overdue POA&Ms" value={c.overdue_poams} testId="card-poams" hint={`${c.open_poams} open`} />
        <Stat label="Evidence freshness" value={c.evidence_fresh_pct === null ? "—" : `${c.evidence_fresh_pct}%`} testId="card-freshness" hint={`controls fully current · ${c.controls_stale} stale/partial`} />
        <Stat label="Pending risk decisions" value={c.pending_risk_decisions} testId="card-pending-risk" hint={`${c.risk_acceptances} accepted`} />
      </div>
      <Panel title="Waiting on your decision" className="mb-5" testId="waiting-on-you">
        {data.waiting_on_you.length === 0 ? <div className="text-[12px] text-slate-500">Nothing awaiting your authority.</div> :
          <div className="flex flex-wrap gap-2">{data.waiting_on_you.map((w: Row, i: number) => (
            <Link key={i} to={w.link} className="btn-secondary px-2.5 py-1 text-[12px]" data-testid={`waiting-${w.kind}-${i}`}>{w.label}{w.due ? ` · ${w.due}` : ""}</Link>))}</div>}
      </Panel>
      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <Panel title="System risk" eyebrow={data.op_score.label} testId="leadership-system-table">
          <Table head={["System", "Op. priority", "Authorization", "Expires", "Open", "CAT I", "KEV", "POA&M open / overdue", "Pending risk", "Evidence fresh"]}>
            {data.systems.map((s: Row) => (
              <tr key={s.id} data-testid={`leadership-row-${s.acronym}`}>
                <td className="td"><Link className="font-medium text-blue-800 hover:underline" to={`/systems/${s.id}`}>{s.name}</Link><div className="text-[10px] uppercase text-slate-400">{s.baseline} · {s.lifecycle_phase}</div></td>
                <td className="td font-mono" title={s.op_score_breakdown.map((x: Row) => `${x.description}: ${x.count}×${x.weight}=${x.points}`).join("\n")} data-testid={`op-score-${s.acronym}`}>{s.op_score}
                  <div className="text-[10px] text-slate-500">{s.op_score_breakdown.map((x: Row) => `${x.code.replace("sys_", "")} ${x.points}`).join(" · ")}</div></td>
                <td className="td text-[12px]">{s.authorization_status}</td>
                <td className="td font-mono text-[11px]">{s.authorization_expiration ?? "—"}{s.days_to_expiration !== null && <div className="text-amber-700">{s.days_to_expiration}d</div>}</td>
                <td className="td font-mono">{s.open_findings}</td><td className="td font-mono">{s.open_cat1}</td><td className="td font-mono">{s.kev_open}</td>
                <td className="td font-mono">{s.open_poams} / {s.overdue_poams}</td><td className="td font-mono">{s.pending_risk_decisions}</td>
                <td className="td font-mono">{s.evidence_fresh_pct === null ? "—" : `${s.evidence_fresh_pct}%`}</td>
              </tr>
            ))}
          </Table>
          <div className="mt-2 text-[10px] text-slate-500" data-testid="op-score-weights">Weights: {data.op_score.weights.map((w: Row) => `${w.description} ×${w.weight}`).join(" · ")}</div>
        </Panel>
        <Panel title="Trend (stored snapshots)" eyebrow="Weekly history is SYNTHETIC; later points are live snapshots" testId="leadership-trend">
          <div className="h-64">
            <ResponsiveContainer width="100%" height={256} minWidth={0}>
              <LineChart data={trend}><CartesianGrid stroke="var(--iv-chart-grid)" strokeDasharray="3 3" /><XAxis dataKey="label" fontSize={11} stroke="var(--iv-chart-axis)" tick={{ fill: "var(--iv-chart-axis)" }} /><YAxis fontSize={11} stroke="var(--iv-chart-axis)" tick={{ fill: "var(--iv-chart-axis)" }} />
                <Tooltip contentStyle={{ background: "var(--iv-surface-solid)", border: "1px solid var(--iv-border-strong)", borderRadius: 12, color: "var(--iv-text)", fontSize: 12 }} /><Legend wrapperStyle={{ fontSize: 11, color: "var(--iv-text-muted)" }} />
                <Line dataKey="open_cat1" name="Open CAT I" stroke="var(--iv-chart-1)" strokeWidth={2} dot={false} />
                <Line dataKey="kev_open" name="KEV" stroke="var(--iv-chart-2)" strokeWidth={2} dot={false} />
                <Line dataKey="evidence_fresh_pct" name="Evidence fresh %" stroke="var(--iv-chart-3)" strokeWidth={2} dot={false} />
                <Line dataKey="open_findings" name="Total open" stroke="var(--iv-chart-4)" strokeWidth={2} dot={false} />
                <Line dataKey="overdue_poams" name="Overdue POA&Ms" stroke="var(--iv-chart-5)" strokeWidth={2} dot={false} />
                <Line dataKey="risk_acceptances" name="Risk acceptances" stroke="var(--iv-chart-6)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex gap-2 text-[11px] text-slate-500"><S v="neutral" label="points" /> {trend.filter((t: Row) => t.synthetic).length} synthetic · {trend.filter((t: Row) => !t.synthetic).length} live</div>
        </Panel>
      </div>
    </div>
  );
}
