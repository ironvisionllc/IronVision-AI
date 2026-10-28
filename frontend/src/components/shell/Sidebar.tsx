import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, ChevronRight, Lock } from "lucide-react";
import { activeNavId, NAV_GROUPS, NAV_ITEMS } from "@/lib/nav";
import { cn } from "@/lib/format";
import { SystemSelector } from "@/components/shell/SystemSelector";
import { useAuth } from "@/context/AuthContext";
import { STEP_STATUS, useActiveSystemId, useRmfSteps } from "@/components/rmf/Stepper";
import type { Row } from "@/lib/useApi";
import { deniedText, showDenied } from "@/components/common/RoleGate";
import { RecentlyViewed } from "@/components/shell/Recent";
import { GuidedToggle } from "@/components/common/Guided";

const APP_VERSION = process.env.REACT_APP_VERSION || "";

function Item({ id, label, path, icon: Icon, perm, active, sub }: Row) {
  const { can } = useAuth();
  if (perm && !can(perm)) return (
    <li><button type="button" className={cn("iv-nav-link group w-full cursor-not-allowed opacity-50", sub && "!pl-9 !text-[12px]")} data-testid={`nav-${id}`} title={deniedText(perm)} onClick={() => showDenied(perm)}>
      <Icon className="h-4 w-4 shrink-0 opacity-80" aria-hidden /><span className="flex-1 truncate text-left">{label}</span><Lock className="h-3 w-3" aria-label="needs another role" /></button></li>);
  return (
    <li><Link to={path} data-testid={`nav-${id}`} aria-current={active ? "page" : undefined} className={cn("iv-nav-link group", active && "is-active", sub && "!pl-9 !text-[12px]")}>
      <Icon className="h-4 w-4 shrink-0 opacity-80" aria-hidden /><span className="flex-1 truncate">{label}</span></Link></li>);
}

/** Global work items, the system dashboard and the 7 RMF steps (status dot + short status); only the open step shows its pages. */
export function Sidebar() {
  const active = activeNavId(useLocation().pathname);
  const activeGroup = NAV_ITEMS.find((n) => n.id === active)?.group;
  const [open, setOpen] = useState<string | null>(null);
  const { data } = useRmfSteps(useActiveSystemId());
  const status = (k?: string) => (k ? data?.steps.find((s: Row) => s.key === k) : undefined);
  const shown = open ?? activeGroup;
  return (
    <aside className="iv-sidebar flex w-64 shrink-0 flex-col" data-testid="sidebar">
      <SystemSelector />
      <nav className="flex-1 overflow-y-auto py-3" aria-label="Primary">
        {NAV_GROUPS.map((g) => {
          const items = NAV_ITEMS.filter((n) => n.group === g.key);
          const st = status(g.step);
          if (!g.step) return (
            <ul key={g.key} className="mb-2" data-testid={`nav-group-${g.key}`}>
              {items.filter((n) => !n.sub || activeGroup === g.key && active === n.id).map((n) => <Item key={n.id} {...n} active={active === n.id} />)}
            </ul>);
          const isOpen = shown === g.key;
          return (
            <div key={g.key} data-testid={`nav-group-${g.key}`}>
              <div className={cn("iv-nav-link group w-full !pr-1", activeGroup === g.key && "font-semibold")}>
                <Link to={g.path!} onClick={() => setOpen(g.key)} className="flex min-w-0 flex-1 items-center gap-2" data-testid={`nav-step-${g.key}`}
                  title={st ? `${g.help}\n${STEP_STATUS[st.status].label}: ${st.summary}` : g.help}>
                  <span className={cn("h-2 w-2 shrink-0 rounded-full", st ? STEP_STATUS[st.status].dot : "bg-slate-300")} data-testid={`nav-step-status-${g.key}`} data-status={st?.status} aria-label={st ? STEP_STATUS[st.status].label : "no system"} />
                  <span className="flex-1 truncate text-left">{g.label}</span>
                  {st && <span className="iv-sb-muted text-[10px]">{STEP_STATUS[st.status].short}</span>}
                </Link>
                <button type="button" onClick={() => setOpen(isOpen ? "__none" : g.key)} aria-expanded={isOpen} aria-label={`${isOpen ? "Collapse" : "Expand"} ${g.label}`} className="rounded p-1" data-testid={`nav-step-toggle-${g.key}`}>
                  {isOpen ? <ChevronDown className="h-3 w-3" aria-hidden /> : <ChevronRight className="h-3 w-3" aria-hidden />}</button>
              </div>
              {isOpen && <ul className="mb-1">{items.map((n) => <Item key={n.id} {...n} sub active={active === n.id} />)}</ul>}
            </div>);
        })}
        <RecentlyViewed />
        <div className="px-5 py-2 sm:hidden" data-testid="sidebar-guided"><GuidedToggle testId="guided-toggle-mobile" /></div>
      </nav>
      {APP_VERSION && <div className="iv-sb-muted border-t px-5 py-1.5 text-[10px]" style={{ borderColor: "var(--iv-sb-border)" }} data-testid="sidebar-footer">v{APP_VERSION}</div>}
    </aside>
  );
}
