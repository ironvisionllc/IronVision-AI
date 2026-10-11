import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { Table } from "@/components/common/Bits";

export function SystemsPage() {
  const { can } = useAuth();
  const { data } = useApi<Row[]>("/systems");
  return (
    <div data-testid="systems-page">
      <PageHeader title="Systems" subtitle="Registered systems in your scope (synthetic tenant)">
        <div className="flex gap-2">
          <Link className="btn-secondary" to="/emass" data-testid="import-emass-btn">eMASS sync / import</Link>
          {can("system.register") && <Link to="/systems/new" className="btn-primary" data-testid="register-system-btn"><Plus className="h-4 w-4" />Register system</Link>}
        </div>
      </PageHeader>
      <Panel testId="systems-table-panel">
        <Table head={["System", "eMASS ID", "Baseline", "Categorization", "Phase", "Authorization", "Assigned controls", "Open findings"]} testId="systems-table">
          {data?.map((s) => (
            <tr key={s.id} data-testid={`system-row-${s.acronym}`}>
              <td className="td"><Link to={`/systems/${s.id}`} className="font-medium text-blue-800 hover:underline">{s.name}</Link> <span className="text-slate-400">{s.acronym}</span></td>
              <td className="td font-mono text-[12px]">{s.emass_id ?? "—"}</td><td className="td uppercase">{s.baseline_key}{s.overlay_keys?.length ? ` + ${s.overlay_keys.join(", ")}` : ""}</td>
              <td className="td">{s.categorization}</td><td className="td">{s.lifecycle_phase}</td><td className="td">{s.authorization_status}</td>
              <td className="td font-mono">{s.metrics.assigned_controls}</td><td className="td font-mono">{s.metrics.open_findings}</td>
            </tr>
          ))}
        </Table>
      </Panel>
    </div>
  );
}

const F = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="block text-[12px] font-medium text-slate-700">{label}<div className="mt-1">{children}</div></label>
);

export function RegisterSystemPage() {
  const nav = useNavigate();
  const { select } = useSystems();
  const { data: ref } = useApi<Row>("/reference/registration");
  const [f, setF] = useState<Row>({ name: "", acronym: "", emass_id: "", description: "", lifecycle_phase: "Design", authorization_status: "Not authorized",
    confidentiality_impact: "Moderate", integrity_impact: "Moderate", availability_impact: "Low", baseline_key: "moderate", include_privacy: false,
    overlay_keys: [], operating_environment: "", deployment_type: "", boundary_description: "", mission_owner: "", organization_name: "", mission_criticality: "" });
  const [tailor, setTailor] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = Object.fromEntries(Object.entries({ ...f, tailoring: tailor }).filter(([, v]) => (v as unknown) !== ""));
    try {
      const r = await api.post<Row>("/systems", body);
      select(r.data.id);
      nav(`/systems/${r.data.id}/controls`);
    } catch (err) { setError(errorMessage(err)); }
  };
  const users = ref?.users ?? [];
  const userSel = (k: string) => (
    <select className="input" value={f[k] ?? ""} onChange={set(k)} data-testid={`reg-${k}`}><option value="">—</option>{users.map((u: Row) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</select>
  );
  const imp = (k: string) => <select className="input" value={f[k]} onChange={set(k)} data-testid={`reg-${k}`}>{["Low", "Moderate", "High"].map((v) => <option key={v}>{v}</option>)}</select>;
  return (
    <form onSubmit={submit} data-testid="register-system-form">
      <PageHeader title="Register system" subtitle="Creates the system, applies baseline + overlays + tailoring, generates control assignments, inheritance and initial implementation records in one transaction." />
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Identity & mission">
          <div className="grid grid-cols-2 gap-3">
            <F label="Name *"><input className="input" required value={f.name} onChange={set("name")} data-testid="reg-name" /></F>
            <F label="Acronym"><input className="input" value={f.acronym} onChange={set("acronym")} data-testid="reg-acronym" /></F>
            <F label="eMASS system ID"><input className="input" value={f.emass_id} onChange={set("emass_id")} data-testid="reg-emass" /></F>
            <F label="Organization"><input className="input" value={f.organization_name} onChange={set("organization_name")} /></F>
            <F label="Mission owner"><input className="input" value={f.mission_owner} onChange={set("mission_owner")} /></F>
            <F label="Mission criticality"><input className="input" value={f.mission_criticality} onChange={set("mission_criticality")} /></F>
            <div className="col-span-2"><F label="Mission / business description"><textarea className="input" rows={2} value={f.description} onChange={set("description")} /></F></div>
            <F label="System owner">{userSel("system_owner_id")}</F><F label="ISSO">{userSel("isso_id")}</F>
            <F label="ISSM">{userSel("issm_id")}</F><F label="AO">{userSel("ao_id")}</F>
          </div>
        </Panel>
        <Panel title="Environment, categorization & baseline">
          <div className="grid grid-cols-3 gap-3">
            <F label="Operating environment"><input className="input" value={f.operating_environment} onChange={set("operating_environment")} /></F>
            <F label="Deployment type"><input className="input" value={f.deployment_type} onChange={set("deployment_type")} /></F>
            <F label="Lifecycle phase"><select className="input" value={f.lifecycle_phase} onChange={set("lifecycle_phase")} data-testid="reg-phase">{["Design", "Build", "Test", "Onboard", "Operations"].map((v) => <option key={v}>{v}</option>)}</select></F>
            <div className="col-span-3"><F label="Boundary description"><textarea className="input" rows={2} value={f.boundary_description} onChange={set("boundary_description")} /></F></div>
            <F label="Confidentiality">{imp("confidentiality_impact")}</F><F label="Integrity">{imp("integrity_impact")}</F><F label="Availability">{imp("availability_impact")}</F>
            <F label="Baseline"><select className="input" value={f.baseline_key} onChange={set("baseline_key")} data-testid="reg-baseline">{["low", "moderate", "high"].map((v) => <option key={v} value={v}>{v}</option>)}</select></F>
            <label className="mt-6 flex items-center gap-2 text-[12px]"><input type="checkbox" checked={f.include_privacy} onChange={(e) => setF({ ...f, include_privacy: e.target.checked })} data-testid="reg-privacy" />Include Privacy baseline</label>
            <div />
            <div className="col-span-3 text-[12px]">
              <div className="mb-1 font-medium text-slate-700">Overlays (versioned)</div>
              {ref?.overlays.map((o: Row) => (
                <label key={o.id} className="flex items-center gap-2"><input type="checkbox" data-testid={`reg-overlay-${o.overlay_key}`} checked={f.overlay_keys.includes(o.overlay_key)}
                  onChange={(e) => setF({ ...f, overlay_keys: e.target.checked ? [...f.overlay_keys, o.overlay_key] : f.overlay_keys.filter((k: string) => k !== o.overlay_key) })} />
                  {o.title} v{o.version} (+{o.controls_add.length}/−{o.controls_remove.length})</label>
              ))}
            </div>
          </div>
        </Panel>
        <Panel title="Tailoring decisions" eyebrow="Each requires a justification">
          {tailor.map((t, i) => (
            <div key={i} className="mb-2 grid grid-cols-[110px_100px_1fr_auto] gap-2">
              <input className="input" placeholder="ac-2.12" value={t.control_id} onChange={(e) => setTailor(tailor.map((x, j) => j === i ? { ...x, control_id: e.target.value } : x))} data-testid={`tailor-control-${i}`} />
              <select className="input" value={t.action} onChange={(e) => setTailor(tailor.map((x, j) => j === i ? { ...x, action: e.target.value } : x))}><option value="remove">remove</option><option value="add">add</option></select>
              <input className="input" placeholder="Justification" value={t.justification} onChange={(e) => setTailor(tailor.map((x, j) => j === i ? { ...x, justification: e.target.value } : x))} data-testid={`tailor-justification-${i}`} />
              <button type="button" className="btn-secondary" onClick={() => setTailor(tailor.filter((_, j) => j !== i))}>Remove</button>
            </div>
          ))}
          <button type="button" className="btn-secondary" onClick={() => setTailor([...tailor, { control_id: "", action: "remove", justification: "" }])} data-testid="tailor-add-btn">Add tailoring decision</button>
        </Panel>
      </div>
      {error && <div className="mt-4 rounded border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800" role="alert" data-testid="register-error">{error}</div>}
      <button className="btn-primary mt-5" type="submit" data-testid="register-submit-btn">Register system</button>
    </form>
  );
}
