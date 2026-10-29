import { api } from "@/lib/api";
import type { Row } from "@/lib/useApi";

export type QState = "uploaded" | "detecting" | "ready" | "needs_decision" | "importing" | "imported" | "failed" | "removed";
export const STATES: [QState, string][] = [["uploaded", "Uploaded"], ["detecting", "Detecting"], ["ready", "Ready"], ["needs_decision", "Needs your decision"],
  ["importing", "Importing"], ["imported", "Imported"], ["failed", "Failed"], ["removed", "Removed"]];
export const LABEL = Object.fromEntries(STATES) as Record<QState, string>;
const ORDER: QState[] = ["needs_decision", "failed", "ready", "importing", "detecting", "uploaded", "imported", "removed"];
export const TONE: Record<QState, string> = {
  uploaded: "bg-slate-100 text-slate-700", detecting: "bg-sky-100 text-sky-900", ready: "bg-blue-100 text-blue-900", needs_decision: "bg-amber-100 text-amber-900",
  importing: "bg-indigo-100 text-indigo-900", imported: "bg-emerald-100 text-emerald-900", failed: "bg-rose-100 text-rose-900", removed: "bg-zinc-200 text-zinc-700",
};

export interface Decision { kind: "type" | "policy_ai" | "target" | "override" | "system"; prompt: string; options: { value: string; label: string }[]; batchSafe: boolean }
export interface QFile { key: string; file: File; det: Row | null; type: string; state: QState; decision?: Decision; res?: Row; error?: string; policyOk?: boolean; emassId?: string; blocked?: boolean }

export const SCANS = ["ckl", "cklb", "xccdf", "nessus_xml", "nessus_csv", "sarif"];
export const GENERIC_EMASS = ["system_details", "categorization", "slcm", "ppsm", "poam"];

export const sortByState = (fs: QFile[]) => [...fs].sort((a, b) => ORDER.indexOf(a.state) - ORDER.indexOf(b.state));
export const removable = (f: QFile) => ["uploaded", "ready", "needs_decision", "failed"].includes(f.state) || (f.state === "imported" && !!f.emassId);

/** After detection: ready, a decision the user must make (never skipped silently), or failed with the reason. */
export function classify(f: QFile, types: Row, preset?: string): QFile {
  const d = f.det || {};
  const type = f.type || (preset && d.candidates?.includes(preset) ? preset : d.type) || "";
  if (!type) {
    if (d.override) return { ...f, type: "", state: "needs_decision", decision: { kind: "override", prompt: d.message, batchSafe: false,
      options: [{ value: d.override, label: d.override_label }, { value: "__remove", label: "Remove this file" }] } };
    return { ...f, type: "", state: "failed", error: d.message || "Not recognised as a supported import" };
  }
  const t = types[type];
  if (!t) return { ...f, type, state: "detecting" };  // type list still loading – re-classified when it arrives
  if (!t.allowed && !t.reason?.startsWith("Choose a target system")) return { ...f, type, state: "failed", blocked: true, error: t.reason };
  if (!t.allowed) return { ...f, type, state: "needs_decision", blocked: true, decision: { kind: "system", prompt: "Choose the target system above – this file then becomes ready", batchSafe: false, options: [] } };
  if (!f.type && (d.ambiguous || d.confidence === "low" || d.confidence === "medium") && (d.candidates || []).length > 1)
    return { ...f, type, state: "needs_decision", decision: { kind: "type", prompt: `Detected as ${t?.label ?? type} with ${d.confidence} confidence – confirm the type`, batchSafe: false,
      options: (d.candidates as string[]).map((c) => ({ value: c, label: types[c]?.label ?? c })) } };
  if (type === "policy" && !f.policyOk) return { ...f, type, state: "needs_decision", decision: { kind: "policy_ai", batchSafe: true,
    prompt: "Policy documents are analysed by the AI Policy Auditor (uses AI budget). Send this one?", options: [{ value: "send", label: "Send to Policy Auditor" }, { value: "__remove", label: "Remove this file" }] } };
  return { ...f, type, state: "ready", decision: undefined, error: undefined, blocked: false };
}

/** Sends the file to the type's EXISTING pipeline endpoint (review gates unchanged). eMASS files whose identity differs pause for a decision. */
export async function route(type: string, sid: string, file: File): Promise<Row> {
  const fd = new FormData();
  fd.append("file", file);
  if (type === "policy") {
    fd.append("title", file.name.replace(/\.[^.]+$/, "")); fd.append("system_ids", sid);
    const r = (await api.post<Row>("/policies", fd)).data;
    return { link: `/policy-auditor/${r.id}`, note: r.duplicate ? r.message : "Queued for Policy Auditor analysis – mappings go to Mapping Review" };
  }
  if (SCANS.includes(type)) {
    const r = (await api.post<Row>(`/systems/${sid}/uploads`, fd)).data;
    return { link: `/ingest-runs/${r.id}`, note: "Received – evidence processing queued" };
  }
  if (type === "control_information") {
    const r = (await api.post<Row>(`/systems/${sid}/emass-imports`, fd)).data;
    return { link: `/systems/${sid}/emass-import/${r.id}`, note: `${r.report?.summary?.rows_to_apply ?? r.counts?.controls ?? 0} row(s) ready for review – exclude rows there before applying`, emass_id: r.id };
  }
  if (GENERIC_EMASS.includes(type)) {
    fd.append("system_id", sid);
    const up = (await api.post<Row>("/emass-imports", fd)).data;
    if (up.mismatch) return { pending_target: true, emass_id: up.id, mismatch: up.mismatch };
    return target(up.id, "update", sid, type);
  }
  if (type === "test_results") {
    await api.post<Row>(`/systems/${sid}/tr/workbooks`, fd);
    return { link: "/test-results", note: "Workbook received – column detection queued (Test Results)" };
  }
  if (type === "test_plan") {
    const p = (await api.post<Row>(`/systems/${sid}/tr/test-plan/preview`, fd)).data;
    return { link: "/test-results#test-plan", note: `Preview: ${p.counts?.accepted ?? 0} procedure(s) can be imported`, preview: p };
  }
  if (type === "hwsw") {
    const r = (await api.post<Row>(`/systems/${sid}/inventory/imports`, fd)).data;
    return { link: "/inventory", note: `Inventory import v${r.version} queued – differences become proposals` };
  }
  throw new Error("Unsupported type");
}

export async function target(id: string, action: "update" | "register" | "cancel", sid: string, type: string): Promise<Row> {
  const r = (await api.post<Row>(`/emass-imports/${id}/target`, { action, ...(action === "update" ? { system_id: sid } : {}), report_type: type })).data;
  const to = r.system_id || sid;
  return action === "cancel" ? { cancelled: true }
    : { link: `/systems/${to}/emass-import/${r.id}`, note: `${(r.items || []).length} item(s) ready for review – exclude items there before applying`, emass_id: r.id, target_done: false };
}

export const targetDecision = (mismatch: string, canRegister: boolean): Decision => ({ kind: "target", batchSafe: true, prompt: mismatch,
  options: [{ value: "update", label: "Update the selected system anyway" }, ...(canRegister ? [{ value: "register", label: "Register it as a new system" }] : []),
    { value: "cancel", label: "Cancel this file" }] });
