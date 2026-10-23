import type { ReactElement } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { SystemProvider } from "@/context/SystemContext";
import { AppShell } from "@/components/shell/AppShell";
import { ProvisioningGate } from "@/components/shell/Sandbox";
import { NAV_ITEMS } from "@/lib/nav";
import LoginPage from "@/pages/LoginPage";
import ControlsPage from "@/pages/ControlsPage";
import AdminPage from "@/pages/AdminPage";
import DocsCenterPage from "@/pages/DocsCenterPage";
import PlaceholderPage from "@/pages/PlaceholderPage";
import LeadershipPage from "@/pages/LeadershipPage";
import { RegisterSystemPage, SystemsPage } from "@/pages/SystemsPage";
import SystemDetailPage from "@/pages/SystemDetailPage";
import WorkbenchPage from "@/pages/WorkbenchPage";
import { IngestRunPage, LedgerPage, SourcesPage } from "@/pages/EvidencePages";
import { useSystems } from "@/context/SystemContext";
import { PoamDetailPage, PoamListPage } from "@/pages/PoamPages";
import { FindingPage, ReviewDetailPage, ReviewsPage } from "@/pages/ReviewPages";
import { InheritancePage, PolicyAuditorPage, PolicyDetailPage, RmfWorkflowPage } from "@/pages/Phase3Pages";
import CciPage from "@/pages/CciPage";
import { AuditLogPage, AuthorizationPage, NotificationPrefsPage } from "@/pages/Phase3Extras";
import { EmassPage, MappingReviewPage } from "@/pages/Phase4Pages";
import HelpPage from "@/pages/HelpPage";
import { AssessPage, AuthorizePage, CategorizePage, ImplementPage, MonitorPage, PreparePage, SelectPage, TraceabilityPage } from "@/pages/RmfStepPages";
import { Toaster } from "sonner";

function ControlsEntry() {
  const { selectedId, systems, loaded } = useSystems();
  if (!loaded) return null;
  return selectedId && systems.some((s) => s.id === selectedId) ? <Navigate to={`/systems/${selectedId}/controls`} replace /> : <ControlsPage />;
}

function Protected({ children }: { children: ReactElement }) {
  const { user } = useAuth();
  if (user === null) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500" data-testid="auth-loading">
        Verifying session…
      </div>
    );
  }
  if (user === false) return <Navigate to="/login" replace />;
  if (user.is_sandbox && !user.persona_role) return <ProvisioningGate />;
  return children;
}

function Shell() {
  return (
    <SystemProvider>
      <AppShell>
        <Routes>
          <Route path="/" element={<Navigate to="/controls" replace />} />
          <Route path="/controls" element={<ControlsEntry />} />
          <Route path="/catalog" element={<ControlsPage />} />
          <Route path="/portfolio" element={<LeadershipPage />} />
          <Route path="/systems" element={<SystemsPage />} />
          <Route path="/systems/new" element={<RegisterSystemPage />} />
          <Route path="/systems/:id" element={<SystemDetailPage />} />
          <Route path="/systems/:id/controls" element={<WorkbenchPage />} />
          <Route path="/systems/:id/controls/:controlId" element={<WorkbenchPage />} />
          <Route path="/evidence-sources" element={<SourcesPage />} />
          <Route path="/ingest-runs/:id" element={<IngestRunPage />} />
          <Route path="/evidence-ledger" element={<LedgerPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/docs-center" element={<DocsCenterPage />} />
          <Route path="/docs-center/:slug" element={<DocsCenterPage />} />
          <Route path="/poam" element={<Navigate to="/poams" replace />} />
          <Route path="/poams" element={<PoamListPage />} />
          <Route path="/poams/:id" element={<PoamDetailPage />} />
          <Route path="/reviews" element={<ReviewsPage />} />
          <Route path="/reviews/:id" element={<ReviewDetailPage />} />
          <Route path="/findings/:id" element={<FindingPage />} />
          <Route path="/inheritance" element={<InheritancePage />} />
          <Route path="/policy-auditor" element={<PolicyAuditorPage />} />
          <Route path="/policy-auditor/:id" element={<PolicyDetailPage />} />
          <Route path="/rmf-workflow" element={<RmfWorkflowPage />} />
          <Route path="/systems/:id/authorization" element={<AuthorizationPage />} />
          <Route path="/settings/notifications" element={<NotificationPrefsPage />} />
          <Route path="/audit-log" element={<AuditLogPage />} />
          <Route path="/emass" element={<EmassPage />} />
          <Route path="/mapping-review" element={<MappingReviewPage />} />
          <Route path="/rmf/prepare" element={<PreparePage />} />
          <Route path="/rmf/categorize" element={<CategorizePage />} />
          <Route path="/rmf/select" element={<SelectPage />} />
          <Route path="/rmf/implement" element={<ImplementPage />} />
          <Route path="/rmf/assess" element={<AssessPage />} />
          <Route path="/rmf/authorize" element={<AuthorizePage />} />
          <Route path="/rmf/monitor" element={<MonitorPage />} />
          <Route path="/traceability" element={<TraceabilityPage />} />
          <Route path="/ccis" element={<CciPage />} />
          <Route path="/help" element={<HelpPage />} />
          {NAV_ITEMS.filter((n) => n.phase !== null).map((n) => (
            <Route key={n.path} path={n.path} element={<PlaceholderPage item={n} />} />
          ))}
          <Route path="*" element={<Navigate to="/controls" replace />} />
        </Routes>
      </AppShell>
    </SystemProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster richColors position="top-right" />
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/*" element={<Protected><Shell /></Protected>} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
