import { useState } from "react";
import { Link2, Paperclip, UploadCloud } from "lucide-react";
import { api, errorMessage as errMsg } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Gated } from "@/components/common/RoleGate";
import { CompletedNext } from "@/components/common/CompletedNext";
import { Modal } from "@/components/common/Modal";
import type { Row } from "@/lib/useApi";

/** Attach evidence where it is shown (control, finding, POA&M): in-app dialog (drop zone / Choose file, no source needed) or link an existing item. */
export function AttachEvidence({ systemId, controlIds, onDone, testId = "attach-evidence" }: { systemId: string; controlIds: string[]; onDone?: () => void; testId?: string }) {
  const [open, setOpen] = useState<"" | "upload" | "link">("");
  const [pct, setPct] = useState<number | null>(null);
  const [over, setOver] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pick, setPick] = useState("");
  const { data: all } = useApi<Row[]>(open === "link" ? `/systems/${systemId}/evidence` : null);
  const target = controlIds.join(", ").toUpperCase();
  const busy = pct !== null;
  const link = async (evidenceId: string) => {
    for (const c of controlIds) await api.post(`/systems/${systemId}/controls/${c}/evidence-links`, { evidence_id: evidenceId });
  };
  const upload = async (f: File) => {
    setPct(0); setMsg(null);
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await api.post<Row>(`/systems/${systemId}/uploads`, fd, { onUploadProgress: (e) => setPct(e.total ? Math.round((100 * e.loaded) / e.total) : 50) });
      if (r.data.evidence_id) await link(r.data.evidence_id);
      setMsg({ ok: true, text: `“${f.name}” ${r.data.status === "duplicate" ? "was already received (same SHA-256) –" : "received – processing;"} linked to ${target}` });
      setOpen(""); onDone?.();  // the dialog closes on success; the completion + next step stays on the tab
    } catch (e) { setMsg({ ok: false, text: errMsg(e) }); } finally { setPct(null); }
  };
  const linkExisting = async () => {
    setPct(0); setMsg(null);
    try { await link(pick); setMsg({ ok: true, text: `Linked to ${target}` }); setOpen(""); setPick(""); onDone?.(); }
    catch (e) { setMsg({ ok: false, text: errMsg(e) }); } finally { setPct(null); }
  };
  const done = msg && (msg.ok
    ? <CompletedNext kind="" testId={`${testId}-done`} next={{ label: `${msg.text}. Next: check the statement still matches the evidence (Implementation tab)`, link: `/systems/${systemId}/controls/${controlIds[0]}?tab=implementation` }} />
    : <div className="mt-2 text-[12px] text-rose-700" role="alert" data-testid={`${testId}-error`}>{msg.text}</div>);
  return (
    <Gated perm="ingest.upload">
      <div className="mb-3" data-testid={testId}>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-primary" onClick={() => { setMsg(null); setOpen("upload"); }} data-testid={`${testId}-btn`}><Paperclip className="h-4 w-4" aria-hidden />Attach evidence</button>
          <button type="button" className="btn-secondary" onClick={() => setOpen(open === "link" ? "" : "link")} data-testid={`${testId}-link-btn`}><Link2 className="h-4 w-4" aria-hidden />Link existing evidence</button>
        </div>
        {open === "link" && <div className="mt-2 flex flex-wrap items-center gap-2">
          <select className="input max-w-md" value={pick} onChange={(e) => setPick(e.target.value)} data-testid={`${testId}-pick`} aria-label="Existing evidence">
            <option value="">Choose evidence in this system…</option>
            {(all || []).map((e) => <option key={e.id} value={e.id}>{e.name} · {String(e.collected_at || "").slice(0, 10)}</option>)}</select>
          <button className="btn-secondary" disabled={!pick || busy} onClick={linkExisting} data-testid={`${testId}-link-save`}>Link</button></div>}
        {open !== "upload" && done}
        {open === "upload" && <Modal title="Attach evidence" onClose={() => setOpen("")} testId={`${testId}-dialog`}>
          <p className="text-[13px]" data-testid={`${testId}-target`}>Target control{controlIds.length > 1 ? "s" : ""}: <b className="font-mono">{target}</b> · no evidence source needed</p>
          <div className={`mt-3 flex flex-col items-center gap-2 rounded-lg border-2 border-dashed p-6 text-center text-[13px] ${over ? "border-sky-600 bg-sky-50" : "border-slate-300"}`}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f && !busy) upload(f); }} data-testid={`${testId}-dropzone`}>
            <UploadCloud className="h-8 w-8 text-slate-500" aria-hidden />
            <span>Drop a file here, or</span>
            <label className={`btn-secondary cursor-pointer ${busy ? "pointer-events-none opacity-60" : ""}`} data-testid={`${testId}-choose`}>Choose file
              <input type="file" className="sr-only" disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} data-testid={`${testId}-input`} /></label>
            <span className="text-[11px] text-slate-500">Scan results, checklists, configuration exports or documents – stored with SHA-256 and linked to the control.</span>
          </div>
          {busy && <div className="mt-3" data-testid={`${testId}-progress`}><div className="h-2 rounded bg-slate-200"><div className="h-2 rounded bg-sky-700 transition-[width]" style={{ width: `${pct}%` }} /></div>
            <div className="mt-1 text-[12px]">Uploading… {pct}%</div></div>}
          {done}
        </Modal>}
      </div>
    </Gated>);
}
