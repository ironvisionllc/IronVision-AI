import { fmtControl } from "@/lib/format";
import { FormEvent, useMemo, useState } from "react";
import { autosaveCall, useAutoSave } from "@/lib/useAutoSave";
import { AutoSaveStatus } from "@/components/common/AutoSaveStatus";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { S, Table } from "@/components/common/Bits";
import { ROLE_LABELS } from "@/lib/nav";
import { Gated } from "@/components/common/RoleGate";
import { ArchiveSystem } from "@/components/rmf/ArchiveSystem";

const ASSET_FIELDS = ["name", "hostname", "ip_address", "cloud_resource_id", "os", "asset_type", "criticality", "network_zone", "environment", "inventory_source"];
const assetVals = (a: Row) => Object.fromEntries(ASSET_FIELDS.map((k) => [k, a[k] ?? ""]));

/** Editing an existing HW/SW asset auto-saves its fields (adding a new asset and confirming it stay explicit). */
function AssetAutoSave({ sid, asset, setAsset }: { sid: string; asset: Row; setAsset: (a: Row) => void }) {
  const [init] = useState(() => assetVals(asset));
  const val = useMemo(() => assetVals(asset), [asset]);
  const as = useAutoSave<Row>({ id: `asset:${asset.id}`, initial: init, value: val, version: asset.updated_at, apply: (x) => setAsset({ ...asset, ...x }),
    save: async (x, base) => {
      if (!String(x.name).trim()) throw { status: 422, detail: [{ loc: ["body", "name"] }] };
      const body = Object.fromEntries(Object.entries(x).map(([k, v]) => [k, v === "" ? null : v]));
      return { version: (await autosaveCall<Row>("patch", `/systems/${sid}/assets/${asset.id}`, body, base)).updated_at };
    } });
  return <AutoSaveStatus a={as} testId="asset-autosave" />;
}

export default function SystemDetailPage() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const { data: s, reload } = useApi<Row>(`/systems/${id}`);
  const assets = useApi<Row[]>(`/systems/${id}/assets`);
  const roles = useApi<Row[]>(`/systems/${id}/roles`);
  const { data: ref } = useApi<Row>("/reference/registration");
  const [asset, setAsset] = useState<Row | null>(null);
  const [role, setRole] = useState({ user_id: "", role: "isso" });
  const [msg, setMsg] = useState("");
  if (!s) return null;

  const saveAsset = async (e: FormEvent) => {
    e.preventDefault();
    const body = Object.fromEntries(ASSET_FIELDS.map((k) => [k, asset?.[k] || null]).filter(([, v]) => v !== null));
    try {
      if (asset?.id) await api.patch(`/systems/${id}/assets/${asset.id}`, { ...body, review_status: "confirmed" });
      else await api.post(`/systems/${id}/assets`, body);
      setAsset(null); assets.reload();
    } catch (err) { setMsg(errorMessage(err)); }
  };
  const act = async (fn: () => Promise<unknown>) => { try { await fn(); setMsg(""); roles.reload(); assets.reload(); reload(); } catch (err) { setMsg(errorMessage(err)); } };

  const fields: [string, unknown][] = [["eMASS ID", s.emass_id], ["Organization", s.organization_name], ["Mission owner", s.mission_owner], ["System owner", s.system_owner_name],
    ["ISSO", s.isso_name], ["ISSM", s.issm_name], ["AO", s.ao_name], ["Environment", s.operating_environment], ["Deployment", s.deployment_type],
    ["Lifecycle phase", s.lifecycle_phase], ["Authorization", s.authorization_status], ["Authorized", s.authorization_date], ["Expires", s.authorization_expiration],
    ["C / I / A", `${s.confidentiality_impact} / ${s.integrity_impact} / ${s.availability_impact}`], ["Categorization (high-water)", s.categorization],
    ["Baseline", `${s.baseline_key}${s.include_privacy ? " + privacy" : ""}`], ["Overlays", (s.overlay_keys || []).join(", ") || "none"], ["Mission criticality", s.mission_criticality]];
  return (
    <div data-testid="system-detail-page">
      <PageHeader title={s.name} subtitle={s.description}>
        <ArchiveSystem s={s} onDone={reload} />
        <Link className="btn-secondary" to={`/systems/${id}/import-center`} data-testid="open-import-center-btn">Import Center</Link>
        <Link className="btn-secondary" to={`/systems/${id}/authorization`} data-testid="open-authorization-btn">Authorization package</Link>
        <Link className="btn-primary" to={`/systems/${id}/controls`} data-testid="open-workbench-btn">Open control workbench ({s.metrics.assigned_controls})</Link>
      </PageHeader>
      {s.archived_at && <div className="mb-3 rounded border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900" data-testid="system-archived-banner">
        Archived {s.archived_at.slice(0, 10)} by {s.archived_by}: {s.archive_reason}. Hidden from active lists – restore to use it again.</div>}
      {msg && <div className="mb-3 rounded border border-rose-300 bg-rose-50 p-2 text-sm text-rose-800" role="alert">{msg}</div>}
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Overview" testId="system-overview">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-[13px]">{fields.map(([k, v]) => <div key={k} className="flex justify-between gap-2 border-b border-slate-100 py-1"><dt className="text-slate-500">{k}</dt><dd className="text-right text-slate-800">{String(v ?? "—")}</dd></div>)}</dl>
          {s.tailoring.length > 0 && <div className="mt-3 text-[12px]"><div className="eyebrow">Tailoring</div>{s.tailoring.map((t: Row) => <div key={t.id}>{t.action} {fmtControl(t.control_id)} – {t.justification}</div>)}</div>}
        </Panel>
        <Panel title="System-scoped roles" testId="system-roles-panel">
          <Table head={["User", "Role", "Scope", ""]}>
            {roles.data?.map((r) => (
              <tr key={r.id}><td className="td">{r.display_name} <span className="text-slate-400">{r.email}</span></td><td className="td">{ROLE_LABELS[r.role] ?? r.role}</td><td className="td">system</td>
                <td className="td"><Gated perm="system.roles.manage"><button className="btn-secondary px-2 py-0.5 text-xs" data-testid={`revoke-role-${r.id}`} onClick={() => act(() => api.delete(`/systems/${id}/roles/${r.id}`))}>Revoke</button></Gated></td></tr>
            ))}
          </Table>
          {can("system.roles.manage") && (
            <div className="mt-3 flex gap-2">
              <select className="input" value={role.user_id} onChange={(e) => setRole({ ...role, user_id: e.target.value })} data-testid="grant-role-user"><option value="">Select user…</option>{ref?.users.map((u: Row) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</select>
              <select className="input w-40" value={role.role} onChange={(e) => setRole({ ...role, role: e.target.value })} data-testid="grant-role-role">{Object.keys(ROLE_LABELS).map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}</select>
              <button className="btn-primary" disabled={!role.user_id} onClick={() => act(() => api.post(`/systems/${id}/roles`, role))} data-testid="grant-role-btn">Grant</button>
            </div>
          )}
        </Panel>
      </div>
      <Panel title={`Asset inventory (${assets.data ? assets.data.length : "…"})`} className="mt-5" testId="assets-panel"
        actions=<Gated perm="system.write"><button className="btn-secondary" onClick={() => setAsset({})} data-testid="add-asset-btn">Add asset</button></Gated>>
        {asset && (
          <form onSubmit={saveAsset} className="mb-4 grid grid-cols-5 gap-2 rounded border border-slate-200 bg-slate-50 p-3" data-testid="asset-form">
            {ASSET_FIELDS.map((k) => <input key={k} className="input" placeholder={k} value={asset[k] ?? ""} required={k === "name"} onChange={(e) => setAsset({ ...asset, [k]: e.target.value })} data-testid={`asset-${k}`} />)}
            <button className="btn-primary" type="submit" data-testid="asset-save-btn">Save</button><button type="button" className="btn-secondary" onClick={() => setAsset(null)}>Cancel</button>
            {asset.id && <div className="col-span-5"><AssetAutoSave sid={id} asset={asset} setAsset={setAsset} /></div>}
          </form>
        )}
        <Table head={["Name", "Hostname", "IP", "Cloud ID", "OS", "Type", "Criticality", "Zone", "Env", "Source", "Last observed", "Review", ""]} testId="assets-table">
          {assets.data?.map((a) => (
            <tr key={a.id} data-testid={`asset-row-${a.name}`}>
              {["name", "hostname", "ip_address", "cloud_resource_id", "os", "asset_type", "criticality", "network_zone", "environment", "inventory_source"].map((k) => <td key={k} className="td text-[12px]">{a[k] ?? "—"}</td>)}
              <td className="td font-mono text-[11px]">{a.last_observed_at?.slice(0, 16) ?? "—"}</td>
              <td className="td">{a.is_unmatched ? <S v="unmatched" label="ingest" /> : <S v="confirmed" />}</td>
              <td className="td whitespace-nowrap"><Gated perm="system.write"><><button className="btn-secondary px-2 py-0.5 text-xs" onClick={() => setAsset(a)} data-testid={`edit-asset-${a.name}`}>Edit</button> <button className="btn-secondary px-2 py-0.5 text-xs" onClick={() => act(() => api.delete(`/systems/${id}/assets/${a.id}`))}>Delete</button></></Gated></td>
            </tr>
          ))}
        </Table>
      </Panel>
    </div>
  );
}
