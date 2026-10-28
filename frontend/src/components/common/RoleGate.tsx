import { ReactNode, useEffect, useState } from "react";
import { Lock } from "lucide-react";
import { useLocation } from "react-router-dom";
import { api, getActingLabel, ROLE_LABEL, setDeniedFormatter } from "@/lib/api";
import { Row } from "@/lib/useApi";
import { useAuth } from "@/context/AuthContext";
import { Modal } from "@/components/common/Workflow";

let matrix: Row | null = null;
let pending: Promise<Row> | null = null;
let inited = false;
export function loadRoleMatrix(): Promise<Row> {
  if (!inited && typeof setDeniedFormatter === "function") { inited = true; setDeniedFormatter((perm, roles) => deniedText(perm, roles.length ? roles : undefined)); }
  if (matrix) return Promise.resolve(matrix);
  if (typeof api?.get !== "function") return Promise.resolve({ roles: [], actions: [] });
  pending = pending ?? Promise.resolve(api.get<Row>("/reference/role-matrix")).then((r) => (matrix = r?.data ?? null) ?? { roles: [], actions: [] }).catch(() => { pending = null; return { roles: [], actions: [] }; });
  return pending;
}
export const cachedAction = (perm: string): Row | undefined => matrix?.actions.find((a: Row) => a.permission === perm);

const join = (roles: string[]) => roles.map((r) => ROLE_LABEL[r] ?? r).join(roles.length > 2 ? ", " : " or ").replace(/, ([^,]*)$/, " or $1");
export function deniedText(perm: string, roles?: string[]): string {
  const a = cachedAction(perm);
  const who = roles ?? a?.roles ?? [];
  return `${a?.action ?? `This action (${perm})`} requires ${who.length ? join(who) : "a role you don't have"}${typeof getActingLabel === "function" && getActingLabel() ? ` – you are acting as ${getActingLabel()}` : ""}.`;
}

export const DENIED_EVENT = "iv:denied";
export const showDenied = (perm: string, roles?: string[]) => window.dispatchEvent(new CustomEvent(DENIED_EVENT, { detail: { perm, roles } }));

/** Keeps a permission-gated option visible: disabled, explained on hover, and a click opens the "requires role X" dialog. */
export function Gated({ perm, children, block }: { perm: string; children: ReactNode; block?: boolean }) {
  const { can } = useAuth();
  const [, force] = useState(0);
  useEffect(() => { if (!matrix) loadRoleMatrix().then(() => force((n) => n + 1)); }, []);
  if (can(perm)) return <>{children}</>;
  return (
    <span role="button" tabIndex={0} className={`${block ? "flex" : "inline-flex"} cursor-not-allowed items-center gap-1 iv-dimmed`} title={deniedText(perm)} data-testid={`gated-${perm}`}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); showDenied(perm); }} onKeyDown={(e) => e.key === "Enter" && showDenied(perm)}>
      <fieldset disabled className="pointer-events-none contents">{children}</fieldset><Lock className="h-3 w-3 shrink-0 text-slate-500" aria-label="needs another role" />
    </span>);
}

/** Global dialog for denied actions (from Gated clicks and from backend 403s). Sandbox accounts can switch persona right here. */
export function DeniedDialog() {
  const { user, actAs } = useAuth();
  const [d, setD] = useState<{ perm: string; roles?: string[] } | null>(null);
  const { pathname } = useLocation();
  useEffect(() => setD(null), [pathname]);  // a denial belongs to the screen that raised it
  useEffect(() => {
    loadRoleMatrix();
    const on = (e: Event) => { loadRoleMatrix().then(() => setD((e as CustomEvent).detail)); };
    window.addEventListener(DENIED_EVENT, on);
    return () => window.removeEventListener(DENIED_EVENT, on);
  }, []);
  if (!d) return null;
  const roles: string[] = d.roles ?? cachedAction(d.perm)?.roles ?? [];
  const sandboxRoles = roles.filter((r) => r !== "platform_admin");
  return (
    <Modal title="This needs a different role" onClose={() => setD(null)} testId="denied-dialog">
      <p className="text-[13px] text-slate-800" data-testid="denied-text">{deniedText(d.perm, roles)}</p>
      {user && user.is_sandbox && sandboxRoles.length > 0 ? <div className="mt-3 text-[12px]"><div className="mb-1 text-slate-600">Sandbox: switch role to continue</div>
        <div className="flex flex-wrap gap-2">{sandboxRoles.map((r) => <button key={r} className="btn-primary px-2.5 py-1 text-[12px]" data-testid={`denied-switch-${r}`}
          onClick={async () => { await actAs(r); setD(null); }}>Switch role to {ROLE_LABEL[r] ?? r}</button>)}</div></div>
        : <p className="mt-2 text-[12px] text-slate-600">Ask your ISSM or administrator to assign you one of these roles for this system. <a className="underline" href="/help">Who can do what</a></p>}
    </Modal>);
}
