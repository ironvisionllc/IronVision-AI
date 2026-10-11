import { Lock } from "lucide-react";
import { Panel } from "@/components/common/Panel";

export function Restricted({ title, permission }: { title: string; permission: string }) {
  return (
    <Panel title={title} testId={`restricted-${permission.replace(/\./g, "-")}`}>
      <div className="flex items-center gap-3 text-sm text-slate-600">
        <Lock className="h-4 w-4 text-slate-400" aria-hidden />
        Your roles do not grant <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[12px]">{permission}</code>.
      </div>
    </Panel>
  );
}
