import { Link, useLocation } from "react-router-dom";
import { activeNavId, NAV_ITEMS } from "@/lib/nav";
import { cn } from "@/lib/format";
import { SystemSelector } from "@/components/shell/SystemSelector";

export function Sidebar() {
  const active = activeNavId(useLocation().pathname);
  return (
    <aside className="iv-sidebar flex w-64 shrink-0 flex-col" data-testid="sidebar">
      <SystemSelector />
      <nav className="flex-1 overflow-y-auto py-3" aria-label="Primary">
        <div className="t-label iv-sb-muted px-5 pb-2 !text-[10px]">Workspace</div>
        <ul>
          {NAV_ITEMS.map(({ id, label, path, icon: Icon, phase }) => (
            <li key={id}>
              <Link to={path} data-testid={`nav-${id}`} aria-current={active === id ? "page" : undefined} className={cn("iv-nav-link group", active === id && "is-active")}>
                <Icon className="h-4 w-4 shrink-0 opacity-80" aria-hidden />
                <span className="flex-1 truncate">{label}</span>
                {phase !== null && <span className="iv-sb-muted rounded border border-current/30 px-1.5 text-[10px] font-medium">P{phase}</span>}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="iv-sb-muted border-t px-5 py-3 text-[10px] leading-relaxed" style={{ borderColor: "var(--iv-sb-border)" }} data-testid="sidebar-footer">
        Phase 5 · Production Hardening
        <br />
        Synthetic tenant only
      </div>
    </aside>
  );
}
