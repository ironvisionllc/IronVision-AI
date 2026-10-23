import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { useActiveSystemId } from "@/components/rmf/Stepper";
import { showNextStep } from "@/components/common/NextStep";

export const PROCESSED_EVENT = "iv:processed";
export const PROCESSING_STARTED = "iv:processing-started";

/** Upload processing state for the active system; polls every 3 s while anything is processing, else every 60 s. */
export function useProcessing(sid: string | null) {
  const [data, setData] = useState<Row | null>(null);
  const load = useCallback(() => { if (sid) api.get<Row>(`/systems/${sid}/processing`).then((r) => setData(r.data)).catch(() => undefined); }, [sid]);
  useEffect(() => {
    load();
    const t = setInterval(load, data?.active ? 3000 : 60000);
    window.addEventListener(PROCESSING_STARTED, load);
    return () => { clearInterval(t); window.removeEventListener(PROCESSING_STARTED, load); };
  }, [load, data?.active]);
  return { data, load };
}

const nextFor = (i: Row, sid: string) => i.kind === "policy"
  ? { label: "review its control mappings and coverage", to: `/policy-auditor/${i.id}` }
  : { label: "review the new mappings in Mapping Review", to: "/mapping-review" };

/** App-wide: when an upload finishes (or fails) show a toast with the summary + Next step and refresh every screen. */
export function ProcessingWatcher() {
  const sid = useActiveSystemId();
  const { data } = useProcessing(sid);
  const prev = useRef<Record<string, string> | null>(null);
  useEffect(() => {
    if (!data || !sid) return;
    const now = Object.fromEntries(data.items.map((i: Row) => [i.id, i.state]));
    if (prev.current) {
      for (const i of data.items as Row[]) {
        if (!["queued", "processing"].includes(prev.current[i.id]) || ["queued", "processing"].includes(i.state)) continue;
        const name = i.title || i.file_name;
        if (i.state === "failed") toast.error(`“${name}” failed: ${i.reason || "unknown error"}`, { duration: 15000 });
        else {
          toast.success(`“${name}” analysed: ${i.summary?.text || "done"}`, { duration: 10000 });
          showNextStep({ message: `“${name}” analysed – ${i.summary?.text || "done"}.`, ...nextFor(i, sid) });
        }
        window.dispatchEvent(new Event(PROCESSED_EVENT));
      }
    }
    prev.current = now;
  }, [data, sid]);
  return null;
}

const BADGE: Record<string, string> = { queued: "bg-slate-200 text-slate-800", processing: "bg-blue-100 text-blue-800", analysed: "bg-emerald-100 text-emerald-800", failed: "bg-rose-100 text-rose-800" };

export function ProcessingBadge({ i }: { i: Row }) {
  const label = i.state === "queued" ? "Queued – waiting for the worker" : i.state === "processing" ? "Processing…" : i.state === "analysed" ? "Analysed" : `Failed${i.reason ? ` (${i.reason})` : ""}`;
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${BADGE[i.state] || "bg-slate-100"}`} data-testid={`processing-badge-${i.id}`}>{label}</span>;
}

/** Recent uploads with their processing badge, summary and a Retry button for failed ones. */
export function ProcessingList({ sid }: { sid: string }) {
  const { data, load } = useProcessing(sid);
  const [msg, setMsg] = useState("");
  const retry = async (i: Row) => {
    try { await api.post(i.kind === "policy" ? `/policies/${i.id}/reanalyze` : `/ingest-runs/${i.id}/retry`); setMsg(`Retrying “${i.title || i.file_name}”…`); load(); window.dispatchEvent(new Event(PROCESSING_STARTED)); }
    catch (e) { setMsg(errorMessage(e)); }
  };
  if (!data?.items.length) return null;
  return (
    <div className="mt-3" data-testid="processing-list">
      <div className="mb-1 text-[12px] font-medium text-slate-700">Recent uploads {data.active ? `· ${data.active} processing` : ""}</div>
      {msg && <div className="mb-1 text-[11px] text-slate-600" role="status">{msg}</div>}
      <ul className="text-[12px]">{data.items.slice(0, 8).map((i: Row) => <li key={i.id} className="flex flex-wrap items-center gap-2 border-t border-slate-100 py-1" data-testid={`processing-item-${i.id}`}>
        <ProcessingBadge i={i} /><span className="font-medium">{i.title || i.file_name}</span>
        {i.summary && <span className="text-[11px] text-slate-600">{i.summary.text}</span>}
        {i.state === "failed" && <button className="btn-secondary px-1.5 py-0.5 text-[10px]" onClick={() => retry(i)} data-testid={`processing-retry-${i.id}`}>Retry</button>}
      </li>)}</ul>
    </div>);
}
