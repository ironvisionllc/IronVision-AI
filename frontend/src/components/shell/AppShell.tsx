import { ReactNode } from "react";
import { SyntheticBanner } from "@/components/shell/SyntheticBanner";
import { Header } from "@/components/shell/Header";
import { Sidebar } from "@/components/shell/Sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full flex-col" data-testid="app-shell">
      <SyntheticBanner />
      <Header />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto px-6 py-7 xl:px-10" data-testid="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}
