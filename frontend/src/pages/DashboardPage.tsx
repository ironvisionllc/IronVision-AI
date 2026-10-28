import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { PageHeader, Panel } from "@/components/common/Panel";
import { STEP_STATUS, useActiveSystemId, useRmfSteps } from "@/components/rmf/Stepper";
import { NeedSystem } from "@/components/common/Bits";
import { StatusChip } from "@/components/common/StatusChip";
import { recentVisits } from "@/components/shell/Recent";
import { GuidedPanel } from "@/components/common/Guided";
import { useSystems } from "@/context/SystemContext";
import { useAuth } from "@/context/AuthContext";
import { useApi, Row } from "@/lib/useApi";
import { cn } from "@/lib/format";

const ROLES: Record<string, string> = { prepare: "System Owner, ISSO", categorize: "ISSO → AO", select: "ISSO → ISSM", implement: "ISSO, System Owner, CCP",
  assess: "SCA", authorize: "ISSM → AO", monitor: "ISSO, ISSM" };
const WAITS: Record<string, string[]> = { categorize: ["ao"], select: ["issm"], assess: ["sca"], authorize: ["issm", "ao"] };

function Readiness({ sid }: { sid: string }) {
  const { data } = useApi<Row>(`/systems/${sid}/documents/ssp/check`);
  const miss: string[] = data?.missing || [];
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3" data-testid="dash-readiness">
      <div className="font-semibold">Readiness for authorization</div>
      {!data ? <div className="text-[12px] text-slate-500">Checking…</div> : miss.length === 0 ? <div className="mt-1 text-[12px] text-emerald-700">No blockers in the SSP check.</div> : <>
        <div className="mt-1 text-[12px]" data-testid="dash-readiness-count">{miss.length} blocker(s)</div>
        <ul className="mt-1 list-disc pl-4 text-[12px] text-slate-700">{miss.slice(0, 4).map((m) => <li key={m}>{m}</li>)}</ul></>}
      <Link className="mt-2 inline-block text-[12px] text-blue-800 underline" to="/rmf/authorize" data-testid="dash-readiness-open">Package & documents →</Link>
    </div>);
}

export default function DashboardPage() {
  const sid = useActiveSystemId();
  const { systems } = useSystems();
  const { user } = useAuth();
  const { data } = useRmfSteps(sid);
  const { data: rev } = useApi<Row>(sid ? "/reviews" : null, { status: "pending" });
  if (!sid) return <NeedSystem />;
  const s = systems.find((x) => x.id === sid) as Row | undefined;
  const pending = (rev?.items || []).filter((r: Row) => r.system_id === sid);
  const last = recentVisits((user || null)?.id)[0];
  const waitingOn = (k: string) => pending.filter((r: Row) => (WAITS[k] || []).includes(r.assigned_role));
  return (
    <div data-testid="dashboard-page">
      <PageHeader title={s?.name ?? "System"} subtitle={`${s?.acronym ?? ""} · ${(s?.categorization || "not categorized").toString()} · ${s?.categorization_mode === "cnssi1253" ? "CNSSI 1253" : "FIPS 199"}`}>
        <StatusChip dim="authorization" v={s?.authorization_status ?? s?.ato_status} testId="dash-authorization" /></PageHeader>
      <GuidedPanel step="prepare" />
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl p-4 text-white" style={{ background: "linear-gradient(135deg,#0f4f5f,#1B839F)" }} data-testid="dash-continue">
        <div className="min-w-0 flex-1"><div className="text-[11px] uppercase tracking-wide opacity-80">Continue where you left off</div>
          <div className="text-[15px] font-semibold">{last ? last.label : "Nothing opened yet on this browser"}</div>
          {data?.next_action && <div className="text-[12px] opacity-90">Recommended next: {data.next_action.label}</div>}</div>
        {last ? <Link className="btn border-white bg-white text-[#0f4f5f] hover:bg-sky-50" style={{ background: "#fff", color: "#0f4f5f" }} to={last.path} data-testid="dash-continue-btn">Resume →</Link>
          : data?.next_action && <Link className="btn border-white" style={{ background: "#fff", color: "#0f4f5f" }} to={data.next_action.link} data-testid="dash-continue-btn">{data.next_action.label} →</Link>}
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" data-testid="dash-steps">
        {(data?.steps || []).map((st: Row) => {
          const w = waitingOn(st.key);
          const status = st.status !== "complete" && w.length ? "awaiting" : st.status;
          return (
            <div key={st.key} className="rounded-xl border border-slate-200 bg-white p-3" data-testid={`dash-step-${st.key}`} data-status={status}>
              <div className="flex items-center gap-2"><span className={cn("h-2.5 w-2.5 rounded-full", STEP_STATUS[status].dot)} aria-hidden /><b>{st.number} · {st.label}</b>
                <span className={cn("ml-auto rounded border px-1.5 text-[11px]", STEP_STATUS[status].chip)} data-testid={`dash-step-status-${st.key}`}>{STEP_STATUS[status].label}</span></div>
              <div className="mt-2 text-[12px] text-slate-700">{st.summary}</div>
              {st.progress && <div className="mt-1 text-[11px] text-slate-500">{st.progress}</div>}
              <div className="mt-1 text-[11px] text-slate-500">{w.length ? `Awaiting: ${w.map((r: Row) => r.assigned_role.toUpperCase()).join(", ")} (${w.length})` : "No pending approvals"} · Roles: {ROLES[st.key]}</div>
              {st.status !== "complete" && <Link className="btn-primary mt-2 inline-flex items-center gap-1 !py-1 text-[12px]" to={st.next_action.link} data-testid={`dash-step-next-${st.key}`}>{st.next_action.label}<ArrowRight className="h-3 w-3" /></Link>}
              {st.status === "complete" && <Link className="btn-secondary mt-2 inline-flex !py-1 text-[12px]" to={st.next_action.link}>View</Link>}
            </div>);
        })}
        <Readiness sid={sid} />
      </div>
      <Panel title={`Pending approvals for this system (${pending.length})`} className="mt-4" testId="dash-pending">
        {pending.length === 0 ? <div className="text-[12px] text-slate-500">Nothing is waiting for approval.</div>
          : <ul className="text-[12px]">{pending.slice(0, 8).map((r: Row) => <li key={r.id} className="border-b border-slate-100 py-1"><Link className="text-blue-800 underline" to={`/reviews/${r.id}`}>{r.title || r.kind}</Link> – waiting for {String(r.assigned_role).toUpperCase()}</li>)}</ul>}
      </Panel>
    </div>);
}
