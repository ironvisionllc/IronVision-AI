import { Link } from "react-router-dom";
import { BookOpen } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/common/Panel";
import { HealthPanel } from "@/components/admin/HealthPanel";
import { RbacDemoPanel } from "@/components/admin/RbacDemoPanel";
import { AiSmokePanel } from "@/components/admin/AiSmokePanel";
import { JobsPanel } from "@/components/admin/JobsPanel";
import { AuditPanel } from "@/components/admin/AuditPanel";
import { RbacMatrixPanel } from "@/components/admin/RbacMatrixPanel";
import { Restricted } from "@/components/admin/Restricted";
import { DemoResetPanel } from "@/components/admin/DemoResetPanel";
import { AdminPhase3Panels } from "@/pages/Phase3Extras";
import { AdminPhase4Panels } from "@/pages/Phase4Pages";

export default function AdminPage() {
  const { can } = useAuth();
  return (
    <div data-testid="admin-page">
      <PageHeader title="Admin" subtitle="Platform health, AI provider check, RBAC enforcement demo and the audit ledger">
        <Link to="/docs-center/digitalocean" className="btn-outline" data-testid="admin-docs-link"><BookOpen className="h-4 w-4" aria-hidden /> Handover Docs</Link>
      </PageHeader>
      <div className="grid gap-5">
        <HealthPanel />
        <div className="grid gap-5 xl:grid-cols-2">
          <RbacDemoPanel />
          {can("admin.ai.test") ? <AiSmokePanel /> : <Restricted title="AI provider smoke test" permission="admin.ai.test" />}
        </div>
        {can("admin.health.read") ? <JobsPanel /> : <Restricted title="Worker jobs" permission="admin.health.read" />}
        {can("audit.read") ? <AuditPanel /> : <Restricted title="Audit events" permission="audit.read" />}
        {can("admin.users.manage") ? <AdminPhase3Panels /> : <Restricted title="Users, security & AI administration" permission="admin.users.manage" />}
        {(can("admin.health.read") || can("risk.admin")) && <AdminPhase4Panels />}
        {can("demo.tools") && <DemoResetPanel />}
        <RbacMatrixPanel />
      </div>
    </div>
  );
}
