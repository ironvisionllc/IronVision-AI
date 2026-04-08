import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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
  X,
  PaperPlaneTilt,
  Gear,
  Trash,
  Clock,
  Warning,
} from "@phosphor-icons/react";

const INTEGRATIONS = [
  {
    id: "slack",
    name: "Slack",
    description: "Send compliance alerts and task notifications to Slack channels",
    icon: SlackLogo,
    category: "Communication",
    status: "available",
    color: "#4A154B",
    configurable: true,
  },
  {
    id: "jira",
    name: "Jira",
    description: "Sync tasks and remediation items with Jira projects",
    icon: Globe,
    category: "Project Management",
    status: "coming_soon",
    color: "#0052CC",
  },
  {
    id: "siem",
    name: "SIEM Integration",
    description: "Connect to Splunk, QRadar, or Sentinel for security event correlation",
    icon: ShieldCheck,
    category: "Security",
    status: "coming_soon",
    color: "#2597B2",
  },
  {
    id: "email",
    name: "Email Notifications",
    description: "Configure SMTP or SendGrid for compliance reminders and alerts",
    icon: Bell,
    category: "Notifications",
    status: "available",
    color: "#FB923C",
  },
  {
    id: "servicenow",
    name: "ServiceNow",
    description: "Integrate with ServiceNow ITSM for incident and change management",
    icon: Globe,
    category: "ITSM",
    status: "coming_soon",
    color: "#62D84E",
  },
  {
    id: "powerbi",
    name: "Power BI / Tableau",
    description: "Export compliance data to BI tools for advanced analytics",
    icon: ChartBar,
    category: "Analytics",
    status: "coming_soon",
    color: "#F2C811",
  },
];

const IntegrationsPage = () => {
  const [slackConfig, setSlackConfig] = useState(null);
  const [slackDialogOpen, setSlackDialogOpen] = useState(false);
  const [slackLoading, setSlackLoading] = useState(false);
  const [slackHistory, setSlackHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [slackForm, setSlackForm] = useState({
    webhook_url: "",
    channel_name: "#general",
    notify_risks: true,
    notify_tasks: true,
    notify_policies: true,
    notify_audits: true,
  });
  const [testLoading, setTestLoading] = useState(false);

  useEffect(() => {
    fetchSlackConfig();
  }, []);

  const fetchSlackConfig = async () => {
    try {
      const res = await axios.get(`${API}/slack/config`);
      setSlackConfig(res.data);
    } catch {}
  };

  const fetchSlackHistory = async () => {
    try {
      const res = await axios.get(`${API}/slack/history`);
      setSlackHistory(res.data);
    } catch {}
  };

  const saveSlackConfig = async () => {
    if (!slackForm.webhook_url.startsWith("https://hooks.slack.com/")) {
      toast.error("Invalid webhook URL. Must start with https://hooks.slack.com/");
      return;
    }
    setSlackLoading(true);
    try {
      await axios.post(`${API}/slack/config`, slackForm);
      toast.success("Slack integration configured successfully!");
      setSlackDialogOpen(false);
      fetchSlackConfig();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to save Slack configuration");
    }
    setSlackLoading(false);
  };

  const testSlackWebhook = async () => {
    if (!slackForm.webhook_url) {
      toast.error("Enter a webhook URL first");
      return;
    }
    setTestLoading(true);
    try {
      const res = await axios.post(`${API}/slack/test`, { webhook_url: slackForm.webhook_url });
      toast.success(res.data.message);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Test failed");
    }
    setTestLoading(false);
  };

  const deleteSlackConfig = async () => {
    try {
      await axios.delete(`${API}/slack/config`);
      toast.success("Slack integration removed");
      setSlackConfig({ configured: false });
    } catch {
      toast.error("Failed to remove Slack configuration");
    }
  };

  const openSlackConfig = () => {
    setSlackForm({
      webhook_url: "",
      channel_name: slackConfig?.channel_name || "#general",
      notify_risks: slackConfig?.notify_risks ?? true,
      notify_tasks: slackConfig?.notify_tasks ?? true,
      notify_policies: slackConfig?.notify_policies ?? true,
      notify_audits: slackConfig?.notify_audits ?? true,
    });
    setSlackDialogOpen(true);
  };

  const categories = [...new Set(INTEGRATIONS.map(i => i.category))];
  const isSlackConnected = slackConfig?.configured;

  return (
    <Layout>
      <div data-testid="integrations-page">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
              Integrations
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Connect your GRC platform with third-party tools and services
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Plug size={18} weight="duotone" className="text-[#2597B2]" />
            <span>{isSlackConnected ? 1 : 0} active</span>
          </div>
        </div>

        {categories.map(cat => (
          <div key={cat} className="mb-8">
            <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500 dark:text-gray-400 mb-3">{cat}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {INTEGRATIONS.filter(i => i.category === cat).map(integration => {
                const Icon = integration.icon;
                const isEnabled = integration.id === "slack" ? isSlackConnected : false;
                const isComingSoon = integration.status === "coming_soon";
                return (
                  <div
                    key={integration.id}
                    className={`iv-card p-5 transition-all duration-200 ${isEnabled ? "border-[#2597B2]/50 shadow-sm" : ""} ${isComingSoon ? "opacity-50" : ""}`}
                    data-testid={`integration-card-${integration.id}`}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div
                          className="w-10 h-10 rounded-lg flex items-center justify-center"
                          style={{ backgroundColor: `${integration.color}15` }}
                        >
                          <Icon size={22} weight="duotone" style={{ color: integration.color }} />
                        </div>
                        <div>
                          <h3 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">{integration.name}</h3>
                          {isComingSoon && <span className="text-xs text-gray-400 font-medium">Coming Soon</span>}
                          {isEnabled && (
                            <span className="text-xs text-emerald-500 font-medium flex items-center gap-1">
                              <CheckCircle size={12} weight="fill" /> Connected
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed mb-3">{integration.description}</p>

                    {integration.id === "slack" && (
                      <div className="flex items-center gap-2 mt-auto">
                        <Button
                          size="sm"
                          className="text-xs h-8 iv-btn-primary"
                          onClick={openSlackConfig}
                          data-testid="slack-configure-btn"
                        >
                          <Gear size={14} className="mr-1" />
                          {isSlackConnected ? "Reconfigure" : "Configure"}
                        </Button>
                        {isSlackConnected && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-xs h-8"
                              onClick={() => { fetchSlackHistory(); setShowHistory(true); }}
                              data-testid="slack-history-btn"
                            >
                              <Clock size={14} className="mr-1" /> History
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-xs h-8 text-red-500 hover:text-red-600 hover:bg-red-50"
                              onClick={deleteSlackConfig}
                              data-testid="slack-delete-btn"
                            >
                              <Trash size={14} />
                            </Button>
                          </>
                        )}
                      </div>
                    )}

                    {integration.id !== "slack" && !isComingSoon && (
                      <Button variant="outline" size="sm" className="text-xs h-8 mt-auto" disabled>
                        Configure <ArrowSquareOut size={12} className="ml-1" />
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {/* Slack Configuration Dialog */}
        <Dialog open={slackDialogOpen} onOpenChange={setSlackDialogOpen}>
          <DialogContent className="sm:max-w-[520px]" data-testid="slack-config-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <SlackLogo size={22} weight="duotone" style={{ color: "#4A154B" }} />
                Configure Slack Integration
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-5 mt-2">
              <div>
                <Label className="text-sm font-medium">Incoming Webhook URL</Label>
                <p className="text-xs text-gray-400 mb-2">
                  Create one at{" "}
                  <a href="https://api.slack.com/messaging/webhooks" target="_blank" rel="noopener noreferrer" className="text-[#2597B2] hover:underline">
                    api.slack.com/messaging/webhooks
                  </a>
                </p>
                <Input
                  placeholder="https://hooks.slack.com/services/T.../B.../..."
                  value={slackForm.webhook_url}
                  onChange={(e) => setSlackForm({ ...slackForm, webhook_url: e.target.value })}
                  data-testid="slack-webhook-input"
                />
              </div>

              <div>
                <Label className="text-sm font-medium">Channel Name</Label>
                <Input
                  placeholder="#general"
                  value={slackForm.channel_name}
                  onChange={(e) => setSlackForm({ ...slackForm, channel_name: e.target.value })}
                  className="mt-1"
                  data-testid="slack-channel-input"
                />
              </div>

              <div>
                <Label className="text-sm font-medium mb-3 block">Notification Events</Label>
                <div className="space-y-3">
                  {[
                    { key: "notify_risks", label: "Risk Alerts", desc: "New risks, severity changes" },
                    { key: "notify_tasks", label: "Task Updates", desc: "Assignments, completions, overdue" },
                    { key: "notify_policies", label: "Policy Changes", desc: "New policies, AI-generated policies" },
                    { key: "notify_audits", label: "Audit Events", desc: "Upcoming audits, findings" },
                  ].map(item => (
                    <div key={item.key} className="flex items-center justify-between py-1">
                      <div>
                        <p className="text-sm font-medium text-gray-800 dark:text-gray-200">{item.label}</p>
                        <p className="text-xs text-gray-400">{item.desc}</p>
                      </div>
                      <Switch
                        checked={slackForm[item.key]}
                        onCheckedChange={(v) => setSlackForm({ ...slackForm, [item.key]: v })}
                        data-testid={`slack-toggle-${item.key}`}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-3 pt-2">
                <Button
                  variant="outline"
                  className="text-xs h-9"
                  onClick={testSlackWebhook}
                  disabled={testLoading || !slackForm.webhook_url}
                  data-testid="slack-test-btn"
                >
                  <PaperPlaneTilt size={14} className="mr-1" />
                  {testLoading ? "Sending..." : "Send Test Message"}
                </Button>
                <div className="flex-1" />
                <Button
                  variant="ghost"
                  className="text-xs h-9"
                  onClick={() => setSlackDialogOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  className="text-xs h-9 iv-btn-primary"
                  onClick={saveSlackConfig}
                  disabled={slackLoading || !slackForm.webhook_url}
                  data-testid="slack-save-btn"
                >
                  {slackLoading ? "Saving..." : "Save Configuration"}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Slack History Dialog */}
        <Dialog open={showHistory} onOpenChange={setShowHistory}>
          <DialogContent className="sm:max-w-[520px]" data-testid="slack-history-dialog">
            <DialogHeader>
              <DialogTitle>Notification History</DialogTitle>
            </DialogHeader>
            <div className="max-h-[400px] overflow-y-auto space-y-2 mt-2">
              {slackHistory.length === 0 ? (
                <div className="text-center py-8 text-gray-400">
                  <Bell size={32} weight="duotone" className="mx-auto mb-2" />
                  <p className="text-sm">No notifications sent yet</p>
                </div>
              ) : slackHistory.map((n, idx) => (
                <div
                  key={n.id || idx}
                  className={`flex items-start gap-3 p-3 rounded-xl border ${n.success ? "border-gray-100 dark:border-gray-700" : "border-red-100 bg-red-50/50"}`}
                  data-testid={`slack-history-item-${idx}`}
                >
                  <div className={`w-2 h-2 rounded-full mt-2 flex-shrink-0 ${n.success ? "bg-emerald-400" : "bg-red-400"}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">{n.title}</p>
                    <p className="text-xs text-gray-500 truncate">{n.message}</p>
                    <p className="text-xs text-gray-400 mt-1">
                      {new Date(n.sent_at).toLocaleString()} · {n.event_type}
                      {!n.success && <span className="text-red-500 ml-2">Failed</span>}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default IntegrationsPage;
