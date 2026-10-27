import { Link, useParams } from "react-router-dom";
import { Row, useApi } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { downloadFile } from "@/lib/download";

const TONE: Row = { applied: "bg-emerald-50 text-emerald-800", "in review": "bg-amber-50 text-amber-900", "not imported": "bg-slate-100 text-slate-600" };

/** Migration completion report: per eMASS file type what was applied, what is still in review or the exception queue, and where it landed. */
export default function MigrationReportPage() {
  const { id } = useParams();
  const { data } = useApi<Row>(`/systems/${id}/migration-report`);
  if (!data) return null;
  return (
    <div data-testid="migration-report-page">
      <PageHeader title={`Migration report – ${data.system.acronym || data.system.name}`} subtitle="What each eMASS import changed, what still needs review, and the RMF step where the data now lives.">
        <Link className="btn-secondary" to={`/systems/${id}/emass-import`} data-testid="migration-back-import">Import Center</Link></PageHeader>
      <div className="space-y-5">
        <Panel title="Coverage" testId="migration-coverage">
          <div className="grid gap-3 md:grid-cols-3">{data.coverage.map((c: Row) => (
            <div key={c.type} className="rounded border border-slate-200 p-3 text-[12px]" data-testid={`migration-coverage-${c.type}`}>
              <div className="flex items-center gap-2"><b className="text-[13px]">{c.label}</b><span className={`ml-auto rounded px-1.5 ${TONE[c.status]}`} data-testid={`migration-status-${c.type}`}>{c.status}</span></div>
              {c.status === "applied" && <p className="mt-1 text-slate-600">{c.applied_fields} field(s) applied</p>}
              <div className="mt-2 flex flex-wrap gap-2">{c.steps.map((s: Row) => <Link key={s.to} className="text-blue-800 underline" to={s.to} data-testid={`migration-step-${c.type}-${s.label.split(" ")[0].toLowerCase()}`}>{s.label} →</Link>)}</div>
            </div>))}
            {data.deferred.map((d: Row) => <div key={d.type} className="rounded border border-dashed border-slate-300 p-3 text-[12px] text-slate-500" data-testid={`migration-deferred-${d.type}`}><b>{d.label}</b> – {d.note}</div>)}
          </div>
        </Panel>
        <Panel title="Exports (eMASS layout, .xlsx)" testId="migration-exports">
          <div className="flex flex-wrap gap-4 text-[12px]">{(data.exports || []).map((x: Row) => (
            <button key={x.type} className="text-blue-800 underline" onClick={() => downloadFile(x.href.replace(/^\/api\/v1/, ""), `${data.system.acronym || "system"}_${x.type}.xlsx`, x.label)} data-testid={`migration-export-${x.type}`}>{x.label}</button>))}</div>
        </Panel>
        <Panel title="Import sessions" testId="migration-sessions">
          <table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>When</th><th>Type</th><th>File (SHA-256)</th><th>Status</th><th>Applied</th><th>Exceptions</th><th>Failed</th><th /></tr></thead>
            <tbody>{data.sessions.map((s: Row) => <tr key={s.id} className="border-t border-slate-100" data-testid={`migration-session-${s.id}`}>
              <td>{new Date(s.created_at).toLocaleString()}</td><td>{s.report_type_label}{s.deferred ? " (deferred)" : ""}</td><td>{s.file_name} <span className="font-mono text-slate-400">{s.sha256.slice(0, 10)}…</span></td>
              <td>{s.status}{s.reverted ? ` · ${s.reverted} reverted` : ""}</td><td>{s.counts?.applied_fields ?? "–"}</td>
              <td className={s.exception_total ? "text-amber-800" : ""}>{s.exception_total}</td><td className={s.failed ? "text-rose-700" : ""}>{s.failed}</td>
              <td><Link className="text-blue-800 underline" to={`/systems/${id}/emass-import/${s.id}`}>Open</Link></td></tr>)}</tbody></table>
          {!data.sessions.length && <p className="text-[12px] text-slate-500">No imports for this system yet.</p>}
        </Panel>
      </div>
    </div>);
}
