import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ContentStats } from "@/lib/types";
import { PageHeader } from "@/components/common/Panel";
import { cn } from "@/lib/format";
import { StatsStrip } from "@/components/controls/StatsStrip";
import { ControlsTable } from "@/components/controls/ControlsTable";
import { ContentVersionsPanel } from "@/components/controls/ContentVersionsPanel";

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
      <PageHeader title="Controls Catalog" subtitle="NIST SP 800-53 Rev 5 with SP 800-53A objectives, SP 800-53B baselines and DISA CCI mappings · read-only" />
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
