import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { deniedText } from "@/components/common/RoleGate";
import { Counter, EField, OtherSelect, residualHint } from "@/components/workbench/emass/fields";
import { ImportedDeleteBar, ImportedMark, useImported } from "@/components/common/Imported";

const PLAN_TEXT = ["responsible_entities", "slcm_criticality", "slcm_reporting", "slcm_tracking"];
const SLCM = ["slcm_criticality", "slcm_frequency", "slcm_method", "slcm_reporting", "slcm_tracking", "slcm_comments"];
const RISK_ENUMS = ["severity", "relevance_of_threat", "likelihood", "impact", "residual_risk_level"];
const RISK_TEXT = ["impact_description", "vulnerability_summary", "recommendations", "mitigations"];
const visible = (st: string) => st === "Not Applicable" ? ["na_justification"] : st === "Manually Inherited" ? ["common_control_provider", ...SLCM]
  : st === "Inherited" ? [] : ["control_designation", "estimated_completion_date", "responsible_entities", ...SLCM];

/** eMASS Implementation Plan + Risk Assessment for one control, with AI / rule suggestions that are never auto-saved. */
export function EmassPanels({ systemId, controlId, onSaved }: { systemId: string; controlId: string; onSaved: () => void }) {
  const url = `/systems/${systemId}/workbench/controls/${controlId}/emass`;
  const { data: d, reload } = useApi<Row>(url);
  const [st, setSt] = useState("Planned");
  const [v, setV] = useState<Row>({});
  const [sug, setSug] = useState<Row | null>(null);
  const [acc, setAcc] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState<Row>({});
  const key = d ? `${controlId}|${d.updated_at}|${d.implementation_status}` : "";
  useEffect(() => { if (d) { setSt(d.implementation_status); setV({ ...d.values }); setAcc(new Set()); setErr({}); } }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setSug(null); }, [controlId]);
  const imp = useImported(systemId, "emass_field");
  const impTools = (k: string) => { const info = imp.items[`${controlId}|${k}`]; return info ? <><ImportedMark info={info} testId={`emass-imported-${k}`} />{!ro && <ImportedDeleteBar selected={[`${controlId}|${k}`]} items={imp.items} onDone={() => { imp.reload(); reload(); onSaved(); }} testId={`emass-delete-imported-${k}`} label="Remove imported value" />}</> : null; };
  if (!d) return null;
  const o = d.options, ro = !d.can_edit, locked = st === "Inherited";
  const req: string[] = o.required[st] || [];
  const set = (k: string, val: string) => setV((p) => ({ ...p, [k]: val }));
  const sugFor = (k: string) => sug?.suggestions.find((s: Row) => s.field === k && String(v[k] ?? "") !== String(s.value));
  const accept = (k: string) => { const s = sugFor(k); if (s) { set(k, s.value); setAcc((p) => new Set(p).add(k)); } };
  const acceptAll = () => (sug?.suggestions || []).forEach((s: Row) => { if (s.field !== "na_justification" || st === "Not Applicable") accept(s.field); });
  const assist = (fields: string[]) => ({ source: sug ? (sug.source === "ai" ? "ai" : "rules") : null, interaction_id: sug?.interaction_id || null, fields: fields.filter((k) => acc.has(k)) });
  const clean = (ks: string[]) => Object.fromEntries(ks.map((k) => [k, typeof v[k] === "string" ? (v[k].trim() || null) : (v[k] ?? null)]));
  const run = async (which: "plan" | "risk") => {
    setBusy(which); setErr((p) => ({ ...p, [which]: "" }));
    const ks = which === "plan" ? visible(st) : [...RISK_ENUMS, ...RISK_TEXT];
    try {
      await api.put(`${url}/${which}`, which === "plan" ? { implementation_status: st, ...clean(ks), assist: assist(ks) } : { ...clean(ks), assist: assist(ks) });
      toast.success(which === "plan" ? `Implementation Plan saved (${st})` : "Risk Assessment saved", { description: acc.size ? "Accepted suggestions are recorded in the audit log." : undefined });
      reload(); onSaved();
    } catch (e) { setErr((p) => ({ ...p, [which]: errorMessage(e) })); } finally { setBusy(""); }
  };
  const suggest = async () => {
    setBusy("suggest");
    try { const r = await api.post<Row>(`${url}/suggest`, { implementation_status: st }); setSug(r.data); setAcc(new Set()); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(""); }
  };
  const field = (k: string) => {
    const max = o.limits[k] || 2000, val = v[k] ?? "";
    const input = ["control_designation", "slcm_frequency", "slcm_method", "common_control_provider"].includes(k) ?
      <select className="input w-full" value={val} disabled={ro || locked} onChange={(e) => set(k, e.target.value)} data-testid={`emass-${k}`}>
        <option value="">— select —</option>{({ control_designation: o.designations, slcm_frequency: o.frequencies, slcm_method: o.methods, common_control_provider: o.providers } as Row)[k].map((x: string) => <option key={x}>{x}</option>)}</select>
      : k === "estimated_completion_date" ? <input type="date" className="input w-full" value={val} disabled={ro || locked} onChange={(e) => set(k, e.target.value)} data-testid={`emass-${k}`} />
      : PLAN_TEXT.includes(k) ? <OtherSelect field={k} value={val} onChange={(x) => set(k, x)} disabled={ro || locked} max={max} />
      : <><textarea className="input w-full" rows={k === "slcm_comments" ? 3 : 2} maxLength={max} value={val} disabled={ro || locked} onChange={(e) => set(k, e.target.value)} data-testid={`emass-${k}`} /><Counter v={val} max={max} testId={`emass-count-${k}`} /></>;
    return <EField key={k} k={k} label={o.labels[k]} extra={impTools(k)} required={req.includes(k)} missing={req.includes(k) && !String(val).trim()} sug={ro ? undefined : sugFor(k)} onAccept={() => accept(k)}>{input}{SLCM.includes(k) && <SlcmChip k={k} />}</EField>;
  };
  const SlcmChip = ({ k }: { k: string }) => {
    const src = d.slcm_source?.[k] || "", sv = d.strategy_values?.[k];
    if (!src && !sv) return null;
    const reset = async () => { try { await api.post(`${url}/slcm-reset`, { fields: [k] }); toast.success(`${o.labels[k]} now follows the Continuous Monitoring Strategy`); reload(); onSaved(); } catch (e) { toast.error(errorMessage(e)); } };
    return <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]" data-testid={`emass-src-${k}`}>
      <span className={`rounded px-1.5 py-0.5 ${src === "Override" ? "bg-amber-50 text-amber-900" : "bg-blue-50 text-blue-900"}`} title="Where the effective eMASS value comes from (override → profile → system default)">{src || "Not set"}</span>
      {src === "Override" && sv && <span className="text-slate-500">Strategy: {sv}</span>}
      {src === "Override" && sv && !ro && !locked && <button className="text-blue-800 underline" onClick={reset} data-testid={`emass-reset-${k}`}>Reset to strategy</button>}</div>;
  };
  const hint = residualHint(v.likelihood, v.impact);
  return (
    <div className="space-y-4" data-testid="emass-panels">
      {ro && <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900" data-testid="emass-readonly">Read-only: {deniedText("implementation.write")} Only the ISSO or System Owner of this system can edit eMASS Implementation Plan and Risk Assessment fields.</div>}
      {sug && <div className="rounded border border-violet-200 bg-violet-50 px-3 py-2 text-[12px] text-violet-900" data-testid="emass-sug-banner">
        <b>{sug.label}</b>{sug.note && <> · {sug.note}</>} · {sug.suggestions.length} suggestion(s){sug.rejected?.length ? `, ${sug.rejected.length} rejected by validation` : ""} · grounded in {sug.grounding?.evidence ?? 0} evidence, {sug.grounding?.open_findings ?? 0} open findings, {sug.grounding?.open_poams ?? 0} POA&Ms
        {sug.suggestions.length > 0 && <button className="ml-2 underline" onClick={acceptAll} data-testid="emass-accept-all">Accept all</button>}
        <button className="ml-2 underline" onClick={() => setSug(null)} data-testid="emass-sug-dismiss">Dismiss</button></div>}
      <Panel title="eMASS Implementation Plan" testId="emass-plan-panel" actions={!ro && !locked && <button className="btn-secondary" disabled={!!busy} onClick={suggest} data-testid="emass-suggest-btn">{busy === "suggest" ? "Suggesting…" : "Suggest values"}</button>}>
        <p className="mb-3 text-[12px] text-slate-600">eMASS field names and values (PUT /api/systems/&#123;systemId&#125;/controls). Implementation Status here and the Status above are the same value: Planned ↔ planned / partially implemented / not implemented, Implemented ↔ implemented, Not Applicable ↔ not applicable, Inherited / Manually Inherited ↔ inherited. Fields marked * are required by eMASS for the chosen status. <a className="text-blue-800 underline" href={`/systems/${systemId}/emass-import`} data-testid="emass-panel-import-link">Import from eMASS</a></p>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-[12px]"><span className="font-medium">Implementation Status *</span>
            <select className="input mt-1 w-full" value={st} disabled={ro} onChange={(e) => setSt(e.target.value)} data-testid="emass-implementation_status">{o.statuses.map((x: string) => <option key={x}>{x}</option>)}</select></label>
          <div className="text-[11px] text-slate-500" data-testid="emass-narrative-note">Implementation Narrative = the current implementation statement below ({d.narrative_length.toLocaleString()} chars{d.narrative_over_limit ? " – OVER the eMASS 2,000-character limit" : ""}).</div>
        </div>
        {locked ? <div className="mt-3 rounded bg-slate-50 px-3 py-2 text-[12px]" data-testid="emass-inherited-note"><b>Inherited:</b> Implementation Plan values come from the providing system / common control provider and are read-only here.
          {d.inheritance ? <div className="mt-1">Provider: <b>{d.inheritance.provider || "not named"}</b>{d.inheritance.package ? ` (${d.inheritance.package})` : ""} · responsibility {d.inheritance.responsibility}{d.inheritance.provider_responsibility ? ` · provider: ${d.inheritance.provider_responsibility}` : ""}</div>
            : <div className="mt-1 text-amber-800">No inheritance record exists – choose Manually Inherited to enter the Common Control Provider.</div>}</div>
          : <div className="mt-3 grid gap-3 md:grid-cols-2">{visible(st).map(field)}</div>}
        {err.plan && <div className="mt-2 text-[12px] text-rose-700" role="alert" data-testid="emass-plan-error">{err.plan}</div>}
        {!ro && <div className="mt-3 flex items-center gap-3"><button className="btn-primary" disabled={!!busy} onClick={() => run("plan")} data-testid="emass-plan-save">{busy === "plan" ? "Saving…" : "Save Implementation Plan"}</button>
          <span className="text-[11px] text-slate-500" data-testid="emass-missing-count">{d.missing_required.length ? `${d.missing_required.length} required field(s) missing in the saved record` : "Saved record has all required fields"}</span></div>}
      </Panel>
      <Panel title="eMASS Risk Assessment" testId="emass-risk-panel">
        {locked && <div className="mb-2 rounded bg-slate-50 px-3 py-2 text-[12px]" data-testid="emass-risk-locked">Risk Assessment cannot be edited while the control is Inherited (eMASS rule).</div>}
        <div className="grid gap-3 md:grid-cols-3">{RISK_ENUMS.map((k) => <EField key={k} k={k} label={o.labels[k]} extra={impTools(k)} sug={ro || locked ? undefined : sugFor(k)} onAccept={() => accept(k)}>
          <select className="input w-full" value={v[k] ?? ""} disabled={ro || locked} onChange={(e) => set(k, e.target.value)} data-testid={`emass-${k}`}><option value="">— select —</option>{o.levels.map((x: string) => <option key={x}>{x}</option>)}</select></EField>)}</div>
        {hint && <div className="mt-2 text-[11px] text-slate-600" data-testid="emass-residual-hint">Computed suggestion (not applied): Likelihood {v.likelihood} × Impact {v.impact} → Residual Risk Level <b>{hint}</b> (NIST SP 800-30 style lookup).</div>}
        <div className="mt-3 grid gap-3 md:grid-cols-2">{RISK_TEXT.map((k) => <EField key={k} k={k} label={o.labels[k]} extra={impTools(k)} sug={ro || locked ? undefined : sugFor(k)} onAccept={() => accept(k)}>
          <textarea className="input w-full" rows={2} maxLength={2000} value={v[k] ?? ""} disabled={ro || locked} onChange={(e) => set(k, e.target.value)} data-testid={`emass-${k}`} /><Counter v={v[k] ?? ""} max={2000} testId={`emass-count-${k}`} /></EField>)}</div>
        {err.risk && <div className="mt-2 text-[12px] text-rose-700" role="alert" data-testid="emass-risk-error">{err.risk}</div>}
        {!ro && !locked && <button className="btn-primary mt-3" disabled={!!busy} onClick={() => run("risk")} data-testid="emass-risk-save">{busy === "risk" ? "Saving…" : "Save Risk Assessment"}</button>}
      </Panel>
    </div>);
}
