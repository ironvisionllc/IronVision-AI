import { Link } from "react-router-dom";
import { Row } from "@/lib/useApi";
import { fmtControl } from "@/lib/format";

/** NSS + PII: the NIST privacy-baseline controls CNSSI 1253 leaves to the Privacy Overlay, with coverage as recorded in the overlay data. */
export function PrivacyOverlayPrompt({ p, onApply }: { p: Row | null | undefined; onApply?: () => void }) {
  if (!p) return null;
  const applied = p.state === "applied";
  return (
    <div className={`mb-3 rounded border p-3 text-[12px] ${applied ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-amber-300 bg-amber-50 text-amber-900"}`} data-testid="privacy-overlay-prompt">
      <b data-testid="privacy-overlay-prompt-message">{p.message}</b>
      {p.pii === "unknown" && <span className="ml-1">(PII answered “Unknown – requires review”.)</span>}
      <details className="mt-1"><summary className="cursor-pointer text-[11px] underline" data-testid="privacy-overlay-prompt-list-toggle">Show the {p.count} controls</summary>
        <ul className="mt-1 max-h-48 overflow-auto text-[11px]" data-testid="privacy-overlay-prompt-list">{p.items.map((i: Row) => <li key={i.control_id}>
          <span className="font-mono">{fmtControl(i.control_id)}</span> {i.title} – <span className={i.covered ? "" : "font-semibold text-rose-800"}>{i.coverage}</span></li>)}</ul></details>
      {!applied && (onApply ? <button className="btn-primary mt-2 px-2 py-0.5 text-[11px]" onClick={onApply} data-testid="privacy-overlay-apply">Apply Privacy Overlay</button>
        : <Link className="btn-primary mt-2 inline-block px-2 py-0.5 text-[11px]" to={p.link} data-testid="privacy-overlay-apply">Apply Privacy Overlay</Link>)}
    </div>);
}
