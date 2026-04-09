import React, { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import {
  ShieldCheck, Warning, Lightning, Eye, Clock, CaretRight, DownloadSimple,
  MagnifyingGlass, Database, GitBranch, Lock, UserCircle, Gear, Bug,
  ChartBar, Plus, Trash, Copy, Play, Stop, Pulse, Plug, Key, Globe,
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
  authentication: Lock, authorization: UserCircle, data_access: Database,
  policy_change: Gear, risk_management: Warning, incident: Bug, system: ShieldCheck,
};

const SOURCE_TYPES = [
  { value: "splunk", label: "Splunk HEC", icon: Globe },
  { value: "cloudtrail", label: "AWS CloudTrail", icon: Globe },
  { value: "qradar", label: "IBM QRadar", icon: Globe },
  { value: "generic", label: "Generic JSON", icon: Plug },
];

const SIEMPage = () => {
  const [dashboard, setDashboard] = useState(null);
  const [events, setEvents] = useState([]);
  const [controlMapping, setControlMapping] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("overview");
  const [filter, setFilter] = useState({ severity: "", category: "", search: "" });
  const [days, setDays] = useState(7);

  // Simulator
  const [simActive, setSimActive] = useState(false);
  const [liveCount, setLiveCount] = useState(0);
  const pollRef = useRef(null);
  const prevCountRef = useRef(0);

  // Source dialog
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false);
  const [newSource, setNewSource] = useState({ name: "", source_type: "splunk" });
  const [createdSource, setCreatedSource] = useState(null);

  const fetchAll = useCallback(async () => {
    try {
      const [dashRes, evRes, mapRes, srcRes, simRes] = await Promise.all([
        axios.get(`${API}/siem/dashboard?days=${days}`),
        axios.get(`${API}/siem/events?days=${days}&limit=200`),
        axios.get(`${API}/siem/control-mapping`),
        axios.get(`${API}/siem/sources`).catch(() => ({ data: [] })),
        axios.get(`${API}/siem/simulator/status`).catch(() => ({ data: { active: false } })),
      ]);
      setDashboard(dashRes.data);
      setEvents(evRes.data);
      setControlMapping(mapRes.data);
      setSources(srcRes.data);
      setSimActive(simRes.data.active);
      prevCountRef.current = dashRes.data.total_events;
    } catch {}
    setLoading(false);
  }, [days]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Live polling when sim active or on events tab
  useEffect(() => {
    if (simActive || tab === "events") {
      pollRef.current = setInterval(async () => {
        try {
          const [evRes, dashRes] = await Promise.all([
            axios.get(`${API}/siem/events?days=${days}&limit=200`),
            axios.get(`${API}/siem/dashboard?days=${days}`),
          ]);
          setEvents(evRes.data);
          setDashboard(dashRes.data);
          const newCount = dashRes.data.total_events - prevCountRef.current;
          if (newCount > 0) setLiveCount(prev => prev + newCount);
          prevCountRef.current = dashRes.data.total_events;
        } catch {}
      }, 4000);
      return () => clearInterval(pollRef.current);
    }
    return () => {};
  }, [simActive, tab, days]);

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

  const toggleSimulator = async () => {
    try {
      if (simActive) {
        await axios.post(`${API}/siem/simulator/stop`);
        setSimActive(false);
        setLiveCount(0);
        toast.success("Simulation stopped");
      } else {
        await axios.post(`${API}/siem/simulator/start`);
        setSimActive(true);
        setLiveCount(0);
        toast.success("Simulation started — live events incoming!");
      }
    } catch { toast.error("Failed to toggle simulator"); }
  };

  const createSource = async () => {
    if (!newSource.name.trim()) { toast.error("Enter a source name"); return; }
    try {
      const res = await axios.post(`${API}/siem/sources`, newSource);
      setCreatedSource(res.data);
      setSources(prev => [...prev, res.data]);
      toast.success("Source created! Copy the webhook URL and API key.");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to create source"); }
  };

  const deleteSource = async (id) => {
    try {
      await axios.delete(`${API}/siem/sources/${id}`);
      setSources(prev => prev.filter(s => s.id !== id));
      toast.success("Source deleted");
    } catch { toast.error("Failed to delete source"); }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text).then(() => toast.success("Copied!")).catch(() => {});
  };

  const filteredEvents = events.filter(ev => {
    if (filter.severity && ev.severity !== filter.severity) return false;
    if (filter.category && ev.category !== filter.category) return false;
    if (filter.search && !ev.details?.toLowerCase().includes(filter.search.toLowerCase()) && !ev.event_type?.toLowerCase().includes(filter.search.toLowerCase())) return false;
    return true;
  });

  const sevChartData = dashboard ? Object.entries(dashboard.severity_distribution).map(([k, v]) => ({ name: SEVERITY_CONFIG[k]?.label || k, value: v, color: SEVERITY_CONFIG[k]?.color || "#9CA3AF" })) : [];
  const threatColor = (level) => level >= 70 ? "#DC2626" : level >= 40 ? "#D97706" : level >= 15 ? "#0891B2" : "#059669";
  const threatLabel = (level) => level >= 70 ? "Critical" : level >= 40 ? "Elevated" : level >= 15 ? "Moderate" : "Low";

  const webhookBaseUrl = `${window.location.origin}/api/siem/ingest/`;

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
          <div className="flex items-center gap-3">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">SIEM Dashboard</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Security event monitoring, control mapping & real-time ingestion</p>
            </div>
            {simActive && (
              <span className="flex items-center gap-1.5 px-3 py-1 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-full text-xs font-semibold text-red-600 dark:text-red-400 animate-pulse" data-testid="sim-live-badge">
                <Pulse size={14} weight="fill" />
                LIVE — {liveCount} new events
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="h-9 px-3 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300" data-testid="siem-period-select">
              <option value={1}>Last 24h</option>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
            <Button onClick={toggleSimulator} size="sm" className={`text-xs h-9 ${simActive ? "bg-red-600 hover:bg-red-700 text-white" : "iv-btn-primary"}`} data-testid="sim-toggle-btn">
              {simActive ? <><Stop size={14} className="mr-1" /> Stop Simulation</> : <><Play size={14} className="mr-1" /> Simulate Live</>}
            </Button>
            {events.length === 0 && (
              <Button onClick={seedDemo} size="sm" className="iv-btn-secondary text-xs h-9" data-testid="siem-seed-btn">
                <Lightning size={14} className="mr-1" /> Seed Demo
              </Button>
            )}
            <Button size="sm" className="iv-btn-secondary text-xs h-9" onClick={() => exportEvents("json")} data-testid="siem-export-btn">
              <DownloadSimple size={14} className="mr-1" /> Export
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 dark:border-gray-700">
          {[
            { key: "overview", label: "Overview", icon: Eye },
            { key: "events", label: "Event Log", icon: Lightning, badge: simActive ? liveCount : null },
            { key: "mapping", label: "Control Mapping", icon: GitBranch },
            { key: "sources", label: "Sources", icon: Plug, badge: sources.length },
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
              {t.badge > 0 && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-[#2597B2]/10 text-[#2597B2]">{t.badge}</span>
              )}
            </button>
          ))}
        </div>

        {/* ===== OVERVIEW TAB ===== */}
        {tab === "overview" && dashboard && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="siem-metrics">
              <div className="iv-card p-5" data-testid="metric-threat-level" style={{ borderLeft: `4px solid ${threatColor(dashboard.threat_level)}` }}>
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Threat Level</p>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-3xl font-bold" style={{ color: threatColor(dashboard.threat_level) }} data-testid="threat-level-score">{dashboard.threat_level}</span>
                  <span className="text-xs font-bold px-2 py-0.5 rounded" style={{ color: threatColor(dashboard.threat_level), backgroundColor: `${threatColor(dashboard.threat_level)}15` }}>{threatLabel(dashboard.threat_level)}</span>
                </div>
              </div>
              <div className="iv-card p-5" data-testid="metric-total-events">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Total Events</p>
                <span className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-1 block" data-testid="total-events-count">{dashboard.total_events}</span>
                <p className="text-xs text-gray-400 mt-1">Last {days} day{days > 1 ? "s" : ""}</p>
              </div>
              <div className="iv-card p-5" data-testid="metric-critical-events">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Critical + High</p>
                <span className="text-3xl font-bold text-red-600 dark:text-red-400 mt-1 block">{(dashboard.severity_distribution.critical || 0) + (dashboard.severity_distribution.high || 0)}</span>
              </div>
              <div className="iv-card p-5" data-testid="metric-categories">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Active Sources</p>
                <span className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-1 block">{sources.length}</span>
                <p className="text-xs text-gray-400 mt-1">{Object.values(dashboard.category_distribution).filter(v => v > 0).length} categories active</p>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
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
              <div className="iv-card p-6" data-testid="critical-events-list">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">Critical & High Events</h3>
                {dashboard.critical_events.length === 0 ? (
                  <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
                    <div className="text-center"><ShieldCheck size={28} weight="duotone" className="mx-auto mb-2 text-green-400" /><p>No critical events</p></div>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[200px] overflow-y-auto">
                    {dashboard.critical_events.map(ev => {
                      const sev = SEVERITY_CONFIG[ev.severity] || SEVERITY_CONFIG.info;
                      return (
                        <div key={ev.id} className="flex items-start gap-3 p-3 rounded-xl border border-gray-100 dark:border-gray-800 hover:border-red-200 dark:hover:border-red-800/30 transition-colors" data-testid={`critical-event-${ev.id}`}>
                          <span className="px-1.5 py-0.5 text-[10px] font-bold rounded flex-shrink-0" style={{ color: sev.color, backgroundColor: sev.bg }}>{sev.label}</span>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate">{ev.details}</p>
                            <p className="text-[10px] text-gray-400 mt-0.5">{ev.source_name || ev.source} · {new Date(ev.timestamp).toLocaleString()}</p>
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

        {/* ===== EVENTS TAB ===== */}
        {tab === "events" && (
          <div className="space-y-4">
            <div className="iv-card p-4 flex items-center gap-3 flex-wrap" data-testid="siem-filters">
              <div className="relative flex-1 min-w-[200px]">
                <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <Input placeholder="Search events..." value={filter.search} onChange={(e) => setFilter({ ...filter, search: e.target.value })} className="pl-9 h-9 text-xs" data-testid="siem-search-input" />
              </div>
              <select value={filter.severity} onChange={(e) => setFilter({ ...filter, severity: e.target.value })} className="h-9 px-3 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800" data-testid="siem-severity-filter">
                <option value="">All Severities</option>
                {Object.entries(SEVERITY_CONFIG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
              <select value={filter.category} onChange={(e) => setFilter({ ...filter, category: e.target.value })} className="h-9 px-3 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800" data-testid="siem-category-filter">
                <option value="">All Categories</option>
                {Object.keys(CATEGORY_ICONS).map(k => <option key={k} value={k}>{k.replace(/_/g, " ")}</option>)}
              </select>
              <span className="text-xs text-gray-400">{filteredEvents.length} events</span>
              {simActive && <span className="text-xs text-green-500 font-semibold animate-pulse flex items-center gap-1"><Pulse size={12} weight="fill" /> Live updating</span>}
            </div>

            <div className="iv-card overflow-hidden" data-testid="siem-events-table">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400 w-[90px]">Severity</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400 w-[170px]">Timestamp</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400 w-[140px]">Event Type</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400">Details</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400 w-[120px]">Source</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 dark:text-gray-400 w-[120px]">Controls</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEvents.length === 0 ? (
                    <tr><td colSpan={6} className="py-12 text-center text-gray-400 text-sm">
                      <Lightning size={28} weight="duotone" className="mx-auto mb-2" />
                      {events.length === 0 ? "No events yet. Click 'Simulate Live' or 'Seed Demo'." : "No events match filters."}
                    </td></tr>
                  ) : filteredEvents.slice(0, 100).map((ev, idx) => {
                    const sev = SEVERITY_CONFIG[ev.severity] || SEVERITY_CONFIG.info;
                    const CatIcon = CATEGORY_ICONS[ev.category] || ShieldCheck;
                    const isNew = idx < liveCount && simActive;
                    return (
                      <tr key={ev.id} className={`border-b border-gray-100 dark:border-gray-800 last:border-0 hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition-colors ${isNew ? "bg-[#2597B2]/[0.03]" : ""}`} data-testid={`siem-event-row-${ev.id}`}>
                        <td className="py-2.5 px-4"><span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded" style={{ color: sev.color, backgroundColor: sev.bg }}>{sev.label}</span></td>
                        <td className="py-2.5 px-4 text-xs text-gray-500 dark:text-gray-400 font-mono">{new Date(ev.timestamp).toLocaleString(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })}</td>
                        <td className="py-2.5 px-4"><span className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300"><CatIcon size={12} weight="duotone" className="text-[#2597B2]" />{ev.event_type.replace(/_/g, " ")}</span></td>
                        <td className="py-2.5 px-4 text-xs text-gray-700 dark:text-gray-300 truncate max-w-[300px]">{ev.details}</td>
                        <td className="py-2.5 px-4 text-xs text-gray-500 dark:text-gray-400">{ev.source_name || ev.source}</td>
                        <td className="py-2.5 px-4">
                          {ev.mapped_controls?.length > 0 && (
                            <div className="flex flex-wrap gap-1">
                              {ev.mapped_controls.slice(0, 3).map(c => <span key={c} className="text-[9px] font-mono font-semibold px-1.5 py-0.5 bg-[#2597B2]/10 text-[#2597B2] rounded">{c}</span>)}
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

        {/* ===== CONTROL MAPPING TAB ===== */}
        {tab === "mapping" && (
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
                        <div className="w-8 h-8 rounded-lg bg-[#2597B2]/10 flex items-center justify-center"><CatIcon size={16} weight="duotone" className="text-[#2597B2]" /></div>
                        <div>
                          <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 capitalize">{cm.category.replace(/_/g, " ")}</p>
                          <p className="text-[10px] text-gray-400">{cm.description}</p>
                        </div>
                      </div>
                      <span className="text-xs font-bold text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded" data-testid={`mapping-count-${cm.category}`}>{cm.event_count_30d} events</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {cm.controls.map(ctrl => <span key={ctrl} className="text-[10px] font-mono font-semibold px-2 py-0.5 border border-[#2597B2]/20 text-[#2597B2] bg-[#2597B2]/5 rounded">{ctrl}</span>)}
                    </div>
                    <div className="flex gap-1.5 mt-2">
                      {cm.frameworks.map(fw => <span key={fw} className="text-[9px] font-medium text-gray-400 bg-gray-50 dark:bg-gray-800 px-1.5 py-0.5 rounded">{fw}</span>)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ===== SOURCES TAB ===== */}
        {tab === "sources" && (
          <div className="space-y-4">
            <div className="iv-card p-5" data-testid="sources-section">
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">External Sources</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Connect external SIEM tools to ingest events via webhook</p>
                </div>
                <Button size="sm" className="iv-btn-primary text-xs h-9" onClick={() => { setNewSource({ name: "", source_type: "splunk" }); setCreatedSource(null); setSourceDialogOpen(true); }} data-testid="add-source-btn">
                  <Plus size={14} className="mr-1" /> Add Source
                </Button>
              </div>

              {sources.length === 0 ? (
                <div className="py-10 text-center border border-dashed border-gray-200 dark:border-gray-700 rounded-xl">
                  <Plug size={32} weight="duotone" className="text-gray-300 dark:text-gray-600 mx-auto mb-3" />
                  <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">No external sources configured</p>
                  <p className="text-xs text-gray-400 mt-1">Click "Add Source" to connect Splunk, CloudTrail, QRadar, or any JSON webhook</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {sources.map(src => (
                    <div key={src.id} className="flex items-center gap-4 p-4 border border-gray-100 dark:border-gray-800 rounded-xl hover:border-[#2597B2]/20 transition-colors" data-testid={`source-${src.id}`}>
                      <div className="w-10 h-10 rounded-lg bg-[#2597B2]/10 flex items-center justify-center flex-shrink-0">
                        <Globe size={18} weight="duotone" className="text-[#2597B2]" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{src.name}</p>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2597B2]/10 text-[#2597B2] font-medium">{src.source_type}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${src.status === "active" ? "bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400" : "bg-gray-100 text-gray-500"}`}>{src.status}</span>
                        </div>
                        <div className="flex items-center gap-4 mt-1 text-xs text-gray-400">
                          <span>{src.event_count || 0} events</span>
                          {src.last_event_at && <span>Last: {new Date(src.last_event_at).toLocaleString()}</span>}
                          <span className="font-mono text-[10px]">key: ...{src.api_key?.slice(-8)}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Button variant="ghost" size="sm" className="text-xs h-8" onClick={() => copyToClipboard(`${webhookBaseUrl}${src.source_key}`)} title="Copy webhook URL"><Copy size={14} /></Button>
                        <Button variant="ghost" size="sm" className="text-xs h-8 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20" onClick={() => deleteSource(src.id)} data-testid={`delete-source-${src.id}`}><Trash size={14} /></Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* How it works */}
            <div className="iv-card p-5" data-testid="sources-howto">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">How Real-Time Ingestion Works</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                  { step: "1", title: "Create a Source", desc: "Register your external tool (Splunk, CloudTrail, QRadar). You'll get a unique webhook URL and API key." },
                  { step: "2", title: "Configure Webhook", desc: "In your SIEM tool, set the webhook URL and include the API key in the X-API-Key header." },
                  { step: "3", title: "Events Flow In", desc: "Events are automatically parsed, classified, and mapped to NIST controls in real-time." },
                ].map(s => (
                  <div key={s.step} className="flex gap-3">
                    <span className="w-7 h-7 rounded-lg bg-[#2597B2] text-white flex items-center justify-center text-xs font-bold flex-shrink-0">{s.step}</span>
                    <div>
                      <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">{s.title}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">{s.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Source Creation Dialog */}
      <Dialog open={sourceDialogOpen} onOpenChange={setSourceDialogOpen}>
        <DialogContent className="sm:max-w-[520px]" data-testid="source-dialog">
          <DialogHeader>
            <DialogTitle>{createdSource ? "Source Created" : "Add External Source"}</DialogTitle>
          </DialogHeader>

          {!createdSource ? (
            <div className="space-y-4 mt-2">
              <div>
                <Label className="text-sm font-medium">Source Name</Label>
                <Input placeholder="e.g., Production Splunk" value={newSource.name} onChange={(e) => setNewSource({ ...newSource, name: e.target.value })} className="mt-1" data-testid="source-name-input" />
              </div>
              <div>
                <Label className="text-sm font-medium">Source Type</Label>
                <div className="grid grid-cols-2 gap-2 mt-1.5">
                  {SOURCE_TYPES.map(st => (
                    <button
                      key={st.value}
                      onClick={() => setNewSource({ ...newSource, source_type: st.value })}
                      className={`flex items-center gap-2.5 p-3 rounded-xl border-2 transition-all ${
                        newSource.source_type === st.value ? "border-[#2597B2] bg-[#2597B2]/5" : "border-gray-100 dark:border-gray-800 hover:border-gray-200"
                      }`}
                      data-testid={`source-type-${st.value}`}
                    >
                      <st.icon size={18} weight="duotone" className={newSource.source_type === st.value ? "text-[#2597B2]" : "text-gray-400"} />
                      <span className={`text-sm font-medium ${newSource.source_type === st.value ? "text-[#2597B2]" : "text-gray-600 dark:text-gray-400"}`}>{st.label}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" size="sm" onClick={() => setSourceDialogOpen(false)}>Cancel</Button>
                <Button size="sm" className="iv-btn-primary" onClick={createSource} data-testid="create-source-btn">Create Source</Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4 mt-2" data-testid="source-created-info">
              <div className="p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl">
                <p className="text-sm font-semibold text-green-700 dark:text-green-400">Source created successfully!</p>
                <p className="text-xs text-green-600 dark:text-green-500 mt-0.5">Save these credentials — the API key won't be shown again.</p>
              </div>

              <div>
                <Label className="text-xs text-gray-500">Webhook URL</Label>
                <div className="flex items-center gap-2 mt-1">
                  <code className="flex-1 text-xs bg-gray-50 dark:bg-gray-800 p-2.5 rounded-lg border border-gray-200 dark:border-gray-700 break-all" data-testid="webhook-url-display">{webhookBaseUrl}{createdSource.source_key}</code>
                  <Button variant="ghost" size="sm" className="h-8" onClick={() => copyToClipboard(`${webhookBaseUrl}${createdSource.source_key}`)} data-testid="copy-webhook-btn"><Copy size={14} /></Button>
                </div>
              </div>

              <div>
                <Label className="text-xs text-gray-500">API Key (X-API-Key header)</Label>
                <div className="flex items-center gap-2 mt-1">
                  <code className="flex-1 text-xs bg-gray-50 dark:bg-gray-800 p-2.5 rounded-lg border border-gray-200 dark:border-gray-700 break-all" data-testid="api-key-display">{createdSource.api_key}</code>
                  <Button variant="ghost" size="sm" className="h-8" onClick={() => copyToClipboard(createdSource.api_key)} data-testid="copy-api-key-btn"><Copy size={14} /></Button>
                </div>
              </div>

              <div className="iv-card p-3 bg-gray-50 dark:bg-gray-800/50">
                <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">Example cURL</p>
                <code className="text-[10px] text-gray-500 dark:text-gray-400 leading-relaxed block whitespace-pre-wrap">
{`curl -X POST "${webhookBaseUrl}${createdSource.source_key}" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: ${createdSource.api_key}" \\
  -d '{"event_type":"login_failed","severity":"high","details":"Failed login from 1.2.3.4"}'`}
                </code>
              </div>

              <div className="flex justify-end pt-2">
                <Button size="sm" className="iv-btn-primary" onClick={() => setSourceDialogOpen(false)}>Done</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </Layout>
  );
};

export default SIEMPage;
