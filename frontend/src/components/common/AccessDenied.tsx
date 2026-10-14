import { useState } from "react";
import { Lock } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { Denied, ROLE_LABEL } from "@/lib/api";

const PREFERRED = ["issm", "ao", "leadership_viewer", "isso", "sca", "system_owner", "devsecops", "platform_admin"];

export function AccessDenied({ denied, area }: { denied: Denied; area: string }) {
  const { user: u, actAs } = useAuth();
  const user = u || null;
  const [busy, setBusy] = useState("");
  const roles = PREFERRED.filter((r) => denied.roles.includes(r)).slice(0, 3);
  const acting = ROLE_LABEL[user?.persona_role ?? ""] ?? "role";
  const names = roles.map((r) => ROLE_LABEL[r] ?? r);
  const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}` : names[0];
  return (
    <div className="panel p-6" role="status" data-testid="access-denied">
      <div className="flex items-center gap-2 t-title text-slate-900"><Lock className="h-4 w-4" />{user?.is_sandbox ? `Your acting role (${acting}) can't view ${area}` : "You don't have access"}</div>
      {user?.is_sandbox ? <>
        <p className="mt-1 text-[13px] text-slate-600">{roles.length ? `Switch to ${list} to view it.` : "No sandbox persona can view this."}</p>
        <div className="mt-3 flex flex-wrap gap-2">{roles.map((r) => (
          <button key={r} className="btn-primary" disabled={!!busy} data-testid={`access-switch-${r}`}
            onClick={async () => { setBusy(r); try { await actAs(r); } finally { setBusy(""); } }}>{busy === r ? "Switching…" : `Switch to ${ROLE_LABEL[r] ?? r}`}</button>))}</div>
      </> : <p className="mt-1 text-[13px] text-slate-600">{area} isn't available to your account. Ask your administrator if you need access.</p>}
    </div>
  );
}
