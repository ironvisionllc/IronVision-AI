import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useApi, Row } from "@/lib/useApi";
import { useAuth } from "@/context/AuthContext";
import { Modal } from "@/components/common/Modal";
import { downloadFile } from "@/lib/download";

type Mode = "view" | "replace" | "history" | "remove";

/** Evidence record actions: view, download, replace / new version (immutable), version history, logical removal. */
export function EvidenceActions({ ev, systemId, onChanged }: { ev: Row; systemId: string; onChanged: () => void }) {
  const { can } = useAuth();
  const [mode, setMode] = useState<Mode | null>(null);
  const [menu, setMenu] = useState(false);
  const pick = (m: Mode) => { setMode(m); setMenu(false); };
  const write = can("evidence.submit") && !!systemId;
  return (
    <div className="relative inline-block">
      <button className="btn-secondary px-2 py-0.5 text-[10px]" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(!menu)} data-testid={`ev-actions-${ev.id}`}>Actions ▾</button>
      {menu && <div role="menu" className="iv-popover absolute right-0 z-20 mt-1 grid w-48 p-1 text-left text-[12px]" onKeyDown={(e) => e.key === "Escape" && setMenu(false)}>
        <button role="menuitem" className="rounded px-2 py-1 text-left hover:bg-slate-100" onClick={() => pick("view")} data-testid={`ev-view-${ev.id}`}>View details</button>
        <button role="menuitem" className="rounded px-2 py-1 text-left hover:bg-slate-100" onClick={() => { setMenu(false); downloadFile(`/evidence/${ev.id}/download`, ev.file_name || "evidence", "Evidence"); }} data-testid={`ev-download-${ev.id}`}>Download</button>
        {write && <button role="menuitem" className="rounded px-2 py-1 text-left hover:bg-slate-100" onClick={() => pick("replace")} data-testid={`ev-replace-${ev.id}`}>Replace</button>}
        {write && <button role="menuitem" className="rounded px-2 py-1 text-left hover:bg-slate-100" onClick={() => pick("replace")} data-testid={`ev-newversion-${ev.id}`}>Upload new version</button>}
        <button role="menuitem" className="rounded px-2 py-1 text-left hover:bg-slate-100" onClick={() => pick("history")} data-testid={`ev-history-${ev.id}`}>Version history</button>
        {write && <button role="menuitem" className="rounded px-2 py-1 text-left text-rose-700 hover:bg-rose-50" onClick={() => pick("remove")} data-testid={`ev-remove-${ev.id}`}>Remove…</button>}
      </div>}
      {mode && <EvidenceDialog ev={ev} mode={mode} onClose={() => setMode(null)} onChanged={onChanged} />}
    </div>);
}

function EvidenceDialog({ ev, mode, onClose, onChanged }: { ev: Row; mode: Mode; onClose: () => void; onChanged: () => void }) {
  const { data, reload } = useApi<Row>(`/evidence/${ev.id}`);
  const [reason, setReason] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr("");
    try { await fn(); reload(); onChanged(); onClose(); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  };
  const upload = () => run(async () => { const f = new FormData(); f.append("reason", reason); f.append("file", file!); await api.post(`/evidence/${ev.id}/versions`, f); });
  const remove = () => run(() => api.post(`/evidence/${ev.id}/remove`, { reason }));
  const title = { view: "Evidence details", replace: "Replace / upload new version", history: "Version history", remove: "Remove evidence" }[mode];
  return (
    <Modal title={`${title} – ${ev.name}`} onClose={onClose} testId="evidence-dialog">
      {!data ? <p className="text-[12px]">Loading…</p> : <div className="grid gap-2 text-[12px]">
        {mode === "view" && <dl className="grid grid-cols-[140px_1fr] gap-x-3 gap-y-1" data-testid="ev-meta">
          {[["Evidence ID", data.evidence_id], ["Version", data.version], ["File name", data.file_name], ["Type", data.type], ["Upload date", data.upload_date], ["Uploaded by", data.uploaded_by],
            ["Status", data.status], ["Replacement reason", data.replacement_reason], ["SHA-256", data.sha256], ["Review status", data.review_status],
            ["Expiration", data.expiration ?? (data.freshness_window_days ? `${data.freshness_window_days}-day freshness window` : "—")], ["Legal hold", data.legal_hold ? "Yes" : "No"]]
            .map(([k, v]) => <><dt key={`k${k}`} className="font-medium text-slate-600">{k}</dt><dd key={`v${k}`} className="break-all">{v ?? "—"}</dd></>)}
          <dt className="font-medium text-slate-600">Related controls</dt><dd>{data.related_controls.map((c: Row) => <div key={c.control_id}>{c.control_id.toUpperCase()}{c.needs_revalidation && <span className="ml-1 text-amber-800">– re-review: {c.reason}</span>}{c.removed && " (mapping closed)"}</div>)}</dd>
        </dl>}
        {mode === "history" && (data.versions ? <table className="w-full text-[11px]" data-testid="ev-versions"><tbody>{data.versions.map((v: Row) => <tr key={v.version}>
          <td className="td">v{v.version}{v.active && " (active)"}</td><td className="td">{v.file_name}</td><td className="td font-mono">{v.sha256.slice(0, 16)}…</td><td className="td">{v.uploaded_by}</td>
          <td className="td">{v.reason}</td><td className="td"><button className="text-blue-800 underline" onClick={() => downloadFile(`/evidence/${ev.id}/download?version=${v.version}`, v.file_name || "evidence", "Evidence version")}>Download</button></td></tr>)}</tbody></table>
          : <p data-testid="ev-history-restricted">Historical versions are visible to evidence submitters, assessors and auditors only.</p>)}
        {mode === "replace" && <>
          <p className="text-slate-600">The new file becomes the active version. The current file and its SHA-256 stay in the version history, and linked control mappings and Test Results rows are flagged “Evidence changed – re-review”.</p>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="ev-file" aria-label="New version file" />
          <textarea className="input" rows={2} placeholder="Replacement reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="ev-reason" />
          <button className="btn-primary w-fit" disabled={busy || !file || reason.trim().length < 5} onClick={upload} data-testid="ev-upload-submit">Upload new version</button></>}
        {mode === "remove" && <>
          {data.legal_hold ? <p className="rounded bg-rose-50 p-2 text-rose-800" data-testid="ev-hold">Under legal hold – it can't be removed until an administrator lifts the hold.</p>
            : <p className="text-slate-600">Removal is logical: the record, its versions and hashes are kept for the audit trail, and its control mappings are closed and flagged for re-review. {data.permanent_deletion}</p>}
          <textarea className="input" rows={2} placeholder="Reason for removal (required)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="ev-remove-reason" />
          <button className="btn-primary w-fit !bg-rose-700" disabled={busy || data.legal_hold || reason.trim().length < 5} onClick={remove} data-testid="ev-remove-confirm">Remove evidence</button></>}
        {err && <div className="text-rose-700" role="alert">{err}</div>}
      </div>}
    </Modal>);
}
