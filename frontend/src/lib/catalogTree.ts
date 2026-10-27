import type { ControlSummary } from "@/lib/types";
import { fmtControl } from "@/lib/format";

export interface TreeNode { c: ControlSummary; enh: ControlSummary[] }
export interface FamilyNode { id: string; title: string; controls: TreeNode[]; base: number; enhancements: number }
export interface SysRow { control_id: string; implementation_status?: string; assessment_status?: string; responsibility?: string; origin?: string }
export type Filters = { baseline: string; implementation_status: string; assessment_status: string; applicability: string };
export const NO_FILTERS: Filters = { baseline: "", implementation_status: "", assessment_status: "", applicability: "" };

export const famKey = (f: string) => `f:${f}`;
export const ctlKey = (c: string) => `c:${c}`;
export const idLabel = (c: ControlSummary) => fmtControl(c.control_id);

/** "AC-2(1)", "ac-2.1", "AC-02(01)", "ac 2 1" → "ac-2.1"; "cci-15" / "CCI-000015" → "CCI-000015"; otherwise free text. */
export function normalizeQuery(q: string): { id: string | null; cci: string | null; text: string } {
  const t = q.trim().toLowerCase();
  const cci = t.match(/^cci[-\s]?0*(\d{1,6})$/);
  if (cci) return { id: null, cci: `CCI-${cci[1].padStart(6, "0")}`, text: t };
  const m = t.match(/^([a-z]{2})[-\s]?0*(\d{1,3})(?:\s*(?:\(\s*0*(\d{1,3})\s*\)|[.\s]0*(\d{1,3})))?$/);
  if (m) return { id: `${m[1]}-${m[2]}${m[3] || m[4] ? `.${m[3] || m[4]}` : ""}`, cci: null, text: t };
  return { id: null, cci: null, text: t };
}

/** Families → base controls → enhancements, derived only from catalog fields (family_id/title, is_enhancement, parent_control_id). */
export function buildTree(items: ControlSummary[], showWithdrawn: boolean): FamilyNode[] {
  const fams = new Map<string, FamilyNode>();
  const nodes = new Map<string, TreeNode>();
  const vis = items.filter((c) => showWithdrawn || !c.is_withdrawn);
  const fam = (c: ControlSummary) => {
    if (!fams.has(c.family_id)) fams.set(c.family_id, { id: c.family_id, title: c.family_title, controls: [], base: 0, enhancements: 0 });
    return fams.get(c.family_id)!;
  };
  for (const c of vis) if (!c.is_enhancement) { const n = { c, enh: [] }; nodes.set(c.control_id, n); fam(c).controls.push(n); fam(c).base += 1; }
  for (const c of vis) if (c.is_enhancement) {
    const p = c.parent_control_id ? nodes.get(c.parent_control_id) : undefined;
    if (p) p.enh.push(c); else fam(c).controls.push({ c, enh: [] });  // parent hidden (withdrawn): shown at control level
    fam(c).enhancements += 1;
  }
  return [...fams.values()];
}

export function applicability(r: SysRow | undefined): string {
  if (!r) return "not_selected";
  if (r.implementation_status === "not_applicable") return "not_applicable";
  if (r.responsibility === "inherited" || r.implementation_status === "inherited") return "inherited";
  return "applicable";
}

export function passes(c: ControlSummary, f: Filters, sys: Map<string, SysRow> | null): boolean {
  if (f.baseline) {
    if (["low", "moderate", "high", "privacy"].includes(f.baseline)) { if (!c.baselines.includes(f.baseline)) return false; }
    else if (!sys || sys.get(c.control_id)?.origin !== f.baseline) return false;
  }
  if (!sys) return true;
  const r = sys.get(c.control_id);
  if (f.implementation_status && r?.implementation_status !== f.implementation_status) return false;
  if (f.assessment_status && r?.assessment_status !== f.assessment_status) return false;
  if (f.applicability && applicability(r) !== f.applicability) return false;
  return true;
}

/** Keep a control if it or any enhancement passes; keep only passing enhancements. Empty families are dropped. */
export function filterTree(tree: FamilyNode[], keep: (c: ControlSummary) => boolean): FamilyNode[] {
  return tree.map((f) => ({ ...f, controls: f.controls.map((n) => ({ c: n.c, enh: n.enh.filter(keep), self: keep(n.c) }))
    .filter((n) => n.self || n.enh.length).map(({ c, enh }) => ({ c, enh })) })).filter((f) => f.controls.length);
}

export function matcher(q: string, cciIndex: Record<string, string[]> | null): ((c: ControlSummary) => boolean) | null {
  const n = normalizeQuery(q);
  if (!n.text) return null;
  if (n.cci) { const ids = new Set(cciIndex?.[n.cci] ?? []); return (c) => ids.has(c.control_id); }
  if (n.id) return (c) => c.control_id === n.id;
  const words = n.text.split(/\s+/).filter(Boolean);
  return (c) => { const hay = `${c.control_id} ${idLabel(c)} ${c.title}`.toLowerCase(); return words.every((w) => hay.includes(w)); };
}

/** Matches plus the family / parent keys to expand so every match is visible. */
export function searchTree(tree: FamilyNode[], match: (c: ControlSummary) => boolean): { matches: Set<string>; expand: Set<string> } {
  const matches = new Set<string>(), expand = new Set<string>();
  for (const f of tree) for (const n of f.controls) {
    if (match(n.c)) { matches.add(n.c.control_id); expand.add(famKey(f.id)); }
    for (const e of n.enh) if (match(e)) { matches.add(e.control_id); expand.add(famKey(f.id)); expand.add(ctlKey(n.c.control_id)); }
  }
  return { matches, expand };
}

/** Keys to expand so a deep-linked control is visible (its family and, for an enhancement, its parent). */
export function pathTo(tree: FamilyNode[], id: string): string[] {
  for (const f of tree) for (const n of f.controls) {
    if (n.c.control_id === id) return [famKey(f.id)];
    if (n.enh.some((e) => e.control_id === id)) return [famKey(f.id), ctlKey(n.c.control_id)];
  }
  return [];
}

export function allKeys(tree: FamilyNode[]): string[] {
  return tree.flatMap((f) => [famKey(f.id), ...f.controls.filter((n) => n.enh.length).map((n) => ctlKey(n.c.control_id))]);
}

export function familyStats(f: FamilyNode, sys: Map<string, SysRow> | null) {
  const all = f.controls.flatMap((n) => [n.c, ...n.enh]);
  if (!sys) return null;
  const rows = all.map((c) => sys.get(c.control_id)).filter(Boolean) as SysRow[];
  return { applicable: rows.filter((r) => applicability(r) !== "not_applicable").length,
           implemented: rows.filter((r) => r.implementation_status === "implemented").length,
           assessed: rows.filter((r) => r.assessment_status && r.assessment_status !== "not_assessed").length };
}

export interface SavedState { expanded: string[]; q: string; withdrawn: boolean; filters: Filters; scrollY: number }
export const stateKey = (sys: string) => `aegis.catalogTree.${sys || "catalog"}`;
export function loadState(sys: string): SavedState | null {
  try { return JSON.parse(sessionStorage.getItem(stateKey(sys)) || "null"); } catch { return null; }
}
export function saveState(sys: string, s: SavedState) { sessionStorage.setItem(stateKey(sys), JSON.stringify(s)); }
