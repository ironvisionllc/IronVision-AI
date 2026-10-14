export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function shortHash(h: string | null | undefined, n = 12): string {
  return h ? `${h.slice(0, n)}…` : "—";
}

export function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

/** eMASS/NIST display form for control IDs: ac-2.3 → AC-2(3). OSCAL keeps its own lowercase dotted form internally. */
export function fmtControl(id: string | null | undefined): string {
  if (!id) return "";
  const [base, ...enh] = id.split(".");
  return base.toUpperCase() + enh.map((e) => `(${e})`).join("");
}

export function human(s: string | null | undefined): string {
  if (!s) return "";
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}
