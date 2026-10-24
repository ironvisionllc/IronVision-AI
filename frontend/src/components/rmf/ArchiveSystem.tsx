import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Archive, RotateCcw } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { useSystems } from "@/context/SystemContext";
import { Gated } from "@/components/common/RoleGate";

/** Logical archive / restore of a system (audited, reason required, nothing deleted). */
export function ArchiveSystem({ s, onDone }: { s: Row; onDone: () => void }) {
  const nav = useNavigate();
  const { refresh } = useSystems();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const archived = !!s.archived_at;
  const submit = async () => {
    try {
      await api.post(`/systems/${s.id}/${archived ? "restore" : "archive"}`, { reason });
      setOpen(false); setReason(""); setErr("");
      await refresh();
      if (archived) onDone(); else nav("/systems");
    } catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <Gated perm="system.register">
      <div className="relative">
        <button className="btn-secondary" onClick={() => setOpen(!open)} data-testid={archived ? "restore-system-btn" : "archive-system-btn"}>
          {archived ? <RotateCcw className="h-4 w-4" /> : <Archive className="h-4 w-4" />}{archived ? "Restore system" : "Archive system"}
        </button>
        {open && (
          <div className="absolute right-0 z-20 mt-1 w-80 rounded-md border border-slate-200 bg-white p-3 text-[12px] shadow-lg" data-testid="archive-system-dialog">
            <p className="text-slate-600">{archived ? "Restore returns the system to all active lists." :
              "Archiving hides the system from active lists. Nothing is deleted; it is audited and can be restored."}</p>
            <label className="mt-2 block font-medium text-slate-700">Reason (required)
              <textarea className="input mt-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="archive-reason" /></label>
            {err && <div className="mt-1 text-rose-700" role="alert" data-testid="archive-error">{err}</div>}
            <div className="mt-2 flex justify-end gap-2">
              <button className="btn-secondary" onClick={() => setOpen(false)} data-testid="archive-cancel">Cancel</button>
              <button className="btn-primary" disabled={reason.trim().length < 5} onClick={submit} data-testid="archive-confirm">{archived ? "Restore" : "Archive"}</button>
            </div>
          </div>
        )}
      </div>
    </Gated>
  );
}
