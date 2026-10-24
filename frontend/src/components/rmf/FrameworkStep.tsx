import { useApi, Row } from "@/lib/useApi";
import { Help } from "@/components/rmf/RolesEditor";

const YNU: [string, string][] = [["yes", "Yes"], ["no", "No"], ["unsure", "Unsure"]];
const YNK: [string, string][] = [["yes", "Yes"], ["no", "No"], ["unknown", "Unknown – requires review"]];

function Radios({ name, value, opts, onChange, testId }: { name: string; value: string | null; opts: [string, string][]; onChange: (v: string) => void; testId: string }) {
  return (
    <div className="mt-1 flex flex-wrap gap-4" role="radiogroup" aria-label={name}>
      {opts.map(([k, l]) => <label key={k} className="flex items-center gap-1.5"><input type="radio" name={testId} checked={value === k} onChange={() => onChange(k)} data-testid={`${testId}-${k}`} />{l}</label>)}
      {!value && <span className="text-[11px] text-amber-800" data-testid={`${testId}-unanswered`}>Not answered yet</span>}
    </div>);
}

/** Categorize · step 1 – framework choice with NSS determination and the classified-information applicability answer. */
export function FrameworkStep({ v, onChange }: { v: Row; onChange: (v: Row) => void }) {
  const { data: ref } = useApi<Row>("/reference/frameworks");
  const set = (k: string, val: unknown) => onChange({ ...v, [k]: val });
  return (
    <div className="mb-4 grid gap-3 text-[12px]" data-testid="framework-step">
      <div>
        <div className="font-medium text-slate-700">Is this a National Security System? <Help text={ref?.nss_help ?? ""} /></div>
        <Radios name="National Security System" value={v.nss_determination ?? null} opts={YNU} onChange={(x) => onChange({ ...v, nss_determination: x, mode: x === "yes" ? "cnssi1253" : x === "no" ? "fips199" : v.mode })} testId="nss" />
        <p className="mt-1 text-[11px] text-slate-500">44 U.S.C. §3552(b)(6) defines an NSS; NIST SP 800-59 is the identification guideline. “Unsure” is recorded and does not pick a framework for you.</p>
      </div>
      <div role="radiogroup" aria-label="Categorization framework" className="grid gap-2 md:grid-cols-2">
        {Object.entries((ref?.frameworks ?? {}) as Record<string, Row>).map(([k, f]) => (
          <label key={k} className={`cursor-pointer rounded-md border p-2.5 ${v.mode === k ? "border-blue-500 bg-blue-50" : "border-slate-200"}`}>
            <input type="radio" className="mr-1.5" checked={v.mode === k} onChange={() => set("mode", k)} data-testid={`cat-mode-${k}`} /><b>{f.label}</b>
            <span className="mt-1 block text-[11px] text-slate-600">{f.help}</span><span className="mt-1 block text-[10px] text-slate-500">{f.source}</span></label>))}
      </div>
      {v.nss_determination === "no" && v.mode === "cnssi1253" && <p className="rounded bg-amber-50 p-2 text-[11px] text-amber-900" data-testid="framework-mismatch">You answered “not an NSS” but chose CNSSI 1253 – confirm with your AO/ISSM.</p>}
      {v.mode === "cnssi1253" && <div>
        <div className="font-medium text-slate-700">Does the system, by intent and design, store, process or transmit classified information?
          <Help text="Decides whether the Classified System Overlay (CNSSI 1253 App. E Att. 5 §3) and DoD Cloud SRG IL6 can apply. A classification level alone never applies the overlay." /></div>
        <Radios name="Processes classified information" value={v.classified_information ?? null} opts={YNK} onChange={(x) => set("classified_information", x)} testId="classified" />
      </div>}
    </div>);
}

/** SRG impact level picker: cloud environments only; IL6 only for DoD cloud + classified up to SECRET + CNSSI 1253 (NSS). */
export function ilOptions(cloud: boolean, mode: string, classified: string | null): { value: string; available: boolean; reason?: string }[] {
  if (!cloud) return [];
  const ok6 = mode === "cnssi1253" && classified === "yes";
  return [...["IL2", "IL4", "IL5"].map((value) => ({ value, available: true })),
    { value: "IL6", available: ok6, reason: ok6 ? undefined : "IL6 needs CNSSI 1253 (NSS) and a Yes to ‘processes classified information’ (classified up to SECRET)." },
    { value: "Not DoD", available: true }];
}
