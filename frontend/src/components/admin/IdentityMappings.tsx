import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { api } from "@/lib/api";

interface Mapping {
  user_id: string;
  email: string;
  user_active: boolean;
  issuer: string;
  keycloak_user_id: string;
  mapped_by: string | null;
  mapped_at: string | null;
  reason: string | null;
  last_used_at: string | null;
}

/** Read-only: OIDC identity mappings are created only by the operator CLI (keycloak-migrate / identity-map), never in the UI. */
export function IdentityMappings() {
  const [rows, setRows] = useState<Mapping[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get<Mapping[]>("/admin/identity-mappings").then((r) => setRows(r.data)).catch(() => setErr("Identity mappings could not be loaded."));
  }, []);
  return (
    <section className="panel p-5" data-testid="identity-mappings-panel">
      <h2 className="t-h3 flex items-center gap-2"><KeyRound className="h-4 w-4" aria-hidden /> Sign-in identity mappings</h2>
      <p className="t-caption mt-1 text-slate-600">Each Keycloak identity (issuer + subject) maps to exactly one account. Created by operators with the audited CLI; read-only here.</p>
      {err && <div role="alert" className="mt-3 text-[13px] text-rose-700" data-testid="identity-mappings-error">{err}</div>}
      {rows && rows.length === 0 && <div className="mt-3 text-[13px] text-slate-600" data-testid="identity-mappings-empty">No identities mapped yet.</div>}
      {rows && rows.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-[13px]" data-testid="identity-mappings-table">
            <thead><tr className="text-slate-500"><th className="py-1 pr-3">Account</th><th className="pr-3">Keycloak user</th><th className="pr-3">Mapped by</th><th className="pr-3">Reason</th><th>Last sign-in</th></tr></thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.keycloak_user_id} className="border-t border-slate-200" data-testid={`identity-mapping-row-${m.user_id}`}>
                  <td className="py-1.5 pr-3">{m.email}{!m.user_active && <span className="ml-1 text-slate-500">(inactive)</span>}</td>
                  <td className="pr-3 font-mono text-[12px]" title={m.issuer}>{m.keycloak_user_id}</td>
                  <td className="pr-3">{m.mapped_by ?? "–"}<div className="text-[11px] text-slate-500">{m.mapped_at?.slice(0, 16).replace("T", " ")}</div></td>
                  <td className="pr-3">{m.reason ?? "–"}</td>
                  <td>{m.last_used_at ? m.last_used_at.slice(0, 16).replace("T", " ") : "never"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
