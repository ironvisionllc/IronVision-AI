import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { BaselinePill } from "@/components/common/StatusPill";
import { S, Sev, Stat, Table } from "@/components/common/Bits";
import { AccessDenied } from "@/components/common/AccessDenied";
import { cn, fmtDate } from "@/lib/format";
import { AddToPoamButton, PoamLink } from "@/components/common/Workflow";
import { ImplementationPanel } from "@/components/workbench/ImplementationPanel";
import { AssessmentPanel } from "@/pages/Phase3Extras";

const REASON: Record<string, string> = { failed_technical_checks: "Failed checks", kev: "KEV", cat1_open: "CAT I", expired_evidence: "Expired evidence",
  missing_implementation_statement: "No narrative", missing_assessment_evidence: "No assessment evidence", unmapped_findings: "Unmapped findings",
  responsibility_split_missing: "Responsibility split not documented", catalog_change: "Catalog/STIG change" };

const KIND: Record<string, string> = { control: "Control", poam: "POA&M", attestation: "Attestation", policy_finding: "Policy", review: "Review", milestone: "Milestone", evidence: "Evidence" };

function QueueItem({ i, active }: { i: Row; active?: string }) {
  const nav = useNavigate();
  return (
    <li className={cn("border-b border-slate-100 px-3 py-2 text-[12px] hover:bg-blue-50", active && active === i.control_id && i.kind === "control" && "bg-blue-50")} data-testid={`queue-item-${i.kind === "control" ? i.control_id : `${i.kind}-${i.ref}`}`}>
      <div className="flex items-center justify-between gap-2">
        <button className="truncate text-left font-medium text-blue-800 hover:underline" onClick={() => nav(i.link)} data-testid={`queue-open-${i.ref}`}><span className="mr-1 rounded bg-slate-100 px-1 text-[10px] uppercase text-slate-600">{KIND[i.kind] ?? i.kind}</span>{i.title}</button>
        <span className="shrink-0 font-mono text-[11px] text-slate-600" title={(i.reasons || []).map((r: Row) => `${r.label ?? r.detail ?? r.code}: +${r.points}`).join("\n")} data-testid={`queue-score-${i.ref}`}>{i.score}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1">
        {(i.reasons || []).map((r: Row, k: number) => <span key={k} className="rounded bg-slate-100 px-1.5 text-[10px] text-slate-700">{r.label ?? r.detail ?? REASON[r.code] ?? r.code.replace(/_/g, " ")} +{r.points}</span>)}
        {i.control_id && i.kind !== "control" && <Link to={i.control_link} className="text-[10px] text-blue-800 underline" data-testid={`queue-control-${i.ref}`}>{i.control_label}</Link>}
        {i.due && <span className="text-[10px] text-slate-500">due {i.due}</span>}
      </div>
    </li>);
}

function WorkQueue({ systemId, active }: { systemId: string; active?: string }) {
  const [mine, setMine] = useState(false);
  const [open, setOpen] = useState<string>("");
  const { data, loading } = useApi<Row>(`/systems/${systemId}/workbench/queue`, { mine });
  if (!data) return <div className="p-3 text-[12px] text-slate-500" data-testid="queue-loading">{loading === false ? "" : "Loading queue…"}</div>;
  const L = data.lanes;
  return (
    <div data-testid="work-queue">
      <div className="flex items-center gap-1 border-b border-slate-200 px-3 py-2 text-[11px]" role="group" aria-label="Queue scope">
        {[["All in system", false], ["Mine", true]].map(([l, v]) => <button key={String(l)} className={cn("rounded-full px-2 py-0.5", mine === v ? "bg-blue-800 text-white" : "bg-slate-100")} onClick={() => setMine(v as boolean)} data-testid={`queue-scope-${v ? "mine" : "all"}`}>{l as string}</button>)}
        <span className="ml-auto text-slate-500" title={data.scoring}>ties: {data.tie_break}</span>
      </div>
      <div className="max-h-[680px] overflow-y-auto">
        <div className="bg-rose-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-rose-800" data-testid="lane-needs-action">Needs action now ({data.counts.needs_action})</div>
        <ul>{L.needs_action.map((i: Row) => <QueueItem key={`${i.kind}-${i.ref}`} i={i} active={active} />)}</ul>
        <div className="bg-amber-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-amber-800" data-testid="lane-due-soon">Due soon – 30 days ({data.counts.due_soon})</div>
        <ul>{L.due_soon.map((i: Row) => <QueueItem key={`${i.kind}-${i.ref}-${i.due}`} i={i} active={active} />)}</ul>
        <div className="bg-slate-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600" data-testid="lane-backlog">Not started / backlog ({data.counts.backlog})</div>
        <ul>{L.backlog.map((f: Row) => <li key={f.family} className="border-b border-slate-100 text-[12px]">
          <button className="flex w-full justify-between px-3 py-1.5 hover:bg-slate-50" onClick={() => setOpen(open === f.family ? "" : f.family)} data-testid={`backlog-family-${f.family}`}><span className="font-mono font-semibold">{f.family}</span><span>{f.count} {open === f.family ? "▾" : "▸"}</span></button>
          {open === f.family && <ul className="pb-1">{f.controls.map((c: Row) => <li key={c.control_id} className="px-5 py-0.5"><Link to={c.link} className="font-mono text-blue-800 hover:underline" data-testid={`backlog-item-${c.control_id}`}>{c.control_label}</Link> <span className="text-slate-600">{c.title}</span> <span className="text-[10px] text-slate-500">{c.reasons.map((r: string) => REASON[r] ?? r.replace(/_/g, " ")).join(", ")}</span></li>)}</ul>}
        </li>)}</ul>
      </div>
    </div>);
}

export default function WorkbenchPage() {
  const { id = "", controlId } = useParams();
  const nav = useNavigate();
  const { select } = useSystems();
  const [status, setStatus] = useState("");
  const [all, setAll] = useState(false);
  useEffect(() => { if (id) select(id); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  const { data: sum } = useApi<Row>(`/systems/${id}/workbench/summary`);
  const { data: list, reload } = useApi<Row[]>(`/systems/${id}/workbench/controls`, { queue: !all, implementation_status: status || undefined });
  return (
    <div data-testid="workbench-page">
      <PageHeader title="Control Workbench" subtitle="Separate statuses: implementation · assessment (SCA only) · monitoring (technical checks) · evidence freshness. Passing checks never mean 'compliant'.">
        <Link to="/catalog" className="btn-secondary" data-testid="open-catalog-btn">Reference catalog</Link>
      </PageHeader>
      {sum && (
        <>
          <div className="mb-1 text-[11px] text-slate-500" data-testid="overlap-note">{sum.overlapping_counts_note}</div>
          <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
            <Stat label="Assigned" value={sum.total_assigned} testId="wb-total-assigned" />
            <Stat label="Controls w/ current evidence" value={`${sum.with_current_evidence} of ${sum.total_assigned}`} testId="wb-current-evidence" hint={`collected evidence items within freshness window: ${sum.metrics.evidence_items_fresh_pct ?? "—"}%`} />
            <Stat label="Fully inherited" value={sum.fully_inherited} testId="wb-inherited" />
            <Stat label="Shared" value={sum.shared} testId="wb-shared" />
            <Stat label="Not assessed" value={sum.not_assessed} testId="wb-not-assessed" />
            <Stat label="Open findings" value={sum.with_open_findings} testId="wb-open-findings" />
            <Stat label="Manual action" value={sum.requiring_manual_action} testId="wb-manual-action" />
            <Stat label="Unmapped findings" value={sum.unmapped_findings} testId="wb-unmapped" hint="system-level queue item" />
          </div>
        </>
      )}
      <div className="grid gap-5 xl:grid-cols-[380px_1fr]">
        <div className="panel" data-testid="isso-queue">
          <div className="flex items-center gap-2 border-b border-slate-200 p-3">
            <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} data-testid="lifecycle-filter"><option value="">All implementation statuses</option>{["planned", "partially_implemented", "implemented", "inherited", "not_applicable"].map((s) => <option key={s} value={s}>{s}</option>)}</select>
            <label className="flex items-center gap-1 whitespace-nowrap text-[12px]"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} data-testid="show-all-toggle" />All controls</label>
          </div>
          {(sum?.unmapped_findings ?? 0) > 0 && <Link to="/mapping-review" className="block border-b border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900" data-testid="queue-unmapped-item">System: {sum?.unmapped_findings} unmapped open findings need mapping or disposition →</Link>}
          {all ? <ul className="max-h-[640px] overflow-y-auto">
            {list?.map((a) => (
              <li key={a.id}>
                <button onClick={() => nav(`/systems/${id}/controls/${a.control_id}`)} data-testid={`queue-item-${a.control_id}`}
                  className={cn("w-full border-b border-slate-100 px-3 py-2 text-left transition-colors hover:bg-blue-50", controlId === a.control_id && "bg-blue-50")}>
                  <div className="flex items-center justify-between"><span className="font-mono text-[12px] font-semibold text-blue-800">{a.label}</span>
                    <span className="font-mono text-[11px] text-slate-600" data-testid={`queue-score-${a.control_id}`}>score {a.priority_score}</span></div>
                  <div className="truncate text-[12px] text-slate-700">{a.title}</div>
                </button>
              </li>
            ))}
          </ul> : <WorkQueue systemId={id} active={controlId} />}
        </div>
        {controlId ? <ControlPanel systemId={id} controlId={controlId} onChange={reload} /> : <div className="panel p-6 text-sm text-slate-500">Select a control from the queue.</div>}
      </div>
    </div>
  );
}

function ControlPanel({ systemId, controlId, onChange }: { systemId: string; controlId: string; onChange: () => void }) {
  const { can } = useAuth();
  const { data: d, reload, error, denied } = useApi<Row>(`/systems/${systemId}/workbench/controls/${controlId}`);
  const [comment, setComment] = useState("");
  const [msg, setMsg] = useState("");
  if (denied) return <AccessDenied denied={denied} area="this control" />;
  if (error) return <div className="panel p-6 text-sm text-rose-700">{error}</div>;
  if (!d) return null;
  const a = d.assignment, c = d.catalog;
  const addComment = async () => { try { await api.post(`/systems/${systemId}/workbench/controls/${controlId}/comments`, { body: comment }); setComment(""); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  return (
    <div className="space-y-4" data-testid="control-panel">
      <Panel testId="control-header">
        <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-lg font-semibold text-blue-800" data-testid="wb-control-id">{c.label}</span>{c.baselines.map((b: string) => <BaselinePill key={b} baseline={b} />)}
          <span className="text-[12px] text-slate-500">origin {a.origin} ({a.origin_detail}) · responsibility <b>{a.responsibility}</b>{a.provider_name ? ` via ${a.provider_name}` : ""}</span></div>
        <h2 className="mt-1 text-lg font-semibold">{c.title}</h2>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="wb-statuses">
          <S v={a.implementation_status} label="Implementation" testId="wb-status-implementation" /><S v={a.assessment_status} label="Assessment" testId="wb-status-assessment" />
          <S v={a.monitoring_status} label="Monitoring" testId="wb-status-monitoring" /><S v={a.evidence_freshness_status} label="Evidence freshness" testId="wb-status-freshness" />
        </div>
        {a.reason_details.length > 0 && <div className="mt-2 text-[11px] text-slate-600" data-testid="wb-score-breakdown">Priority {a.priority_score}: {a.reason_details.map((r: Row) => `${r.description} (+${r.points})`).join(" · ")}</div>}
        <div className="mt-1 text-[11px] text-slate-400">Last eMASS sync: {d.emass_sync}</div>
      </Panel>
      <Panel title="Supporting evidence" testId="wb-evidence">
        <div className="mb-2 flex flex-wrap gap-3 text-[12px]" data-testid="wb-evidence-summary">{d.evidence_summary.map((s: Row) => <span key={s.source_type} className="rounded border border-slate-200 px-2 py-1">{s.source_type === "stig_checklist" ? "STIG" : "ACAS"}: {s.assets_scanned} assets scanned, {s.failed_rules} failed rules, {s.passed_checks} passing checks</span>)}</div>
        <Table head={["Evidence", "Source", "Collected", "Age", "State", "SHA-256"]}>
          {d.evidence.map((e: Row) => <tr key={e.id}><td className="td text-[12px]">{e.name}</td><td className="td text-[12px]">{e.source_name}</td><td className="td font-mono text-[11px]">{fmtDate(e.collected_at)}</td>
            <td className="td font-mono text-[11px]">{Math.floor((Date.now() - new Date(e.collected_at).getTime()) / 86400000)}d</td><td className="td"><S v={e.state} /></td><td className="td font-mono text-[11px]">{e.sha256.slice(0, 12)}…</td></tr>)}
        </Table>
      </Panel>
      <Panel title={`Open findings (${d.open_findings.length})`} testId="wb-open-findings-table">
        <Table head={["Rule", "Requirement", "Severity", "Asset", "Mapping provenance", "Action"]}>
          {d.open_findings.map((f: Row) => <tr key={f.id}><td className="td font-mono text-[11px]">{f.vuln_id ?? f.rule_id}</td><td className="td text-[12px]">{f.title}{f.is_kev && <> <S v="critical" label="KEV" /></>}</td>
            <td className="td text-[12px]"><Sev v={f.cat ?? f.severity} /></td><td className="td text-[12px]">{f.asset_name}</td><td className="td text-[11px]">{f.mapping.source}{f.mapping.cci_id && ` (${f.mapping.cci_id})`} · {f.mapping.review_status}</td><td className="td"><Link className="mr-1 text-[11px] text-blue-800 underline" to={`/findings/${f.id}`} data-testid={`wb-finding-link-${f.id}`}>view</Link>{f.poam ? <span className="text-[11px]" data-testid={`wb-finding-linked-${f.id}`}>Linked: <PoamLink id={f.poam.id} humanId={f.poam.human_id} /></span> : <AddToPoamButton findingId={f.id} onDone={reload} />}</td></tr>)}
        </Table>
      </Panel>
      {d.policy_parameters?.length > 0 && <Panel title="Policy & parameters" testId="wb-policy-parameters">
        <Table head={["Parameter", "Organization-defined value (source)", "Observed value (source)", "Result", "Policy finding / POA&M"]}>
          {d.policy_parameters.map((p: Row) => <tr key={p.parameter} data-testid={`wb-param-${p.parameter}`}><td className="td text-[12px]">{p.parameter.replace(/_/g, " ")}</td>
            <td className="td text-[12px]"><b>{p.odp_value}</b><div className="text-[10px] text-slate-500">{p.odp_source}</div></td>
            <td className="td text-[12px]"><b>{p.observed_value ?? "—"}</b><div className="text-[10px] text-slate-500">{p.observed_source}</div></td>
            <td className="td">{p.result ? <S v={p.result} testId={`wb-param-result-${p.parameter}`} /> : "no observation"}</td>
            <td className="td text-[11px]">{p.policy_findings.map((f: Row) => <div key={f.id}><Link className="text-blue-800 underline" to={`/policy-auditor/${f.policy_id}`}>{f.policy}</Link> · {f.status === "proposed" ? <i>proposed (unconfirmed)</i> : f.status}{f.finding_id && <> · <Link className="text-blue-800 underline" to={`/findings/${f.finding_id}`}>finding</Link></>}</div>)}
              {p.poams.map((x: Row) => <div key={x.id}><PoamLink id={x.id} humanId={x.human_id} /></div>)}</td></tr>)}
        </Table>
      </Panel>}
      <ImplementationPanel systemId={systemId} controlId={controlId} d={d} reload={() => { reload(); onChange(); }} />
      <Panel title="POA&Ms for this control" testId="wb-poams">{d.poams.length === 0 ? <div className="text-[12px] text-slate-500">None</div> : d.poams.map((p: Row) => <div key={p.id} className="text-[12px]"><PoamLink id={p.id} humanId={p.human_id} /> {p.weakness} <S v={p.status} /> due {p.due_date ?? "—"}</div>)}</Panel>
      <Panel title="SCA assessment" testId="wb-assessment-panel"><AssessmentPanel systemId={systemId} controlId={controlId} objectives={c.objectives} onDone={() => { reload(); onChange(); }} /></Panel>
      <Panel title="Catalog: statement, parameters, objectives, CCIs" testId="wb-catalog">
        <pre className="whitespace-pre-wrap font-sans text-[13px] text-slate-800" data-testid="wb-statement">{(d.statement_segments || [{ text: c.statement }]).map((s: Row, i: number) => s.text !== undefined ? <span key={i}>{s.text}</span> :
          s.value ? <mark key={i} className="rounded bg-emerald-50 px-0.5 text-emerald-900" title={`${s.original} · ${s.source}`} data-testid={`odp-filled-${s.odp_id}`}>{s.value}</mark> :
          <span key={i} className="rounded bg-amber-50 px-0.5 text-amber-900" title="Organization-defined parameter not yet defined for this system" data-testid={`odp-missing-${s.odp_id}`}>{s.original} <i className="text-[10px]">(not yet defined)</i></span>)}</pre>
        <div className="mt-3 text-[12px]">{c.parameters?.map((p: Row) => <div key={p.id}><span className="font-mono text-slate-500">{p.id}</span> {p.rendered}</div>)}</div>
        {c.enhancements.length > 0 && <div className="mt-3 text-[12px]"><b>Enhancements:</b> {c.enhancements.map((e: Row) => e.label).join(", ")}</div>}
        <div className="mt-3 text-[12px]"><b>Objectives:</b> {c.objectives.filter((o: Row) => o.prose).length}</div>
        <div className="mt-3 text-[12px]" data-testid="wb-cci-list"><b>CCIs</b> ({d.cci_provenance.source} {d.cci_provenance.version}, sha {d.cci_provenance.sha256?.slice(0, 12)}…): {c.ccis.map((x: Row) => x.cci_id).join(", ")}</div>
      </Panel>
      <Panel title="Reviewer comments" testId="wb-comments">
        {d.comments.map((m: Row) => <div key={m.id} className="border-b border-slate-100 py-1 text-[12px]"><b>{m.author_email}</b> {fmtDate(m.created_at)}: {m.body}</div>)}
        {can("comment.write") && <div className="mt-2 flex gap-2"><input className="input" value={comment} onChange={(e) => setComment(e.target.value)} data-testid="wb-comment-input" /><button className="btn-secondary" disabled={!comment} onClick={addComment} data-testid="wb-comment-btn">Comment</button></div>}
      </Panel>
    </div>
  );
}
