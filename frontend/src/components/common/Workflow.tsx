import { ReactNode, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bell } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { useAuth } from "@/context/AuthContext";
import { Modal } from "./Modal";

export { Modal };

export function PoamLink({ id, humanId }: { id: string; humanId: string }) {
  return <Link to={`/poams/${id}`} className="font-mono text-[12px] font-semibold text-blue-800 hover:underline" data-testid={`poam-link-${humanId}`}>{humanId}</Link>;
}

export function AddToPoamButton({ findingId, onDone }: { findingId: string; onDone?: () => void }) {
  const { can } = useAuth();
  const nav = useNavigate();
  const [m, setM] = useState<Row | null>(null);
  const [f, setF] = useState<Row>({});
  const [err, setErr] = useState("");
  if (!can("poam.manage")) return null;
  const open = async () => {
    const r = await api.get<Row>(`/findings/${findingId}/poam-match`);
    setM(r.data); setF({ ...r.data.prefill, control_ids: r.data.prefill.control_ids.join(", "), due_date: "", remediation_plan: "" }); setErr("");
  };
  const link = async (pid: string) => {
    try { await api.post(`/poams/${pid}/findings`, { finding_id: findingId }); setM(null); onDone?.(); nav(`/poams/${pid}`); } catch (e) { setErr(errorMessage(e)); }
  };
  const create = async (override?: string) => {
    try {
      const body = { system_id: f.system_id, finding_ids: [findingId], weakness: f.weakness, severity: f.severity || undefined, cat: f.cat || undefined,
        source_label: f.source_label, control_ids: String(f.control_ids).split(",").map((s) => s.trim()).filter(Boolean),
        due_date: f.due_date || undefined, remediation_plan: f.remediation_plan || undefined, allow_duplicate_justification: override };
      const r = await api.post<Row>("/poams", body); setM(null); onDone?.(); nav(`/poams/${r.data.id}`);
    } catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <>
      <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={open} data-testid={`add-to-poam-${findingId}`}>Add to POA&M</button>
      {m && (
        <Modal title="Add finding to POA&M" onClose={() => setM(null)} testId="add-poam-modal">
          {m.matches.length > 0 && (
            <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-[13px]" data-testid="poam-match-notice">
              <div className="mb-2 font-medium text-amber-900">Matches an existing open POA&M (rule v{m.match_rule?.version}: {m.match_rule?.description})</div>
              {m.matches.map((x: Row) => (
                <div key={x.id} className="flex items-center justify-between gap-2 py-1"><span><b>{x.human_id}</b> {x.weakness}</span>
                  <button className="btn-primary px-2 py-1 text-xs" onClick={() => link(x.id)} data-testid={`link-existing-${x.human_id}`}>Link to existing {x.human_id}</button></div>
              ))}
            </div>
          )}
          <div className="grid gap-2 text-[13px]">
            <label>Weakness<textarea className="input" rows={2} value={f.weakness} onChange={(e) => setF({ ...f, weakness: e.target.value })} data-testid="poam-form-weakness" /></label>
            <div className="grid grid-cols-3 gap-2">
              <label>Controls<input className="input" value={f.control_ids} onChange={(e) => setF({ ...f, control_ids: e.target.value })} data-testid="poam-form-controls" /></label>
              <label>Severity<select className="input" value={f.severity ?? ""} onChange={(e) => setF({ ...f, severity: e.target.value })} data-testid="poam-form-severity">{["critical", "high", "medium", "low"].map((s) => <option key={s}>{s}</option>)}</select></label>
              <label>Due date<input type="date" className="input" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} data-testid="poam-form-due" /></label>
            </div>
            <div className="text-[11px] text-slate-500">Asset {f.asset_name ?? "—"} · Source {f.source_label} · IDs {(f.vuln_ids || []).join(", ")} · Evidence {f.evidence_id ? <Link className="text-blue-800 underline" to="/evidence-ledger">{String(f.evidence_id).slice(0, 8)}</Link> : "—"}</div>
            <label>Remediation plan<textarea className="input" rows={2} value={f.remediation_plan} onChange={(e) => setF({ ...f, remediation_plan: e.target.value })} data-testid="poam-form-plan" /></label>
          </div>
          {err && <div className="mt-2 text-[12px] text-rose-700" role="alert" data-testid="poam-form-error">{err}</div>}
          <div className="mt-3 flex justify-end gap-2">
            {m.matches.length > 0
              ? <button className="btn-secondary" onClick={() => { const j = window.prompt("Justify creating a separate POA&M (min 10 chars)"); if (j) create(j); }} data-testid="poam-create-anyway">Create separate POA&M anyway…</button>
              : <button className="btn-primary" onClick={() => create()} data-testid="poam-form-submit">Create POA&M</button>}
          </div>
        </Modal>
      )}
    </>
  );
}

export function NotificationBell() {
  const { data, reload } = useApi<Row>("/notifications");
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const go = async (n: Row) => { await api.post(`/notifications/${n.id}/ack`); setOpen(false); reload(); if (n.link) nav(n.link); };
  return (
    <div className="relative">
      <button className="btn-ghost relative px-2 py-1.5" onClick={() => { setOpen(!open); reload(); }} aria-label="Notifications" data-testid="notification-bell">
        <Bell className="h-4 w-4" />
        {data?.unread > 0 && <span className="absolute -right-1 -top-1 rounded-full bg-rose-600 px-1.5 text-[10px] font-bold text-white" data-testid="notification-count">{data?.unread}</span>}
      </button>
      {open && (
        <div className="iv-popover absolute right-0 z-50 mt-2 max-h-[70vh] w-96 overflow-y-auto" data-testid="notification-panel" onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
          {(data?.items || []).length === 0 && <div className="p-3 text-[12px] text-slate-500">No notifications</div>}
          {(data?.items || []).map((n: Row) => (
            <button key={n.id} onClick={() => go(n)} className={`block w-full border-b border-slate-200/60 px-3.5 py-2.5 text-left text-[12px] hover:bg-blue-50 ${n.read_at ? "opacity-60" : ""}`} data-testid={`notification-${n.id}`}>
              <div className="font-heading font-semibold text-slate-900">{n.title}</div>{n.body && <div className="text-slate-500">{n.body}</div>}
              <div className="text-[10px] uppercase text-slate-400">{n.kind} · {new Date(n.created_at).toLocaleString()} {n.read_at ? "· acknowledged" : ""}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
