import { useState } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Row, useApi } from "@/lib/useApi";

/** Export Test Plan: every procedure of the selected controls in the importer's eMASS-style layout (re-imports cleanly). */
export function TestPlanExport({ sid }: { sid: string }) {
  const { data, error } = useApi<Row>(`/systems/${sid}/test-plan/export/summary`);
  const [busy, setBusy] = useState(false);
  if (error) return null;  // role without Test Plan access
  const download = async () => {
    setBusy(true);
    try {
      const r = await api.get(`/systems/${sid}/test-plan/export`, { responseType: "blob" });
      const name = /filename="([^"]+)"/.exec(r.headers["content-disposition"] || "")?.[1] || "TestPlan.xlsx";
      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(r.data), download: name });
      a.click(); URL.revokeObjectURL(a.href);
      toast.success(`Exported ${r.headers["x-row-count"]} procedure(s) – ${name}`);
    } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };
  return (<div className="mt-3 flex flex-wrap items-center gap-2 border-t border-blue-100 pt-3" data-testid="tp-export">
    <button className="btn-secondary" disabled={busy || !data?.rows} onClick={download} data-testid="tp-export-btn"><Download className="h-4 w-4" aria-hidden />Export Test Plan</button>
    <span className="text-[12px] text-slate-600" data-testid="tp-export-count">
      {data ? <><b>{data.rows}</b> procedure(s) across {data.controls} selected control(s){data.inherited ? `, ${data.inherited} inherited procedure(s)` : ""}</> : "…"}
    </span>
    <p className="w-full text-[11px] text-slate-500" data-testid="tp-export-note">Includes every control × CCI procedure of the selected controls (not tailored-out or withdrawn), with procedures, test method, inherited flag and SCA-approved results. {data?.label}.</p>
  </div>);
}
