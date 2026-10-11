import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { api } from "@/lib/api";
import type { RbacMatrix } from "@/lib/types";
import { ROLE_LABELS } from "@/lib/nav";
import { Panel } from "@/components/common/Panel";

export function RbacMatrixPanel() {
  const [m, setM] = useState<RbacMatrix | null>(null);
  useEffect(() => {
    api.get<RbacMatrix>("/rbac/matrix").then((r) => setM(r.data)).catch(() => setM(null));
  }, []);
  if (!m) return null;
  const roles = Object.keys(m.roles);

  return (
    <Panel title="Permission matrix" eyebrow="Authorization layer (independent of authentication provider)" testId="rbac-matrix-panel">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="th">Permission</th>
              {roles.map((r) => <th key={r} className="th text-center">{ROLE_LABELS[r] ?? r}</th>)}
            </tr>
          </thead>
          <tbody>
            {Object.entries(m.permissions).map(([perm, desc]) => (
              <tr key={perm}>
                <td className="td"><div className="font-mono text-[12px] text-slate-800">{perm}</div><div className="text-[11px] text-slate-500">{desc}</div></td>
                {roles.map((r) => (
                  <td key={r} className="td text-center" data-testid={`rbac-cell-${r}-${perm}`}>
                    {m.matrix[r]?.includes(perm) ? <Check className="mx-auto h-4 w-4 text-emerald-600" aria-label="granted" /> : <span className="text-slate-300">·</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
