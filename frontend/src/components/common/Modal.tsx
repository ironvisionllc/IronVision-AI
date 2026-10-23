import { ReactNode, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

export function Modal({ title, onClose, children, testId, wide }: { title: string; onClose: () => void; children: ReactNode; testId: string; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    ref.current?.focus();  // mount only: re-focusing on re-render would steal focus from inputs
    const k = (e: KeyboardEvent) => e.key === "Escape" && close.current();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  return createPortal(
    <div className="iv-overlay fixed inset-0 z-50 flex items-start justify-center p-10" data-testid={testId}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
        className={`iv-popover animate-fade-up max-h-[85vh] w-full overflow-y-auto p-6 focus:outline-none ${wide ? "max-w-5xl" : "max-w-2xl"}`}>
        <div className="mb-4 flex items-center justify-between"><h3 className="t-title text-slate-900">{title}</h3>
          <button className="btn-ghost px-1.5 py-1.5" onClick={onClose} aria-label="Close" data-testid={`${testId}-close`}><X className="h-4 w-4" /></button></div>
        {children}
      </div>
    </div>,
    document.body,  // portal: a transformed ancestor (animate-fade-up panels) would otherwise clip a fixed overlay
  );
}
