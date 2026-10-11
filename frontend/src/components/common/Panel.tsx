import { ReactNode } from "react";
import { cn } from "@/lib/format";

interface Props {
  title?: string;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
}

export function Panel({ title, eyebrow, actions, children, className, testId }: Props) {
  return (
    <section className={cn("panel animate-fade-up", className)} data-testid={testId}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-4 border-b px-5 py-3.5" style={{ borderColor: "var(--iv-border)" }}>
          <div>
            {eyebrow && <div className="eyebrow">{eyebrow}</div>}
            {title && <h2 className="font-heading text-[15px] font-semibold tracking-tight text-slate-900">{title}</h2>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="t-headline text-slate-900" data-testid="page-title">{title}</h1>
        {subtitle && <p className="t-caption mt-1.5 max-w-3xl text-slate-600">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}
