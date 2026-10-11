import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { ContentVersion } from "@/lib/types";
import { fmtDate } from "@/lib/format";
import { StatusPill } from "@/components/common/StatusPill";

const TYPE_LABEL: Record<string, string> = { oscal_catalog: "OSCAL catalog", oscal_profile: "OSCAL baseline profile", cci_list: "DISA CCI list" };

export function ContentVersionsPanel() {
  const [rows, setRows] = useState<ContentVersion[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<ContentVersion[]>("/content/versions").then((r) => setRows(r.data)).catch((e) => setError(errorMessage(e)));
  }, []);

  return (
    <div className="panel animate-fade-up" data-testid="content-versions-panel">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-[15px] font-semibold text-slate-900">Pinned reference content</h2>
        <p className="text-[12px] text-slate-500">Each file is vendored in the repository, verified against its pinned SHA-256 before load, and archived to object storage.</p>
      </div>
      {error && <div className="p-4 text-sm text-rose-700" role="alert">{error}</div>}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="th">Content</th><th className="th">Version</th><th className="th">Pin (tag / commit)</th>
              <th className="th">SHA-256</th><th className="th">Effective</th><th className="th text-right">Items</th><th className="th">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows?.map((v) => (
              <tr key={v.id} data-testid={`content-version-row-${v.content_key}`}>
                <td className="td">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{TYPE_LABEL[v.content_type] ?? v.content_type}</div>
                  <div className="font-medium text-slate-800">{v.title}</div>
                  <a href={v.source_url} target="_blank" rel="noreferrer" className="mt-0.5 inline-flex items-center gap-1 break-all text-[11px] text-blue-700 hover:text-blue-900 hover:underline">
                    {v.file_name} <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                  </a>
                </td>
                <td className="td font-mono text-[12px]">{v.version ?? "—"}</td>
                <td className="td font-mono text-[11px]">
                  {v.release_tag ? <><div>{v.release_tag}</div><div className="text-slate-500" title={v.commit_sha ?? ""}>{v.commit_sha?.slice(0, 12)}</div></> : <span className="text-slate-500">direct download</span>}
                </td>
                <td className="td max-w-[220px] break-all font-mono text-[11px] text-slate-600" data-testid={`content-version-sha-${v.content_key}`}>{v.sha256}</td>
                <td className="td font-mono text-[12px]">{v.effective_date ?? "—"}<div className="text-[10px] text-slate-400">loaded {fmtDate(v.loaded_at)}</div></td>
                <td className="td text-right font-mono text-[12px]">{v.item_count?.toLocaleString() ?? "—"}</td>
                <td className="td"><StatusPill tone={v.status === "loaded" ? "success" : "warning"} dot>{v.status}</StatusPill></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
