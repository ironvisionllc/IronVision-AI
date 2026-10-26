import { ReactNode } from "react";
import { Row } from "@/lib/useApi";

export const OTHER_CHOICES: Record<string, string[]> = {
  responsible_entities: ["ISSO", "System Owner", "ISSO; System Owner", "System Administrator", "Network Operations", "DevSecOps team", "Common Control Provider"],
  slcm_criticality: ["High", "Moderate", "Low"],
  slcm_reporting: ["Monthly ConMon report to the ISSM", "Quarterly ConMon report to the AO", "Annual security review report to the ISSM", "Automated ConMon dashboard (continuous)"],
  slcm_tracking: ["eMASS POA&M", "ConMon tracker reviewed by the ISSO", "Ticketing system (change / incident)", "ACAS / STIG scan results reviewed by the ISSO"],
};
const OTHER = "__other";

/** Dropdown of common choices plus "Other…" (reveals a text box); the stored value is always the plain text string. */
export function OtherSelect({ field, value, onChange, disabled, max }: { field: string; value: string; onChange: (v: string) => void; disabled?: boolean; max: number }) {
  const choices = OTHER_CHOICES[field] || [];
  const custom = !!value && !choices.includes(value);
  return (
    <div>
      <select className="input w-full" value={custom ? OTHER : value} disabled={disabled} data-testid={`emass-${field}`} aria-label={field}
        onChange={(e) => onChange(e.target.value === OTHER ? (custom ? value : " ") : e.target.value)}>
        <option value="">— select —</option>{choices.map((c) => <option key={c} value={c}>{c}</option>)}<option value={OTHER}>Other…</option>
      </select>
      {(custom || value === " ") && <textarea className="input mt-1 w-full" rows={2} maxLength={max} value={value.trimStart()} disabled={disabled}
        onChange={(e) => onChange(e.target.value || " ")} placeholder="Type the value" data-testid={`emass-${field}-other`} />}
    </div>);
}

export function Counter({ v, max, testId }: { v: string; max: number; testId: string }) {
  const n = (v || "").trim().length;
  return <div className={`text-right text-[10px] ${n > max ? "text-rose-700" : "text-slate-400"}`} data-testid={testId}>{n.toLocaleString()} / {max.toLocaleString()}</div>;
}

/** Label + required marker + inline suggestion (accept per field). */
export function EField({ k, label, required, missing, sug, onAccept, children }: { k: string; label: string; required?: boolean; missing?: boolean;
  sug?: Row; onAccept?: () => void; children: ReactNode }) {
  return (
    <label className="block text-[12px]" data-testid={`emass-field-${k}`}>
      <span className="font-medium">{label}{required && <span className="text-rose-700" title="Required by eMASS for this Implementation Status"> *</span>}</span>
      {missing && <span className="ml-1 rounded bg-rose-50 px-1 text-[10px] text-rose-800" data-testid={`emass-missing-${k}`}>required</span>}
      <div className="mt-1">{children}</div>
      {sug && <div className="mt-1 rounded border border-violet-200 bg-violet-50 px-2 py-1 text-[11px] text-violet-900" data-testid={`emass-sug-${k}`}>
        Suggested: <b>{String(sug.value)}</b> <span className="text-violet-700">– {sug.reason}</span>
        <button type="button" className="ml-2 text-violet-900 underline" onClick={(e) => { e.preventDefault(); onAccept?.(); }} data-testid={`emass-accept-${k}`}>Accept</button></div>}
    </label>);
}

const LV = ["Very Low", "Low", "Moderate", "High", "Very High"];
const TABLE = [[0, 0, 0, 1, 1], [0, 1, 1, 1, 2], [0, 1, 2, 2, 3], [0, 1, 2, 3, 4], [0, 1, 2, 3, 4]];
export const residualHint = (l?: string, i?: string) => (l && i && LV.includes(l) && LV.includes(i) ? LV[TABLE[LV.indexOf(l)][LV.indexOf(i)]] : null);
