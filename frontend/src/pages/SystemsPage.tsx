import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { PageHeader, Panel } from "@/components/common/Panel";
import { Table } from "@/components/common/Bits";
import { showNextStep } from "@/components/common/NextStep";
import { RolesEditor } from "@/components/rmf/RolesEditor";
import { CategorizeForm, EMPTY_CAT, catBody, useCategorization } from "@/components/rmf/CategorizeForm";

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
          {data && data.length === 0 && <tr><td className="td py-8 text-center" colSpan={8} data-testid="systems-empty">
            <div className="t-title text-slate-900">Register your first system</div>
            <p className="mt-1 text-[13px] text-slate-600">Your workspace is empty. Register a system to pick its baseline, then add evidence sources or upload scans.</p>
            {can("system.register") && <Link to="/systems/new" className="btn-primary mt-3 inline-flex" data-testid="systems-empty-register"><Plus className="h-4 w-4" />Register system</Link>}
          </td></tr>}
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
  const { select, refresh } = useSystems();
  const { data: ref } = useApi<Row>("/reference/rmf");
  const [f, setF] = useState<Row>({ name: "", acronym: "", emass_id: "", description: "", lifecycle_phase: "Design", authorization_status: "Not authorized",
    boundary_description: "", mission_owner: "", organization_name: "", deployment_type: "" });
  const [roles, setRoles] = useState<Row>({});
  const [cat, setCat] = useState<Row>(EMPTY_CAT);
  const calc = useCategorization(cat);
  const [baseline, setBaseline] = useState("");
  const [error, setError] = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const auto = calc?.baseline ?? "";
  const chosen = baseline && (["low", "moderate", "high"].indexOf(baseline) >= ["low", "moderate", "high"].indexOf(auto)) ? baseline : auto;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!cat.information_types.length) { setError("Pick at least one information type in Categorize – the app derives the impact level and baseline from them."); return; }
    if (calc?.errors.length) { setError(calc.errors.join("; ")); return; }
    const c = catBody(cat);
    const body = Object.fromEntries(Object.entries({ ...f, ...c, ...(c.cia ? { confidentiality_impact: c.cia.c || undefined, integrity_impact: c.cia.i || undefined, availability_impact: c.cia.a || undefined } : {}),
      cia: undefined, mode: undefined, categorization_mode: cat.mode, key_roles: roles, baseline_key: chosen || "moderate", include_privacy: cat.processes_pii === true })
      .filter(([, v]) => (v as unknown) !== "" && v !== undefined));
    try {
      const r = await api.post<Row>("/systems", body);
      await refresh();
      select(r.data.id);
      showNextStep({ message: `System “${r.data.name}” registered: ${r.data.categorization ?? ""} categorization, ${r.data.baseline_key} baseline, ${r.data.metrics.assigned_controls} controls assigned.`,
        label: "review the baseline, overlays and tailoring in Select", to: "/rmf/select" });
      nav("/rmf/select");
    } catch (err) { setError(errorMessage(err)); }
  };
  return (
    <form onSubmit={submit} data-testid="register-system-form">
      <PageHeader title="Register system" subtitle="Step 1 Prepare and step 2 Categorize in one form: name the system and its key people, pick its information types, and the app derives the impact level and baseline. Overlays and tailoring follow in step 3 Select." />
      <div className="grid gap-5">
        <Panel title="1 · Prepare – identity and key roles">
          <div className="grid gap-3 md:grid-cols-3">
            <F label="Name *"><input className="input" required value={f.name} onChange={set("name")} data-testid="reg-name" /></F>
            <F label="Acronym"><input className="input" value={f.acronym} onChange={set("acronym")} data-testid="reg-acronym" /></F>
            <F label="eMASS system ID"><input className="input" value={f.emass_id} onChange={set("emass_id")} data-testid="reg-emass" /></F>
            <F label="Organization"><input className="input" value={f.organization_name} onChange={set("organization_name")} /></F>
            <F label="Mission owner"><input className="input" value={f.mission_owner} onChange={set("mission_owner")} /></F>
            <F label="Lifecycle phase"><select className="input" value={f.lifecycle_phase} onChange={set("lifecycle_phase")} data-testid="reg-phase">{["Design", "Build", "Test", "Onboard", "Operations"].map((v) => <option key={v}>{v}</option>)}</select></F>
            <div className="md:col-span-3"><F label="Mission / business description"><textarea className="input" rows={2} value={f.description} onChange={set("description")} /></F></div>
            <div className="md:col-span-3"><F label="Authorization boundary (what is inside the system)"><textarea className="input" rows={2} value={f.boundary_description} onChange={set("boundary_description")} /></F></div>
          </div>
          <div className="mt-4"><RolesEditor meta={ref} value={roles} onChange={setRoles} /></div>
        </Panel>
        <div><h2 className="mb-2 font-heading text-[15px] font-semibold text-slate-900">2 · Categorize</h2><CategorizeForm v={cat} onChange={setCat} /></div>
        <Panel title="Baseline" eyebrow="Chosen automatically from the categorization">
          <div className="flex flex-wrap items-end gap-3 text-[12px]">
            <div>From categorization: <b className="capitalize" data-testid="reg-auto-baseline">{auto || "— pick information types first"}</b></div>
            <F label="Baseline to register with"><select className="input" value={chosen} onChange={(e) => setBaseline(e.target.value)} data-testid="reg-baseline">
              {["low", "moderate", "high"].filter((x) => !auto || ["low", "moderate", "high"].indexOf(x) >= ["low", "moderate", "high"].indexOf(auto)).map((v) => <option key={v} value={v}>{v[0].toUpperCase() + v.slice(1)}</option>)}</select></F>
            {cat.processes_pii === true && <span className="rounded bg-violet-50 px-2 py-1 text-violet-900">+ privacy baseline (system processes PII)</span>}
          </div>
          <p className="mt-2 text-[11px] text-slate-500">You can only choose the derived baseline or a higher one. Overlays and tailoring (adding or removing controls with a rationale) are in step 3 Select after registration.</p>
        </Panel>
      </div>
      {error && <div className="mt-4 rounded border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800" role="alert" data-testid="register-error">{error}</div>}
      <button className="btn-primary mt-5" type="submit" data-testid="register-submit-btn">Register system</button>
    </form>
  );
}
