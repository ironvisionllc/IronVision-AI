import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import {
  ShieldCheck, Warning, Lightning, Eye, Clock, CaretRight, DownloadSimple,
  FunnelSimple, MagnifyingGlass, ArrowRight, Database, GitBranch, Lock,
  UserCircle, Gear, Bug, ChartBar,
} from "@phosphor-icons/react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";

const SEVERITY_CONFIG = {
  critical: { color: "#DC2626", bg: "#FEE2E2", label: "Critical" },
  high: { color: "#D97706", bg: "#FEF3C7", label: "High" },
  medium: { color: "#0891B2", bg: "#CFFAFE", label: "Medium" },
  low: { color: "#059669", bg: "#D1FAE5", label: "Low" },
  info: { color: "#6B7280", bg: "#F3F4F6", label: "Info" },
};

const CATEGORY_ICONS = {
  authentication: Lock,
  authorization: UserCircle,
  data_access: Database,
  policy_change: Gear,
  risk_management: Warning,
  incident: Bug,
  system: ShieldCheck,
};

const SIEMPage = () => {
  const [dashboard, setDashboard] = useState(null);
  const [events, setEvents] = useState([]);
  const [controlMapping, setControlMapping] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("overview");
  const [filter, setFilter] = useState({ severity: "", category: "", search: "" });
  const [days, setDays] = useState(7);

  useEffect(() => {
    fetchAll();
  }, [days]);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [dashRes, evRes, mapRes] = await Promise.all([
        axios.get(`${API}/siem/dashboard?days=${days}`),
        axios.get(`${API}/siem/events?days=${days}&limit=200`),
        axios.get(`${API}/siem/control-mapping`),
      ]);
      setDashboard(dashRes.data);
      setEvents(evRes.data);
      setControlMapping(mapRes.data);
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  const seedDemo = async () => {
    try {
      const res = await axios.post(`${API}/siem/seed-demo`);
      toast.success(`Seeded ${res.data.count} demo events`);
      fetchAll();
    } catch { toast.error("Failed to seed demo events"); }
  };

  const exportEvents = async (format) => {
    try {
      if (format === "json") {
        const res = await axios.get(`${API}/siem/export?format=json&days=${days}`);
        const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `siem_events_${days}d.json`; a.click(); URL.revokeObjectURL(url);
      } else {
        const res = await axios.get(`${API}/siem/export?format=${format}&days=${days}`, { responseType: "blob" });
        const url = URL.createObjectURL(new Blob([res.data]));
        const a = document.createElement("a"); a.href = url; a.download = `siem_events_${days}d.${format === "syslog" ? "log" : format}`; a.click(); URL.revokeObjectURL(url);
      }
      toast.success(`Exported as ${format.toUpperCase()}`);
    } catch { toast.error("Export failed"); }
  };

  const filteredEvents = events.filter(ev => {
    if (filter.severity && ev.severity !== filter.severity) return false;
    if (filter.category && ev.category !== filter.category) return false;
    if (filter.search && !ev.details?.toLowerCase().includes(filter.search.toLowerCase()) && !ev.event_type?.toLowerCase().includes(filter.search.toLowerCase())) return false;
    return true;
  });

  const sevChartData = dashboard ? Object.entries(dashboard.severity_distribution).map(([k, v]) => ({ name: SEVERITY_CONFIG[k]?.label || k, value: v, color: SEVERITY_CONFIG[k]?.color || "#9CA3AF" })) : [];
  const catChartData = dashboard ? Object.entries(dashboard.category_distribution).filter(([, v]) => v > 0).map(([k, v]) => ({ name: k.replace(/_/g, " "), value: v })) : [];

  const threatColor = (level) => level >= 70 ? "#DC2626" : level >= 40 ? "#D97706" : level >= 15 ? "#0891B2" : "#059669";
  const threatLabel = (level) => level >= 70 ? "Critical" : level >= 40 ? "Elevated" : level >= 15 ? "Moderate" : "Low";

  if (loading) return (
    <Layout>
      <div className="flex items-center justify-center h-[60vh]" data-testid="siem-loading">
        <div className="flex flex-col items-center gap-4">
          <div className="iv-spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
          <p className="text-gray-500 dark:text-gray-400 text-sm font-medium">Loading SIEM data...</p>
        </div>
      </div>
    </Layout>
  );

  return (
    <Layout>
      <div data-testid="siem-page" className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">SIEM Dashboard</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Security event monitoring and control mapping</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="h-9 px-3 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2597B2]"
              data-testid="siem-period-select"
            >
              <option value={1}>Last 24h</option>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
            {events.length === 0 && (
              <Button onClick={seedDemo} size="sm" className="iv-btn-secondary text-xs h-9" data-testid="siem-seed-btn">
                <Lightning size={14} className="mr-1" /> Seed Demo Data
              </Button>
            )}
            <div className="relative">
              <Button size="sm" className="iv-btn-secondary text-xs h-9" onClick={() => exportEvents("json")} data-testid="siem-export-btn">
                <DownloadSimple size={14} className="mr-1" /> Export
              </Button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 dark:border-gray-700">
          {[
            { key: "overview", label: "Overview", icon: Eye },
            { key: "events", label: "Event Log", icon: Lightning },
            { key: "mapping", label: "Control Mapping", icon: GitBranch },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-all ${
                tab === t.key ? "border-[#2597B2] text-[#2597B2]" : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400"
              }`}
              data-testid={`siem-tab-${t.key}`}
            >
              <t.icon size={15} weight={tab === t.key ? "fill" : "regular"} />
              {t.label}
            </button>
          ))}
        </div>

        {/* Overview Tab */}
        {tab === "overview" && dashboard && (
          <div className="space-y-6">
            {/* Top Metrics */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="siem-metrics">
              {/* Threat Level */}
              <div className="iv-card p-5" data-testid="metric-threat-level" style={{ borderLeft: `4px solid ${threatColor(dashboard.threat_level)}` }}>
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Threat Level</p>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-3xl font-bold" style={{ color: threatColor(dashboard.threat_level) }} data-testid="threat-level-score">{dashboard.threat_level}</span>
                  <span className="text-xs font-bold px-2 py-0.5 rounded" style={{ color: threatColor(dashboard.threat_level), backgroundColor: `${threatColor(dashboard.threat_level)}15` }}>
                    {threatLabel(dashboard.threat_level)}
                  </span>
                </div>
              </div>

              {/* Total Events */}
              <div className="iv-card p-5" data-testid="metric-total-events">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Total Events</p>
                <span className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-1 block" data-testid="total-events-count">{dashboard.total_events}</span>
                <p className="text-xs text-gray-400 mt-1">Last {days} day{days > 1 ? "s" : ""}</p>
              </div>

              {/* Critical/High */}
              <div className="iv-card p-5" data-testid="metric-critical-events">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Critical + High</p>
                <span className="text-3xl font-bold text-red-600 dark:text-red-400 mt-1 block">
                  {(dashboard.severity_distribution.critical || 0) + (dashboard.severity_distribution.high || 0)}
                </span>
                <p className="text-xs text-gray-400 mt-1">{dashboard.severity_distribution.critical || 0} critical, {dashboard.severity_distribution.high || 0} high</p>
              </div>

              {/* Categories Monitored */}
              <div className="iv-card p-5" data-testid="metric-categories">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Categories</p>
                <span className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-1 block">
                  {Object.values(dashboard.category_distribution).filter(v => v > 0).length}
                </span>
                <p className="text-xs text-gray-400 mt-1">of {Object.keys(dashboard.category_distribution).length} monitored</p>
              </div>
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Severity Distribution */}
              <div className="iv-card p-6" data-testid="severity-chart">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">Severity Distribution</h3>
                {sevChartData.some(d => d.value > 0) ? (
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={sevChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F010" />
                      <XAxis dataKey="name" fontSize={11} tickLine={false} axisLine={false} />
                      <YAxis fontSize={11} tickLine={false} axisLine={false} />
                      <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E2E8F0" }} />
                      <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={28}>
                        {sevChartData.map((e, i) => <Cell key={i} fill={e.color} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-48 flex items-center justify-center text-gray-400 text-sm">No events yet</div>
                )}
              </div>

              {/* Critical Events */}
              <div className="iv-card p-6" data-testid="critical-events-list">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">Critical & High Events</h3>
                {dashboard.critical_events.length === 0 ? (
                  <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
                    <div className="text-center">
                      <ShieldCheck size={28} weight="duotone" className="mx-auto mb-2 text-green-400" />
                      <p>No critical events</p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[200px] overflow-y-auto">
                    {dashboard.critical_events.map(ev => {
                      const sev = SEVERITY_CONFIG[ev.severity] || SEVERITY_CONFIG.info;
                      return (
                        <div key={ev.id} className="flex items-start gap-3 p-3 rounded-xl border border-gray-100 dark:border-gray-800 hover:border-red-200 dark:hover:border-red-800/30 transition-colors" data-testid={`critical-event-${ev.id}`}>
                          <span className="px-1.5 py-0.5 text-[10px] font-bold rounded" style={{ color: sev.color, backgroundColor: sev.bg }}>{sev.label}</span>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate">{ev.details}</p>
                            <p className="text-[10px] text-gray-400 mt-0.5">{ev.user_name || "System"} · {new Date(ev.timestamp).toLocaleString()}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Events Tab */}
        {tab === "events" && (
          <div className="space-y-4">
            {/* Filters */}
            <div className="iv-card p-4 flex items-center gap-3 flex-wrap" data-testid="siem-filters">
              <div className="relative flex-1 min-w-[200px]">
                <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <Input
                  placeholder="Search events..."
                  value={filter.search}
                  onChange={(e) => setFilter({ ...filter, search: e.target.value })}
                  className="pl-9 h-9 text-xs"
                  data-testid="siem-search-input"
                />
              </div>
              <select
                value={filter.severity}
                onChange={(e) => setFilter({ ...filter, severity: e.target.value })}
                className="h-9 px-3 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
                data-testid="siem-severity-filter"
              >
                <option value="">All Severities</option>
                {Object.entries(SEVERITY_CONFIG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
              <select
                value={filter.category}
                onChange={(e) => setFilter({ ...filter, category: e.target.value })}
                className="h-9 px-3 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
                data-testid="siem-category-filter"
              >
                <option value="">All Categories</option>
                {Object.keys(CATEGORY_ICONS).map(k => <option key={k} value={k}>{k.replace(/_/g, " ")}</option>)}
              </select>
              <span className="text-xs text-gray-400">{filteredEvents.length} events</span>
            </div>

            {/* Event Table */}
            <div className="iv-card overflow-hidden" data-testid="siem-events-table">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400 w-[90px]">Severity</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400 w-[170px]">Timestamp</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400 w-[140px]">Event Type</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400">Details</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400 w-[100px]">User</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400 w-[120px]">Controls</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEvents.length === 0 ? (
                    <tr><td colSpan={6} className="py-12 text-center text-gray-400 text-sm">
                      <Lightning size={28} weight="duotone" className="mx-auto mb-2" />
                      {events.length === 0 ? "No events yet. Click 'Seed Demo Data' to populate." : "No events match filters."}
                    </td></tr>
                  ) : filteredEvents.slice(0, 100).map(ev => {
                    const sev = SEVERITY_CONFIG[ev.severity] || SEVERITY_CONFIG.info;
                    const CatIcon = CATEGORY_ICONS[ev.category] || ShieldCheck;
                    return (
                      <tr key={ev.id} className="border-b border-gray-100 dark:border-gray-800 last:border-0 hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition-colors" data-testid={`siem-event-row-${ev.id}`}>
                        <td className="py-2.5 px-4">
                          <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded" style={{ color: sev.color, backgroundColor: sev.bg }}>{sev.label}</span>
                        </td>
                        <td className="py-2.5 px-4 text-xs text-gray-500 dark:text-gray-400 font-mono">
                          {new Date(ev.timestamp).toLocaleString(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                        </td>
                        <td className="py-2.5 px-4">
                          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
                            <CatIcon size={12} weight="duotone" className="text-[#2597B2]" />
                            {ev.event_type.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td className="py-2.5 px-4 text-xs text-gray-700 dark:text-gray-300 truncate max-w-[300px]">{ev.details}</td>
                        <td className="py-2.5 px-4 text-xs text-gray-500 dark:text-gray-400">{ev.user_name || "-"}</td>
                        <td className="py-2.5 px-4">
                          {ev.mapped_controls?.length > 0 && (
                            <div className="flex flex-wrap gap-1">
                              {ev.mapped_controls.slice(0, 3).map(c => (
                                <span key={c} className="text-[9px] font-mono font-semibold px-1.5 py-0.5 bg-[#2597B2]/10 text-[#2597B2] rounded">{c}</span>
                              ))}
                              {ev.mapped_controls.length > 3 && <span className="text-[9px] text-gray-400">+{ev.mapped_controls.length - 3}</span>}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Control Mapping Tab */}
        {tab === "mapping" && (
          <div className="space-y-4">
            <div className="iv-card p-5" data-testid="control-mapping-summary">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">Event-to-Control Framework Mapping</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-5">SIEM events are automatically mapped to NIST 800-53 and NIST 800-171 controls for continuous compliance evidence.</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {controlMapping.map(cm => {
                  const CatIcon = CATEGORY_ICONS[cm.category] || ShieldCheck;
                  return (
                    <div key={cm.category} className="p-4 border border-gray-100 dark:border-gray-800 rounded-xl hover:border-[#2597B2]/30 transition-colors" data-testid={`mapping-${cm.category}`}>
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2.5">
                          <div className="w-8 h-8 rounded-lg bg-[#2597B2]/10 flex items-center justify-center">
                            <CatIcon size={16} weight="duotone" className="text-[#2597B2]" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 capitalize">{cm.category.replace(/_/g, " ")}</p>
                            <p className="text-[10px] text-gray-400">{cm.description}</p>
                          </div>
                        </div>
                        <span className="text-xs font-bold text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded" data-testid={`mapping-count-${cm.category}`}>
                          {cm.event_count_30d} events
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {cm.controls.map(ctrl => (
                          <span key={ctrl} className="text-[10px] font-mono font-semibold px-2 py-0.5 border border-[#2597B2]/20 text-[#2597B2] bg-[#2597B2]/5 rounded">{ctrl}</span>
                        ))}
                      </div>
                      <div className="flex gap-1.5 mt-2">
                        {cm.frameworks.map(fw => (
                          <span key={fw} className="text-[9px] font-medium text-gray-400 bg-gray-50 dark:bg-gray-800 px-1.5 py-0.5 rounded">{fw}</span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
};

export default SIEMPage;
