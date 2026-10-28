import { Link } from "react-router-dom";
import { Panel } from "@/components/common/Panel";
import { StatusChip } from "@/components/common/StatusChip";
import { DIM_HELP, DIM_LABEL, Dim, GLOSSARY } from "@/lib/glossary";

/** Help hub: documentation, the RMF overview and the status glossary in one place (R7 Help merge). */
export function HelpTopics() {
  return (
    <Panel title="Help topics" testId="help-topics">
      <div className="flex flex-wrap gap-2 text-[13px]">
        <Link className="btn-secondary" to="/docs-center" data-testid="help-docs-link">Documentation</Link>
        <Link className="btn-secondary" to="/rmf-workflow" data-testid="help-rmf-link">RMF overview</Link>
        <a className="btn-secondary" href="#help-glossary" data-testid="help-glossary-link">Status glossary</a>
        <a className="btn-secondary" href="#role-matrix" data-testid="help-roles-link">Who can do what</a>
      </div>
      <div id="help-glossary" className="mt-4 space-y-3" data-testid="help-glossary">
        {(Object.keys(GLOSSARY) as Dim[]).map((d) => (
          <div key={d} data-testid={`help-glossary-${d}`}>
            <div className="text-[13px] font-semibold text-slate-900">{DIM_LABEL[d]}</div>
            <div className="text-[12px] text-slate-600">{DIM_HELP[d]}</div>
            <div className="mt-1 flex flex-wrap gap-1.5">{Object.keys(GLOSSARY[d]).map((v) => <StatusChip key={v} dim={d} v={v} />)}</div>
          </div>))}
      </div>
    </Panel>);
}
