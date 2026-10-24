export function SourceBadge({ label, collector }: { label: string; collector?: string | null }) {
  const mocked = label === "MOCKED source";
  return <span className={`rounded px-1 text-[10px] font-semibold ${mocked ? "bg-rose-600 text-white" : "bg-slate-100 text-slate-700"}`} data-testid={mocked ? "mocked-badge" : "source-badge"}>
    {label}{collector ? ` · ${collector}` : ""}</span>;
}
