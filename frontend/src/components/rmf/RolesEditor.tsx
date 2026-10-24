import { HelpCircle } from "lucide-react";
import { Row } from "@/lib/useApi";

export function Help({ text }: { text: string }) {
  return <span title={text} className="inline-flex cursor-help align-middle text-slate-400" aria-label={text}><HelpCircle className="h-3.5 w-3.5" /></span>;
}

/** Key RMF roles: assign an existing user, or a name/e-mail placeholder when the person has no account yet. */
export function RolesEditor({ meta: refData, value, onChange, registration }: { meta: Row | null; value: Row; onChange: (v: Row) => void; registration?: boolean }) {
  const users: Row[] = refData?.users ?? [];
  const set = (k: string, v: Row) => onChange({ ...value, [k]: v });
  return (
    <div className="grid gap-3 md:grid-cols-2" data-testid="roles-editor">
      {(refData?.key_roles ?? []).filter((r: Row) => !registration || r.registration !== false).map((r: Row) => {
        const v = value[r.key] ?? {};
        const mode = v.user_id ? "user" : v.name !== undefined ? "placeholder" : "";
        return (
          <div key={r.key} className="rounded-md border border-slate-200 p-3 text-[12px]" data-testid={`role-${r.key}`}>
            <div className="mb-1 flex items-center gap-1.5 font-medium text-slate-800">{r.label}{r.registration === false && <span className="font-normal text-slate-500" data-testid={`role-${r.key}-not-at-registration`}>(not assigned at registration)</span>} <Help text={r.help} />
              {r.required && <span className="rounded bg-slate-100 px-1 text-[10px] text-slate-600">required</span>}</div>
            <select className="input" value={v.user_id ?? (mode === "placeholder" ? "__ph" : "")} data-testid={`role-${r.key}-user`}
              onChange={(e) => set(r.key, e.target.value === "__ph" ? { name: "", email: "" } : e.target.value ? { user_id: e.target.value } : {})}>
              <option value="">— not assigned —</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
              <option value="__ph">Someone without an account (enter name / e-mail)</option>
            </select>
            {mode === "placeholder" && <div className="mt-2 grid grid-cols-2 gap-2">
              <input className="input" placeholder="Full name" value={v.name ?? ""} onChange={(e) => set(r.key, { ...v, name: e.target.value })} data-testid={`role-${r.key}-name`} />
              <input className="input" placeholder="E-mail (optional)" value={v.email ?? ""} onChange={(e) => set(r.key, { ...v, email: e.target.value })} data-testid={`role-${r.key}-email`} />
            </div>}
          </div>);
      })}
    </div>);
}

export const rolesFromHolders = (roles: Row | null | undefined): Row =>
  Object.fromEntries(Object.entries(roles ?? {}).filter(([, v]) => v).map(([k, v]) => [k, (v as Row).user_id ? { user_id: (v as Row).user_id } : { name: (v as Row).name ?? "", email: (v as Row).email ?? "" }]));
