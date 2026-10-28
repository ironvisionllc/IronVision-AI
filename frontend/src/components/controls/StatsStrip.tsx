import type { ContentStats } from "@/lib/types";

export function StatsStrip({ stats }: { stats: ContentStats | null }) {
  if (!stats) return null;
  if (!stats.loaded) {
    return (
      <div className="panel mb-5 border-amber-300 bg-amber-50 p-4 text-sm text-amber-900" data-testid="content-not-loaded">
        Reference content has not been loaded yet. The worker loads it automatically after seeding.
      </div>
    );
  }
  const b = stats.baselines ?? {};
  const L = stats.counts?.labels;
  const items: [string, number | undefined, string][] = [
    ["Rev 5 catalog (base + enh.)", stats.controls_total, "stat-controls-total"],
    ["Base controls", stats.base_controls, "stat-base-controls"],
    ["Enhancements", stats.enhancements, "stat-enhancements"],
    ["Withdrawn", stats.withdrawn, "stat-withdrawn"],
    ["800-53A objectives", stats.assessment_objectives, "stat-objectives"],
    ["Low / Mod / High", undefined, "stat-baselines"],
    ["CCIs", stats.ccis, "stat-ccis"],
    ["CCI → Rev5 maps", stats.cci_rev5_mappings, "stat-cci-maps"],
  ];
  return (<>
    <div className="panel mb-1 grid grid-cols-2 divide-slate-200 md:grid-cols-4 2xl:grid-cols-8 2xl:divide-x" data-testid="content-stats">
      {items.map(([label, value, id]) => (
        <div key={id} className="px-4 py-3">
          <div className="eyebrow !text-[10px]">{label}</div>
          <div className="mt-1 whitespace-nowrap font-mono text-lg font-semibold text-slate-900" data-testid={id}>
            {id === "stat-baselines" ? `${b.low ?? 0} / ${b.moderate ?? 0} / ${b.high ?? 0}` : value === undefined || value === null ? "…" : value.toLocaleString()}
          </div>
          {id === "stat-baselines" && <div className="text-[10px] text-slate-500">Privacy: {b.privacy ?? 0} · base + enhancements</div>}
        </div>
      ))}
    </div>
    {L && <div className="mb-5 text-[11px] text-slate-600" data-testid="catalog-counts-reconciliation">{L.rev5_total} · {L.selectable}. A system&apos;s count = its baseline (base + enhancements) after overlays and tailoring – see the Control Workbench.</div>}
  </>);
}
