import { useState } from "react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { fmtDate } from "@/lib/format";

/** Platform admin: self-signup trial sandboxes – last activity, days until inactivity deletion, Make permanent / Make expirable again. */
export function SandboxOrgsPanel() {
  const { data, error, reload } = useApi<Row>("/admin/sandboxes");
  const [busy, setBusy] = useState("");
  const set = async (o: Row, permanent: boolean) => {
    const msg = permanent
      ? `Make “${o.name}” a permanent sandbox? It will never be deleted for inactivity. It stays a sandbox: personas, the SYNTHETIC label and sandbox separation-of-duties rules are unchanged.`
      : `Make “${o.name}” expirable again? It will be deleted after ${data?.inactivity_days} days without activity.`;
    if (!window.confirm(msg)) return;
    setBusy(o.id);
    try { await api.post(`/admin/sandboxes/${o.id}/permanence`, { permanent, confirm: true }); toast.success(permanent ? "Sandbox is now permanent" : "Sandbox is expirable again"); reload(); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(""); }
  };
  if (error) return null;  // not a platform administrator
  return (
    <Panel title="Sandbox organizations" testId="admin-sandboxes">
      <p className="text-[12px] text-slate-600">Self-signup trial sandboxes are deleted after {data?.inactivity_days ?? "…"} days without activity. “Make permanent” keeps one; it stays a sandbox.</p>
      <div className="mt-2 overflow-x-auto"><table className="w-full text-[12px]" data-testid="admin-sandboxes-table">
        <thead><tr className="text-left text-slate-500"><th>Organization</th><th>Last activity</th><th>Days until deletion</th><th /></tr></thead>
        <tbody>{(data?.items || []).map((o: Row) => (
          <tr key={o.id} className="border-t border-slate-200" data-testid={`admin-sandbox-${o.id}`}>
            <td className="py-1.5"><b>{o.name}</b>{o.is_demo && <span className="ml-1 text-slate-500">(shared demo)</span>}{o.permanent && <span className="ml-1 rounded-full bg-emerald-100 px-1.5 text-[11px] font-semibold text-emerald-900">Permanent</span>}</td>
            <td>{o.last_activity_at ? fmtDate(o.last_activity_at) : "—"}</td>
            <td data-testid={`admin-sandbox-days-${o.id}`}>{o.permanent ? "never" : o.is_demo ? "nightly reset" : o.days_until_deletion ?? "—"}</td>
            <td className="text-right">{!o.is_demo && (o.permanent
              ? <button className="btn-secondary px-2 py-0.5 text-[11px]" disabled={busy === o.id} onClick={() => set(o, false)} data-testid={`admin-sandbox-expirable-${o.id}`}>Undo – make expirable again</button>
              : <button className="btn-primary px-2 py-0.5 text-[11px]" disabled={busy === o.id} onClick={() => set(o, true)} data-testid={`admin-sandbox-permanent-${o.id}`}>Make permanent</button>)}</td>
          </tr>))}</tbody></table></div>
    </Panel>);
}
