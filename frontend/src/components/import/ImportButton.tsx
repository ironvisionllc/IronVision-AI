import { Link } from "react-router-dom";
import { Upload } from "lucide-react";

/** Replaces the scattered upload buttons: opens the Import Center pre-set to this system and type. */
export function importCenterHref(systemId?: string | null, type?: string) {
  const base = systemId ? `/systems/${systemId}/import-center` : "/import-center";
  return type ? `${base}?type=${encodeURIComponent(type)}` : base;
}

export function ImportButton({ systemId, type, label = "Import…", testId, primary }: { systemId?: string | null; type?: string; label?: string; testId: string; primary?: boolean }) {
  return (
    <Link className={`${primary ? "btn-primary" : "btn-secondary"} inline-flex items-center gap-1.5`} to={importCenterHref(systemId, type)} data-testid={testId}
      title="Opens the Import Center – one place for every import">
      <Upload className="h-4 w-4" aria-hidden />{label}</Link>);
}
