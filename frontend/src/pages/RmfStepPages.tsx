import { ReactNode, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { cn, fmtControl } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { PageHeader, Panel } from "@/components/common/Panel";
import { NeedSystem, Stat } from "@/components/common/Bits";
import { showNextStep } from "@/components/common/NextStep";
import { NextActionButton, STEP_STATUS, StepChips, useActiveSystemId, useRmfSteps } from "@/components/rmf/Stepper";
import { Help, RolesEditor, rolesFromHolders } from "@/components/rmf/RolesEditor";
import { CategorizeForm, catBody, catFromSystem } from "@/components/rmf/CategorizeForm";

function StepFrame({ k, title, purpose, children }: { k: string; title: string; purpose: string; children?: ReactNode }) {
  const { systems, loaded } = useSystems();
  const sid = useActiveSystemId();
  const { data } = useRmfSteps(sid);
  const step = data?.steps.find((s: Row) => s.key === k);
  if (loaded && !systems.length) return (
    <div data-testid={`rmf-page-${k}`}>
      <PageHeader title={title} subtitle={purpose} />
      <div className="panel p-6 text-[13px]" data-testid="rmf-empty"><div className="t-title text-slate-900">Register a system first</div>
        <p className="mt-1 text-slate-600">Every RMF step works on one system. Register the system you are authorizing to begin.</p>
        <Link to="/systems/new" className="btn-primary mt-3 inline-flex" data-testid="rmf-empty-register">Register your first system</Link></div>
    </div>);
  if (!sid) return <NeedSystem />;
  return (
    <div data-testid={`rmf-page-${k}`}>
      <PageHeader title={title} subtitle={purpose}>{data && <NextActionButton data={data} />}</PageHeader>
      {data && <StepChips steps={data.steps} />}
      {step && <div className={cn("mb-5 rounded-md border p-4 text-[13px]", STEP_STATUS[step.status]?.chip)} data-testid="step-status">
        <div className="flex flex-wrap items-center gap-2"><b data-testid="step-status-label">{STEP_STATUS[step.status]?.label}</b>
          {step.progress && <span className="rounded bg-white/70 px-1.5 text-[11px]" data-testid="step-progress">{step.progress}</span>}</div>
        <div className="mt-1" data-testid="step-summary">{step.summary}</div>
        <div className="mt-1 text-[11px] opacity-80">How this is decided: {step.criteria}</div>
      </div>}
      {children}
    </div>);
}

const Msg = ({ m }: { m: { ok?: string; err?: string } }) => <>
  {m.ok && <div className="mb-3 rounded border border-emerald-300 bg-emerald-50 p-2 text-[12px] text-emerald-900" role="status" data-testid="step-ok">{m.ok}</div>}
  {m.err && <div className="mb-3 rounded border border-rose-300 bg-rose-50 p-2 text-[12px] text-rose-800" role="alert" data-testid="step-error">{m.err}</div>}</>;

export function PreparePage() {
  const sid = useActiveSystemId();
  const { can } = useAuth();
  const { data: ref } = useApi<Row>("/reference/rmf");
  const { data } = useApi<Row>(sid ? `/systems/${sid}/prepare` : null);
  const [roles, setRoles] = useState<Row>({});
  const [m, setM] = useState<{ ok?: string; err?: string }>({});
  useEffect(() => { if (data) setRoles(rolesFromHolders(data.roles)); }, [data]);
  const save = async () => {
    try { await api.put(`/systems/${sid}/prepare`, { roles }); setM({ ok: "Key roles saved." });
      showNextStep({ message: "Key roles saved.", label: "categorize the system (information types and impact)", to: "/rmf/categorize" });
    } catch (e) { setM({ err: errorMessage(e) }); }
  };
  return (
    <StepFrame k="prepare" title="Step 1 · Prepare – key roles" purpose="Record who is responsible for this system. Pick an existing user, or enter a name and e-mail for someone who has no account yet.">
      <Panel title="Key roles" actions={can("system.write") ? <button className="btn-primary" onClick={save} data-testid="prepare-save">Save roles</button>
        : <span className="text-[11px] text-slate-500" title="Saving roles needs the 'system.write' permission (ISSO, ISSM or System Owner)">Read only for your role</span>}>
        <Msg m={m} />
        <RolesEditor meta={ref} value={roles} onChange={setRoles} />
        <p className="mt-3 text-[11px] text-slate-500">Assigning someone here records them in the authorization package. It does not change what they can do in the app – access is granted under Admin → Users.</p>
      </Panel>
    </StepFrame>);
}

export function CategorizePage() {
  const sid = useActiveSystemId();
  const { can } = useAuth();
  const { data, reload } = useApi<Row>(sid ? `/systems/${sid}/categorization` : null);
  const [v, setV] = useState<Row | null>(null);
  const [m, setM] = useState<{ ok?: string; err?: string }>({});
  useEffect(() => { if (data) setV(catFromSystem(data)); }, [data]);
  const save = async () => {
    try { const r = await api.put<Row>(`/systems/${sid}/categorization`, catBody(v!)); reload();
      const acts: string[] = r.data.select_actions;
      const msg = `Categorization saved: ${r.data.calculation.overall} (${r.data.calculation.c}/${r.data.calculation.i}/${r.data.calculation.a}).${acts.length ? ` In Select: ${acts.join("; ")}.` : ""}`;
      setM({ ok: msg }); showNextStep({ message: msg, label: "review the baseline, overlays and tailoring in Select", to: "/rmf/select" });
    } catch (e) { setM({ err: errorMessage(e) }); }
  };
  return (
    <StepFrame k="categorize" title="Step 2 · Categorize" purpose="Choose the kinds of information the system handles. The app applies NIST's provisional impact levels, takes the high-water mark (FIPS 199) and picks the matching 800-53B baseline.">
      <Msg m={m} />
      {v && <CategorizeForm v={v} onChange={setV} />}
      {can("system.write") && <button className="btn-primary mt-5" onClick={save} data-testid="categorize-save">Save categorization</button>}
    </StepFrame>);
}

function Baseline({ sid, d, reload }: { sid: string; d: Row; reload: () => void }) {
  const [key, setKey] = useState(d.baseline_key);
  const [priv, setPriv] = useState(d.include_privacy || !!d.processes_pii);
  const [m, setM] = useState<{ ok?: string; err?: string }>({});
  const apply = async () => {
    try { const r = await api.post<Row>(`/systems/${sid}/select/baseline`, { baseline_key: key, include_privacy: priv }); reload();
      setM({ ok: `Baseline applied: ${r.data.added} control(s) added. ${r.data.counts.labels.reconciliation}.${r.data.beyond_baseline.length ? ` ${r.data.beyond_baseline.length} control(s) are no longer in this baseline – remove them below with a rationale if they are not needed.` : ""}` });
    } catch (e) { setM({ err: errorMessage(e) }); }
  };
  const rec = d.recommended_baseline;
  return (
    <Panel title="Baseline" eyebrow="NIST SP 800-53B" testId="select-baseline">
      <Msg m={m} />
      <div className="grid gap-3 text-[12px] md:grid-cols-4">
        <div>Current baseline<div className="text-[15px] font-semibold capitalize" data-testid="select-current">{d.baseline_key}</div></div>
        <div>From categorization<div className="text-[15px] font-semibold capitalize" data-testid="select-recommended">{rec ?? "— (categorize first)"}</div></div>
        <label className="font-medium">Baseline to apply<select className="input mt-1" value={key} onChange={(e) => setKey(e.target.value)} data-testid="select-baseline-key">
          {["low", "moderate", "high"].map((x) => <option key={x} value={x}>{x[0].toUpperCase() + x.slice(1)}</option>)}</select></label>
        <label className="mt-5 flex items-center gap-2"><input type="checkbox" checked={priv} onChange={(e) => setPriv(e.target.checked)} data-testid="select-privacy" />
          Privacy baseline <Help text="800-53B privacy baseline – required when the system processes PII (answered in Categorize)." /></label>
      </div>
      {d.processes_pii && !d.include_privacy && <p className="mt-2 text-[12px] text-amber-800">The system processes PII – apply the privacy baseline.</p>}
      <button className="btn-primary mt-3" onClick={apply} data-testid="select-apply-baseline">Apply baseline</button>
      <p className="mt-2 text-[11px] text-slate-500">Applying adds missing baseline controls. It never deletes controls: use tailoring below (with a rationale) to remove any.</p>
    </Panel>);
}

function Overlays({ sid, d, reload }: { sid: string; d: Row; reload: () => void }) {
  const { can } = useAuth();
  const [m, setM] = useState<{ ok?: string; err?: string }>({});
  const [ver, setVer] = useState<Record<string, string>>({});
  const toggle = async (o: Row) => {
    try { const r = await api.post<Row>(`/systems/${sid}/select/overlay`, { overlay_key: o.key, apply: !o.applied }); reload();
      setM({ ok: `${o.title}: ${o.applied ? "removed" : "applied"} (+${r.data.added.length} / −${r.data.removed.length} controls). ${r.data.counts.labels.reconciliation}.` });
    } catch (e) { setM({ err: errorMessage(e) }); }
  };
  const importCsv = async (o: Row, f: File) => {
    const fd = new FormData(); fd.append("file", f); fd.append("version", ver[o.key] || "1");
    try { const r = await api.post<Row>(`/overlays/${o.key}/import`, fd); reload(); setM({ ok: `Official list imported for ${o.title}: +${r.data.add} / −${r.data.remove} controls. You can now apply it.` }); }
    catch (e) { setM({ err: errorMessage(e) }); }
  };
  return (
    <Panel title="Overlays" eyebrow="Add or remove controls for a special situation" testId="select-overlays">
      <Msg m={m} />
      <table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th className="py-1">Overlay</th><th>Controls</th><th>Status</th><th /></tr></thead><tbody>
        {d.overlays.map((o: Row) => <tr key={o.key} className="border-t border-slate-100 align-top" data-testid={`overlay-${o.key}`}>
          <td className="py-2"><b className="font-medium">{o.title}</b> {!o.structure_only && <span className="text-slate-400">v{o.version}</span>}{o.synthetic && <span className="ml-1 rounded bg-amber-100 px-1 text-[10px] text-amber-800">SYNTHETIC</span>}
            {o.structure_only && <div className="mt-0.5 text-[11px] text-slate-500">{o.description}</div>}</td>
          <td className="py-2 font-mono">{o.structure_only ? "—" : `+${o.add} / −${o.remove}`}</td>
          <td className="py-2">{o.applied ? <span className="text-emerald-700">Applied</span> : o.structure_only ? <span className="text-amber-800" data-testid={`overlay-${o.key}-structure`}>Structure only – load the official control list</span> : "Available"}</td>
          <td className="py-2 text-right">{o.structure_only ? (can("admin.content.load") ? <span className="flex items-center justify-end gap-1">
              <input className="input w-20 py-0.5 text-[11px]" placeholder="version" value={ver[o.key] ?? ""} onChange={(e) => setVer({ ...ver, [o.key]: e.target.value })} />
              <label className="btn-secondary cursor-pointer px-2 py-0.5 text-[11px]" title="CSV with columns control_id,action (add/remove)">Import official list (CSV)
                <input type="file" accept=".csv" className="hidden" onChange={(e) => e.target.files?.[0] && importCsv(o, e.target.files[0])} data-testid={`overlay-${o.key}-import`} /></label></span>
              : <span className="text-[11px] text-slate-500">An administrator must import the official list</span>)
            : <button className="btn-secondary px-2 py-0.5 text-[11px]" onClick={() => toggle(o)} data-testid={`overlay-${o.key}-toggle`}>{o.applied ? "Remove" : "Apply"}</button>}</td>
        </tr>)}</tbody></table>
    </Panel>);
}

function Tailoring({ sid, d, reload }: { sid: string; d: Row; reload: () => void }) {
  const { data: tr, reload: reTr } = useApi<Row[]>(`/systems/${sid}/traceability`);
  const [action, setAction] = useState("remove");
  const [ids, setIds] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [why, setWhy] = useState("");
  const [m, setM] = useState<{ ok?: string; err?: string }>({});
  const shown = useMemo(() => (tr ?? []).filter((r) => !q || r.control_id.includes(q.toLowerCase().replace("(", ".").replace(")", ""))).slice(0, 200), [tr, q]);
  const submit = async () => {
    const all = [...picked, ...ids.split(/[\s,;]+/).filter(Boolean)];
    if (why.trim().length < 10) { setM({ err: "Write a rationale of at least 10 characters – it is required for every tailoring decision and is kept in the audit history." }); return; }
    try { const r = await api.post<Row>(`/systems/${sid}/select/tailor`, { action, control_ids: all, justification: why }); reload(); reTr(); setPicked([]); setIds(""); setWhy("");
      const msg = `${action === "remove" ? "Removed" : "Added"} ${r.data.controls.length} control(s).${r.data.skipped.length ? ` Skipped (already ${action === "remove" ? "absent" : "selected"}): ${r.data.skipped.join(", ")}.` : ""} ${r.data.counts.labels.reconciliation}.`;
      setM({ ok: msg }); showNextStep({ message: msg, label: "track implementation of the selected controls", to: "/rmf/implement" });
    } catch (e) { setM({ err: errorMessage(e) }); }
  };
  return (
    <Panel title="Tailoring decisions" eyebrow="Add or remove controls – each decision needs a rationale" testId="select-tailoring">
      <Msg m={m} />
      <div className="grid gap-4 text-[12px] lg:grid-cols-2">
        <div>
          <label className="font-medium">Decision<select className="input mt-1" value={action} onChange={(e) => { setAction(e.target.value); setPicked([]); }} data-testid="tailor-action">
            <option value="remove">Remove controls from this system</option><option value="add">Add controls (tailor in)</option></select></label>
          {action === "remove" && <>
            <input className="input mt-2" placeholder="Filter selected controls, e.g. ac-2" value={q} onChange={(e) => setQ(e.target.value)} data-testid="tailor-filter" />
            <div className="mt-1 flex items-center gap-2 text-[11px]"><button className="underline" onClick={() => setPicked(shown.map((r) => r.control_id))} data-testid="tailor-select-all">Select all shown ({shown.length})</button>
              <button className="underline" onClick={() => setPicked([])}>Clear</button><span>{picked.length} selected</span></div>
            <ul className="mt-1 max-h-52 overflow-y-auto rounded border border-slate-200" data-testid="tailor-list">{shown.map((r) => <li key={r.control_id} className="border-b border-slate-100 px-2 py-1">
              <label className="flex items-center gap-2"><input type="checkbox" checked={picked.includes(r.control_id)} data-testid={`tailor-pick-${r.control_id}`}
                onChange={(e) => setPicked(e.target.checked ? [...picked, r.control_id] : picked.filter((x) => x !== r.control_id))} />
                <span className="font-mono">{fmtControl(r.control_id)}</span><span className="text-slate-500">{r.origin}</span></label></li>)}</ul></>}
          <label className="mt-2 block font-medium">{action === "remove" ? "…or type control IDs" : "Control IDs to add"}<textarea className="input mt-1" rows={2} placeholder="e.g. AC-2(11), ac-6.9, SC-7(18)" value={ids}
            onChange={(e) => setIds(e.target.value)} data-testid="tailor-ids" /></label>
        </div>
        <div>
          <label className="font-medium">Rationale (shared by all controls in this decision)<textarea className="input mt-1" rows={4} value={why} onChange={(e) => setWhy(e.target.value)}
            placeholder="e.g. Accounts are managed by the enterprise IdP, which is inherited" data-testid="tailor-justification" /></label>
          <button className="btn-primary mt-2" onClick={submit} data-testid="tailor-submit">{action === "remove" ? "Remove selected controls" : "Add controls"}</button>
          <p className="mt-2 text-[11px] text-slate-500">Removing a control deletes its statement and evidence links for this system; the decision, who made it and the rationale are kept in the audit log.</p>
        </div>
      </div>
      {d.tailoring.length > 0 && <table className="mt-4 w-full text-[12px]" data-testid="tailor-history"><thead><tr className="text-left text-slate-500"><th>Control</th><th>Decision</th><th>Rationale</th><th>When</th></tr></thead>
        <tbody>{d.tailoring.slice(0, 50).map((t: Row) => <tr key={t.id} className="border-t border-slate-100"><td className="py-1 font-mono">{fmtControl(t.control_id)}</td><td>{t.action === "remove" ? "Removed" : "Added"}</td>
          <td>{t.justification}</td><td>{new Date(t.created_at).toLocaleDateString()}</td></tr>)}</tbody></table>}
    </Panel>);
}

export function SelectPage() {
  const sid = useActiveSystemId();
  const { can } = useAuth();
  const { data, reload } = useApi<Row>(sid ? `/systems/${sid}/select` : null);
  return (
    <StepFrame k="select" title="Step 3 · Select – baseline, overlays and tailoring" purpose="Decide which controls apply: start from the baseline that matches the categorization, apply overlays for special situations, then tailor controls in or out with a rationale.">
      {data && sid && <div className="grid gap-5">
        <div className="panel p-4 text-[12px]" data-testid="select-counts"><b>Control count:</b> <span data-testid="select-reconciliation">{data.counts.labels.reconciliation}</span>
          <Help text="Same numbers as the Workbench and dashboard (one shared calculation): baseline − removed + added by overlays + tailored in = assigned." /></div>
        {can("system.write") ? <><Baseline sid={sid} d={data} reload={reload} /><Overlays sid={sid} d={data} reload={reload} /><Tailoring sid={sid} d={data} reload={reload} /></>
          : <p className="text-[12px] text-slate-600">Changing the control selection needs the “system.write” permission (ISSO, ISSM or System Owner). You can view the selection in the <Link className="underline" to="/traceability">traceability matrix</Link>.</p>}
      </div>}
    </StepFrame>);
}

const Go = ({ to, title, text, testId }: { to: string; title: string; text: string; testId: string }) => (
  <Link to={to} className="panel card-interactive block p-4" data-testid={testId}><div className="font-heading font-semibold text-slate-900">{title} →</div><div className="mt-1 text-[12px] text-slate-600">{text}</div></Link>);

export function ImplementPage() {
  const sid = useActiveSystemId();
  return (
    <StepFrame k="implement" title="Step 4 · Implement" purpose="Put the selected controls in place: write how each one is implemented, mark what you inherit, and collect evidence that proves it.">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Go to={`/systems/${sid}/controls?implementation_status=planned`} title="Controls still to implement" text="Workbench filtered to controls with status Planned." testId="impl-go-workbench" />
        <Go to="/inheritance" title="Inheritance" text="Mark controls inherited or shared from a common control provider." testId="impl-go-inheritance" />
        <Go to="/policy-auditor" title="Policy Auditor" text="Upload policies and map them to the -1 (policy and procedure) controls." testId="impl-go-policy" />
        <Go to="/evidence-sources" title="Add evidence" text="Upload STIG checklists, SCAP / ACAS scans and documents." testId="impl-go-evidence" />
        <Go to="/mapping-review" title="Status suggestions" text="Approve controls whose current evidence passes." testId="impl-go-suggestions" />
      </div>
    </StepFrame>);
}

export function AssessPage() {
  const sid = useActiveSystemId();
  return (
    <StepFrame k="assess" title="Step 5 · Assess" purpose="The Security Control Assessor (SCA) tests each control and records Satisfied / Other than satisfied. Review the automated mappings the assessment relies on.">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Go to={`/systems/${sid}/controls?assessment_status=not_assessed`} title="Controls not yet assessed" text="Workbench filtered to assessment status Not assessed." testId="assess-go-workbench" />
        <Go to="/reviews" title="Reviews and SCA assessments" text="Assessment requests and results." testId="assess-go-reviews" />
        <Go to="/mapping-review" title="Mapping Review" text="Approve STIG, policy and status mappings before relying on them." testId="assess-go-mapping" />
        <Go to="/poams" title="POA&M" text="Track weaknesses found in the assessment." testId="assess-go-poam" />
      </div>
    </StepFrame>);
}

const DECISIONS = [["ATO", "Authorization to Operate for a fixed period."], ["ATO with conditions", "ATO that requires specific actions by a set date."],
  ["IATT", "Interim Authorization to Test – testing only."], ["DATO", "Denial of authorization – the system may not operate."]];

export function AuthorizePage() {
  const sid = useActiveSystemId();
  const { data } = useApi<Row>(sid ? `/systems/${sid}/authorize` : null);
  return (
    <StepFrame k="authorize" title="Step 6 · Authorize" purpose="Assemble the authorization package (SSP, SAR, POA&M) and send it to the Authorizing Official (AO), who records the decision and its expiration date.">
      {data && <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <Panel title="Authorization package checklist" testId="auth-checklist">
          <ul className="text-[13px]">{data.checklist.map((i: Row, n: number) => <li key={i.item} className="flex items-center gap-2 border-b border-slate-100 py-1.5" data-testid={`auth-check-${n}`} data-done={i.done}>
            <span className={i.done ? "text-emerald-600" : "text-amber-600"} aria-label={i.done ? "done" : "to do"}>{i.done ? "✓" : "○"}</span>
            <span className="flex-1">{i.item}</span><Link to={i.link} className="text-[11px] text-blue-800 underline">Open</Link></li>)}</ul>
        </Panel>
        <Panel title="AO decision" testId="auth-decision">
          <div className="text-[13px]"><div>Status: <b data-testid="auth-status">{data.authorization_status}</b></div>
            <div>Type: {data.authorization_type ?? "—"}</div><div>Expires: <b>{data.authorization_expiration ?? "—"}</b></div></div>
          <ul className="mt-3 text-[11px] text-slate-600">{DECISIONS.map(([k, h]) => <li key={k}><b>{k}</b> – {h}</li>)}</ul>
          <Link to={`/systems/${sid}/authorization`} className="btn-primary mt-3 inline-flex" data-testid="auth-open">Submit package / record AO decision</Link>
        </Panel>
      </div>}
    </StepFrame>);
}

export function MonitorPage() {
  const sid = useActiveSystemId();
  const { can } = useAuth();
  const { data: s } = useApi<Row>(sid ? `/systems/${sid}` : null);
  const { data: jobs } = useApi<Row[]>(can("admin.health.read") ? "/scheduled-jobs" : null);
  const mt = s?.metrics ?? {};
  return (
    <StepFrame k="monitor" title="Step 7 · Monitor" purpose="Continuous monitoring (ConMon): keep evidence current, fix new findings and POA&Ms on time, and watch the authorization expiration date.">
      {s && <div className="mb-5 grid gap-3 md:grid-cols-3 xl:grid-cols-6" data-testid="monitor-stats">
        <Stat label="Controls with current evidence" value={`${mt.controls_with_current_evidence ?? 0} / ${mt.assigned_controls ?? 0}`} testId="mon-current" hint="Evidence collected within its freshness window" />
        <Stat label="Controls with stale / expired evidence" value={mt.controls_stale ?? 0} testId="mon-stale" />
        <Stat label="Open findings" value={mt.open_findings ?? 0} testId="mon-findings" />
        <Stat label="Open CAT I / KEV" value={`${mt.open_cat1 ?? 0} / ${mt.kev_open ?? 0}`} testId="mon-cat1" hint="KEV = CISA Known Exploited Vulnerabilities" />
        <Stat label="Overdue POA&Ms" value={mt.overdue_poams ?? 0} testId="mon-poams" />
        <Stat label="Days to ATO expiration" value={mt.days_to_expiration ?? "—"} testId="mon-expiry" />
      </div>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Go to="/evidence-ledger" title="Evidence Ledger" text="Every evidence item, its age and content updates." testId="mon-go-ledger" />
        <Go to={`/systems/${sid}/controls?has_evidence=no`} title="Controls without evidence" text="Workbench filtered to controls that have no evidence yet." testId="mon-go-stale" />
        <Go to="/evidence-sources" title="Evidence sources" text="Connected tools and upload history." testId="mon-go-sources" />
        <Go to="/poams" title="POA&M" text="Open and overdue items." testId="mon-go-poam" />
      </div>
      <Panel title="ConMon schedule" className="mt-5" testId="mon-schedule">
        {jobs ? <table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th>Job</th><th>Schedule</th><th>Next run</th><th>Last run</th></tr></thead>
          <tbody>{jobs.map((j) => <tr key={j.id} className="border-t border-slate-100"><td className="py-1">{j.job_type}</td><td className="font-mono">{j.cron ?? j.schedule ?? j.interval_minutes ?? "—"}</td>
            <td>{j.next_run_at ? new Date(j.next_run_at).toLocaleString() : "—"}</td><td>{j.last_run_at ? new Date(j.last_run_at).toLocaleString() : "never"}</td></tr>)}</tbody></table>
          : <p className="text-[12px] text-slate-600">Automated ConMon jobs (evidence expiry, attestation reminders, KEV refresh) run on a schedule managed by administrators.</p>}
      </Panel>
    </StepFrame>);
}

export function TraceabilityPage() {
  const sid = useActiveSystemId();
  const { data } = useApi<Row[]>(sid ? `/systems/${sid}/traceability` : null);
  const [q, setQ] = useState("");
  if (!sid) return <NeedSystem />;
  const rows = (data ?? []).filter((r) => !q || JSON.stringify(r).toLowerCase().includes(q.toLowerCase()));
  return (
    <div data-testid="traceability-page">
      <PageHeader title="Traceability matrix" subtitle="Every assigned control with its origin, implementation statement, evidence, open findings, POA&Ms and assessment – one row per control." />
      <Panel testId="traceability-panel" actions={<input className="input w-64" placeholder="Search controls, statuses…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="trace-search" />}>
        <div className="mb-2 text-[12px] text-slate-600" data-testid="trace-count">{data ? `${rows.length.toLocaleString()} of ${data.length.toLocaleString()} controls` : "Loading the matrix…"}</div>
        {data && !data.length && <p className="text-[12px] text-slate-600" data-testid="trace-empty">No controls are selected for this system yet – apply a baseline in <Link className="underline" to="/rmf/select">Step 3 · Select</Link>.</p>}
        <div className="max-h-[65vh] overflow-auto"><table className="w-full text-[12px]"><thead className="sticky top-0 bg-white"><tr className="text-left text-slate-500">
          {["Control", "Origin", "Responsibility", "Statement", "Implementation", "Evidence", "Open findings", "Open POA&Ms", "Assessment", "Freshness"].map((h) => <th key={h} className="py-1 pr-2">{h}</th>)}</tr></thead>
          <tbody>{rows.slice(0, 1500).map((r) => <tr key={r.control_id} className="border-t border-slate-100" data-testid={`trace-row-${r.control_id}`}>
            <td className="py-1 pr-2"><Link to={`/systems/${sid}/controls/${r.control_id}`} className="font-mono text-blue-800 hover:underline">{fmtControl(r.control_id)}</Link></td>
            <td>{r.origin}</td><td>{r.responsibility}</td><td>{r.statement}</td><td>{r.implementation_status.replace(/_/g, " ")}</td><td className="font-mono">{r.evidence}</td>
            <td className="font-mono">{r.open_findings}</td><td className="font-mono">{r.open_poams}</td><td>{r.assessment_status.replace(/_/g, " ")}</td><td>{r.freshness.replace(/_/g, " ")}</td></tr>)}</tbody></table></div>
      </Panel>
    </div>);
}

const GUIDE: [string, string][] = [
  ["Prepare", "Name the system owner, ISSO, ISSM, AO, SCA and other key people."],
  ["Categorize", "Pick the SP 800-60 information types; the app derives the FIPS 199 / CNSSI 1253 impact and the baseline."],
  ["Select", "Apply the baseline and any overlays, then tailor controls in or out with a rationale."],
  ["Implement", "Write implementation statements, mark inheritance, upload STIG / SCAP / ACAS results and policies."],
  ["Assess", "The SCA tests the controls; approve automated mappings in Mapping Review."],
  ["Authorize", "Assemble the SSP, SAR and POA&M; the AO records ATO, ATO with conditions, IATT or DATO."],
  ["Monitor", "Keep evidence current, close findings and POA&Ms, and watch the expiration date."],
];

export function RmfOverview() {
  const { systems, loaded } = useSystems();
  const sid = useActiveSystemId();
  const { data } = useRmfSteps(sid);
  return (
    <div className="mb-6" data-testid="rmf-overview">
      {loaded && !systems.length && <div className="panel mb-4 p-5" data-testid="rmf-empty"><div className="t-title text-slate-900">Start your first authorization</div>
        <p className="mt-1 text-[13px] text-slate-600">Your workspace is empty. Register the system you are authorizing; the app then walks you through the 7 steps below.</p>
        <Link to="/systems/new" className="btn-primary mt-3 inline-flex" data-testid="rmf-empty-register">Register your first system</Link></div>}
      {data && <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><StepChips steps={data.steps} compact /><NextActionButton data={data} /></div>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {GUIDE.map(([name, text], i) => { const st = data?.steps[i];
          return <Link key={name} to={`/rmf/${name.toLowerCase()}`} className={cn("panel card-interactive border-l-4 p-4", st ? { complete: "border-emerald-400", needs_attention: "border-amber-400", not_started: "border-slate-300" }[st.status as string] : "border-slate-300")}
            title={st ? `How this is decided: ${st.criteria}` : undefined} data-testid={`guide-${name.toLowerCase()}`}>
            <div className="flex items-center justify-between"><span className="font-heading font-semibold text-slate-900">{i + 1}. {name}</span>{st && <span className="text-[11px]">{STEP_STATUS[st.status].label}</span>}</div>
            <div className="mt-1 text-[12px] text-slate-600">{text}</div>{st && <div className="mt-1 text-[11px] text-slate-500">{st.summary}</div>}</Link>; })}
      </div>
    </div>);
}
