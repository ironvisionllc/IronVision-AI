import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import { cn } from "@/lib/format";
import logo from "@/assets/brand/logo.svg";
import logoMono from "@/assets/brand/logo-mono.svg";

export const PRODUCT_NAME = "IronVision AI";
export const TAGLINE = "Intelligent Risk. Continuous Assurance.";

/** Uses the single swappable brand files in src/assets/brand/ (logo.svg / logo-mono.svg). */
export function BrandMark({ className, variant = "auto" }: { className?: string; variant?: "auto" | "color" | "mono" }) {
  const { theme } = useTheme();
  const mono = variant === "mono" || (variant === "auto" && theme === "dark");
  return <img src={mono ? logoMono : logo} alt={`${PRODUCT_NAME} logo`} className={cn("shrink-0 select-none", className ?? "h-8 w-8")} draggable={false} data-testid="brand-logo" />;
}

export function Wordmark({ className }: { className?: string }) {
  return <span className={cn("font-heading font-extrabold tracking-tight", className)}>IronVision <span className="iv-wordmark-ai">AI</span></span>;
}

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button type="button" onClick={toggle} className={cn("btn-ghost px-2 py-1.5", className)} data-testid="theme-toggle-btn"
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} title={dark ? "Light theme" : "Dark theme"} aria-pressed={dark}>
      {dark ? <Sun className="h-4 w-4" aria-hidden /> : <Moon className="h-4 w-4" aria-hidden />}
    </button>
  );
}
