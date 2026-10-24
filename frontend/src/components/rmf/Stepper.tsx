import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, ChevronDown, ChevronRight, X } from "lucide-react";
import { MUTATED_EVENT } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { cn } from "@/lib/format";
import { useSystems } from "@/context/SystemContext";
import { useAuth } from "@/context/AuthContext";

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
    <ol className={cn("flex items-center gap-1.5", compact ? "min-w-0 flex-nowrap whitespace-nowrap" : "mb-5 flex-wrap")} data-testid="rmf-stepper" aria-label="RMF steps">
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

// Start and dashboard pages only; the Getting started page says the same thing in its body, and RMF step pages have their own stepper.
const BAR_PATHS = ["/controls", "/systems", "/portfolio"];
const prefKey = (uid: string) => `iv-next-bar:${uid}`;

function useBarPref(uid: string | undefined, action: string) {
  const read = (): Row => { try { return uid ? JSON.parse(localStorage.getItem(prefKey(uid)) || "{}") : {}; } catch { return {}; } };
  const [pref, setPref] = useState<Row>(read);
  useEffect(() => { setPref(read()); }, [uid]);  // eslint-disable-line react-hooks/exhaustive-deps
  const save = (p: Row) => { setPref(p); if (uid) localStorage.setItem(prefKey(uid), JSON.stringify(p)); };
  return { dismissed: pref.dismissed === action, collapsed: !!pref.collapsed,
    dismiss: () => save({ ...pref, dismissed: action }), toggle: () => save({ ...pref, collapsed: !pref.collapsed }) };
}

/** Getting started / next action bar: Start + dashboard pages only, collapsible to one line, dismissible per user until the next action changes. */
export function RmfBar() {
  const { systems, loaded } = useSystems();
  const { user } = useAuth();
  const { pathname } = useLocation();
  const sid = useActiveSystemId();
  const { data } = useRmfSteps(sid);
  const next = !systems.length ? { label: "Register your first system", link: "/systems/new" } : data?.next_action;
  const p = useBarPref(user ? user.id : undefined, next ? `${sid ?? "none"}:${next.label}` : "");
  if (!loaded || !next || !BAR_PATHS.includes(pathname) || p.dismissed) return null;
  const go = <Link to={next.link} className="font-semibold text-blue-800 underline-offset-2 hover:underline" data-testid="rmf-next-action">Next: {next.label} →</Link>;
  return (
    <div className="flex min-h-[32px] flex-nowrap items-center gap-3 overflow-x-auto border-b border-blue-100 bg-blue-50/60 px-3 py-1 text-[12px] sm:px-6" data-testid="rmf-bar">
      <button type="button" onClick={p.toggle} aria-expanded={!p.collapsed} aria-label={p.collapsed ? "Show RMF steps" : "Collapse to one line"} className="shrink-0 text-slate-600" data-testid="rmf-bar-toggle">
        {p.collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}</button>
      {!p.collapsed && (!systems.length
        ? <span className="whitespace-nowrap text-slate-600">ATO work follows 7 RMF steps – {RMF_STEP_NAMES.join(" → ")}. <Link to="/rmf-workflow" className="text-blue-800 underline" data-testid="rmf-bar-guide">How the 7 steps work</Link></span>
        : data && <><span className="shrink-0 font-semibold text-slate-800" title="The RMF steps are for this system – change it in the sidebar">{data.system.acronym || data.system.name}</span><StepChips steps={data.steps} compact /></>)}
      <span className={cn("shrink-0 whitespace-nowrap", !p.collapsed && "ml-auto")}>{go}</span>
      <button type="button" onClick={p.dismiss} aria-label="Dismiss until the next action changes" title="Dismiss until the next action changes" className="ml-auto shrink-0 text-slate-500 hover:text-slate-800" data-testid="rmf-bar-dismiss"><X className="h-3.5 w-3.5" /></button>
    </div>);
}
