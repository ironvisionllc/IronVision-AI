import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Compass, X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const k = (uid?: string) => `iv.guided.${uid || "anon"}`;
const EVT = "iv-guided-changed";

/** Guided Mode: per user (this browser), off by default; same data and rules as streamlined mode – only explanations are added. */
export function useGuided(): [boolean, (on: boolean) => void, boolean] {
  const { user } = useAuth();
  const read = () => localStorage.getItem(k((user || null)?.id));
  const [v, setV] = useState(read());
  useEffect(() => { const f = () => setV(read()); f(); window.addEventListener(EVT, f); return () => window.removeEventListener(EVT, f); }, [(user || null)?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (on: boolean) => { localStorage.setItem(k((user || null)?.id), on ? "on" : "off"); window.dispatchEvent(new Event(EVT)); };
  return [v === "on", set, v === null];
}

export function GuidedToggle({ testId = "guided-toggle" }: { testId?: string }) {
  const [on, set] = useGuided();
  return <button type="button" className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${on ? "border-violet-300 bg-violet-50 text-violet-800" : "border-slate-300 text-slate-600"}`}
    onClick={() => set(!on)} aria-pressed={on} aria-label={`Guided mode: ${on ? "on" : "off"}`} data-testid={testId} title="Guided mode explains each step: purpose, what you need, who does it and what comes next">
    <Compass className="inline h-3 w-3 md:mr-1" aria-hidden /><span className="hidden md:inline">Guided mode: {on ? "on" : "off"}</span></button>;
}

export function GuidedFirstLogin() {
  const [, set, unset] = useGuided();
  const { user } = useAuth();
  if (!user || !unset) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 w-[22rem] rounded-xl border border-violet-200 bg-white p-4 shadow-xl" role="dialog" aria-label="Guided mode" data-testid="guided-first-login">
      <div className="flex items-start gap-2"><Compass className="mt-0.5 h-4 w-4 text-violet-700" aria-hidden /><div className="flex-1 text-[13px]">
        <b>New to RMF in IronVision?</b><p className="mt-1 text-slate-600">Guided mode explains every step: its purpose, the information you need, who does it and what comes next. You can switch it in the header at any time.</p></div>
        <button onClick={() => set(false)} aria-label="Close" data-testid="guided-first-login-close"><X className="h-4 w-4" /></button></div>
      <div className="mt-3 flex justify-end gap-2"><button className="btn-secondary" onClick={() => set(false)} data-testid="guided-first-login-no">No, I know eMASS</button>
        <button className="btn-primary" onClick={() => set(true)} data-testid="guided-first-login-yes">Turn on guided mode</button></div>
    </div>);
}

const GUIDE: Record<string, [string, string, string, string, string, string]> = {
  prepare: ["Name the people responsible and describe the system.", "Every later approval needs a named System Owner, ISSO, ISSM, AO and SCA.", "Names or e-mails for each role; system boundary and inventory.", "System Owner, ISSO", "Categorize", "/rmf/categorize"],
  categorize: ["Decide how bad a loss of confidentiality, integrity or availability would be (FIPS 199 / CNSSI 1253).", "The result picks the control baseline.", "The SP 800-60 information types the system processes; whether it contains PII.", "ISSO proposes · AO approves", "Select", "/rmf/select"],
  select: ["Choose the controls: baseline, overlays, tailoring, parameters and the monitoring strategy.", "Only selected controls are implemented, assessed and authorized.", "The approved categorization; organization-defined parameter values.", "ISSO proposes · ISSM approves the strategy", "Implement", "/rmf/implement"],
  implement: ["Describe how each control is met and attach evidence.", "The SCA assesses what you write here; the SSP is generated from it.", "Implementation statements, status, responsible entities, evidence, policies.", "ISSO, System Owner, common control providers", "Assess", "/rmf/assess"],
  assess: ["The SCA independently tests each control and records a determination.", "Determinations and findings feed the SAR and the POA&M.", "Evidence, implementation statements, test results, scans.", "SCA (independent of the implementer)", "Authorize", "/rmf/authorize"],
  authorize: ["Assemble the package; the AO decides on the risk.", "Without the AO's decision the system may not operate.", "SSP, SAR, RAR, POA&M – validated before download.", "ISSM reviews · AO decides", "Monitor", "/rmf/monitor"],
  monitor: ["Keep evidence current and controls monitored on schedule.", "The authorization stays valid only while risk is monitored.", "The approved monitoring strategy (SLCM), fresh evidence, scan results.", "ISSO, ISSM", "My Work", "/my-work"],
};

export function GuidedPanel({ step }: { step: string }) {
  const [on] = useGuided();
  const g = GUIDE[step];
  if (!on || !g) return null;
  return (
    <div className="mb-4 rounded-xl border border-violet-200 bg-violet-50 p-4 text-[13px] text-slate-800" data-testid="guided-panel">
      <div className="text-[11px] font-bold uppercase tracking-wide text-violet-800">Guided mode · {step}</div>
      <div className="mt-2 grid gap-3 md:grid-cols-5">
        <div><b>Purpose</b><br />{g[0]}</div><div><b>Why it matters</b><br />{g[1]}</div><div><b>You need</b><br />{g[2]}</div><div><b>Who</b><br />{g[3]}</div>
        <div><b>What's next</b><br /><Link className="text-violet-800 underline" to={g[5]} data-testid="guided-next">{g[4]} →</Link></div>
      </div>
    </div>);
}
