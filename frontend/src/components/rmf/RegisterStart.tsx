import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { useSystems } from "@/context/SystemContext";

const CHOICES = [
  ["scratch", "Start from scratch", "Name the system and pick its information types – the app derives the impact level and baseline."],
  ["emass", "Import an existing eMASS system", "Upload eMASS exports (System Details, Categorization, Test Results, SLCM, HW/SW, PPSM) in the Import Center; review every value before anything is saved."],
  ["copy", "Copy setup from an existing IronVision AI system", "Reuse baseline, overlays, tailoring, ODP values, ISCM strategy/profiles and policy links. Assessments, evidence, POA&Ms, test results, approvals and inventory are never copied."],
] as const;

/** Registration migration wizard: the first choice before the registration form. */
export function RegisterStart({ onScratch, onCopy }: { onScratch: () => void; onCopy: (tpl: Row) => void }) {
  const { systems } = useSystems();
  const [pick, setPick] = useState("");
  const [mode, setMode] = useState("");
  const copy = async () => {
    try { onCopy((await api.get<Row>(`/systems/${pick}/setup-template`)).data); }
    catch (e) { toast.error(errorMessage(e)); }
  };
  return (
    <Panel title="How do you want to start?" testId="register-start">
      <div className="grid gap-3 md:grid-cols-3" role="radiogroup" aria-label="Registration start">
        {CHOICES.map(([k, t, d]) => (
          <button type="button" key={k} role="radio" aria-checked={mode === k} onClick={() => (k === "scratch" ? onScratch() : setMode(k))}
            className={`rounded border p-3 text-left text-[12px] transition-colors hover:border-blue-500 ${mode === k ? "border-blue-600 bg-blue-50" : "border-slate-200"}`}
            data-testid={`register-start-${k}`}><b className="text-[13px]">{t}</b><p className="mt-1 text-slate-600">{d}</p></button>))}
      </div>
      {mode === "emass" && <p className="mt-3 text-[12px]" data-testid="register-start-emass-hint">Open the <Link className="text-blue-800 underline" to="/emass-import" data-testid="register-open-import-center">eMASS Import Center</Link>, upload the System Details or Categorization export and choose “Register new system” – the form is pre-filled, nothing is created until you submit. Control Information and POA&M imports are deferred.</p>}
      {mode === "copy" && <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px]">
        <select className="input" value={pick} onChange={(e) => setPick(e.target.value)} data-testid="register-copy-source"><option value="">Source system…</option>
          {systems.map((s: Row) => <option key={s.id} value={s.id}>{s.acronym} – {s.name}</option>)}</select>
        <button type="button" className="btn-primary" disabled={!pick} onClick={copy} data-testid="register-copy-continue">Continue with this setup</button></div>}
    </Panel>);
}
