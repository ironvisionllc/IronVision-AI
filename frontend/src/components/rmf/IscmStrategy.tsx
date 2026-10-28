import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";
import { useAuth } from "@/context/AuthContext";
import { Panel } from "@/components/common/Panel";
import { Help } from "@/components/rmf/RolesEditor";

const SLCM = ["slcm_criticality", "slcm_frequency", "slcm_method", "slcm_reporting", "slcm_tracking", "slcm_comments"];
const STATUS: Record<string, string> = { draft: "Draft – not yet feeding controls", pending_approval: "Pending ISSM approval", approved: "Approved", rejected: "Returned by the ISSM" };

function SlcmInputs({ vals, set, o, prefix, ro }: { vals: Row; set: (k: string, v: string) => void; o: Row; prefix: string; ro: boolean }) {
  return <div className="grid gap-2 md:grid-cols-3">{SLCM.map((k) => <label key={k} className="block text-[12px]"><span className="font-medium">{o.fields[k]}</span>
    {k === "slcm_frequency" || k === "slcm_method" ? <select className="input mt-1 w-full" disabled={ro} value={vals[k] ?? ""} onChange={(e) => set(k, e.target.value)} data-testid={`${prefix}-${k}`}>
      <option value="">— not set (control decides) —</option>{(k === "slcm_frequency" ? o.frequencies : o.methods).map((x: string) => <option key={x}>{x}</option>)}</select>
      : <input className="input mt-1 w-full" disabled={ro} maxLength={k === "slcm_comments" ? 4000 : 2000} value={vals[k] ?? ""} onChange={(e) => set(k, e.target.value)} data-testid={`${prefix}-${k}`} />}</label>)}</div>;
}

/** Select · Task S-5 – Continuous Monitoring Strategy (ISCM). Its approved values feed the eMASS SLCM fields of every control (override → profile → default). */
export function IscmStrategy({ sid }: { sid: string }) {
  const { can, user } = useAuth();
  const { data: d, reload } = useApi<Row>(`/systems/${sid}/iscm`);
  const { data: promo, reload: reloadPromo } = useApi<Row>(`/systems/${sid}/iscm/promote-preview`);
  const [f, setF] = useState<Row>({ defaults: {}, profiles: [] });
  const [busy, setBusy] = useState("");
  useEffect(() => { if (d) setF(d.strategy ? { ...d.strategy } : { narrative: "", scope: "", defaults: {}, profiles: [], reporting: [], review_activities: [], evidence_requirements: [] }); }, [d]);
  if (!d) return null;
  const o = d.options, s = d.strategy, ro = !can("system.write");
  const u = user || null;
  const isIssm = u?.persona_role === "issm" || (u?.roles || []).some((r: Row) => r.role === "issm");
  const act = async (name: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(name);
    try { await fn(); toast.success(ok); reload(); reloadPromo(); } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(""); }
  };
  const body = () => ({ ...f, profiles: (f.profiles || []).map((p: Row) => ({ name: p.name, match_type: p.match_type, match_value: p.match_value, values: p.values || {} })) });
  const setP = (i: number, patch: Row) => setF((x) => ({ ...x, profiles: x.profiles.map((p: Row, j: number) => j === i ? { ...p, ...patch } : p) }));
  const list = (k: string, cols: string[], label: string) => <div className="text-[12px]"><div className="font-medium">{label}</div>
    {(f[k] || []).map((r: Row, i: number) => <div key={i} className="mt-1 flex gap-1">{cols.map((c) => <input key={c} className="input flex-1" disabled={ro} placeholder={c} value={r[c] ?? ""}
      onChange={(e) => setF((x) => ({ ...x, [k]: x[k].map((y: Row, j: number) => j === i ? { ...y, [c]: e.target.value } : y) }))} data-testid={`iscm-${k}-${i}-${c}`} />)}
      {!ro && <button className="text-rose-700" onClick={() => setF((x) => ({ ...x, [k]: x[k].filter((_: Row, j: number) => j !== i) }))} aria-label="Remove">×</button>}</div>)}
    {!ro && <button className="mt-1 text-blue-800 underline" onClick={() => setF((x) => ({ ...x, [k]: [...(x[k] || []), {}] }))} data-testid={`iscm-add-${k}`}>+ Add</button>}</div>;
  return (
    <Panel title="Continuous Monitoring Strategy (ISCM) – SP 800-37 Task S-5" testId="iscm-panel"
      actions={<Link className="text-[12px] text-blue-800 underline" to="/rmf/monitor" data-testid="iscm-go-monitor">Monitor execution (Step 7) →</Link>}>
      <p className="text-[12px] text-slate-600">One system-level strategy for how controls are monitored. Its approved values <b>feed the eMASS SLCM fields</b> (SLCM Criticality, Frequency, Method, Reporting, Tracking, Comments) of every control; a control can still override any field in its Implementation Plan.
        <Help text="Effective value per control: per-control override → first matching profile → system default. Inherited and Not Applicable controls have no SLCM values (eMASS rule). Exports (eMASS xlsx, OSCAL SSP, sync payload) always use the effective value." /></p>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px]" data-testid="iscm-status">
        <span className={`rounded px-2 py-0.5 ${s?.status === "approved" ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"}`}>{s ? `${STATUS[s.status]} · v${s.version}` : "No strategy yet"}</span>
        {s?.approved_snapshot && <span data-testid="iscm-feeds">Feeds eMASS SLCM fields for <b>{d.feeds.controls}</b> of {d.feeds.total} controls · {d.feeds.overrides} with per-control overrides</span>}
        {s?.approved_by && <span className="text-slate-500">Approved by {s.approved_by.persona_email} {s.approved_at?.slice(0, 10)}</span>}
        {s?.is_synthetic && <span className="text-slate-500">SYNTHETIC demo strategy</span>}
        {d.pending_changes && s?.approved_snapshot && <span className="text-amber-800">Edits are not in effect until the ISSM approves them – controls use v{s.approved_snapshot.version}.</span>}</div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <label className="block text-[12px]"><span className="font-medium">Strategy narrative</span><textarea className="input mt-1 w-full" rows={3} disabled={ro} value={f.narrative ?? ""} onChange={(e) => setF({ ...f, narrative: e.target.value })} data-testid="iscm-narrative" /></label>
        <label className="block text-[12px]"><span className="font-medium">Scope</span><textarea className="input mt-1 w-full" rows={3} disabled={ro} value={f.scope ?? ""} onChange={(e) => setF({ ...f, scope: e.target.value })} data-testid="iscm-scope" /></label>
      </div>
      <div className="mt-3 text-[12px] font-medium" id="iscm-defaults" data-testid="iscm-defaults-heading">System default SLCM values</div>
      <SlcmInputs vals={f.defaults || {}} o={o} prefix="iscm-default" ro={ro} set={(k, v) => setF({ ...f, defaults: { ...f.defaults, [k]: v } })} />
      <div className="mt-3 text-[12px] font-medium">Profiles (family / control list / Security Control Designation) – first match wins</div>
      {(f.profiles || []).map((p: Row, i: number) => <div key={i} className="mt-2 rounded border border-slate-200 p-2" data-testid={`iscm-profile-${i}`}>
        <div className="mb-1 flex flex-wrap gap-2 text-[12px]"><input className="input" placeholder="Name" disabled={ro} value={p.name ?? ""} onChange={(e) => setP(i, { name: e.target.value })} data-testid={`iscm-profile-${i}-name`} />
          <select className="input" disabled={ro} value={p.match_type ?? "family"} onChange={(e) => setP(i, { match_type: e.target.value })} data-testid={`iscm-profile-${i}-type`}>{o.match_types.map((t: string) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select>
          <input className="input flex-1" placeholder="e.g. au,si  or  ac-2,ac-3  or  Common" disabled={ro} value={p.match_value ?? ""} onChange={(e) => setP(i, { match_value: e.target.value })} data-testid={`iscm-profile-${i}-match`} />
          {!ro && <button className="text-rose-700" onClick={() => setF({ ...f, profiles: f.profiles.filter((_: Row, j: number) => j !== i) })} data-testid={`iscm-profile-${i}-remove`}>Remove</button>}</div>
        <SlcmInputs vals={p.values || {}} o={o} prefix={`iscm-profile-${i}`} ro={ro} set={(k, v) => setP(i, { values: { ...(p.values || {}), [k]: v } })} /></div>)}
      {!ro && <button className="mt-2 text-[12px] text-blue-800 underline" onClick={() => setF({ ...f, profiles: [...(f.profiles || []), { name: "", match_type: "family", match_value: "", values: {} }] })} data-testid="iscm-add-profile">+ Add profile</button>}
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        {list("review_activities", ["activity", "frequency", "role"], "Assessment / review activities")}
        {list("evidence_requirements", ["evidence", "freshness_days"], "Evidence collection requirements")}
        {list("reporting", ["report", "audience", "frequency"], "Reporting and review schedule")}
      </div>
      <div className="mt-2 text-[11px] text-slate-500" data-testid="iscm-people">Responsible monitoring personnel (from Key roles): ISSO {(d.people.isso || []).join(", ") || "—"} · ISSM {(d.people.issm || []).join(", ") || "—"} · System Owner {(d.people.system_owner || []).join(", ") || "—"}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        {!ro && <button className="btn-secondary" disabled={!!busy} onClick={() => act("save", () => api.put(`/systems/${sid}/iscm`, body()), "Draft saved – submit it for ISSM approval to take effect")} data-testid="iscm-save">Save draft</button>}
        {!ro && (!s || ["draft", "rejected"].includes(s.status)) && <button className="btn-primary" disabled={!!busy} onClick={() => act("submit", async () => { await api.put(`/systems/${sid}/iscm`, body()); return api.post(`/systems/${sid}/iscm/submit`); }, "Saved and submitted to the ISSM – it takes effect when the ISSM approves it")} data-testid="iscm-submit">Save & submit for ISSM approval</button>}
        {isIssm && s?.status === "pending_approval" && <>
          <button className="btn-primary" disabled={!!busy} onClick={() => act("ok", () => api.post(`/systems/${sid}/iscm/decision`, { approve: true }), "Strategy approved – SLCM values updated")} data-testid="iscm-approve">Approve (ISSM)</button>
          <button className="btn-secondary" disabled={!!busy} onClick={() => act("no", () => api.post(`/systems/${sid}/iscm/decision`, { approve: false }), "Returned to the ISSO")} data-testid="iscm-reject">Return</button></>}
      </div>
      {!ro && !!promo?.items?.length && <div className="mt-4 rounded border border-blue-200 bg-blue-50/40 p-3 text-[12px]" data-testid="iscm-promote">
        <div className="font-medium">Promote common values (reviewed action – never automatic)</div><div className="text-slate-600">{promo.note}</div>
        {promo.items.map((it: Row, i: number) => <div key={i} className="mt-1 flex flex-wrap items-center gap-2" data-testid={`iscm-promote-${i}`}><span>{it.controls} of {it.of} controls override <b>{it.label}</b> = “{it.value}” ({it.families.join(", ")})</span>
          <button className="underline" onClick={() => act("promote", () => api.post(`/systems/${sid}/iscm/promote`, { field: it.field, value: it.value, target: it.suggest, families: it.families }), "Added to the draft strategy")} data-testid={`iscm-promote-${i}-btn`}>
            {it.suggest === "system_default" ? "Make it the system default" : `Make it the ${it.families.join("/")} profile value`}</button></div>)}</div>}
    </Panel>);
}
