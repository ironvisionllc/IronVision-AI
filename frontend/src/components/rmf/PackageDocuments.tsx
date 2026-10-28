import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { downloadFile } from "@/lib/download";

const DOCS: [string, string][] = [["ssp", "System Security Plan (SSP)"], ["sar", "Security Assessment Report (SAR)"], ["rar", "Risk Assessment Report (RAR)"]];

/** Authorize: generate SSP / SAR / RAR from recorded data. Missing-information check first; output is always labelled DRAFT. */
export function PackageDocuments({ systemId, acronym, kinds = ["ssp", "sar", "rar"], eyebrow }: { systemId: string; acronym: string; kinds?: string[]; eyebrow?: string }) {
  const [chk, setChk] = useState<Record<string, Row>>({});
  const [err, setErr] = useState("");
  const check = async (k: string) => { setErr(""); try { const r = await api.get<Row>(`/systems/${systemId}/documents/${k}/check`); setChk((c) => ({ ...c, [k]: r.data })); } catch (e) { setErr(errorMessage(e)); } };
  return <Panel title={`Generate ${DOCS.filter(([k]) => kinds.includes(k)).map(([k]) => k.toUpperCase()).join(" / ")} (DOCX, PDF)`} eyebrow={eyebrow ?? "RMF Step 6 · Authorize (R-1/R-2) · generated from this system's records, never auto-approved"} testId="package-documents">
    <div className="space-y-3">{DOCS.filter(([k]) => kinds.includes(k)).map(([k, label]) => <div key={k} className="rounded border border-slate-200 p-2" data-testid={`doc-${k}`}>
      <div className="flex flex-wrap items-center gap-2 text-[13px]"><b>{label}</b>
        <button className="btn-secondary" onClick={() => check(k)} data-testid={`doc-${k}-check`}>Check missing information</button>
        <button className="btn-secondary" onClick={() => downloadFile(`/systems/${systemId}/documents/${k}?format=docx`, `${acronym}_${k.toUpperCase()}_DRAFT.docx`, label)} data-testid={`doc-${k}-docx`}>DOCX</button>
        <button className="btn-secondary" onClick={() => downloadFile(`/systems/${systemId}/documents/${k}?format=pdf`, `${acronym}_${k.toUpperCase()}_DRAFT.pdf`, label)} data-testid={`doc-${k}-pdf`}>PDF</button>
        {k !== "rar" && <span className="text-[11px] text-slate-500">OSCAL JSON: use “OSCAL exports” above ({k === "ssp" ? "system-security-plan" : "assessment-results"})</span>}
        {k === "ssp" && <button className="btn-secondary" onClick={() => downloadFile(`/systems/${systemId}/emass/implementation-plan.xlsx`, `${acronym}_eMASS-implementation-plan.xlsx`, "eMASS-formatted Implementation Plan")} data-testid="pkg-export-emass-plan" title="eMASS-formatted Implementation Plan (moved here from the Control Workbench)">eMASS Implementation Plan (xlsx)</button>}
      </div>
      {chk[k] && <div className="mt-1 text-[12px]" data-testid={`doc-${k}-status`}><b className={chk[k].missing.length ? "text-amber-800" : "text-emerald-800"}>{chk[k].status}</b>
        {chk[k].missing.length > 0 ? <ul className="list-disc pl-5">{chk[k].missing.map((m: string, i: number) => <li key={i} data-testid={`doc-${k}-missing-${i}`}>{m}</li>)}</ul>
          : <span className="ml-2 text-slate-600">No missing information detected – still a DRAFT until reviewed and approved.</span>}</div>}
    </div>)}</div>
    {err && <div className="mt-2 text-[12px] text-rose-700" role="alert">{err}</div>}
  </Panel>;
}
