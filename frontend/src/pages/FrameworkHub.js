import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import Layout from "@/components/Layout";
import FrameworksPage from "@/pages/FrameworksPage";
import MappingsPage from "@/pages/MappingsPage";
import CrossFrameworkPage from "@/pages/CrossFrameworkPage";
import { ShieldCheck, GitBranch, FlowArrow } from "@phosphor-icons/react";

const TABS = [
  { id: "frameworks", label: "Frameworks", icon: ShieldCheck },
  { id: "mappings", label: "Control Mappings", icon: GitBranch },
  { id: "cross-framework", label: "Cross-Framework", icon: FlowArrow },
];

const FrameworkHub = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get("tab") || "frameworks";
  const [activeTab, setActiveTab] = useState(TABS.find(t => t.id === initialTab) ? initialTab : "frameworks");

  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  return (
    <Layout>
      <div data-testid="framework-hub-page">
        <div className="mb-6">
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
            Frameworks & Mapping
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5">
            Manage compliance frameworks, map controls, and view cross-framework relationships
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 border-b border-gray-200 dark:border-gray-700 mb-6" data-testid="framework-hub-tabs">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              data-testid={`framework-tab-${tab.id}`}
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
        <div data-testid="framework-hub-content">
          {activeTab === "frameworks" && <FrameworksPage embedded />}
          {activeTab === "mappings" && <MappingsPage embedded />}
          {activeTab === "cross-framework" && <CrossFrameworkPage embedded />}
        </div>
      </div>
    </Layout>
  );
};

export default FrameworkHub;
