import { AlertTriangle } from "lucide-react";

export const SYNTHETIC_TEXT = "SYNTHETIC DEMONSTRATION DATA – NOT FOR CUI/CLASSIFIED/OPERATIONAL DATA";
// Build-time environment label (staging builds: REACT_APP_ENV_LABEL=staging).
const ENV_LABEL = (process.env.REACT_APP_ENV_LABEL || "").toLowerCase();

export function SyntheticBanner() {
  return (
    <div role="note" data-testid="synthetic-data-banner" aria-label={SYNTHETIC_TEXT} title={SYNTHETIC_TEXT}
      className="iv-banner flex h-6 shrink-0 items-center justify-center gap-1.5 overflow-hidden whitespace-nowrap px-3 text-center font-heading text-[10px] font-bold uppercase leading-none tracking-[0.12em]">
      <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden />
      {ENV_LABEL === "staging" && <span data-testid="staging-banner-label">STAGING – SYNTHETIC DATA · </span>}
      <span className="hidden md:inline">{SYNTHETIC_TEXT}</span>
      <span className="md:hidden" aria-hidden>SYNTHETIC DATA – NOT FOR CUI/CLASSIFIED</span>
    </div>
  );
}
