import { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Horizontal scroll container for wide tables (visible scrollbar; optional sticky first column). */
export function TableScroll({ children, className, stickyFirst, testId }: { children: ReactNode; className?: string; stickyFirst?: boolean; testId?: string }) {
  return <div className={cn("iv-table-scroll", stickyFirst && "iv-sticky-first", className)} data-testid={testId}>{children}</div>;
}
