import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import Layout from "@/components/Layout";
import AuditsPage from "@/pages/AuditsPage";
import EvidencePage from "@/pages/EvidencePage";
import { Calendar, FolderOpen } from "@phosphor-icons/react";

const TABS = [
  { id: "audits", label: "Audit Management", icon: Calendar },
  { id: "evidence", label: "Evidence Library", icon: FolderOpen },
];

const ComplianceHub = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get("tab") || "audits";
  const [activeTab, setActiveTab] = useState(TABS.find(t => t.id === initialTab) ? initialTab : "audits");

  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  return (
    <Layout>
      <div data-testid="compliance-hub-page">
        <div className="mb-6">
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
            Compliance
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5">
            Manage audits and maintain your evidence library
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 border-b border-gray-200 dark:border-gray-700 mb-6" data-testid="compliance-hub-tabs">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              data-testid={`compliance-tab-${tab.id}`}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeTab === tab.id
                  ? "border-[#2597B2] text-[#2597B2]"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300"
              }`}
            >
              <tab.icon size={16} weight={activeTab === tab.id ? "duotone" : "regular"} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div data-testid="compliance-hub-content">
          {activeTab === "audits" && <AuditsPage embedded />}
          {activeTab === "evidence" && <EvidencePage embedded />}
        </div>
      </div>
    </Layout>
  );
};

export default ComplianceHub;
