import { Children, ReactNode, useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

const narrow = () => typeof window !== "undefined" && window.matchMedia?.("(max-width: 639px)").matches;

/** Page/panel actions: whole buttons wrap to the next line; on phones the first action stays and the rest sit one click away in "More ▾". */
export function ActionBar({ children, testId = "action-bar" }: { children: ReactNode; testId?: string }) {
  const items = Children.toArray(children).filter(Boolean);
  const [small, setSmall] = useState(narrow());
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { const f = () => setSmall(narrow()); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f); }, []);
  useEffect(() => {
    if (!open) return;
    const f = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", f); return () => document.removeEventListener("mousedown", f);
  }, [open]);
  if (!small || items.length <= 2) return <div className="flex flex-wrap items-center gap-2" data-testid={testId}>{items}</div>;
  return (
    <div ref={ref} className="relative flex flex-wrap items-center gap-2" data-testid={testId}>
      {items[0]}
      <button type="button" className="btn-secondary" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen(!open)} data-testid={`${testId}-more`}>
        More<ChevronDown className="h-4 w-4" aria-hidden /></button>
      {/* kept mounted (hidden) so every action and its test id stays in the DOM; one click shows them */}
      <div role="menu" hidden={!open} className="iv-popover absolute right-0 top-full z-40 mt-1 flex min-w-[14rem] flex-col items-stretch gap-2 p-2" data-testid={`${testId}-menu`}>
        {items.slice(1)}</div>
    </div>);
}
