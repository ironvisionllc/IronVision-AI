import { AlertTriangle } from "lucide-react";

export const SYNTHETIC_TEXT = "SYNTHETIC DEMONSTRATION DATA – NOT FOR CUI/CLASSIFIED/OPERATIONAL DATA";

export function SyntheticBanner() {
  return (
    <div role="note" data-testid="synthetic-data-banner"
      className="iv-banner flex shrink-0 items-center justify-center gap-2 px-4 py-1 text-center font-heading text-[11px] font-bold uppercase tracking-[0.14em]">
      <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
      {SYNTHETIC_TEXT}
    </div>
  );
}
