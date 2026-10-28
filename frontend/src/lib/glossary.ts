/** One vocabulary per status dimension (eMASS wording where it exists): label, colour, one-line meaning. */
export type Dim = "implementation" | "coverage" | "assessment" | "authorization" | "freshness" | "poam";
type Entry = [label: string, cls: string];
const SOLID = "rounded px-1.5 py-0.5 text-[11px] font-semibold";
const OUTLINE = "rounded border bg-white px-1.5 py-0.5 text-[11px] font-medium";
export const DIM_LABEL: Record<Dim, string> = { implementation: "Implementation", coverage: "Policy coverage", assessment: "Assessment",
  authorization: "Authorization", freshness: "Evidence", poam: "POA&M" };
export const DIM_HELP: Record<Dim, string> = {
  implementation: "What the system owner says is in place (eMASS Implementation Status).",
  coverage: "Whether an approved policy requires the control – never an assessment result.",
  assessment: "The SCA's independent determination (eMASS Compliance Status).",
  authorization: "The AO's decision for the whole system.",
  freshness: "Whether evidence is within its required review period. Two scoped counts are used, never mixed: “Controls with current evidence: X of Y assigned controls” and “Evidence items within their freshness window: N of M collected items”.",
  poam: "eMASS POA&M status of the weakness.",
};
export const GLOSSARY: Record<Dim, Record<string, Entry>> = {
  implementation: {
    planned: ["Planned", `${SOLID} bg-sky-100 text-sky-900`], implemented: ["Implemented", `${SOLID} bg-emerald-100 text-emerald-900`],
    partially_implemented: ["Partially Implemented", `${SOLID} bg-amber-100 text-amber-900`], not_implemented: ["Not Implemented", `${SOLID} bg-rose-100 text-rose-900`],
    not_applicable: ["Not Applicable", `${SOLID} bg-slate-200 text-slate-700`], inherited: ["Inherited", `${SOLID} bg-violet-100 text-violet-900`],
  },
  coverage: {
    met: ["Covered by policy", `${OUTLINE} border-emerald-400 text-emerald-800`], covered: ["Covered by policy", `${OUTLINE} border-emerald-400 text-emerald-800`],
    partial: ["Partially covered", `${OUTLINE} border-amber-400 text-amber-800`], gaps: ["Not covered", `${OUTLINE} border-rose-400 text-rose-800`],
    not_covered: ["Not covered", `${OUTLINE} border-rose-400 text-rose-800`], none: ["Not analysed", `${OUTLINE} border-slate-300 text-slate-600`],
  },
  assessment: {
    satisfied: ["Satisfied", `${SOLID} bg-emerald-600 text-white`], other_than_satisfied: ["Other Than Satisfied", `${SOLID} bg-rose-600 text-white`],
    not_assessed: ["Not Assessed", `${SOLID} bg-slate-200 text-slate-800`], not_applicable: ["Not Applicable", `${SOLID} bg-slate-500 text-white`],
  },
  authorization: {
    ato: ["ATO", "rounded-sm bg-emerald-700 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white"],
    ato_with_conditions: ["ATO with conditions", "rounded-sm bg-emerald-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white"],
    iatt: ["IATT", "rounded-sm bg-sky-700 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white"],
    dato: ["DATO", "rounded-sm bg-rose-700 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white"],
    expired: ["Expired", "rounded-sm bg-rose-900 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white"],
    none: ["Not yet authorized", "rounded-sm bg-slate-500 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white"],
  },
  freshness: {
    current: ["● Current", "text-[11px] font-medium text-emerald-700"], due_soon: ["● Due soon", "text-[11px] font-medium text-amber-700"],
    stale: ["● Stale", "text-[11px] font-medium text-rose-700"], missing: ["○ Missing", "text-[11px] font-medium text-slate-500"],
  },
  poam: {
    ongoing: ["Ongoing", "rounded-full bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-800 ring-1 ring-sky-300"],
    risk_accepted: ["Risk Accepted", "rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-semibold text-violet-800 ring-1 ring-violet-300"],
    completed: ["Completed", "rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 ring-1 ring-emerald-300"],
    delayed: ["Delayed", "rounded-full bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-800 ring-1 ring-rose-300"],
  },
};
const ALIAS: Record<string, string> = { open: "ongoing", closed: "completed", draft: "ongoing", compliant: "satisfied", non_compliant: "other_than_satisfied",
  "non-compliant": "other_than_satisfied", no_data: "missing", expiring: "due_soon", unknown: "none" };

export function lookup(dim: Dim, v?: string | null): Entry {
  const k = (v || "none").toLowerCase().replace(/[\s-]+/g, "_");
  return GLOSSARY[dim][k] ?? GLOSSARY[dim][ALIAS[k]] ?? [String(v || "—").replace(/_/g, " "), "rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700"];
}
