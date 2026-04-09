import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import Layout from "@/components/Layout";
import PolicyBuilderPage from "@/pages/PolicyBuilderPage";
import PolicyLibraryPage from "@/pages/PolicyLibraryPage";
import DocumentsPage from "@/pages/DocumentsPage";
import { FileText, Files, CloudArrowUp } from "@phosphor-icons/react";

const TABS = [
  { id: "builder", label: "Policy Builder", icon: FileText },
  { id: "library", label: "Policy Library", icon: Files },
  { id: "documents", label: "Document Analysis", icon: CloudArrowUp },
];

const PolicyHub = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get("tab") || "builder";
  const [activeTab, setActiveTab] = useState(TABS.find(t => t.id === initialTab) ? initialTab : "builder");

  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  return (
    <Layout>
      <div data-testid="policy-hub-page">
        <div className="mb-6">
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
            Policies & Documents
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5">
            Create, manage, and analyze compliance policies and documents
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 border-b border-gray-200 dark:border-gray-700 mb-6" data-testid="policy-hub-tabs">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              data-testid={`policy-tab-${tab.id}`}
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
        <div data-testid="policy-hub-content">
          {activeTab === "builder" && <PolicyBuilderPage embedded />}
          {activeTab === "library" && <PolicyLibraryPage embedded />}
          {activeTab === "documents" && <DocumentsPage embedded />}
        </div>
      </div>
    </Layout>
  );
};

export default PolicyHub;
