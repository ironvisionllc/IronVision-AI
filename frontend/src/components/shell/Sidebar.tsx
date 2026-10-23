import { Link, useLocation } from "react-router-dom";
import { activeNavId, NAV_GROUPS, NAV_ITEMS } from "@/lib/nav";
import { cn } from "@/lib/format";
import { SystemSelector } from "@/components/shell/SystemSelector";
import { useAuth } from "@/context/AuthContext";
import { STEP_STATUS, useActiveSystemId, useRmfSteps } from "@/components/rmf/Stepper";
import type { Row } from "@/lib/useApi";

export function Sidebar() {
  const active = activeNavId(useLocation().pathname);
  const { can } = useAuth();
  const { data } = useRmfSteps(useActiveSystemId());
  const status = (k?: string) => (k ? data?.steps.find((s: Row) => s.key === k) : undefined);
  return (
    <aside className="iv-sidebar flex w-64 shrink-0 flex-col" data-testid="sidebar">
      <SystemSelector />
      <nav className="flex-1 overflow-y-auto py-3" aria-label="Primary">
        {NAV_GROUPS.map((g) => {
          const items = NAV_ITEMS.filter((n) => n.group === g.key && (!n.perm || can(n.perm)));
          const st = status(g.step);
          return (
            <div key={g.key} className="mb-2" data-testid={`nav-group-${g.key}`}>
              <div className="t-label iv-sb-muted flex items-center gap-1.5 px-5 pb-1 pt-1 !text-[10px]" title={st ? `${g.help}\n${STEP_STATUS[st.status].label}: ${st.summary}` : g.help}>
                {st && <span className={cn("h-1.5 w-1.5 rounded-full", STEP_STATUS[st.status].dot)} data-testid={`nav-step-status-${g.key}`} data-status={st.status} aria-label={STEP_STATUS[st.status].label} />}
                {g.label}
              </div>
              <ul>
                {items.map(({ id, label, path, icon: Icon, phase }) => (
                  <li key={id}>
                    <Link to={path} data-testid={`nav-${id}`} aria-current={active === id ? "page" : undefined} className={cn("iv-nav-link group", active === id && "is-active")}>
                      <Icon className="h-4 w-4 shrink-0 opacity-80" aria-hidden />
                      <span className="flex-1 truncate">{label}</span>
                      {phase !== null && <span className="iv-sb-muted rounded border border-current/30 px-1.5 text-[10px] font-medium">P{phase}</span>}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>);
        })}
      </nav>
      <div className="iv-sb-muted border-t px-5 py-3 text-[10px] leading-relaxed" style={{ borderColor: "var(--iv-sb-border)" }} data-testid="sidebar-footer">
        Phase 5 · Production Hardening
        <br />
        Synthetic tenant only
      </div>
    </aside>
  );
}
