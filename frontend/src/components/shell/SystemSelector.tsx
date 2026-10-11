import { Server } from "lucide-react";
import { useSystems } from "@/context/SystemContext";

export function SystemSelector() {
  const { systems, loaded, selectedId, select } = useSystems();
  const empty = loaded && systems.length === 0;

  return (
    <div className="border-b px-4 py-4" style={{ borderColor: "var(--iv-sb-border)" }} data-testid="system-selector">
      <label htmlFor="system-select" className="t-label iv-sb-muted mb-1.5 flex items-center gap-1.5 !text-[10px]">
        <Server className="h-3 w-3" aria-hidden /> Active system
      </label>
      <select id="system-select" data-testid="system-selector-select" disabled={empty || !loaded} value={selectedId}
        onChange={(e) => select(e.target.value)} className="input py-1.5 text-[13px]">
        {!loaded && <option value="">Loading…</option>}
        {empty && <option value="">No systems registered</option>}
        {systems.length > 0 && <option value="">Select a system…</option>}
        {systems.map((s) => (
          <option key={s.id} value={s.id}>{s.acronym ? `${s.acronym} – ${s.name}` : s.name}</option>
        ))}
      </select>
      {empty && <p className="iv-sb-muted mt-2 text-[11px] leading-snug" data-testid="system-selector-empty">Register a system on the Systems page.</p>}
    </div>
  );
}
