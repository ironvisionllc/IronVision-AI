import { ReactNode } from "react";
import { AlertOctagon, AlertTriangle, CheckCircle2, Circle, Clock3, Info, PencilLine, XCircle } from "lucide-react";
import { cn } from "@/lib/format";

/** IronVision status categories: Draft=gold · Under Review=brand · Approved=emerald · Failed=red · Critical=coral · Warning=gold · Informational=teal. */
export type Tone = "success" | "warning" | "critical" | "failed" | "info" | "review" | "draft" | "neutral" | "primary";

const TONES: Record<Tone, string> = {
  success: "bg-emerald-50 text-emerald-800 border-emerald-200",
  warning: "bg-amber-50 text-amber-800 border-amber-300",
  draft: "bg-amber-50 text-amber-900 border-amber-300 border-dashed",
  critical: "bg-rose-50 text-rose-700 border-rose-300",
  failed: "bg-rose-100 text-rose-800 border-rose-400",
  info: "bg-sky-50 text-sky-800 border-sky-200",
  review: "bg-blue-100 text-blue-800 border-blue-300",
  primary: "bg-blue-100 text-blue-800 border-blue-300",
  neutral: "bg-slate-100 text-slate-700 border-slate-300",
};

const ICONS: Record<Tone, typeof Info> = {
  success: CheckCircle2, warning: AlertTriangle, draft: PencilLine, critical: AlertOctagon, failed: XCircle,
  info: Info, review: Clock3, primary: Clock3, neutral: Circle,
};

export function StatusPill({ tone, children, dot = false, testId, prefix }: { tone: Tone; children: ReactNode; dot?: boolean; testId?: string; prefix?: string }) {
  const Icon = ICONS[tone];
  return (
    <span data-testid={testId} className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-4 whitespace-nowrap", TONES[tone])}>
      {dot && <Icon className="h-3 w-3 shrink-0" aria-hidden strokeWidth={2.4} />}
      {prefix && <span className="text-[9px] font-bold uppercase tracking-wider opacity-75">{prefix}: </span>}
      {children}
    </span>
  );
}

const BASELINE_TONE: Record<string, Tone> = { low: "success", moderate: "warning", high: "critical", privacy: "info" };

export function BaselinePill({ baseline }: { baseline: string }) {
  return <StatusPill tone={BASELINE_TONE[baseline] ?? "neutral"}>{baseline.toUpperCase()}</StatusPill>;
}
