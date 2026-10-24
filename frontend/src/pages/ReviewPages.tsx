import { FindingMappingHistory, ScoreBreakdown } from "@/pages/Phase4Pages";
import { SimulatedSignatureNote } from "@/components/shell/Sandbox";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { ControlLink, S, Table } from "@/components/common/Bits";
import { AddToPoamButton } from "@/components/common/Workflow";
import { cn, fmtDate } from "@/lib/format";

const TABS = [["issm", "ISSM"], ["sca", "Control Assessor"], ["ao", "Authorizing Official"], ["mine", "My requests"]];

export function ReviewsPage() {
  const [tab, setTab] = useState("issm");
  const { data } = useApi<Row>("/reviews", tab === "mine" ? { mine: true } : { role: tab });
  const { data: rules } = useApi<Row[]>("/decision-rules");
  return (
    <div data-testid="reviews-page">
      <PageHeader title="Reviews" subtitle="Approval engine driven by versioned decision rules. Requesters cannot decide their own requests." />
      <div className="mb-4 flex gap-1 border-b border-slate-200" role="tablist">
        {TABS.map(([k, l]) => (
          <button key={k} role="tab" onClick={() => setTab(k)} data-testid={`reviews-tab-${k}`}
            className={cn("border-b-2 px-4 py-2 text-[13px] font-medium", tab === k ? "border-blue-700 text-blue-800" : "border-transparent text-slate-600")}>
            {l}{k !== "mine" && <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 font-mono text-[11px]" data-testid={`reviews-count-${k}`}>{data?.counts?.[k] ?? 0}</span>}
          </button>))}
      </div>
      <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <Panel testId="reviews-table-panel">
          <Table head={["Request", "Type", "System", "Control", "Finding / POA&M", "Requester", "Assigned", "Requested", "Deadline", "Status"]} testId="reviews-table">
            {data?.items.map((r: Row) => (
              <tr key={r.id} data-testid={`review-row-${r.human_id}`}>
                <td className="td"><Link className="font-mono text-[12px] font-semibold text-blue-800 hover:underline" to={`/reviews/${r.id}`}>{r.human_id}</Link></td>
                <td className="td text-[12px]">{r.type_label}</td><td className="td text-[12px]">{r.system_acronym}</td>
                <td className="td">{r.control_id ? <ControlLink systemId={r.system_id} controlId={r.control_id} /> : "—"}</td>
                <td className="td text-[12px]">{r.poam_id ? <Link className="text-blue-800 underline" to={`/poams/${r.poam_id}`}>{r.poam_human_id}</Link> : r.finding_id ? <Link className="text-blue-800 underline" to={`/findings/${r.finding_id}`}>{r.finding_title?.slice(0, 40)}</Link> : "—"}</td>
                <td className="td text-[12px]">{r.requester_email}</td><td className="td uppercase text-[12px]">{r.assigned_role}</td>
                <td className="td font-mono text-[11px]">{fmtDate(r.created_at)}</td><td className="td font-mono text-[11px]">{r.deadline ?? "—"}</td><td className="td"><S v={r.status} /></td>
              </tr>))}
          </Table>
        </Panel>
        <Panel title="Who can decide what" eyebrow="Generated from decision_rules" testId="decision-rules-panel">
          {rules?.map((r) => (
            <div key={r.id} className="border-b border-slate-100 py-2 text-[12px]" data-testid={`rule-${r.request_type}`}>
              <div className="font-medium">{r.type_label} <span className="text-slate-400">v{r.version}</span></div>
              <div className="text-slate-600">{r.steps.map((s: Row, i: number) => `${i + 1}. ${s.role.toUpperCase()} ${s.action}s`).join(" → ")}</div>
            </div>))}
        </Panel>
      </div>
    </div>
  );
}

export function ReviewDetailPage() {
  const { id = "" } = useParams();
  const { data, reload } = useApi<Row>(`/reviews/${id}`);
  const [rationale, setRationale] = useState("");
  const [msg, setMsg] = useState("");
  if (!data) return null;
  const r = data.request;
  const act = async (action: string) => {
    try { await api.post(`/reviews/${id}/decisions`, { action, rationale }); setMsg(`Recorded: ${action}`); setRationale(""); reload(); } catch (e) { setMsg(errorMessage(e)); }
  };
  const step = data.current_step;
  return (
    <div data-testid="review-detail-page">
      <PageHeader title={`${r.human_id} · ${r.type_label}`} subtitle={`${r.system_name} · rule "${r.rule_label}" v${r.rule_version}`}><S v={r.status} testId="review-status" /></PageHeader>
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Request" testId="review-request">
          <dl className="grid grid-cols-[140px_1fr] gap-y-1.5 text-[13px]">
            <dt className="text-slate-500">Control</dt><dd>{r.control_id ? <ControlLink systemId={r.system_id} controlId={r.control_id} /> : "—"}</dd>
            {r.request_type === "authorization_package_review" && <><dt className="text-slate-500">Package</dt><dd><Link className="text-blue-800 underline" to={`/systems/${r.system_id}/authorization`} data-testid="review-authz-link">Open authorization package (AO records decision there)</Link></dd></>}
            <dt className="text-slate-500">POA&M</dt><dd>{r.poam_id ? <Link className="text-blue-800 underline" to={`/poams/${r.poam_id}`} data-testid="review-poam-link">{r.poam_human_id}</Link> : "—"}</dd>
            <dt className="text-slate-500">Finding</dt><dd>{r.finding_id ? <Link className="text-blue-800 underline" to={`/findings/${r.finding_id}`}>{r.finding_title}</Link> : "—"}</dd>
            <dt className="text-slate-500">Justification</dt><dd data-testid="review-justification">{r.justification}</dd>
            <dt className="text-slate-500">Requester</dt><dd>{r.requester_name} ({r.requester_email})</dd>
            <dt className="text-slate-500">Assigned role</dt><dd className="uppercase">{r.assigned_role} {step && `(${step.action})`}</dd>
            <dt className="text-slate-500">Requested / deadline</dt><dd>{fmtDate(r.created_at)} / {r.deadline ?? "—"}</dd>
            <dt className="text-slate-500">Payload</dt><dd className="font-mono text-[11px]">{r.payload ? JSON.stringify(r.payload) : "—"}</dd>
            <dt className="text-slate-500">Evidence</dt><dd>{data.evidence.map((e: Row) => <Link key={e.id} to="/evidence-ledger" className="mr-2 text-blue-800 underline">{e.name} ({e.sha256.slice(0, 10)}…)</Link>)}{data.evidence.length === 0 && "—"}</dd>
          </dl>
          {data.implementation && <div className="mt-3 rounded bg-slate-50 p-2 text-[12px]" data-testid="review-implementation"><b>Implementation v{data.implementation.version}</b> {data.implementation.ai_generated && "(AI-assisted draft)"}<p className="whitespace-pre-wrap">{data.implementation.narrative}</p></div>}
        </Panel>
        <Panel title="Decision" testId="review-decision-panel">
          {r.status !== "pending" ? <div className="text-[13px] text-slate-600">This request is {r.status.replace(/_/g, " ")}.</div>
            : !data.can_decide ? <div className="text-[13px] text-slate-600" data-testid="review-cannot-decide">{data.is_requester ? "You requested this; you cannot decide it." : `Only ${r.assigned_role.toUpperCase()} (per decision rule) can act on this step.`}</div>
              : <>
                <SimulatedSignatureNote />
                <textarea className="input" rows={3} placeholder="Rationale (required, min 10 chars)" value={rationale} onChange={(e) => setRationale(e.target.value)} data-testid="review-rationale" />
                <div className="mt-2 flex flex-wrap gap-2">
                  {step.action === "decide" && <button className="btn-primary" onClick={() => act("approve")} data-testid="review-approve-btn">{data.signature_label}</button>}
                  {step.action === "endorse" && <button className="btn-primary" onClick={() => act("endorse")} data-testid="review-endorse-btn">Endorse (simulated signature – not CAC/PIV)</button>}
                  <button className="btn-secondary" onClick={() => act("return")} data-testid="review-return-btn">Return with comments</button>
                  <button className="btn-secondary" onClick={() => act("request_evidence")} data-testid="review-more-evidence-btn">Request more evidence</button>
                  <button className="btn-secondary" onClick={() => act("escalate")} data-testid="review-escalate-btn">Escalate</button>
                  <button className="btn-secondary border-rose-300 text-rose-700" onClick={() => act("reject")} data-testid="review-reject-btn">Reject</button>
                </div>
              </>}
          {msg && <div className="mt-2 text-[12px]" role="alert" data-testid="review-msg">{msg}</div>}
          <div className="mt-4 text-[12px] font-medium">Decision history</div>
          {data.decisions.map((d: Row) => <div key={d.id} className="border-b border-slate-100 py-1 text-[12px]" data-testid={`decision-${d.id}`}><b>{d.action}</b> by {d.decider_name} ({d.decider_email}; {(d.decider_roles || []).map((x: string) => x.toUpperCase()).join("/")}) · {d.decision_authority} · {fmtDate(d.created_at)}<div className="text-slate-600">{d.rationale}</div><div className="text-[10px] text-slate-400">{d.signature}</div></div>)}
        </Panel>
      </div>
    </div>
  );
}

export function FindingPage() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const { data, reload } = useApi<Row>(`/findings/${id}`);
  const [msg, setMsg] = useState("");
  if (!data) return null;
  const f = data.finding;
  const fp = async () => {
    const j = window.prompt("False-positive justification (min 10 chars)"); if (!j) return;
    try { await api.post(`/findings/${id}/request-false-positive`, { justification: j }); setMsg("False-positive review requested (ISSM decides)"); reload(); } catch (e) { setMsg(errorMessage(e)); }
  };
  return (
    <div data-testid="finding-page">
      <PageHeader title={`${f.vuln_id ?? f.plugin_id ?? f.rule_id} · ${f.title}`} subtitle={`${f.source_type} · ${f.cat ?? f.severity} · first seen ${fmtDate(f.first_seen_at)} · last seen ${fmtDate(f.last_seen_at)}`}>
        <S v={f.current_state} testId="finding-state" />{f.remediation_status && <S v={f.remediation_status} label="remediation" />}{f.disposition && <S v={f.disposition} />}
        {f.current_state === "open" && <AddToPoamButton findingId={f.id} onDone={reload} />}
        {f.current_state !== "open" && <span className="text-[11px] text-slate-500" data-testid="finding-passing-note">Passing / not-applicable result – evidence of compliance, not an open finding</span>}
        {can("finding.map") && !f.disposition && f.current_state === "open" && <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={fp} data-testid="request-false-positive-btn">Request false positive</button>}
      </PageHeader>
      {msg && <div className="panel mb-4 p-3 text-[13px]" data-testid="finding-msg">{msg}</div>}
      <div className="grid gap-5 xl:grid-cols-2">
        <ScoreBreakdown findingId={f.id} />
        <FindingMappingHistory findingId={f.id} />
        <Panel title="Asset" testId="finding-asset">{data.asset ? <div className="text-[13px]">{data.asset.name} · {data.asset.ip_address} · {data.asset.criticality} {data.asset.is_unmatched && <S v="unmatched" label="asset" />}</div> : "—"}</Panel>
        <Panel title="Controls (grouped, provenance)" testId="finding-controls">
          {data.controls.map((c: Row) => <div key={c.control_id} className="text-[12px]"><ControlLink systemId={f.system_id} controlId={c.control_id} /> {c.ccis.length > 0 && <span className="font-mono">via {c.ccis.join(", ")}</span>} <span className="text-slate-500">{c.review_status} · {c.sources.join("; ")}</span></div>)}
        </Panel>
        <Panel title="POA&M" testId="finding-poams">{data.poams.map((p: Row) => <div key={p.id} className="text-[12px]"><Link className="font-mono text-blue-800 underline" to={`/poams/${p.id}`}>{p.human_id}</Link> {p.weakness} <S v={p.status} /></div>)}{data.poams.length === 0 && "—"}</Panel>
        <Panel title="Reviews" testId="finding-reviews">{data.reviews.map((r: Row) => <div key={r.id} className="text-[12px]"><Link className="font-mono text-blue-800 underline" to={`/reviews/${r.id}`}>{r.human_id}</Link> {r.type_label} <S v={r.status} /></div>)}{data.reviews.length === 0 && "—"}</Panel>
        <Panel title={`Observation history (${data.observations.length})`} testId="finding-observations">
          <Table head={["Observed", "Status", "File"]}>{data.observations.map((o: Row) => <tr key={o.id}><td className="td font-mono text-[11px]">{fmtDate(o.observed_at)}</td><td className="td"><S v={o.observed_status} /></td><td className="td text-[12px]">{o.file_name}</td></tr>)}</Table>
        </Panel>
        <Panel title="Evidence" testId="finding-evidence">{data.evidence.map((e: Row) => <div key={e.id} className="text-[12px]"><Link to="/evidence-ledger" className="text-blue-800 underline">{e.name}</Link> · {e.sha256.slice(0, 12)}… <S v={e.state} /></div>)}</Panel>
      </div>
    </div>
  );
}
