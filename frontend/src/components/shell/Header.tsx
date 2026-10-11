import { LogOut, ShieldAlert, Users } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ROLE_LABELS } from "@/lib/nav";
import { NotificationBell } from "@/components/common/Workflow";
import { GlobalSearch } from "@/pages/Phase3Extras";
import { BrandMark, TAGLINE, ThemeToggle, Wordmark } from "@/components/shell/Brand";

export function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const switchUser = async () => {
    sessionStorage.setItem("aegis.switch_user", "1");
    await logout();
    navigate("/login?switch=1", { replace: true });
  };
  const sysRoles = user.roles.filter((r) => r.scope_type === "system");

  return (
    <header className="iv-header relative z-30 flex shrink-0 items-center justify-between gap-4 px-6 py-2.5" data-testid="app-header">
      <div className="flex items-center gap-3">
        <BrandMark className="h-9 w-9" />
        <div className="leading-tight">
          <div className="text-[17px]" data-testid="brand-title"><Wordmark /></div>
          <div className="t-label !text-[10px] !tracking-[0.08em]" data-testid="brand-tagline">{TAGLINE}</div>
        </div>
      </div>
      <div className="flex min-w-0 items-center gap-2.5">
        <GlobalSearch />
        {user.auth_is_simulated && (
          <span data-testid="dev-auth-indicator" className="hidden items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-amber-800 xl:inline-flex">
            <ShieldAlert className="h-3 w-3" aria-hidden /> Dev auth – simulated, not CAC/PIV
          </span>
        )}
        <div className="hidden text-right leading-tight md:block" data-testid="current-user">
          <div className="font-heading text-[13px] font-semibold text-slate-900" data-testid="current-user-name">{user.display_name}</div>
          <div className="text-[11px] text-slate-500" data-testid="current-user-email">{user.email}</div>
        </div>
        <div className="hidden gap-1 lg:flex" data-testid="current-user-roles">
          {user.roles.filter((r) => r.scope_type === "org").map((r) => (
            <span key={`${r.role}-${r.scope_id}`} className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-0.5 text-[11px] font-semibold text-blue-800">
              {ROLE_LABELS[r.role] ?? r.role}
              <span className="ml-1 font-normal text-blue-700">· {r.scope_type}</span>
            </span>
          ))}
          {sysRoles.length > 0 && (
            <span className="rounded-full border border-slate-300 px-2.5 py-0.5 text-[11px] text-slate-600" data-testid="system-role-count"
              title={sysRoles.map((r) => ROLE_LABELS[r.role] ?? r.role).join(", ")}>
              +{sysRoles.length} system roles
            </span>
          )}
        </div>
        <NotificationBell />
        <ThemeToggle />
        <button type="button" onClick={switchUser} data-testid="header-switch-user-btn" className="btn-secondary px-2.5 py-1 text-xs">
          <Users className="h-3.5 w-3.5" aria-hidden /> Switch user (dev only)
        </button>
        <button type="button" onClick={logout} data-testid="header-logout-btn" aria-label="Sign out" title="Sign out" className="btn-ghost px-2 py-1.5">
          <LogOut className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </header>
  );
}
