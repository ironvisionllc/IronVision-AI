import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { ChevronDown, FlaskConical } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage, MUTATED_EVENT } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { Row } from "@/lib/useApi";
import { Modal } from "@/components/common/Modal";
import { showNextStep } from "@/components/common/NextStep";

const ROLE_COLOR: Record<string, string> = {
  isso: "bg-blue-700", issm: "bg-violet-700", sca: "bg-teal-700", ao: "bg-rose-700", system_owner: "bg-amber-700",
  devsecops: "bg-emerald-700", leadership_viewer: "bg-slate-700", privacy_official: "bg-teal-700", platform_admin: "bg-zinc-800",
};
const ROLE_SHORT: Record<string, string> = {
  isso: "ISSO", issm: "ISSM", sca: "SCA", ao: "AO", system_owner: "System Owner", devsecops: "DevSecOps", leadership_viewer: "Leadership", privacy_official: "Privacy", platform_admin: "Admin",
};

export function ActingAs() {
  const { user, actAs } = useAuth();
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const role = user ? user.persona_role : undefined;
  useEffect(() => {
    if (!role) return;
    setToast(`Acting as ${ROLE_SHORT[role] ?? role}`);
    const t = setTimeout(() => setToast(""), 3500);
    return () => clearTimeout(t);
  }, [role]);
  if (!user || !user.is_sandbox || !user.persona_role) return null;
  const change = async (r: string) => { setBusy(true); try { await actAs(r); } finally { setBusy(false); } };
  const name = user.display_name.replace(/\s*\([^)]*persona\)\s*$/i, "");
  return (
    <label className={`flex min-w-0 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold text-white ${ROLE_COLOR[user.persona_role] ?? "bg-slate-700"}`} data-testid="acting-as"
      title={`${user.display_name} · ${user.email}\nSandbox persona – simulated identity, not acceptable for production separation of duties`}>
      <span className="hidden sm:inline">Acting as</span>
      <select className="rounded bg-white/15 px-1 text-[11px] font-semibold text-white outline-none [field-sizing:content]" value={user.persona_role} disabled={busy} onChange={(e) => change(e.target.value)} data-testid="acting-as-select" aria-label="Acting as role">
        {Object.entries(ROLE_SHORT).map(([k, v]) => <option key={k} value={k} className="text-slate-900">{v}</option>)}
      </select>
      <span className="hidden max-w-[140px] truncate font-medium md:inline" data-testid="acting-as-name">{name}</span>
      {toast && <span role="status" className="fixed right-6 top-16 z-50 rounded-lg bg-slate-900 px-3 py-2 text-[12px] font-medium text-white shadow-lg" data-testid="acting-as-toast">{toast}</span>}
    </label>
  );
}

export function ProvisioningGate() {
  const { actAs, logout } = useAuth();
  const [st, setSt] = useState<Row | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await api.get<Row>("/sandbox/status");
        if (!alive) return;
        setSt(r.data);
        if (r.data.status === "ready") { await actAs("isso"); return; }
      } catch (e) { setErr(errorMessage(e)); }
      if (alive) setTimeout(tick, 2500);
    };
    tick();
    return () => { alive = false; };
  }, [actAs]);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center" data-testid="sandbox-provisioning">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-200 border-t-blue-700" aria-hidden />
      <h1 className="t-title">Preparing your sandbox…</h1>
      <p className="max-w-md text-[13px] text-slate-600">{st?.workspace === "demo"
        ? "We are registering 4 synthetic systems and ingesting the sample STIG checklists and ACAS scans into the demo tenant. This usually takes under a minute."
        : "We are setting up your private, empty workspace (decision rules, reference content and personas). This takes a few seconds."}</p>
      <div className="w-72 rounded-full bg-slate-200"><div className="h-2 rounded-full bg-blue-700 transition-[width] duration-500" style={{ width: `${st?.progress?.pct ?? 5}%` }} data-testid="sandbox-progress" /></div>
      <div className="text-[12px] text-slate-500">{st?.progress?.step ?? "queued"}</div>
      {err && <div className="text-[12px] text-rose-700">{err}</div>}
      <button className="btn-ghost text-[12px]" onClick={logout}>Sign out</button>
    </div>
  );
}

export const SIGNATURE_NOTE = "Persona approvals are simulated signatures – not CAC/PIV.";

/** Inline reminder for approval and sign-off dialogs (sandbox accounts only). */
export function SimulatedSignatureNote() {
  const { user } = useAuth();
  if (!user || !user.is_sandbox) return null;
  return <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-900" role="note" data-testid="simulated-signature-note">Sandbox: {SIGNATURE_NOTE}</p>;
}

/** Compact "Sandbox" chip in the header; the workspace details and actions live in its popover. */
export function SandboxChip() {
  const { user } = useAuth();
  const { data, reload } = useApi<Row>(user && user.is_sandbox ? "/sandbox/status" : null);
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const loc = useLocation();
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let t: ReturnType<typeof setTimeout> | undefined;
    const later = () => { clearTimeout(t); t = setTimeout(reload, 600); };  // debounce bursts of writes
    window.addEventListener(MUTATED_EVENT, later);
    window.addEventListener("focus", reload);
    return () => { clearTimeout(t); window.removeEventListener(MUTATED_EVENT, later); window.removeEventListener("focus", reload); };
  }, [reload]);
  useEffect(() => { reload(); setOpen(false); }, [loc.pathname, reload]);
  useEffect(() => {
    if (!open) return;
    panel.current?.focus();
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); btn.current?.focus(); } };
    const click = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("keydown", key);
    document.addEventListener("mousedown", click);
    return () => { window.removeEventListener("keydown", key); document.removeEventListener("mousedown", click); };
  }, [open]);
  if (!data?.sandbox) return null;
  const reset = async () => { setBusy(true); try { await api.post("/sandbox/reset"); window.location.reload(); } finally { setBusy(false); } };
  const ex = data.expiry;
  const loadDemo = async () => {
    if (!window.confirm("Load the SYNTHETIC demo data (4 sample systems, scans, findings, POA&Ms) into your workspace? Remove it any time with “Clear my workspace”.")) return;
    setBusy(true); try { const r = await api.post("/sandbox/demo-data");
      showNextStep({ message: r.data.already_loaded ? "Demo data was already loaded." : `SYNTHETIC demo data loaded: ${r.data.systems} fictional sample systems with scans, findings and POA&Ms.`, label: "open the Control Workbench and pick a control", to: "/controls" });
      window.location.reload(); } catch (e) { window.alert(errorMessage(e)); } finally { setBusy(false); }
  };
  const kind = data.is_demo ? "Demo workspace" : "Private sandbox";
  return (
    <div ref={wrap} className="relative shrink-0" data-testid="sandbox-bar">
      <button ref={btn} type="button" onClick={() => setOpen(!open)} aria-haspopup="dialog" aria-expanded={open} aria-controls="sandbox-popover"
        aria-label={`${kind} details${ex?.warn ? ` – deleted in ${ex.expires_in_days} day(s) without activity` : ""}`} data-testid="sandbox-chip"
        className={`flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold ${ex?.warn ? "border-amber-400 bg-amber-50 text-amber-900" : "border-slate-300 bg-slate-50 text-slate-700"}`}>
        <FlaskConical className="h-3 w-3" aria-hidden />{data.is_demo ? "Demo" : "Sandbox"}{ex?.warn && <span> · {ex.expires_in_days}d left</span>}
        <ChevronDown className="h-3 w-3" aria-hidden />
      </button>
      {open && <div id="sandbox-popover" ref={panel} tabIndex={-1} role="dialog" aria-label={`${kind} details`} data-testid="sandbox-popover"
        className="iv-popover absolute right-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-1.5rem)] space-y-2 p-3 text-left text-[12px] text-slate-700 focus:outline-none">
        <div data-testid="sandbox-label"><b>{kind}</b><div className="text-slate-900">{data.org_name}</div></div>
        <div data-testid="sandbox-operator">Operated by <span className="break-all">{data.operator.email}</span></div>
        <p className="text-[11px] text-slate-600" data-testid="sandbox-signature-note">{SIGNATURE_NOTE}</p>
        <p className={`text-[11px] ${ex?.warn ? "font-semibold text-amber-800" : "text-slate-600"}`} data-testid="sandbox-expiry">{ex?.warn ? `Inactive ${ex.idle_days} days – deleted in ${ex.expires_in_days} day(s) without activity` : ex?.message}</p>
        <div className="flex flex-wrap gap-2 pt-1">
          {!data.is_demo && !data.demo_data_loaded && <button className="btn-primary px-2 py-0.5 text-[11px]" disabled={busy} onClick={loadDemo} data-testid="sandbox-load-demo-btn"
            title="Adds fictional sample systems, scans, findings and POA&Ms to YOUR workspace so you can explore every feature. Clearly labelled SYNTHETIC. Remove any time with “Clear my workspace”.">{busy ? "Loading demo data…" : "Load demo data (SYNTHETIC)"}</button>}
          {!data.is_demo && data.demo_data_loaded && <span className="rounded bg-amber-100 px-1.5 text-[10px] font-semibold text-amber-800" data-testid="sandbox-demo-loaded">SYNTHETIC demo data loaded</span>}
          <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => { setOpen(false); setConfirm(true); }} data-testid="sandbox-reset-btn">{data.reset_label}</button>
        </div>
      </div>}
      {confirm && <Modal title={data.reset_label} onClose={() => setConfirm(false)} testId="sandbox-reset-modal">
        <p className="text-[13px] text-slate-700" data-testid="sandbox-reset-text">{data.reset_confirm}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setConfirm(false)} data-testid="sandbox-reset-cancel">Cancel</button>
          <button className="btn-primary" disabled={busy} onClick={reset} data-testid="sandbox-reset-confirm">{busy ? "Working…" : data.is_demo ? "Yes, reset demo data" : "Yes, clear everything"}</button>
        </div>
      </Modal>}
    </div>
  );
}

/** Synthetic sample files (STIG .ckl / ACAS) – shown in the "Upload a file" help, sandbox accounts only. */
export function SampleFilesLink() {
  const { user } = useAuth();
  if (!user || !user.is_sandbox) return null;
  const samples = async () => {
    const r = await api.get("/sandbox/samples.zip", { responseType: "blob" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(r.data as Blob), download: "ironvision-samples-SYNTHETIC.zip" });
    a.click(); URL.revokeObjectURL(a.href);
  };
  return <button type="button" className="text-[11px] text-blue-800 underline" onClick={samples} data-testid="download-samples"
    title="Fictional STIG checklists and ACAS scans for trying the upload – not real system data">Sample/test data (SYNTHETIC) – download sample STIG and ACAS files</button>;
}
