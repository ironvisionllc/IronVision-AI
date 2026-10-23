import { ReactNode, useState } from "react";
import { Menu } from "lucide-react";
import { SyntheticBanner } from "@/components/shell/SyntheticBanner";
import { Header } from "@/components/shell/Header";
import { Sidebar } from "@/components/shell/Sidebar";
import { SandboxBar } from "@/components/shell/Sandbox";
import { NextStepBanner } from "@/components/common/NextStep";
import { RmfBar } from "@/components/rmf/Stepper";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { DeniedDialog } from "@/components/common/RoleGate";

export function AppShell({ children }: { children: ReactNode }) {
  const [nav, setNav] = useState(false);
  return (
    <div className="flex h-full flex-col" data-testid="app-shell">
      <SyntheticBanner />
      <Header />
      <SandboxBar />
      <RmfBar />
      <NextStepBanner />
      <DeniedDialog />
      <div className="relative flex min-h-0 flex-1">
        <button className="absolute left-2 top-2 z-30 rounded-md border border-slate-200 bg-white p-1.5 lg:hidden" onClick={() => setNav(!nav)} aria-label="Toggle navigation" data-testid="nav-toggle"><Menu size={16} /></button>
        <div className={`${nav ? "absolute inset-y-0 left-0 z-20 flex shadow-xl" : "hidden"} lg:static lg:flex`} onClick={() => setNav(false)}><Sidebar /></div>
        <main className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-7 pt-12 md:px-6 lg:pt-7 xl:px-10" data-testid="main-content">
          <Breadcrumbs />
          {children}
        </main>
      </div>
    </div>
  );
}
