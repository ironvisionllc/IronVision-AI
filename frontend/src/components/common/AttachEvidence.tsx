import { useState } from "react";
import { Link2, Paperclip } from "lucide-react";
import { api, errorMessage as errMsg } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Gated } from "@/components/common/RoleGate";
import { CompletedNext } from "@/components/common/CompletedNext";
import type { Row } from "@/lib/useApi";

/** Attach evidence where it is shown (control, finding, POA&M): upload (no source needed) or link an existing item, pre-linked to the controls. */
export function AttachEvidence({ systemId, controlIds, onDone, testId = "attach-evidence" }: { systemId: string; controlIds: string[]; onDone?: () => void; testId?: string }) {
  const [open, setOpen] = useState<"" | "upload" | "link">("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pick, setPick] = useState("");
  const { data: all } = useApi<Row[]>(open === "link" ? `/systems/${systemId}/evidence` : null);
  const link = async (evidenceId: string) => {
    for (const c of controlIds) await api.post(`/systems/${systemId}/controls/${c}/evidence-links`, { evidence_id: evidenceId });
  };
  const upload = async (f: File) => {
    setBusy(true); setMsg(null);
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await api.post(`/systems/${systemId}/uploads`, fd);
      if (r.data.evidence_id) await link(r.data.evidence_id);
      setMsg({ ok: true, text: `“${f.name}” ${r.data.status === "duplicate" ? "was already received (same SHA-256) –" : "received – processing;"} linked to ${controlIds.join(", ").toUpperCase()}` });
      setOpen(""); onDone?.();
    } catch (e) { setMsg({ ok: false, text: errMsg(e) }); } finally { setBusy(false); }
  };
  const linkExisting = async () => {
    setBusy(true); setMsg(null);
    try { await link(pick); setMsg({ ok: true, text: `Linked to ${controlIds.join(", ").toUpperCase()}` }); setOpen(""); setPick(""); onDone?.(); }
    catch (e) { setMsg({ ok: false, text: errMsg(e) }); } finally { setBusy(false); }
  };
  return (
    <Gated perm="ingest.upload">
      <div className="mb-3" data-testid={testId}>
        <div className="flex flex-wrap gap-2">
          <label className={`btn-primary cursor-pointer ${busy ? "pointer-events-none" : ""}`} data-testid={`${testId}-btn`}>
            <Paperclip className="h-4 w-4" aria-hidden />{busy ? "Uploading…" : "Attach evidence"}
            <input type="file" className="sr-only" disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} data-testid={`${testId}-input`} />
          </label>
          <button type="button" className="btn-secondary" onClick={() => setOpen(open === "link" ? "" : "link")} data-testid={`${testId}-link-btn`}><Link2 className="h-4 w-4" aria-hidden />Link existing evidence</button>
        </div>
        {open === "link" && <div className="mt-2 flex flex-wrap items-center gap-2">
          <select className="input max-w-md" value={pick} onChange={(e) => setPick(e.target.value)} data-testid={`${testId}-pick`} aria-label="Existing evidence">
            <option value="">Choose evidence in this system…</option>
            {(all || []).map((e) => <option key={e.id} value={e.id}>{e.name} · {String(e.collected_at || "").slice(0, 10)}</option>)}</select>
          <button className="btn-secondary" disabled={!pick || busy} onClick={linkExisting} data-testid={`${testId}-link-save`}>Link</button></div>}
        {msg && (msg.ok
          ? <CompletedNext kind="" testId={`${testId}-done`} next={{ label: `${msg.text}. Next: check the statement still matches the evidence (Implementation tab)`, link: `/systems/${systemId}/controls/${controlIds[0]}?tab=implementation` }} />
          : <div className="mt-2 text-[12px] text-rose-700" role="alert" data-testid={`${testId}-error`}>{msg.text}</div>)}
      </div>
    </Gated>);
}
