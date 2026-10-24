import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { useAuth } from "@/context/AuthContext";

/** 6 · Authorize – authorization strategy: the authorization type sought (moved here from registration). Audited; system.write only. */
export function AuthStrategy({ sid, value, onSaved }: { sid: string; value: string | null; onSaved: () => void }) {
  const { can } = useAuth();
  const { data: ref } = useApi<Row>("/reference/rmf");
  const [edit, setEdit] = useState(false);
  const [v, setV] = useState(value ?? "");
  const [why, setWhy] = useState("");
  const [err, setErr] = useState("");
  const save = async () => {
    try { await api.put(`/systems/${sid}/authorization-strategy`, { authorization_type: v || null, justification: why }); setEdit(false); setErr(""); onSaved(); }
    catch (e) { setErr(errorMessage(e)); }
  };
  if (!edit) return <div data-testid="auth-type">Authorization type sought: <b>{value ?? "—"}</b>
    {can("system.write") && <button className="ml-2 text-[11px] text-blue-800 underline" onClick={() => { setV(value ?? ""); setEdit(true); }} data-testid="auth-type-edit">Change</button>}</div>;
  return (
    <div className="my-2 grid gap-1.5 rounded border border-slate-200 p-2 text-[12px]" data-testid="auth-type-form">
      <label className="font-medium">Authorization type sought (authorization strategy)
        <select className="input mt-1" value={v} onChange={(e) => setV(e.target.value)} data-testid="auth-type-select"><option value="">— not decided —</option>
          {(ref?.authorization_types ?? []).map((o: Row) => <option key={o.value} value={o.value} title={o.help}>{o.value}</option>)}</select></label>
      <input className="input" placeholder="Reason for the change (required, audited)" value={why} onChange={(e) => setWhy(e.target.value)} data-testid="auth-type-why" />
      {err && <div className="text-rose-700" role="alert">{err}</div>}
      <div className="flex gap-2"><button className="btn-primary px-2 py-0.5 text-[11px]" disabled={why.trim().length < 5} onClick={save} data-testid="auth-type-save">Save</button>
        <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => setEdit(false)}>Cancel</button></div>
    </div>);
}
