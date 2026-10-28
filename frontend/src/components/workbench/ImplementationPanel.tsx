import { EmassSubmitButton } from "@/pages/Phase4Pages";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { Panel } from "@/components/common/Panel";
import { S } from "@/components/common/Bits";
import { fmtDate } from "@/lib/format";
import { Gated } from "@/components/common/RoleGate";


function diffLines(a: string, b: string) {
  const A = a.split(/(?<=[.!?])\s+|\n/), B = b.split(/(?<=[.!?])\s+|\n/);
  return [...A.filter((x) => !B.includes(x)).map((t) => ({ t, k: "-" })), ...B.filter((x) => !A.includes(x)).map((t) => ({ t, k: "+" }))];
}

export function ImplementationPanel({ systemId, controlId, d, reload }: { systemId: string; controlId: string; d: Row; reload: () => void }) {
  const { can } = useAuth();
  const [narr, setNarr] = useState("");
  const [ai, setAi] = useState<Row | null>(null);
  const impl = d.assignment.implementation_status;  // status is saved in the separate Status section
  const [busy, setBusy] = useState<string | false>(false);
  const [msg, setMsg] = useState("");
  const [diff, setDiff] = useState<Row | null>(null);
  // reset only when the control or its latest saved version changes – quiet background refreshes must not discard an unsaved draft
  const latestKey = `${controlId}:${d.implementations[0]?.id ?? ""}:${d.implementations[0]?.version ?? ""}`;
  useEffect(() => { setNarr(d.implementations[0]?.narrative ?? ""); setAi(null); }, [latestKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const versions: Row[] = d.implementations;
  const latest = versions[0];
  const approved = d.approved_implementation;
  const evName = (id: string) => d.evidence.find((e: Row) => e.id === id)?.name ?? id.slice(0, 8);
  const generate = async (mode = "auto") => {
    setBusy(mode); setMsg("");
    try {
      const r = await api.post<Row>(`/systems/${systemId}/workbench/controls/${controlId}/ai-draft`, null, { params: { mode } });
      if (!(r.data.draft?.narrative || "").trim()) { setMsg("The draft came back empty – nothing was changed in the editor. Try Template draft or write the statement manually."); return; }
      setAi(r.data); setNarr(r.data.draft.narrative); setMsg(`${r.data.template ? "Template" : "AI"} draft loaded into the editor – not saved yet. Review it, then Save draft version.`);
    }
    catch (e) { setMsg(`Draft generation failed – the editor was not changed. ${errorMessage(e)}`); } finally { setBusy(false); }
  };
  const save = async () => {
    try {
      await api.put(`/systems/${systemId}/workbench/controls/${controlId}/implementation`, {
        narrative: narr, implementation_status: impl, ai_generated: !!ai && !ai.template, prompt_version: ai ? `${ai.prompt_id}@${ai.prompt_version}` : undefined,
        interaction_id: ai?.template ? undefined : ai?.interaction_id, citations: ai?.draft.citations ?? [], ai_sections: ai ? { verified_facts: ai.draft.verified_facts, interpretation: ai.draft.interpretation, suggested_actions: ai.draft.suggested_actions, missing_information: ai.draft.missing_information } : undefined });
      setMsg("Saved as new draft version – next: attach evidence (Evidence & Policies tab) or request review"); setAi(null); reload();
    } catch (e) { setMsg(errorMessage(e)); }
  };
  const requestReview = async () => {
    const j = window.prompt("Note for reviewer (min 10 chars)", "Please review this implementation statement"); if (!j) return;
    try { await api.post(`/systems/${systemId}/workbench/implementations/${latest.id}/request-review`, { justification: j }); setMsg("Review requested (routes per decision rule)"); reload(); }
    catch (e) { setMsg(errorMessage(e)); }
  };
  const sections = ai?.draft ?? latest?.ai_sections;
  return (
    <Panel title="Implementation statement" eyebrow="Versioned · AI drafts are never auto-approved or submitted" testId="wb-narrative">
      {approved ? <div className="mb-3 rounded border border-emerald-200 bg-emerald-50 p-2 text-[12px]" data-testid="wb-approved-narrative"><b>Current approved (v{approved.version})</b>{approved.needs_reconsideration && <span className="ml-2"><S v="near_expiration" label="needs reconsideration" /></span>}<p className="mt-1 whitespace-pre-wrap">{approved.narrative}</p></div>
        : <div className="mb-3 text-[12px] text-slate-500" data-testid="wb-no-approved">No approved statement yet.</div>}
      {latest?.needs_reconsideration && (latest.narrative ?? "").trim() !== "" && <div className="mb-2 text-[12px] text-amber-800" data-testid="wb-needs-reconsideration">Linked evidence changed since this version was written – needs reconsideration.</div>}
      {ai?.template ? <div className="mb-2 inline-block rounded bg-sky-100 px-2 py-0.5 text-[11px] font-bold tracking-wide text-sky-900" data-testid="template-draft-label">TEMPLATE DRAFT (no AI) · {ai.prompt_version}{!ai.ai_status?.configured && ai.ai_status?.reason ? ` · ${ai.ai_status.reason}` : ""}</div>
        : (ai || latest?.ai_generated) && <div className="mb-2 inline-block rounded bg-amber-100 px-2 py-0.5 text-[11px] font-bold tracking-wide text-amber-900" data-testid="ai-draft-label">AI DRAFT – not reviewed{ai && ` · ${ai.model} · ${ai.prompt_id}@${ai.prompt_version}`}</div>}
      {!ai && latest?.prompt_version?.startsWith("template") && <div className="mb-2 inline-block rounded bg-sky-100 px-2 py-0.5 text-[11px] font-bold text-sky-900">TEMPLATE DRAFT (no AI)</div>}
      <textarea className="input" rows={7} id="wb-narrative" value={narr} onChange={(e) => setNarr(e.target.value)} disabled={!can("implementation.write")} autoFocus={can("implementation.write")} data-testid="wb-narrative-input" />
      {ai && ai.stripped_citations.length > 0 && <div className="mt-1 text-[11px] text-rose-700" data-testid="ai-stripped">{ai.stripped_citations.length} citation(s) to non-existent evidence were removed.</div>}
      {(ai?.draft.citations ?? latest?.citations ?? []).length > 0 && <div className="mt-2 text-[12px]" data-testid="ai-citations"><b>Citations:</b> {(ai?.draft.citations ?? latest.citations).map((c: string) => <Link key={c} to="/evidence-ledger" className="mr-2 text-blue-800 underline">{evName(c)}</Link>)}</div>}
      {sections && <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="ai-sections">
        {[["verified_facts", "Verified facts"], ["interpretation", "Interpretation"], ["suggested_actions", "Suggested actions"], ["missing_information", "Missing information"]].map(([k, l]) => (
          <div key={k} className="rounded border border-slate-200 p-2 text-[12px]" data-testid={`ai-section-${k}`}><div className="font-medium">{l}</div><ul className="list-disc pl-4">{(sections[k] || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></div>))}
      </div>}
      {ai && <div className="mt-1 text-[11px] text-slate-500">Grounded on {ai.grounding.evidence_count} current evidence item(s). Policies: {ai.grounding.policies}</div>}
      <div className="sticky bottom-0 z-10 -mx-4 mt-3 flex flex-wrap items-center gap-2 border-t border-slate-200 bg-white px-4 py-2" data-testid="wb-narrative-actions">
        <Gated perm="implementation.write"><>
          <button className="btn-secondary" onClick={() => generate("auto")} disabled={!!busy} data-testid="ai-generate-btn">{busy === "auto" ? "Generating…" : "Generate draft"}</button>
          <button className="btn-secondary" onClick={() => generate("template")} disabled={!!busy} data-testid="template-generate-btn">{busy === "template" ? "Building template…" : "Template draft"}</button>
          <button className="btn-primary" onClick={save} disabled={!narr.trim()} data-testid="wb-narrative-save">Save draft version</button>
          <button className="btn-secondary" onClick={requestReview} disabled={!latest || latest.review_status !== "draft" || !!ai} data-testid="wb-request-review">Request review</button>
        </></Gated>
        <EmassSubmitButton systemId={systemId} controlId={controlId} />
      </div>
      {msg && <div className="mt-2 text-[12px]" role="alert" data-testid="wb-narrative-msg">{msg}</div>}
      <div className="mt-4 text-[12px] font-medium">Version history</div>
      {versions.map((v, i) => (
        <div key={v.id} className="flex items-center justify-between border-b border-slate-100 py-1 text-[12px]" data-testid={`impl-version-${v.version}`}>
          <span data-testid={`impl-author-${v.version}`}>v{v.version} · {fmtDate(v.created_at)} · {v.author_name ? `${v.author_name}${(v.author_roles || []).length ? ` (${v.author_roles.map((x: string) => x.toUpperCase()).join("/")})` : ""}` : "System (seed)"} · {v.ai_generated ? "AI-assisted" : v.prompt_version?.startsWith("template") ? "template" : "manual"} {v.prompt_version && `(${v.prompt_version})`}</span>
          <span className="flex items-center gap-2"><S v={v.review_status} />{versions[i + 1] && <button className="text-blue-800 underline" onClick={() => setDiff({ v, prev: versions[i + 1] })} data-testid={`impl-diff-${v.version}`}>diff</button>}</span>
        </div>))}
      {diff && <div className="mt-2 rounded bg-slate-50 p-2 font-mono text-[11px]" data-testid="impl-diff-view">v{diff.prev.version} → v{diff.v.version}{diffLines(diff.prev.narrative, diff.v.narrative).map((x, i) => <div key={i} className={x.k === "+" ? "text-emerald-700" : "text-rose-700"}>{x.k} {x.t}</div>)}</div>}
    </Panel>
  );
}
