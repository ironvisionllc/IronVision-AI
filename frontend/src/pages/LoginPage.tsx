import { FormEvent, useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { KeyRound, ShieldAlert, UserRound } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";
import type { AuthProviderInfo } from "@/lib/types";
import { cn } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/nav";
import { SyntheticBanner } from "@/components/shell/SyntheticBanner";
import { BrandLockup, BrandMark, ThemeToggle, Wordmark } from "@/components/shell/Brand";

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [info, setInfo] = useState<AuthProviderInfo | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pwRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.get<AuthProviderInfo>("/auth/provider").then((r) => setInfo(r.data)).catch(() => setInfo(null));
  }, []);

  if (user) return <Navigate to="/controls" replace />;

  const pick = (addr: string) => {
    setEmail(addr);
    setError("");
    pwRef.current?.focus();
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      sessionStorage.removeItem("aegis.switch_user");
      navigate("/controls", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col" data-testid="login-page">
      <SyntheticBanner />
      <div className="grid min-h-0 flex-1 lg:grid-cols-[1.05fr_1fr]">
        <aside className="iv-hero relative hidden flex-col items-center justify-center overflow-hidden px-14 py-12 lg:flex" data-testid="login-hero">
          <div className="pointer-events-none absolute inset-0 opacity-[0.5]" style={{ backgroundImage: "linear-gradient(var(--iv-hero-grid) 1px, transparent 1px), linear-gradient(90deg, var(--iv-hero-grid) 1px, transparent 1px)", backgroundSize: "44px 44px" }} />
          <div className="relative flex max-w-md flex-col items-center text-center">
            <BrandLockup className="w-72" />
            <div className="mt-5 font-heading text-[2.6rem] font-extrabold leading-none tracking-[0.18em]" data-testid="login-brand" aria-label="IronVision AI">
              <span className="sr-only">IronVision </span><span className="iv-wordmark-ai">AI</span>
            </div>
            <h1 className="t-title mt-6 text-slate-900" data-testid="login-tagline">Intelligent Risk. <span className="text-blue-700">Continuous Assurance.</span></h1>
            <p className="t-caption mt-3 text-slate-600">
              RMF automation for ISSOs, ISSMs, assessors and authorizing officials — grounded in pinned, hash-verified NIST SP 800-53 Rev 5 and DISA CCI reference content.
            </p>
            <div className="t-label mt-8 !text-[10px]">Phase 5 · Production Hardening</div>
          </div>
        </aside>

        <main className="relative flex items-center justify-center overflow-y-auto px-6 py-10">
          <ThemeToggle className="absolute right-5 top-4" />
          <div className="w-full max-w-md animate-fade-up">
            <div className="mb-6 flex items-center gap-2.5 lg:hidden"><BrandMark /><Wordmark className="text-lg" /></div>
            {info?.oidc_enabled && <a className="btn-primary mb-4 w-full justify-center py-2.5" href={`${process.env.REACT_APP_BACKEND_URL}/api/v1/auth/oidc/login`} data-testid="oidc-login-btn">Sign in with enterprise SSO (OIDC)</a>}
            {info && !info.dev_password_enabled && !info.oidc_enabled && <div className="panel p-4 text-[13px]" data-testid="external-auth-note">Sign-in is handled by {info.label}. Password sign-in is disabled.</div>}
            {(!info || info.dev_password_enabled) && <>
            <div className="mb-4 flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2.5 text-[12px] font-bold uppercase tracking-wide text-amber-900" data-testid="dev-auth-label">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              {info?.label ?? "DEVELOPMENT AUTHENTICATION – SIMULATED, NOT CAC/PIV"}
            </div>
            <form onSubmit={submit} className="panel p-7" data-testid="login-form">
              <h2 className="t-title text-slate-900">Sign in</h2>
              <p className="t-caption mt-1 text-slate-600">Provider: <span className="font-mono text-[12px]">{info?.provider ?? "…"}</span></p>
              <label className="t-label mt-6 block" htmlFor="email">Email</label>
              <input id="email" type="email" autoComplete="username" required className="input mt-1.5" value={email}
                onChange={(e) => setEmail(e.target.value)} data-testid="login-email-input" />
              <label className="t-label mt-4 block" htmlFor="password">Password</label>
              <input id="password" ref={pwRef} type="password" autoComplete="current-password" required className="input mt-1.5"
                value={password} onChange={(e) => setPassword(e.target.value)} data-testid="login-password-input" />
              {error && <div role="alert" className="mt-3 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-[13px] text-rose-800" data-testid="login-error">{error}</div>}
              <button type="submit" disabled={busy} className="btn-primary mt-6 w-full justify-center py-2.5" data-testid="login-submit-btn">
                <KeyRound className="h-4 w-4" aria-hidden /> {busy ? "Signing in…" : "Sign in"}
              </button>
            </form>
            {info?.is_simulated && info.dev_accounts.length > 0 && (
              <DevPicker accounts={info.dev_accounts} selected={email} onPick={pick} highlight={location.search.includes("switch") || sessionStorage.getItem("aegis.switch_user") === "1"} />
            )}
            </>}
          </div>
        </main>
      </div>
    </div>
  );
}

function DevPicker({ accounts, selected, onPick, highlight }: {
  accounts: AuthProviderInfo["dev_accounts"]; selected: string; onPick: (e: string) => void; highlight: boolean;
}) {
  return (
    <div className={cn("panel mt-4 p-4", highlight && "ring-2 ring-blue-500/30")} data-testid="dev-user-picker">
      <div className="flex items-center justify-between">
        <div className="eyebrow">Switch user (dev only)</div>
        <span className="text-[11px] text-slate-500">{accounts.length} synthetic accounts</span>
      </div>
      <p className="mt-1 text-[12px] text-slate-500">Selecting fills the email; enter the documented dev password.</p>
      <ul className="mt-3 grid grid-cols-2 gap-1.5">
        {accounts.map((a) => (
          <li key={a.email}>
            <button type="button" onClick={() => onPick(a.email)} data-testid={`dev-user-option-${a.role}`}
              className={cn("flex w-full items-center gap-2 rounded-lg border px-2 py-1.5 text-left transition-colors duration-150",
                selected === a.email ? "border-blue-500 bg-blue-50" : "bg-surface border-slate-200 hover:border-blue-300 hover:bg-blue-50")}>
              <UserRound className="h-3.5 w-3.5 shrink-0 text-blue-700" aria-hidden />
              <span className="min-w-0">
                <span className="block truncate font-heading text-[12px] font-semibold text-slate-800">{ROLE_LABELS[a.role] ?? a.role_label}</span>
                <span className="block truncate font-mono text-[10px] text-slate-500">{a.email}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
