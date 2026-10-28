import { Link } from "react-router-dom";
import { PageHeader, Panel } from "@/components/common/Panel";
import { useActiveSystemId } from "@/components/rmf/Stepper";
import { useAuth } from "@/context/AuthContext";
import { useSystems } from "@/context/SystemContext";
import { useApi, Row } from "@/lib/useApi";

const ROLE_OF = (u: Row | null): string => {
  const r = u?.persona_role || (u?.roles || []).map((x: Row) => x.role).find((x: string) => ["sca", "ao", "issm", "isso"].includes(x)) || "isso";
  return ["sca", "ao", "issm"].includes(r) ? r : "isso";
};
const INTRO: Record<string, [string, string]> = {
  isso: ["Your work: statements, evidence, imports and findings", "Approve and authorize actions are not shown – they belong to the ISSM and AO (separation of duties)."],
  sca: ["Assessments assigned to you", "Only assessment work is shown – the SCA does not edit implementation statements (independence)."],
  issm: ["Approvals and oversight", "Assessment determinations stay with the SCA; authorization decisions with the AO."],
  ao: ["Decisions waiting for you", "Decisions only. Packages open read-only."],
};

/** Role-based home: review requests assigned to the role + (ISSO) the active system's work queue + notifications. Read-only aggregation of existing endpoints. */
export default function MyWorkPage() {
  const { user } = useAuth();
  const role = ROLE_OF(user as Row | null);
  const sid = useActiveSystemId();
  const { systems } = useSystems();
  const { data: rev } = useApi<Row>("/reviews", { status: "pending", ...(role === "isso" ? {} : { role }) });
  const { data: q } = useApi<Row>(role === "isso" && sid ? `/systems/${sid}/workbench/queue` : null);
  const { data: notes } = useApi<Row>("/notifications");
  const name = (id: string) => (systems.find((s) => s.id === id) as Row | undefined)?.acronym ?? "";
  const reviews: Row[] = (rev?.items || []).filter((r: Row) => role !== "isso" || r.requester_id === (user || null)?.id || !r.assigned_role);
  const items: Row[] = [...(q?.needs_action || []), ...(q?.due_soon || [])].slice(0, 12);
  return (
    <div data-testid="my-work-page" data-role={role}>
      <PageHeader title={`My Work – ${role.toUpperCase()}`} subtitle={INTRO[role][0]} />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[["Waiting for you", role === "isso" ? items.length : reviews.length], ["Pending reviews (yours)", reviews.length], ["Unread notifications", notes?.unread ?? 0], ["Systems", systems.length]].map(([l, v]) =>
          <div key={l} className="rounded-xl border border-slate-200 bg-white p-3"><div className="text-[11px] text-slate-500">{l}</div><div className="text-2xl font-semibold" data-testid={`mywork-stat-${String(l).split(" ")[0].toLowerCase()}`}>{v}</div></div>)}
      </div>
      {role === "isso" && <Panel title={`Next actions${sid ? ` – ${name(sid)}` : ""}`} testId="mywork-queue">
        {!sid ? <div className="text-[12px]">Choose a system in the sidebar.</div> : items.length === 0 ? <div className="text-[12px] text-slate-500">Nothing needs action right now.</div>
          : <ul className="text-[12px]">{items.map((i) => <li key={`${i.kind}-${i.ref}-${i.due ?? ""}`} className="flex items-center gap-2 border-b border-slate-100 py-1.5">
            <span className="rounded bg-slate-100 px-1 text-[10px] uppercase text-slate-600">{i.kind}</span><span className="flex-1 truncate">{i.label ?? i.title ?? i.ref}</span>
            <Link className="btn-secondary !py-0.5 text-[11px]" to={i.link} data-testid={`mywork-open-${i.ref}`}>Open →</Link></li>)}</ul>}
      </Panel>}
      <Panel title={role === "isso" ? "Your review requests" : `Waiting for ${role.toUpperCase()}`} className="mt-4" testId="mywork-reviews">
        {reviews.length === 0 ? <div className="text-[12px] text-slate-500">Nothing pending.</div>
          : <ul className="text-[12px]">{reviews.slice(0, 15).map((r) => <li key={r.id} className="flex items-center gap-2 border-b border-slate-100 py-1.5"><b className="w-14 shrink-0">{name(r.system_id)}</b>
            <span className="flex-1 truncate">{r.title || r.kind}</span><span className="text-[11px] text-slate-500">{String(r.assigned_role || "").toUpperCase()}</span>
            <Link className="btn-secondary !py-0.5 text-[11px]" to={role === "sca" && r.control_id ? `/assess/workspace/${r.control_id}` : `/reviews/${r.id}`} data-testid={`mywork-review-${r.id}`}>Open →</Link></li>)}</ul>}
      </Panel>
      <Panel title="Recent notifications" className="mt-4" testId="mywork-notifications">
        <ul className="text-[12px]">{(notes?.items || []).slice(0, 6).map((n: Row) => <li key={n.id} className="border-b border-slate-100 py-1">{n.link ? <Link className="text-blue-800 underline" to={n.link}>{n.title || n.body}</Link> : (n.title || n.body)}</li>)}</ul>
      </Panel>
      <p className="mt-3 text-[11px] text-slate-500" data-testid="mywork-sod-note">{INTRO[role][1]}</p>
    </div>);
}
