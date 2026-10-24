import { fmtControl } from "@/lib/format";
import { TableScroll } from "@/components/common/TableScroll";
import { ReactNode, useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { ControlDetail } from "@/lib/types";
import { BaselinePill, StatusPill } from "@/components/common/StatusPill";

interface Props {
  controlId: string | null;
  onClose: () => void;
  onNavigate: (id: string) => void;
}

function Section({ title, count, children, testId }: { title: string; count?: number; children: ReactNode; testId: string }) {
  return (
    <section className="border-b border-slate-200 px-6 py-5" data-testid={testId}>
      <h3 className="eyebrow mb-3">{title}{count !== undefined && <span className="ml-2 font-mono text-slate-400">{count}</span>}</h3>
      {children}
    </section>
  );
}

export function ControlDetailDrawer({ controlId, onClose, onNavigate }: Props) {
  const [detail, setDetail] = useState<ControlDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!controlId) return;
    setDetail(null);
    setError("");
    api.get<ControlDetail>(`/controls/${controlId}`).then((r) => setDetail(r.data)).catch((e) => setError(errorMessage(e)));
  }, [controlId]);

  return (
    <Dialog.Root open={!!controlId} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="iv-overlay fixed inset-0 z-40" />
        <Dialog.Content className="animate-drawer-in fixed right-0 top-0 z-50 flex h-full w-full max-w-3xl flex-col border-l border-slate-200 bg-surface shadow-2xl focus:outline-none" data-testid="control-detail-drawer">
          <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-6 py-5">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-semibold text-blue-800" data-testid="control-detail-id">{detail?.label ?? controlId}</span>
                {detail?.is_enhancement && <StatusPill tone="info">Enhancement of {fmtControl(detail.parent_control_id)}</StatusPill>}
                {detail?.is_withdrawn && <StatusPill tone="neutral">Withdrawn</StatusPill>}
                {detail?.baselines.map((b) => <BaselinePill key={b} baseline={b} />)}
              </div>
              <Dialog.Title className="t-title mt-1 text-slate-900" data-testid="control-detail-title">{detail?.title ?? "Loading…"}</Dialog.Title>
              <Dialog.Description className="text-[12px] text-slate-500">{detail ? `${detail.family_id.toUpperCase()} · ${detail.family_title} · ${detail.source}` : ""}</Dialog.Description>
            </div>
            <Dialog.Close className="btn-secondary px-2 py-1" data-testid="control-detail-close-btn" aria-label="Close"><X className="h-4 w-4" /></Dialog.Close>
          </header>
          <div className="flex-1 overflow-y-auto">
            {error && <div className="p-6 text-sm text-rose-700" role="alert">{error}</div>}
            {detail && <DetailBody d={detail} onNavigate={onNavigate} />}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function DetailBody({ d, onNavigate }: { d: ControlDetail; onNavigate: (id: string) => void }) {
  return (
    <>
      <Section title="Control statement" testId="control-detail-statement">
        <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-slate-800">{d.statement ?? "No statement (withdrawn or incorporated elsewhere)."}</pre>
      </Section>
      <Section title="Parameters (ODPs)" count={d.parameters?.length ?? 0} testId="control-detail-parameters">
        {d.parameters?.length ? (
          <TableScroll><table className="w-full border-collapse"><tbody>
            {d.parameters.map((p) => (
              <tr key={p.id}><td className="td w-40 font-mono text-[11px] text-slate-500">{p.id}</td><td className="td">{p.rendered ?? p.label}</td></tr>
            ))}
          </tbody></table></TableScroll>
        ) : <p className="text-sm text-slate-500">None.</p>}
      </Section>
      {d.guidance && (
        <Section title="Discussion / guidance" testId="control-detail-guidance">
          <p className="text-[13px] leading-relaxed text-slate-700">{d.guidance}</p>
        </Section>
      )}
      <Section title="SP 800-53A assessment objectives" count={d.objectives.length} testId="control-detail-objectives">
        <ul className="space-y-1">
          {d.objectives.filter((o) => o.prose).map((o) => (
            <li key={o.objective_id} className="flex gap-2 text-[13px] text-slate-700" style={{ paddingLeft: `${Math.max(0, o.depth - 1) * 16}px` }}>
              <span className="w-28 shrink-0 font-mono text-[11px] text-slate-500">{o.label}</span><span>{o.prose}</span>
            </li>
          ))}
        </ul>
        {d.assessment_methods && d.assessment_methods.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {d.assessment_methods.map((m, i) => <StatusPill key={i} tone="neutral">{m.method ?? "method"}</StatusPill>)}
          </div>
        )}
      </Section>
      <Section title="Mapped CCIs (DISA, Rev 5 references)" count={d.ccis.length} testId="control-detail-ccis">
        {d.ccis.length ? (
          <TableScroll><table className="w-full border-collapse">
            <thead><tr><th className="th w-28">CCI</th><th className="th w-28">Reference</th><th className="th">Definition</th><th className="th w-32">Review</th></tr></thead>
            <tbody>
              {d.ccis.map((c) => (
                <tr key={`${c.cci_id}-${c.reference_index}`}>
                  <td className="td font-mono text-[12px]">{c.cci_id}</td>
                  <td className="td font-mono text-[11px] text-slate-500">{c.reference_index}</td>
                  <td className="td">{c.definition}</td>
                  <td className="td"><StatusPill tone={c.review_status === "source_asserted" ? "info" : "warning"}>{c.review_status.replace("_", " ")}</StatusPill></td>
                </tr>
              ))}
            </tbody>
          </table></TableScroll>
        ) : <p className="text-sm text-slate-500">No CCIs reference this control in the pinned CCI list.</p>}
      </Section>
      {d.enhancements.length > 0 && (
        <Section title="Enhancements" count={d.enhancements.length} testId="control-detail-enhancements">
          <ul className="grid gap-1 sm:grid-cols-2">
            {d.enhancements.map((e) => (
              <li key={e.control_id}>
                <button type="button" onClick={() => onNavigate(e.control_id)} data-testid={`enhancement-link-${e.control_id}`}
                  className="w-full rounded px-2 py-1 text-left text-[13px] text-slate-700 transition-colors duration-100 hover:bg-blue-50 hover:text-blue-900">
                  <span className="mr-2 font-mono text-[12px] font-semibold text-blue-800">{e.label}</span>
                  <span className={e.is_withdrawn ? "text-slate-400 line-through" : ""}>{e.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <div className="px-6 py-4 font-mono text-[11px] text-slate-400" data-testid="control-detail-provenance">
        provenance: catalog_version={String(d.provenance?.catalog_version_id ?? "—")} · sha256={String(d.provenance?.sha256 ?? "—").slice(0, 16)}…
      </div>
    </>
  );
}
