import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, X } from "lucide-react";

type Next = { message: string; label: string; to: string };
const KEY = "iv:next-step";

/** After a completed action: a confirmation plus a link to the logical next task (survives a page reload). */
export function showNextStep(n: Next) {
  sessionStorage.setItem(KEY, JSON.stringify(n));
  window.dispatchEvent(new Event(KEY));
}

export function NextStepBanner() {
  const [n, setN] = useState<Next | null>(null);
  useEffect(() => {
    const read = () => { const v = sessionStorage.getItem(KEY); setN(v ? JSON.parse(v) : null); };
    read();
    window.addEventListener(KEY, read);
    return () => window.removeEventListener(KEY, read);
  }, []);
  if (!n) return null;
  const close = () => { sessionStorage.removeItem(KEY); setN(null); };
  return (
    <div className="flex items-center gap-3 border-b border-emerald-200 bg-emerald-50 px-5 py-2 text-[13px] text-emerald-900" role="status" data-testid="next-step-banner">
      <CheckCircle2 className="h-4 w-4 shrink-0" />
      <span data-testid="next-step-message">{n.message}</span>
      <Link to={n.to} onClick={close} className="font-semibold underline" data-testid="next-step-link">Next step: {n.label} →</Link>
      <button className="ml-auto" onClick={close} aria-label="Dismiss" data-testid="next-step-dismiss"><X className="h-4 w-4" /></button>
    </div>);
}
