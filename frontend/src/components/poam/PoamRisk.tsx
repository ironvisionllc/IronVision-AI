import { useMemo, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { autosaveCall, useAutoSave } from "@/lib/useAutoSave";
import { AutoSaveStatus } from "@/components/common/AutoSaveStatus";

const F: [string, string][] = [["raw_severity", "Raw Severity"], ["relevance_of_threat", "Relevance of Threat"], ["likelihood", "Likelihood"], ["impact", "Impact"], ["residual_risk_level", "Residual Risk Level"]];
const KEYS = [...F.map((x) => x[0]), "mitigations", "comments"];

/** eMASS POA&M risk fields – separate from the technical severity / CAT; defaults can come from the control's Risk Assessment. */
export function PoamRisk({ poamId, editable }: { poamId: string; editable: boolean }) {
  const { data, reload } = useApi<Row>(`/poams/${poamId}/risk`);
  const [f, setF] = useState<Row | null>(null);
  const [msg, setMsg] = useState("");
  const init = useMemo<Row>(() => (data ? Object.fromEntries(KEYS.map((k) => [k, data.emass[k] ?? null])) : {}), [data]);
  const last = useRef<Row | null>(null);
  const val = useMemo<Row>(() => (f ? Object.fromEntries(KEYS.map((k) => [k, f[k] ?? null])) : init), [f, init]);
  // only changed fields are sent, so untouched imported/control-derived values keep their source
  const as = useAutoSave<Row>({ id: data && editable ? `poamrisk:${poamId}` : null, initial: init, value: val, version: data?.updated_at ?? null,
    resetKey: data?.updated_at ?? "", apply: (x) => setF(x),
    save: async (x, base) => {
      const prev = last.current || init, body: Row = {};
      for (const k of KEYS) if ((x[k] ?? null) !== (prev[k] ?? null)) body[k] = x[k] || null;
      if (!Object.keys(body).length) return;
      const r = await autosaveCall<Row>("patch", `/poams/${poamId}`, body, base); last.current = x; return { version: r.updated_at };
    } });
  if (!data) return null;
  const v = f ?? data.emass;
  const src = (k: string) => data.source[k] ? (data.source[k] === "manual" ? "entered manually" : data.source[k].startsWith("control:") ? `from ${data.source[k].slice(8).toUpperCase()} Risk Assessment` : "from eMASS import") : "";
  const save = async () => { try { const body: Row = {}; for (const k of KEYS) if ((v[k] ?? null) !== (data.emass[k] ?? null)) body[k] = v[k] || null; await api.patch(`/poams/${poamId}`, body); setF(null); setMsg("Risk fields saved (audited)"); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  const fromControl = async (cid: string) => { try { const r = await api.post<Row>(`/poams/${poamId}/risk/from-control`, { control_id: cid }); setMsg(`Filled ${Object.keys(r.data.applied).length} field(s) from ${cid.toUpperCase()}; kept your existing values for ${r.data.kept.length}.`); setF(null); reload(); } catch (e) { setMsg(errorMessage(e)); } };
  return <Panel title="Risk (eMASS POA&M fields)" testId="poam-risk">
    <div className="mb-2 rounded bg-slate-50 p-2 text-[12px]" data-testid="poam-risk-technical">Technical severity: <b>{data.technical.severity ?? "—"}</b> {data.technical.cat ?? ""} · <span className="text-slate-500">{data.technical.note}</span></div>
    <div className="grid grid-cols-2 gap-2 text-[12px]" onBlur={as.flush}>{F.map(([k, l]) => <label key={k}>{l}
      <select className="input" value={v[k] ?? ""} disabled={!editable} onChange={(e) => setF({ ...v, [k]: e.target.value })} data-testid={`poam-risk-${k}`}>
        <option value="">— not set —</option>{data.scale.map((s: string) => <option key={s}>{s}</option>)}</select>
      {src(k) && <span className="text-[10px] text-slate-500" data-testid={`poam-risk-src-${k}`}>{src(k)}</span>}</label>)}</div>
    {["mitigations", "comments"].map((k) => <label key={k} className="mt-2 block text-[12px] capitalize">{k}
      <textarea className="input" rows={2} value={v[k] ?? ""} disabled={!editable} onBlur={as.flush} onChange={(e) => setF({ ...v, [k]: e.target.value })} data-testid={`poam-risk-${k}`} /></label>)}
    {editable && <div className="mt-2 flex flex-wrap items-center gap-2">
      <button className="btn-primary" disabled={!f} onClick={save} data-testid="poam-risk-save">{as.on ? "Save now" : "Save risk fields"}</button>
      {data.control_risk_assessments.filter((c: Row) => Object.keys(c.values).length).map((c: Row) =>
        <button key={c.control_id} className="btn-secondary" onClick={() => fromControl(c.control_id)} data-testid={`poam-risk-from-${c.control_id}`}>Fill empty fields from {c.control_id.toUpperCase()} Risk Assessment</button>)}
      <AutoSaveStatus a={as} testId="poam-risk-autosave" />
    </div>}
    {msg && <div className="mt-2 text-[12px]" role="alert" data-testid="poam-risk-msg">{msg}</div>}
  </Panel>;
}
