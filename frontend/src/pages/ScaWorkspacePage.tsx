import { Link, useNavigate, useParams } from "react-router-dom";
import { PageHeader, Panel } from "@/components/common/Panel";
import { useActiveSystemId } from "@/components/rmf/Stepper";
import { NeedSystem } from "@/components/common/Bits";
import { StatusChip } from "@/components/common/StatusChip";
import { AssessmentPanel } from "@/pages/Phase3Extras";
import { GuidedPanel } from "@/components/common/Guided";
import { useApi, Row } from "@/lib/useApi";
import { cn, fmtDate } from "@/lib/format";

const FLOW = ["1 Select control", "2 Review evidence", "3 Record determination", "4 Save → next"];

/** SCA workspace: one queue (not-assessed controls) → evidence + implementation + imported eMASS test results → existing AssessmentPanel. */
export default function ScaWorkspacePage() {
  const sid = useActiveSystemId();
  const { controlId } = useParams();
  const nav = useNavigate();
  const { data: list, reload } = useApi<Row[]>(sid ? `/systems/${sid}/workbench/controls` : null, { assessment_status: "not_assessed" });
  const { data: tr } = useApi<Row[]>(sid ? `/systems/${sid}/tr/workbooks` : null);
  const { data: d, reload: reloadD } = useApi<Row>(sid && controlId ? `/systems/${sid}/workbench/controls/${controlId}` : null);
  if (!sid) return <NeedSystem />;
  const queue = list || [];
  const next = () => { const i = queue.findIndex((a) => a.control_id === controlId); const n = queue[i + 1] ?? queue[0]; reload(); reloadD(); if (n) nav(`/assess/workspace/${n.control_id}`); };
  const trs = (Array.isArray(tr) ? tr : (tr as unknown as Row | undefined)?.items || []) as Row[];
  return (
    <div data-testid="sca-workspace-page">
      <PageHeader title="SCA workspace" subtitle="Independent assessment: select a control, review its evidence, record the determination, save and move to the next." />
      <GuidedPanel step="assess" />
      <ol className="mb-4 flex flex-wrap gap-2" data-testid="sca-flow">{FLOW.map((f, i) => <li key={f} className={cn("min-w-[10rem] flex-1 whitespace-nowrap rounded-lg px-2 py-1.5 text-center text-[12px] font-semibold",
        (controlId ? (i <= 2) : i === 0) ? "bg-sky-700 text-white" : "bg-slate-100 text-slate-600")}>{f}</li>)}</ol>
      {trs.length > 0 && <div className="mb-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-[12px] text-sky-900" data-testid="sca-tr-imports">
        Imported test results ({trs.length} workbook{trs.length > 1 ? "s" : ""}, historical – they never change a determination by themselves):{" "}
        {trs.slice(0, 3).map((w) => <Link key={w.id} className="mr-2 underline" to={`/test-results?workbook=${w.id}`}>{w.file_name || w.name} {w.row_count ?? w.rows ? ` (${w.row_count ?? w.rows} rows)` : ""}</Link>)}</div>}
      <div className="grid gap-4 xl:grid-cols-[300px_1fr]">
        <Panel title={`Queue – not assessed (${queue.length})`} testId="sca-queue">
          <ul className="max-h-[620px] overflow-y-auto text-[12px]">{queue.slice(0, 400).map((a) => <li key={a.control_id}>
            <button className={cn("w-full border-b border-slate-100 px-2 py-1.5 text-left hover:bg-sky-50", a.control_id === controlId && "bg-sky-50 font-semibold")} onClick={() => nav(`/assess/workspace/${a.control_id}`)} data-testid={`sca-item-${a.control_id}`}>
              <span className="block font-mono text-sky-800">{a.label}</span><span className="block text-slate-600">{a.title}</span></button></li>)}</ul>
        </Panel>
        {!controlId || !d ? <div className="panel p-6 text-[13px] text-slate-500" data-testid="sca-empty">Select a control from the queue.</div> : (
          <div className="space-y-3" data-testid="sca-control">
            <Panel testId="sca-control-header"><div className="flex flex-wrap items-center gap-2"><b className="font-mono text-lg text-sky-800">{d.catalog.label}</b><span>{d.catalog.title}</span>
              <span className="ml-auto flex flex-wrap gap-1.5"><StatusChip dim="implementation" v={d.assignment.implementation_status} showDim /><StatusChip dim="assessment" v={d.assignment.assessment_status} showDim />
                <StatusChip dim="freshness" v={d.assignment.evidence_freshness_status} showDim /></span></div></Panel>
            <div className="grid gap-3 lg:grid-cols-2">
              <Panel title="Implementation (by the ISSO – read-only here)" testId="sca-implementation">
                <div className="whitespace-pre-wrap text-[12px]">{(d.implementations || [])[0]?.text || (d.approved_implementation?.text) || "No implementation statement yet."}</div></Panel>
              <Panel title={`Evidence (${d.evidence.length})`} testId="sca-evidence">
                <ul className="text-[12px]">{d.evidence.slice(0, 10).map((e: Row) => <li key={e.id} className="border-b border-slate-100 py-1">{e.name} · {e.source_name} · {fmtDate(e.collected_at)} <span className="font-mono text-[10px]">{e.sha256.slice(0, 10)}…</span></li>)}
                  {d.evidence.length === 0 && <li className="text-slate-500">No evidence attached.</li>}</ul>
                {d.open_findings.length > 0 && <div className="mt-2 text-[12px] text-rose-700">{d.open_findings.length} open finding(s) – <Link className="underline" to={`/systems/${sid}/controls/${controlId}?tab=findings`}>view</Link></div>}</Panel>
            </div>
            <Panel title="Record determination" testId="sca-determination"><AssessmentPanel systemId={sid} controlId={controlId} objectives={d.catalog.objectives} onDone={next} /></Panel>
          </div>)}
      </div>
    </div>);
}
