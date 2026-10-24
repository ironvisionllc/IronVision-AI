import { useState } from "react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { useAuth } from "@/context/AuthContext";

type Body = { items?: { control_id: string; parameter_id: string }[]; control_id?: string; family?: string };

/** Adopt CNSSI 1253 values (409 → confirm the listed conflicts) with an Undo in the toast. Returns true when adopted. */
export async function adoptCnssi(sid: string, body: Body, done: () => void): Promise<boolean> {
  const post = (confirm: boolean) => api.post<Row>(`/systems/${sid}/parameters/cnssi-adopt`, { ...body, confirm_conflicts: confirm });
  let r;
  try { r = await post(false); } catch (e: any) {
    const c = e?.response?.status === 409 ? e.response.data.conflicts as Row[] : null;
    if (!c) { toast.error(errorMessage(e)); return false; }
    if (!window.confirm(c.map((x) => x.message).join("\n"))) return false;
    try { r = await post(true); } catch (e2) { toast.error(errorMessage(e2)); return false; }
  }
  const id = r.data.undo_id;
  toast.success(`Adopted ${r.data.adopted} CNSSI 1253 value(s) – source recorded, audited`, {
    duration: 10000, action: { label: "Undo", onClick: async () => {
      try { await api.post(`/systems/${sid}/parameters/cnssi-adopt/${id}/undo`); toast.success("Previous value(s) restored"); done(); } catch (e) { toast.error(errorMessage(e)); }
    } } });
  done();
  return true;
}

/** Workbench: CNSSI 1253 value beside each ODP of the control (NSS systems only). */
export function CnssiParams({ sid, cid, p, reload }: { sid: string; cid: string; p: Row; reload: () => void }) {
  const { can } = useAuth();
  const [busy, setBusy] = useState(false);
  const edit = can("system.write");
  const run = async (b: Body) => { setBusy(true); await adoptCnssi(sid, b, reload); setBusy(false); };
  const mapped = p.odps.filter((o: Row) => o.cnssi_value);
  if (!mapped.length && !p.control_level.length) return null;
  return (
    <Panel title="CNSSI 1253 parameter values" eyebrow={p.source ? `${p.source} (PDF p. ${p.pdf_page})` : undefined} testId="wb-cnssi-params"
      actions={edit && mapped.length > 1 ? <button className="btn-secondary px-2 py-0.5 text-[11px]" disabled={busy} data-testid="wb-cnssi-adopt-all"
        onClick={() => window.confirm(`Adopt all ${mapped.length} CNSSI 1253 values for ${cid.toUpperCase()}? Current values are kept in history and can be undone.`) && run({ control_id: cid })}>
        Adopt all CNSSI values for this control</button> : undefined}>
      {!edit && <p className="mb-2 text-[11px] text-slate-500" data-testid="wb-cnssi-locked">Locked – adopting parameter values needs the ISSO or System Owner role (system.write).</p>}
      <table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th className="py-1">Parameter</th><th>Current system value</th><th>CNSSI 1253 value</th><th>Status</th><th /></tr></thead>
        <tbody>{mapped.map((o: Row) => <tr key={o.parameter_id} className="border-t border-slate-100 align-top" data-testid={`wb-cnssi-${o.parameter_id}`}>
          <td className="py-1.5"><span className="font-mono text-[11px]">{o.parameter_id}</span><div className="text-[11px] text-slate-500">{o.description}</div></td>
          <td className="py-1.5">{o.effective_value ?? "—"}{o.source && <div className="text-[10px] text-slate-500">{o.source}</div>}
            {o.overlay_value && <div className="text-[10px] text-indigo-800">Overlay: {o.overlay_value}</div>}</td>
          <td className="py-1.5" data-testid={`wb-cnssi-value-${o.parameter_id}`}>CNSSI 1253 value: {o.cnssi_value} <span className="text-slate-500">({o.cnssi_ref})</span></td>
          <td className="py-1.5">{o.cnssi_status_label}</td>
          <td className="py-1.5 text-right">{edit && o.cnssi_status !== "matches" && <button className="btn-primary px-2 py-0.5 text-[11px]" disabled={busy}
            onClick={() => run({ items: [{ control_id: cid, parameter_id: o.parameter_id }] })} data-testid={`wb-cnssi-adopt-${o.parameter_id}`}>Adopt CNSSI value</button>}</td></tr>)}</tbody></table>
      {p.control_level.map((x: Row, i: number) => <p key={i} className="mt-2 rounded bg-amber-50 p-2 text-[11px] text-amber-900" data-testid={`wb-cnssi-control-level-${i}`}>
        CNSSI 1253 value: {x.value} – applies to control – choose parameter ({x.reason}). Document text: “{x.annotation}”</p>)}
    </Panel>);
}
