import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Compass, KeyRound, ShieldAlert } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";
import type { Row } from "@/lib/useApi";
import type { AuthProviderInfo } from "@/lib/types";
import { SyntheticBanner } from "@/components/shell/SyntheticBanner";
import { BrandLockup, BrandMark, ThemeToggle, Wordmark } from "@/components/shell/Brand";

const OIDC_ERRORS: Record<string, string> = {
  idp: "Single sign-on did not complete. Please try again.",
  registration_email_exists: "This email belongs to an existing account; contact the administrator.",
  registration_reserved: "This username or email is reserved. Please register with your own email address.",
  registration_rate_limited: "Too many new accounts from this network. Please try again later.",
  registration_invalid: "Registration needs a valid email address.",
  registration_unavailable: "Account creation is temporarily unavailable. Please try again in a minute.",
};

export default function LoginPage() {
  const oidcError = new URLSearchParams(window.location.search).get("oidc_error");
  const { user, login, demoLogin } = useAuth();
  const navigate = useNavigate();
  const [info, setInfo] = useState<AuthProviderInfo | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [note, setNote] = useState("");
  const pwRef = useRef<HTMLInputElement>(null);
  const [demoErr, setDemoErr] = useState("");

  useEffect(() => {
    api.get<AuthProviderInfo>("/auth/provider").then((r) => setInfo(r.data)).catch(() => setInfo(null));
  }, []);

  if (user) return <Navigate to="/controls" replace />;

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

  const demo = async () => {
    setBusy(true); setDemoErr("");
    try { await demoLogin(); navigate("/controls", { replace: true }); } catch (err) { setDemoErr(errorMessage(err)); } finally { setBusy(false); }
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
            
          </div>
        </aside>

        <main className="relative flex items-center justify-center overflow-y-auto px-6 py-10">
          <ThemeToggle className="absolute right-5 top-4" />
          <div className="w-full max-w-md animate-fade-up">
            <div className="mb-6 flex items-center gap-2.5 lg:hidden"><BrandMark /><Wordmark className="text-lg" /></div>
            {oidcError && <div role="alert" className="mb-4 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-[13px] text-rose-800" data-testid="oidc-error">{OIDC_ERRORS[oidcError] ?? OIDC_ERRORS.idp}</div>}
            {info?.oidc_enabled && <div className="panel p-7" data-testid="oidc-block">
              <h2 className="t-title text-slate-900">Sign in</h2>
              <a className="btn-primary mt-5 w-full justify-center py-2.5" href={`${process.env.REACT_APP_BACKEND_URL}/api/v1/auth/oidc/login`} data-testid="oidc-login-btn"><KeyRound className="h-4 w-4" aria-hidden /> Sign in</a>
              {info.registration_enabled && <a className="btn-secondary mt-3 w-full justify-center py-2.5" href={`${process.env.REACT_APP_BACKEND_URL}/api/v1/auth/oidc/register`} data-testid="oidc-register-btn">Create account</a>}
              {info.registration_enabled && <div className="mt-1.5 text-center text-[11px] text-slate-500" data-testid="oidc-register-caption">Free private sandbox · clean workspace · deleted after 30 days without activity</div>}
            </div>}
            {info && !info.dev_password_enabled && !info.oidc_enabled && <div className="panel p-4 text-[13px]" data-testid="external-auth-note">Sign-in is handled by {info.label}. Password sign-in is disabled.</div>}
            {(!info || info.dev_password_enabled) && <>
            <div className="mb-4 flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2.5 text-[12px] font-bold uppercase tracking-wide text-amber-900" data-testid="dev-auth-label">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              {info?.label ?? "DEVELOPMENT AUTHENTICATION – SIMULATED, NOT CAC/PIV"}
            </div>
            {note && <div className="mb-3 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-[13px] text-emerald-800" data-testid="signup-success">{note}</div>}
            {mode === "login" && <form onSubmit={submit} className="panel p-7" data-testid="login-form">
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
            </form>}
            </>}
            {mode === "login" && info?.demo_login_enabled && <div className="mt-4 text-center" data-testid="demo-login-block">
              <div className="mb-3 flex items-center gap-3 text-[11px] uppercase tracking-wide text-slate-400"><span className="h-px flex-1 bg-slate-200" />or<span className="h-px flex-1 bg-slate-200" /></div>
              <button type="button" disabled={busy} className="btn-secondary w-full justify-center py-2.5" onClick={demo} data-testid="demo-login-btn">
                <Compass className="h-4 w-4" aria-hidden /> {busy ? "Opening demo…" : "Explore the demo – no sign-up"}
              </button>
              <div className="mt-1.5 text-[11px] text-slate-500" data-testid="demo-login-caption">Synthetic data · shared demo workspace · resets nightly</div>
              {demoErr && <div role="alert" className="mt-2 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-[13px] text-rose-800" data-testid="demo-login-error">{demoErr}</div>}
            </div>}
            {info?.dev_password_enabled && info?.signup_enabled && (mode === "signup" ? <><SignupForm onDone={(e) => { setEmail(e); setMode("login"); setNote("Account created – your private sandbox is being prepared. Sign in to continue."); }} />
              <button type="button" className="mt-3 w-full text-center text-[13px] text-blue-800 underline" onClick={() => setMode("login")} data-testid="show-login-btn">I already have an account – sign in</button></>
              : <button type="button" className="mt-4 w-full text-center text-[13px] text-blue-800 underline" onClick={() => setMode("signup")} data-testid="show-signup-btn">New here? Create a free sandbox account</button>)}
            <footer className="mt-8 border-t border-slate-200 pt-3 text-center text-[12px] text-slate-500" data-testid="login-footer">
              <Link to="/whitepaper" className="text-blue-800 underline" data-testid="login-whitepaper-link">Read the IronVision AI whitepaper (PDF / DOCX)</Link>
            </footer>
          </div>
        </main>
      </div>
    </div>
  );
}

function SignupForm({ onDone }: { onDone: (email: string) => void }) {
  const [f, setF] = useState({ name: "", email: "", password: "", organization: "", iv_hp_fax_only: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState<Row | null>(null);
  useEffect(() => { api.get<Row>("/auth/signup/start").then((r) => setToken({ ...r.data, at: Date.now() })).catch(() => setToken(null)); }, []);
  const rules = [["12+ characters", f.password.length >= 12], ["a lowercase letter", /[a-z]/.test(f.password)], ["an uppercase letter", /[A-Z]/.test(f.password)],
    ["a digit", /\d/.test(f.password)], ["a symbol", /[^A-Za-z0-9]/.test(f.password)],
    ["not your email name", !(f.email.split("@")[0].length >= 3 && f.password.toLowerCase().includes(f.email.split("@")[0].toLowerCase()))]] as const;
  const pwOk = rules.every(([, ok]) => ok);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!pwOk) { setErr("Password needs: " + rules.filter(([, ok]) => !ok).map(([l]) => l).join(", ")); return; }
    setBusy(true); setErr("");
    try {
      const wait = token ? Number(token.min_seconds) * 1000 - (Date.now() - token.at) : 0;  // client clock only: no skew
      if (wait > 0) await new Promise((r) => setTimeout(r, wait + 100));  // very fast autofill+submit: wait out the minimum instead of failing
      await api.post("/auth/signup", { ...f, form_token: token?.form_token });
      onDone(f.email);
    } catch (x) {
      setErr(errorMessage(x));
      api.get<Row>("/auth/signup/start").then((r) => setToken({ ...r.data, at: Date.now() })).catch(() => undefined);
    } finally { setBusy(false); }
  };
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <form onSubmit={submit} className="panel p-7" data-testid="signup-form">
      <h2 className="t-title text-slate-900">Create a sandbox account</h2>
      <p className="t-caption mt-1 text-slate-600">You get a private sandbox with a copy of the 4 synthetic demo systems. Synthetic data only – do not upload CUI or real system data. Sandboxes are deleted after 30 days without activity.</p>
      <label className="t-label mt-5 block" htmlFor="su-name">Name</label><input id="su-name" required autoComplete="name" className="input mt-1.5" value={f.name} onChange={set("name")} data-testid="signup-name-input" />
      <label className="t-label mt-3 block" htmlFor="su-email">Email</label><input id="su-email" type="email" required autoComplete="email" className="input mt-1.5" value={f.email} onChange={set("email")} data-testid="signup-email-input" />
      <label className="t-label mt-3 block" htmlFor="su-pw">Password</label><input id="su-pw" type="password" required autoComplete="new-password" className="input mt-1.5" value={f.password} onChange={set("password")} data-testid="signup-password-input" />
      <ul className="mt-1 flex flex-wrap gap-2 text-[11px]" data-testid="signup-password-rules">{rules.map(([l, ok]) => <li key={l} className={ok ? "text-emerald-700" : "text-slate-500"}>{ok ? "✓" : "○"} {l}</li>)}</ul>
      <label className="t-label mt-3 block" htmlFor="su-org">Organization (optional)</label><input id="su-org" autoComplete="organization" className="input mt-1.5" value={f.organization} onChange={set("organization")} data-testid="signup-org-input" />
      {/* bot trap: off-screen (not display:none), unusual name, excluded from autofill + password managers + tab order + a11y tree */}
      <div aria-hidden="true" style={{ position: "absolute", left: "-10000px", top: "auto", width: 1, height: 1, overflow: "hidden" }}>
        <label htmlFor="iv-hp-fax">Leave this empty</label>
        <input id="iv-hp-fax" type="text" name="iv_hp_fax_only" tabIndex={-1} autoComplete="off" data-lpignore="true" data-1p-ignore="true" data-bwignore="true" data-form-type="other"
          value={f.iv_hp_fax_only} onChange={set("iv_hp_fax_only")} data-testid="signup-trap-input" />
      </div>
      {err && <div role="alert" className="mt-3 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-[13px] text-rose-800" data-testid="signup-error">{err}</div>}
      <button type="submit" disabled={busy} className="btn-primary mt-5 w-full justify-center py-2.5" data-testid="signup-submit-btn">{busy ? "Creating…" : "Create account"}</button>
    </form>);
}
