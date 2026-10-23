import { useEffect } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { MUTATED_EVENT } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { cn } from "@/lib/format";
import { useSystems } from "@/context/SystemContext";

export const STEP_STATUS: Record<string, { label: string; dot: string; chip: string }> = {
  complete: { label: "Complete", dot: "bg-emerald-500", chip: "border-emerald-300 bg-emerald-50 text-emerald-900" },
  needs_attention: { label: "Needs attention", dot: "bg-amber-500", chip: "border-amber-300 bg-amber-50 text-amber-900" },
  not_started: { label: "Not started", dot: "bg-slate-300", chip: "border-slate-200 bg-white text-slate-600" },
};
const STEP_PATH: Record<string, string> = { prepare: "/rmf/prepare", categorize: "/rmf/categorize", select: "/rmf/select", implement: "/rmf/implement",
  assess: "/rmf/assess", authorize: "/rmf/authorize", monitor: "/rmf/monitor" };
export const RMF_STEP_NAMES = ["Prepare", "Categorize", "Select", "Implement", "Assess", "Authorize", "Monitor"];

export function useRmfSteps(sid: string | null) {
  const r = useApi<Row>(sid ? `/systems/${sid}/rmf-steps` : null);
  const { reload } = r;
  useEffect(() => {
    let t: ReturnType<typeof setTimeout> | undefined;
    const later = () => { clearTimeout(t); t = setTimeout(reload, 700); };
    window.addEventListener(MUTATED_EVENT, later);
    return () => { clearTimeout(t); window.removeEventListener(MUTATED_EVENT, later); };
  }, [reload]);
  return r;
}

export function useActiveSystemId(): string | null {
  const { selectedId, systems } = useSystems();
  return selectedId && systems.some((s) => s.id === selectedId) ? selectedId : null;
}

const tip = (s: Row) => `${STEP_STATUS[s.status]?.label}: ${s.summary}\n\nHow this is decided: ${s.criteria}`;

export function StepChips({ steps, compact }: { steps: Row[]; compact?: boolean }) {
  return (
    <ol className={cn("flex flex-wrap items-center gap-1.5", !compact && "mb-5")} data-testid="rmf-stepper" aria-label="RMF steps">
      {steps.map((s, i) => (
        <li key={s.key} className="flex items-center gap-1.5">
          {i > 0 && <span className="text-slate-300" aria-hidden>›</span>}
          <Link to={STEP_PATH[s.key]} title={tip(s)} data-testid={`rmf-step-${s.key}`} data-status={s.status}
            className={cn("flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium hover:shadow-sm", STEP_STATUS[s.status]?.chip)}>
            <span className={cn("h-2 w-2 rounded-full", STEP_STATUS[s.status]?.dot)} aria-hidden />
            {s.number} {s.label}{!compact && <span className="sr-only"> – {STEP_STATUS[s.status]?.label}</span>}
          </Link>
        </li>))}
    </ol>);
}

export function NextActionButton({ data, className }: { data: Row; className?: string }) {
  const n = data.next_action;
  return <Link to={n.link} className={cn("btn-primary inline-flex items-center gap-1.5", className)} data-testid="rmf-next-action"
    title={`Next RMF step: ${n.step}`}>Next action: {n.label}<ArrowRight className="h-3.5 w-3.5" /></Link>;
}

/** Replaces the old 3-step "Get started" bar: always shows where the selected system is in the 7 RMF steps and the next task. */
export function RmfBar() {
  const { systems, loaded } = useSystems();
  const sid = useActiveSystemId();
  const { data } = useRmfSteps(sid);
  if (!loaded) return null;
  if (!systems.length) return (
    <div className="flex flex-wrap items-center gap-3 border-b border-blue-100 bg-blue-50/60 px-6 py-2 text-[12px]" data-testid="rmf-bar">
      <b>Getting started:</b>
      <span className="text-slate-600">ATO work follows 7 RMF steps – {RMF_STEP_NAMES.join(" → ")}. Start by registering the system you are authorizing.</span>
      <Link to="/systems/new" className="btn-primary px-2.5 py-1 text-[12px]" data-testid="rmf-next-action">Next action: Register your first system</Link>
      <Link to="/rmf-workflow" className="text-blue-800 underline" data-testid="rmf-bar-guide">How the 7 steps work</Link>
    </div>);
  if (!data) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-blue-100 bg-blue-50/60 px-6 py-1.5 text-[12px]" data-testid="rmf-bar">
      <span className="font-semibold text-slate-800" title="The RMF steps below are for this system – change it in the sidebar">{data.system.acronym || data.system.name}</span>
      <StepChips steps={data.steps} compact />
      <NextActionButton data={data} className="ml-auto px-2.5 py-1 text-[12px]" />
    </div>);
}
