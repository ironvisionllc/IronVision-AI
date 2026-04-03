import React, { useState } from "react";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { 
  Plug, 
  SlackLogo, 
  ChartBar, 
  ShieldCheck, 
  Bell,
  Globe,
  ArrowSquareOut,
  CheckCircle,
  Circle
} from "@phosphor-icons/react";

const INTEGRATIONS = [
  {
    id: "slack",
    name: "Slack",
    description: "Send compliance alerts and task notifications to Slack channels",
    icon: SlackLogo,
    category: "Communication",
    status: "available",
    color: "#4A154B"
  },
  {
    id: "jira",
    name: "Jira",
    description: "Sync tasks and remediation items with Jira projects",
    icon: Globe,
    category: "Project Management",
    status: "available",
    color: "#0052CC"
  },
  {
    id: "siem",
    name: "SIEM Integration",
    description: "Connect to Splunk, QRadar, or Sentinel for security event correlation",
    icon: ShieldCheck,
    category: "Security",
    status: "available",
    color: "#2597B2"
  },
  {
    id: "email",
    name: "Email Notifications",
    description: "Configure SMTP or SendGrid for compliance reminders and alerts",
    icon: Bell,
    category: "Notifications",
    status: "available",
    color: "#FB923C"
  },
  {
    id: "servicenow",
    name: "ServiceNow",
    description: "Integrate with ServiceNow ITSM for incident and change management",
    icon: Globe,
    category: "ITSM",
    status: "coming_soon",
    color: "#62D84E"
  },
  {
    id: "powerbi",
    name: "Power BI / Tableau",
    description: "Export compliance data to BI tools for advanced analytics",
    icon: ChartBar,
    category: "Analytics",
    status: "coming_soon",
    color: "#F2C811"
  },
];

const IntegrationsPage = () => {
  const [enabled, setEnabled] = useState({});

  const toggleIntegration = (id) => {
    if (INTEGRATIONS.find(i => i.id === id)?.status === "coming_soon") {
      toast.info("This integration is coming soon!");
      return;
    }
    setEnabled(prev => {
      const next = { ...prev, [id]: !prev[id] };
      if (next[id]) {
        toast.success(`${INTEGRATIONS.find(i => i.id === id)?.name} integration enabled`);
      } else {
        toast.info(`${INTEGRATIONS.find(i => i.id === id)?.name} integration disabled`);
      }
      return next;
    });
  };

  const categories = [...new Set(INTEGRATIONS.map(i => i.category))];

  return (
    <Layout>
      <div data-testid="integrations-page">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Integrations</h1>
            <p className="text-sm text-gray-600 mt-2">Connect your GRC platform with third-party tools and services</p>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Plug size={18} weight="duotone" className="text-[#2597B2]" />
            <span>{Object.values(enabled).filter(Boolean).length} active</span>
          </div>
        </div>

        {categories.map(cat => (
          <div key={cat} className="mb-8">
            <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500 mb-3">{cat}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {INTEGRATIONS.filter(i => i.category === cat).map(integration => {
                const Icon = integration.icon;
                const isEnabled = enabled[integration.id];
                const isComingSoon = integration.status === "coming_soon";
                return (
                  <div key={integration.id} className={`bg-white rounded-lg border p-5 transition-all duration-200 ${isEnabled ? "border-[#2597B2] shadow-sm" : "border-gray-200 hover:shadow-sm hover:-translate-y-[1px]"} ${isComingSoon ? "opacity-60" : ""}`} data-testid={`integration-card-${integration.id}`}>
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${integration.color}15` }}>
                          <Icon size={22} weight="duotone" style={{ color: integration.color }} />
                        </div>
                        <div>
                          <h3 className="font-semibold text-gray-900 text-sm">{integration.name}</h3>
                          {isComingSoon && <span className="text-xs text-gray-400 font-medium">Coming Soon</span>}
                          {isEnabled && <span className="text-xs text-[#4ADE80] font-medium flex items-center gap-1"><CheckCircle size={12} weight="fill" /> Connected</span>}
                        </div>
                      </div>
                      <Switch
                        checked={isEnabled || false}
                        onCheckedChange={() => toggleIntegration(integration.id)}
                        disabled={isComingSoon}
                        data-testid={`integration-toggle-${integration.id}`}
                      />
                    </div>
                    <p className="text-xs text-gray-500 leading-relaxed">{integration.description}</p>
                    {isEnabled && !isComingSoon && (
                      <Button variant="outline" size="sm" className="mt-3 text-xs h-8" data-testid={`integration-configure-${integration.id}`}>
                        Configure <ArrowSquareOut size={12} className="ml-1" />
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </Layout>
  );
};

export default IntegrationsPage;
