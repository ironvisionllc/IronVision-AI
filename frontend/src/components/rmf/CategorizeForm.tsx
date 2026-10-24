import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { Help } from "@/components/rmf/RolesEditor";
import { FrameworkStep, ilOptions } from "@/components/rmf/FrameworkStep";

const LV = ["Low", "Moderate", "High"];
export const EMPTY_CAT: Row = { mode: "fips199", information_types: [], cia: { c: "", i: "", a: "" }, mission_criticality: "", system_type: "",
  acquisition_category: "", operating_environment: "", environment_detail: {}, processes_pii: null, pta: {} };

export function catFromSystem(s: Row): Row {
  return { ...EMPTY_CAT, mode: s.categorization_mode || "fips199", nss_determination: s.nss_determination ?? null, classified_information: s.applicability_flags?.classified_information ?? null,
    information_types: (s.information_types ?? []).map((t: Row) => ({ id: t.id, c: t.c, i: t.i, a: t.a, rationale: t.rationale ?? "" })),
    cia: { c: s.confidentiality_impact ?? "", i: s.integrity_impact ?? "", a: s.availability_impact ?? "" },
    ...Object.fromEntries(["mission_criticality", "system_type", "acquisition_category", "operating_environment"].map((k) => [k, s[k] ?? ""])),
    environment_detail: s.environment_detail ?? {}, processes_pii: s.processes_pii ?? null, pta: s.pta ?? {} };
}

export function catBody(v: Row): Row {
  const b: Row = { ...v, information_types: v.information_types, cia: v.mode === "cnssi1253" ? v.cia : null };
  delete b.authorization_type;  // set in 6 · Authorize (authorization strategy)
  for (const k of ["mission_criticality", "system_type", "acquisition_category", "operating_environment"]) if (!b[k]) delete b[k];
  return b;
}

/** Live FIPS 199 / CNSSI 1253 calculation from the server (single source of truth). */
export function useCategorization(v: Row) {
  const [calc, setCalc] = useState<Row | null>(null);
  const key = JSON.stringify([v.mode, v.information_types, v.cia]);
  useEffect(() => {
    const t = setTimeout(() => {
      api.post<Row>("/reference/categorize", { mode: v.mode, information_types: v.information_types, cia: v.mode === "cnssi1253" ? v.cia : null })
        .then((r) => setCalc(r.data)).catch(() => setCalc(null));
    }, 250);
    return () => clearTimeout(t);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return calc;
}

function InfoTypePicker({ v, onChange, catalog }: { v: Row; onChange: (v: Row) => void; catalog: Row[] }) {
  const [q, setQ] = useState("");
  const byId = useMemo(() => Object.fromEntries(catalog.map((t) => [t.id, t])), [catalog]);
  const chosen = new Set(v.information_types.map((t: Row) => t.id));
  const hits = catalog.filter((t) => !chosen.has(t.id) && (!q || `${t.id} ${t.name} ${t.line_of_business}`.toLowerCase().includes(q.toLowerCase()))).slice(0, 40);
  const upd = (id: string, patch: Row) => onChange({ ...v, information_types: v.information_types.map((t: Row) => t.id === id ? { ...t, ...patch } : t) });
  return (
    <div data-testid="info-type-picker">
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <input className="input" placeholder={`Search ${catalog.length} information types (name, ID or line of business)…`} value={q} onChange={(e) => setQ(e.target.value)} data-testid="info-type-search" />
          <ul className="mt-2 max-h-64 overflow-y-auto rounded border border-slate-200 text-[12px]" data-testid="info-type-results">
            {hits.map((t) => <li key={t.id} className="flex items-center gap-2 border-b border-slate-100 px-2 py-1.5">
              <span className="w-14 shrink-0 font-mono text-[11px] text-slate-500">{t.id}</span>
              <span className="flex-1"><b className="font-medium">{t.name}</b> <span className="text-slate-500">· {t.line_of_business}</span></span>
              <span className="shrink-0 font-mono text-[10px] text-slate-500" title="Provisional confidentiality / integrity / availability">{t.c[0]}/{t.i[0]}/{t.a[0]}</span>
              <button type="button" className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => onChange({ ...v, information_types: [...v.information_types, { id: t.id, c: t.c, i: t.i, a: t.a, rationale: "" }] })}
                data-testid={`info-type-add-${t.id}`}>Add</button></li>)}
            {!hits.length && <li className="px-2 py-3 text-slate-500">No matching information types.</li>}
          </ul>
        </div>
        <div>
          <div className="mb-1 text-[12px] font-medium text-slate-700">Selected ({v.information_types.length})</div>
          {!v.information_types.length && <p className="rounded border border-dashed border-slate-300 p-3 text-[12px] text-slate-500" data-testid="info-type-empty">
            Search on the left and click <b>Add</b> for every kind of information the system stores or processes. Each one comes with NIST's provisional impact levels.</p>}
          {v.information_types.map((t: Row) => {
            const ref = byId[t.id] ?? {};
            const adjusted = ["c", "i", "a"].some((k) => t[k] !== ref[k]);
            return <div key={t.id} className="mb-2 rounded border border-slate-200 p-2 text-[12px]" data-testid={`info-type-row-${t.id}`}>
              <div className="flex items-center gap-2"><span className="font-mono text-[11px] text-slate-500">{t.id}</span><b className="flex-1 font-medium">{ref.name}</b>
                <button type="button" className="text-[11px] text-rose-700 underline" onClick={() => onChange({ ...v, information_types: v.information_types.filter((x: Row) => x.id !== t.id) })}>Remove</button></div>
              {ref.note && <div className="mt-1 text-[11px] text-amber-800">{ref.note}</div>}
              <div className="mt-1.5 grid grid-cols-3 gap-2">{(["c", "i", "a"] as const).map((k) => (
                <label key={k} className="text-[11px] text-slate-600">{{ c: "Confidentiality", i: "Integrity", a: "Availability" }[k]} <span className="text-slate-400">(provisional {ref[k]})</span>
                  <select className="input mt-0.5" value={t[k]} onChange={(e) => upd(t.id, { [k]: e.target.value })} data-testid={`info-type-${t.id}-${k}`}>
                    {["N/A", ...LV].map((x) => <option key={x}>{x}</option>)}</select></label>))}</div>
              {adjusted && <input className="input mt-1.5" placeholder="Why you changed the provisional level (required)" value={t.rationale} onChange={(e) => upd(t.id, { rationale: e.target.value })}
                data-testid={`info-type-${t.id}-rationale`} />}
            </div>;
          })}
        </div>
      </div>
    </div>);
}

function Calculation({ calc }: { calc: Row | null }) {
  if (!calc || !calc.rows.length) return null;
  return (
    <div className="mt-4 rounded-md border border-blue-200 bg-blue-50/50 p-3 text-[12px]" data-testid="cat-calc">
      <div className="font-semibold text-slate-800">How the categorization is calculated</div>
      <ol className="ml-4 mt-1 list-decimal text-slate-700">{calc.steps.map((s: string) => <li key={s}>{s}</li>)}</ol>
      <div className="mt-2">Security category: <span className="font-mono">{calc.security_category}</span></div>
      <div className="mt-1 text-[13px]">Result: <b data-testid="cat-overall">{calc.overall ?? "—"}</b> → baseline <b data-testid="cat-baseline">{calc.baseline ? calc.baseline[0].toUpperCase() + calc.baseline.slice(1) : "—"}</b></div>
      {calc.errors.length > 0 && <ul className="mt-2 list-disc pl-4 text-rose-700" data-testid="cat-errors">{calc.errors.map((e: string) => <li key={e}>{e}</li>)}</ul>}
    </div>);
}

function Choice({ label, help, value, options, onChange, testId }: { label: string; help: string; value: string; options: Row[]; onChange: (v: string) => void; testId: string }) {
  const cur = options.find((o) => o.value === value);
  return <label className="block text-[12px] font-medium text-slate-700">{label} <Help text={help} />
    <select className="input mt-1" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testId}><option value="">— choose —</option>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label ?? o.value}</option>)}</select>
    {cur?.help && <span className="mt-1 block text-[11px] font-normal text-slate-500">{cur.help}</span>}</label>;
}

export function CategorizeForm({ v, onChange }: { v: Row; onChange: (v: Row) => void }) {
  const { data: cat } = useApi<Row>("/reference/info-types");
  const { data: ref } = useApi<Row>("/reference/rmf");
  const calc = useCategorization(v);
  const set = (k: string, val: unknown) => onChange({ ...v, [k]: val });
  const env = (ref?.environments ?? []).find((e: Row) => e.value === v.operating_environment);
  const det = v.environment_detail ?? {};
  const pta = v.pta ?? {};
  return (
    <div className="grid gap-5" data-testid="categorize-form">
      <Panel title="Framework, information types and impact" eyebrow="Steps 1–4 · framework → types (NIST SP 800-60 Vol. 2 Rev. 1) → C/I/A → calculation">
        <FrameworkStep v={v} onChange={onChange} />
        <InfoTypePicker v={v} onChange={onChange} catalog={cat?.types ?? []} />
        {v.mode === "cnssi1253" && <div className="mt-3 grid grid-cols-3 gap-3 text-[12px]" data-testid="cnssi-cia">
          {(["c", "i", "a"] as const).map((k) => <label key={k} className="font-medium text-slate-700">{{ c: "Confidentiality", i: "Integrity", a: "Availability" }[k]} (chosen separately)
            <select className="input mt-1" value={v.cia?.[k] ?? ""} onChange={(e) => set("cia", { ...v.cia, [k]: e.target.value })} data-testid={`cnssi-${k}`}>
              <option value="">From information types</option>{LV.map((x) => <option key={x}>{x}</option>)}</select></label>)}
        </div>}
        <Calculation calc={calc} />
        <p className="mt-2 text-[11px] text-slate-500">{cat?.source}</p>
      </Panel>
      <Panel title="Mission and system type" eyebrow={ref?.emass_note ?? "eMASS-aligned; verify against your eMASS instance"}>
        <div className="mb-4 text-[12px]" role="radiogroup" aria-label="Mission criticality">
          <div className="mb-1 font-medium text-slate-700">Mission criticality <Help text="How important the system is to the organization's mission (eMASS field)." /></div>
          <div className="grid gap-2 md:grid-cols-3">{(ref?.mission_criticality ?? []).map((m: Row) => (
            <label key={m.value} className={`cursor-pointer rounded-md border p-2.5 ${v.mission_criticality === m.value ? "border-blue-500 bg-blue-50" : "border-slate-200"}`} data-testid={`mc-${m.value}`}>
              <input type="radio" className="mr-1.5" checked={v.mission_criticality === m.value} onChange={() => set("mission_criticality", m.value)} /><b>{m.label}</b>
              <span className="mt-1 block text-[11px] text-slate-600">{m.help}</span></label>))}</div>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <Choice label="System type" help="eMASS system type – what kind of system this is." value={v.system_type} options={ref?.system_types ?? []} onChange={(x) => set("system_type", x)} testId="cat-system-type" />
          <Choice label="Acquisition category" help="DoD acquisition category (ACAT) of the program, if any." value={v.acquisition_category} options={ref?.acquisition_categories ?? []} onChange={(x) => set("acquisition_category", x)} testId="cat-acat" />
        </div>
      </Panel>
      <Panel title="Operating environment">
        <div className="grid gap-3 md:grid-cols-4 text-[12px]">
          <Choice label="Where the system runs" help="Hosting environment – drives inheritance (e.g. from a cloud provider) and some overlays." value={v.operating_environment}
            options={ref?.environments ?? []} onChange={(x) => set("operating_environment", x)} testId="cat-environment" />
          {env?.cloud && <>
            <label className="font-medium text-slate-700">Cloud service provider<input className="input mt-1" value={det.csp ?? ""} onChange={(e) => set("environment_detail", { ...det, csp: e.target.value })} data-testid="cat-csp" /></label>
            <label className="font-medium text-slate-700">FedRAMP authorization<select className="input mt-1" value={det.fedramp ?? ""} onChange={(e) => set("environment_detail", { ...det, fedramp: e.target.value })} data-testid="cat-fedramp">
              <option value="">—</option>{["None", "LI-SaaS", "Low", "Moderate", "High"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="font-medium text-slate-700">DoD Impact Level <Help text="DoD Cloud Computing SRG impact level of the cloud service offering. IL6 = classified up to SECRET." />
              <select className="input mt-1" value={det.impact_level ?? ""} onChange={(e) => set("environment_detail", { ...det, impact_level: e.target.value })} data-testid="cat-il">
                <option value="">—</option>{ilOptions(true, v.mode, v.classified_information ?? null).map((o) => <option key={o.value} value={o.value} disabled={!o.available} title={o.reason}>{o.value}{o.available ? "" : " (unavailable)"}</option>)}</select>
              {!ilOptions(true, v.mode, v.classified_information ?? null).find((o) => o.value === "IL6")?.available && <span className="mt-1 block text-[10px] font-normal text-slate-500" data-testid="cat-il6-reason">IL6 unavailable: needs CNSSI 1253 (NSS) and a Yes to “processes classified information”.</span>}</label></>}
          {!env?.cloud && v.operating_environment && <p className="text-[11px] text-slate-500 md:col-span-3" data-testid="cat-il-none">No DoD impact level here – SRG impact levels apply to cloud service offerings.</p>}
          {v.operating_environment === "other" && <label className="font-medium text-slate-700 md:col-span-3">Describe the environment<input className="input mt-1" value={det.other ?? ""}
            onChange={(e) => set("environment_detail", { ...det, other: e.target.value })} data-testid="cat-env-other" /></label>}
        </div>
      </Panel>
      <Panel title="Privacy (Privacy Threshold Analysis)">
        <div className="text-[12px]" data-testid="cat-privacy">
          <div className="font-medium text-slate-700">Does the system collect, use, store or share personally identifiable information (PII)? <Help text="PII = information that can identify a person (name, SSN, e-mail, biometrics…). A 'Yes' adds the privacy controls." /></div>
          <div className="mt-1 flex flex-wrap gap-4" role="radiogroup" aria-label="Processes PII">{([["Yes", "yes", true], ["No", "no", false], ["Unknown – requires review", "unknown", null]] as const).map(([l, k, b]) => (
            <label key={k} className="flex items-center gap-1.5"><input type="radio" name="pii" checked={k === "unknown" ? v.processes_pii === null && pta.pii_status === "unknown" : v.processes_pii === b}
              onChange={() => onChange({ ...v, processes_pii: b, pta: { ...pta, pii_status: k } })} data-testid={`pii-${k}`} />{l}</label>))}
            {v.processes_pii === null && pta.pii_status !== "unknown" && <span className="text-[11px] text-amber-800" data-testid="pii-unanswered">Not answered yet</span>}</div>
          {pta.pii_status === "unknown" && <p className="mt-2 rounded bg-amber-50 p-2 text-[11px] text-amber-900" data-testid="pii-unknown-note">Recorded as “requires review” (not as No). A privacy official must resolve it in the Privacy Threshold Analysis.</p>}
          {v.processes_pii === true && <div className="mt-3 grid gap-3 md:grid-cols-2" data-testid="pta-followup">
            <label className="font-medium text-slate-700">What kinds of PII?<input className="input mt-1" placeholder="e.g. names, e-mail, SSN, health data" value={pta.pii_types ?? ""} onChange={(e) => set("pta", { ...pta, pii_types: e.target.value })} data-testid="pta-types" /></label>
            <label className="font-medium text-slate-700">Whose PII?<select className="input mt-1" value={pta.whose ?? ""} onChange={(e) => set("pta", { ...pta, whose: e.target.value })} data-testid="pta-whose">
              <option value="">—</option>{["Members of the public", "Employees / contractors", "Both"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="font-medium text-slate-700">Is a System of Records Notice (SORN) needed?<select className="input mt-1" value={pta.sorn ?? ""} onChange={(e) => set("pta", { ...pta, sorn: e.target.value })} data-testid="pta-sorn">
              <option value="">—</option>{["Yes – published", "Yes – not yet published", "No", "Unknown"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="font-medium text-slate-700">Privacy Impact Assessment (PIA)?<select className="input mt-1" value={pta.pia ?? ""} onChange={(e) => set("pta", { ...pta, pia: e.target.value })} data-testid="pta-pia">
              <option value="">—</option>{["Completed", "In progress", "Not started"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <p className="rounded bg-violet-50 p-2 text-[11px] text-violet-900 md:col-span-2">Because the system processes PII, the NIST SP 800-53B privacy baseline is applied in Select{v.mode === "cnssi1253" ? ", together with the CNSSI 1253 Privacy Overlay (load its official control list under Select → Overlays)" : ""}.</p>
          </div>}
        </div>
      </Panel>
    </div>);
}
