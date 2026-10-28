import { DIM_HELP, DIM_LABEL, Dim, lookup } from "@/lib/glossary";

/** The only status chip for the six RMF status dimensions – distinct label, colour and a one-line tooltip everywhere. */
export function StatusChip({ dim, v, showDim, testId }: { dim: Dim; v?: string | null; showDim?: boolean; testId?: string }) {
  const [label, cls] = lookup(dim, v);
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap ${cls}`} title={`${DIM_LABEL[dim]}: ${label} – ${DIM_HELP[dim]}`} data-testid={testId} data-dim={dim} data-value={v ?? ""}>
      {showDim && <span className="opacity-70">{DIM_LABEL[dim]}:</span>}{label}
    </span>);
}
