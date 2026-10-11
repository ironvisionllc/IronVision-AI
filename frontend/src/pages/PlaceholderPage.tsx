import { Clock } from "lucide-react";
import type { NavItem } from "@/lib/nav";
import { PageHeader } from "@/components/common/Panel";

export default function PlaceholderPage({ item }: { item: NavItem }) {
  const Icon = item.icon;
  return (
    <div data-testid={`placeholder-page-${item.id}`}>
      <PageHeader title={item.label} />
      <div className="panel animate-fade-up flex max-w-2xl items-start gap-5 p-8">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-500">
          <Icon className="h-6 w-6" aria-hidden />
        </div>
        <div>
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-sky-300 bg-sky-50 px-2.5 py-0.5 text-[11px] font-semibold text-sky-800" data-testid="placeholder-phase-badge">
            <Clock className="h-3 w-3" aria-hidden /> Coming in Phase {item.phase}
          </div>
          <h2 className="text-lg font-semibold text-slate-900">Not yet built</h2>
          <p className="mt-1 text-sm leading-relaxed text-slate-600">{item.summary}</p>
          <p className="mt-3 text-xs text-slate-500">
            This module is intentionally empty in the current phase. No data, actions, or results are simulated here.
          </p>
        </div>
      </div>
    </div>
  );
}
