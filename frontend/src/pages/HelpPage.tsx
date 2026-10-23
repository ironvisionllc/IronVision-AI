import { useState } from "react";
import { useApi, Row } from "@/lib/useApi";
import { getActingLabel } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, Panel } from "@/components/common/Panel";

/** Action → role matrix generated from the backend RBAC table (same data the server enforces). */
export default function HelpPage() {
  const { data } = useApi<Row>("/reference/role-matrix");
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const rows = (data?.actions ?? []).filter((a: Row) => !q || `${a.action} ${a.description}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div data-testid="help-page">
      <PageHeader title="Help: who can do what" subtitle="Each action and the roles allowed to do it. The server enforces exactly this table; options you can't use stay visible but locked, and clicking them tells you which role is needed." />
      <Panel testId="role-matrix" eyebrow={getActingLabel() ? `You are acting as ${getActingLabel()}` : undefined}
        actions={<input className="input w-64" placeholder="Search actions…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="role-matrix-search" />}>
        <div className="overflow-x-auto"><table className="w-full text-[12px]"><thead><tr className="text-left text-slate-500"><th className="py-1">Action</th>
          {(data?.roles ?? []).map((r: Row) => <th key={r.key} className="px-1 text-center" title={r.label}>{r.label.replace("Information System Security ", "IS ").replace("Platform ", "")}</th>)}<th>You</th></tr></thead>
          <tbody>{rows.map((a: Row) => <tr key={a.permission} className="border-t border-slate-100" data-testid={`matrix-${a.permission}`}>
            <td className="py-1.5 pr-2"><div className="font-medium text-slate-800">{a.action}</div><div className="text-[10px] text-slate-500">{a.permission}</div></td>
            {(data?.roles ?? []).map((r: Row) => <td key={r.key} className="text-center">{a.roles.includes(r.key) ? <span className="text-emerald-700" aria-label="allowed">✓</span> : <span className="text-slate-300" aria-label="not allowed">–</span>}</td>)}
            <td className="text-center">{can(a.permission) ? <span className="text-emerald-700">yes</span> : <span className="text-slate-400">no</span>}</td></tr>)}</tbody></table></div>
        <p className="mt-3 text-[11px] text-slate-500">Separation of duties: the AO decides authorizations and the SCA records assessments; the ISSO cannot do either. Platform administrators manage the app but never hold AO / SCA decision rights.</p>
      </Panel>
    </div>);
}
