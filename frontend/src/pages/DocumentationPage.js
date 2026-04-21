import React from "react";
import Layout from "@/components/Layout";
import {
  FileText, ShieldCheck, BookOpen, Presentation, Newspaper, ArrowSquareOut
} from "@phosphor-icons/react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const DOCS = [
  {
    title: "Marketing Overview",
    description: "Product positioning, value propositions, 8 core pillars, and framework coverage for IronVision AI.",
    href: `${BACKEND_URL}/docs/marketing.html`,
    icon: Newspaper,
    color: "bg-[#2597B2]",
    tag: "Marketing",
  },
  {
    title: "Security Architecture",
    description: "Infrastructure diagram, authentication model, data security, API security, OSCAL compliance, and operational security.",
    href: `${BACKEND_URL}/docs/security-architecture.html`,
    icon: ShieldCheck,
    color: "bg-red-500",
    tag: "Technical",
  },
  {
    title: "UI Walkthrough Guide",
    description: "Step-by-step guide covering every major feature — from login to evidence collection, with pro tips.",
    href: `${BACKEND_URL}/docs/ui-walkthrough.html`,
    icon: BookOpen,
    color: "bg-emerald-500",
    tag: "User Guide",
  },
  {
    title: "Executive Pitch Deck",
    description: "8-slide presentation for stakeholders — problem, solution, 8 pillars, DevSecOps, OSCAL, target market. Print to PDF.",
    href: `${BACKEND_URL}/docs/pitch-deck.html`,
    icon: Presentation,
    color: "bg-purple-500",
    tag: "Sales",
  },
  {
    title: "Product Brochure",
    description: "2-page A4 brochure with capabilities, frameworks, architecture, and sector-specific value props. Print to PDF.",
    href: `${BACKEND_URL}/docs/brochure.html`,
    icon: FileText,
    color: "bg-amber-500",
    tag: "Sales",
  },
];

const TAG_COLORS = {
  Marketing: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400",
  Technical: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  "User Guide": "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  Sales: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

const DocumentationPage = () => {
  return (
    <Layout>
      <div data-testid="documentation-page">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight" style={{ fontFamily: "Inter, sans-serif" }}>
            Documentation
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
            Marketing materials, security documentation, user guides, and sales collateral
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="docs-grid">
          {DOCS.map((doc) => {
            const Icon = doc.icon;
            return (
              <a
                key={doc.title}
                href={doc.href}
                target="_blank"
                rel="noopener noreferrer"
                className="iv-card p-6 flex flex-col hover:shadow-lg transition-all group"
                data-testid={`doc-card-${doc.title.toLowerCase().replace(/\s+/g, "-")}`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className={`w-12 h-12 ${doc.color} bg-opacity-90 rounded-lg flex items-center justify-center`}>
                    <Icon size={24} weight="duotone" className="text-white" />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${TAG_COLORS[doc.tag] || "bg-gray-100 text-gray-600"}`}>
                      {doc.tag}
                    </span>
                    <ArrowSquareOut size={16} className="text-gray-400 group-hover:text-[#2597B2] transition-colors" />
                  </div>
                </div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2 group-hover:text-[#2597B2] transition-colors">
                  {doc.title}
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-3 flex-1">
                  {doc.description}
                </p>
                <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
                  <span className="text-sm font-medium text-[#2597B2] group-hover:underline">
                    Open Document
                  </span>
                </div>
              </a>
            );
          })}
        </div>

        <div className="mt-8 iv-card p-5 bg-gray-50 dark:bg-gray-800/50" data-testid="docs-tip">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Printing to PDF</h3>
          <p className="text-sm text-gray-500">
            All documents are print-optimized. Open any document and use your browser's <strong>Print</strong> function (Ctrl+P / Cmd+P)
            to export as PDF. The Pitch Deck renders as landscape slides, and the Brochure renders as A4 pages.
          </p>
        </div>
      </div>
    </Layout>
  );
};

export default DocumentationPage;
