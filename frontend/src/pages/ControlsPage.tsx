import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ContentStats } from "@/lib/types";
import { PageHeader } from "@/components/common/Panel";
import { cn } from "@/lib/format";
import { StatsStrip } from "@/components/controls/StatsStrip";
import { ControlsTable } from "@/components/controls/ControlsTable";
import { ContentVersionsPanel } from "@/components/controls/ContentVersionsPanel";
import { Link } from "react-router-dom";
import { useSystems } from "@/context/SystemContext";

function NoSystemHint() {
  const { systems, loaded } = useSystems();
  if (!loaded || systems.length > 0) return null;
  return (
    <div className="panel mb-5 flex flex-wrap items-center gap-3 border-blue-200 bg-blue-50 p-4 text-[13px] text-slate-700" data-testid="controls-no-system">
      <div><b>No system yet.</b> The Control Workbench – where you set status, write implementation statements and attach evidence – opens once you register the system you are seeking an ATO for.</div>
      <Link to="/systems/new" className="btn-primary ml-auto" data-testid="controls-register-system">Register your first system</Link>
    </div>);
}

const TABS = [
  { id: "catalog", label: "Catalog" },
  { id: "versions", label: "Content versions" },
] as const;

export default function ControlsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("catalog");
  const [stats, setStats] = useState<ContentStats | null>(null);

  useEffect(() => {
    api.get<ContentStats>("/content/stats").then((r) => setStats(r.data)).catch(() => setStats(null));
  }, []);

  return (
    <div data-testid="controls-page">
      <PageHeader title="Controls Catalog" subtitle="Reference: every NIST SP 800-53 Rev 5 control, its assessment objectives (800-53A), baselines (800-53B) and DISA CCIs. Read-only – your system's own controls live in the Control Workbench." />
      <NoSystemHint />
      <StatsStrip stats={stats} />
      <div className="mb-4 flex gap-1 border-b border-slate-300" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)} data-testid={`controls-tab-${t.id}`}
            className={cn("-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors duration-150",
              tab === t.id ? "border-blue-700 text-blue-800" : "border-transparent text-slate-600 hover:text-slate-900")}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "catalog" ? <ControlsTable /> : <ContentVersionsPanel />}
    </div>
  );
}
