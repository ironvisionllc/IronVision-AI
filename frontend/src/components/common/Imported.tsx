import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";

export type ImportedInfo = { import_kind: string; import_id: string; file_name: string; entry_id: string; actions: string[]; decision?: boolean };

/** Destination-screen provenance: entity id → the import that created it (for the marker and row-level Delete). */
export function useImported(sid: string | null | undefined, kind: string) {
  const { data, reload } = useApi<Row>(sid ? `/systems/${sid}/imported-data/index?kind=${kind}` : null);
  return { items: (data?.items || {}) as Record<string, ImportedInfo>, reload };
}

export function ImportedMark({ info, testId }: { info?: ImportedInfo; testId: string }) {
  if (!info) return null;
  return <Link to={`/import-center/manage/${info.import_kind}/${info.import_id}`} className="ml-1 inline-block rounded bg-sky-50 px-1 text-[10px] text-sky-900 dark:bg-sky-950 dark:text-sky-200"
    title="Open Manage imported data" data-testid={testId}>Imported from {info.file_name}</Link>;
}

const actionFor = (i: ImportedInfo) => (i.actions.includes("delete") ? "delete" : i.actions.includes("clear") ? "clear" : "restore");

/** Multi-select Delete for imported rows on a destination screen: confirm → per-import requests → toast with Undo (also 30 days in Manage). */
export function ImportedDeleteBar({ selected, items, onDone, testId, label }: { selected: string[]; items: Record<string, ImportedInfo>; onDone: () => void; testId: string; label?: string }) {
  const [busy, setBusy] = useState(false);
  const picked = selected.map((id) => items[id]).filter(Boolean);
  const run = async () => {
    const decisions = picked.filter((i) => i.decision).length;
    if (!window.confirm(`Delete ${picked.length} imported item(s)?${decisions ? ` ${decisions} carry an approved decision – it is kept and flagged for re-review.` : ""} You can undo this for 30 days.`)) return;
    setBusy(true);
    const ops: [string, string, string][] = [];
    try {
      const by: Record<string, ImportedInfo[]> = {};
      picked.forEach((i) => { const k = `${i.import_kind}/${i.import_id}`; by[k] = [...(by[k] || []), i]; });
      let ok = 0, failed = 0;
      for (const [k, list] of Object.entries(by)) {
        const groups: Record<string, string[]> = {};
        list.forEach((i) => { groups[actionFor(i)] = [...(groups[actionFor(i)] || []), i.entry_id]; });
        for (const [action, ids] of Object.entries(groups)) {
          const r = (await api.post<Row>(`/imported-data/${k}`, { action, ids, force: true })).data;
          ok += r.ok; failed += r.failed;
          if (r.op?.op_id) ops.push([k, r.op.op_id, k.split("/")[0]]);
        }
      }
      onDone();
      toast.success(`${ok} deleted${failed ? `, ${failed} need attention in Manage imported data` : ""}`, {
        duration: 15000, action: ops.length ? { label: "Undo", onClick: () => undoAll(ops, onDone) } : undefined });
    } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };
  if (!picked.length) return null;
  return <button className="rounded bg-rose-700 px-2 py-1 text-[12px] font-semibold text-white disabled:opacity-40" disabled={busy} onClick={run} data-testid={testId}>
    {label || `Delete selected imported (${picked.length})`}</button>;
}

async function undoAll(ops: [string, string, string][], onDone: () => void) {
  try {
    for (const [k, op, kind] of ops.reverse()) await api.post(kind === "emass" ? `/emass-imports/${k.split("/")[1]}/manage/${op}/undo` : `/imported-data/${k}/undo/${op}`);
    toast.success("Undone"); onDone();
  } catch (e) { toast.error(errorMessage(e)); }
}

/** Row checkbox shown only for imported rows the role can change. */
export function ImportedCheck({ id, info, checked, onChange }: { id: string; info?: ImportedInfo; checked: boolean; onChange: (id: string, on: boolean) => void }) {
  if (!info || !info.actions.length) return null;
  return <input type="checkbox" className="mr-1 align-middle" checked={checked} onChange={(e) => onChange(id, e.target.checked)} aria-label="Select imported row" data-testid={`imp-select-${id}`} />;
}

export function useSelection() {
  const [sel, setSel] = useState<string[]>([]);
  const toggle = (id: string, on: boolean) => setSel((s) => (on ? [...new Set([...s, id])] : s.filter((x) => x !== id)));
  return { sel, toggle, clear: () => setSel([]) };
}
