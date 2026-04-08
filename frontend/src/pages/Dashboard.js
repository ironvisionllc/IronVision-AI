import React, { useState, useEffect, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import Layout from "@/components/Layout";
import {
  FileText, GitBranch, Warning, Calendar, ShieldCheck, ListChecks, Users,
  ArrowRight, Clock, DownloadSimple, CaretRight, Lightning, ChartBar, FolderOpen,
  TrendUp, TrendDown, Minus, Gauge, Eye, CaretDown
} from "@phosphor-icons/react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area } from "recharts";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const TAB_KEYS = ["overdue", "upcoming", "activity"];

const Dashboard = () => {
  const { user } = useContext(AuthContext);
  const [analytics, setAnalytics] = useState(null);
  const [execSummary, setExecSummary] = useState(null);
  const [trendData, setTrendData] = useState([]);
  const [controlHealth, setControlHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [activityTab, setActivityTab] = useState("overdue");

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/analytics/dashboard`).catch(() => ({ data: null })),
      axios.get(`${API}/reports/executive-summary`).catch(() => ({ data: null })),
      axios.get(`${API}/compliance-trends`).catch(() => ({ data: [] })),
      axios.get(`${API}/control-effectiveness/dashboard`).catch(() => ({ data: null })),
    ]).then(([a, e, t, ch]) => {
      setAnalytics(a.data);
      setExecSummary(e.data);
      setTrendData(Array.isArray(t.data) ? t.data : []);
      setControlHealth(ch.data);
    }).finally(() => setLoading(false));
  }, []);

  const downloadPdf = async () => {
    setPdfLoading(true);
    try {
      const res = await axios.get(`${API}/reports/executive-pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `compliance_report_${new Date().toISOString().slice(0,10)}.pdf`;
      document.body.appendChild(link); link.click(); link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Report downloaded successfully");
    } catch { toast.error("Failed to generate report"); } finally { setPdfLoading(false); }
  };

  const frameworkChartData = (execSummary?.framework_scores || []).filter(f => f.total_controls > 0).slice(0, 6).map(f => ({
    name: f.framework_name.length > 18 ? f.framework_name.slice(0, 18) + "..." : f.framework_name,
    score: f.score, mapped: f.mapped_controls, total: f.total_controls,
    fill: f.score >= 80 ? "#10B981" : f.score >= 60 ? "#2597B2" : f.score >= 40 ? "#F59E0B" : "#EF4444"
  }));

  const overallScore = execSummary?.overall_compliance_score || 0;
  const overallGrade = execSummary?.overall_grade || "F";
  const gradeColors = { 
    A: { text: "#059669", bg: "#D1FAE5", border: "#10B981" }, 
    B: { text: "#0891B2", bg: "#CFFAFE", border: "#06B6D4" }, 
    C: { text: "#D97706", bg: "#FEF3C7", border: "#F59E0B" }, 
    D: { text: "#DC2626", bg: "#FEE2E2", border: "#EF4444" }, 
    F: { text: "#DC2626", bg: "#FEE2E2", border: "#EF4444" } 
  };
  const gradeStyle = gradeColors[overallGrade] || gradeColors.F;

  const heatmap = analytics?.risk_heatmap || [];
  const heatmapColor = (c) => c === 0 ? "#F1F5F9" : c === 1 ? "#FDE68A" : c === 2 ? "#FB923C" : "#EF4444";
  const priorityStyles = { 
    critical: { text: "#DC2626", bg: "rgba(239, 68, 68, 0.1)" },
    high: { text: "#D97706", bg: "rgba(245, 158, 11, 0.1)" },
    medium: { text: "#0891B2", bg: "rgba(6, 182, 212, 0.1)" },
    low: { text: "#059669", bg: "rgba(16, 185, 129, 0.1)" }
  };
  const actionIconMap = { policy_created: FileText, risk_created: Warning, task_created: ListChecks, task_updated: ListChecks, vendor_created: Users, evidence_added: ShieldCheck, mapping_created: GitBranch };

  const openRisks = execSummary?.risk_summary?.open || 0;
  const overdueTasks = execSummary?.task_summary?.overdue || 0;
  const pendingAudits = execSummary?.audit_summary?.total || 0;
  const effectivenessScore = controlHealth?.overall_score ?? 0;

  // Attention items for the command bar
  const attentionItems = [];
  if (openRisks > 0) attentionItems.push({ label: `${openRisks} Open Risk${openRisks > 1 ? "s" : ""}`, href: "/risks", color: "#F59E0B", icon: Warning });
  if (overdueTasks > 0) attentionItems.push({ label: `${overdueTasks} Overdue Task${overdueTasks > 1 ? "s" : ""}`, href: "/tasks", color: "#EF4444", icon: Clock });
  if (effectivenessScore < 50 && controlHealth) attentionItems.push({ label: `Control Health: ${effectivenessScore}%`, href: "/frameworks", color: "#EF4444", icon: Gauge });

  if (loading) return (
    <Layout>
      <div className="flex items-center justify-center h-[60vh]" data-testid="dashboard-loading">
        <div className="flex flex-col items-center gap-4">
          <div className="iv-spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
          <p className="text-gray-500 dark:text-gray-400 text-sm font-medium">Loading dashboard...</p>
        </div>
      </div>
    </Layout>
  );

  return (
    <Layout>
      <div data-testid="dashboard-page" className="space-y-6">
        {/* Command Bar — What Needs Attention */}
        {attentionItems.length > 0 && (
          <div className="iv-card p-0 overflow-hidden" data-testid="command-bar" style={{ borderLeft: "4px solid #2597B2" }}>
            <div className="flex items-center gap-4 px-5 py-4">
              <div className="flex-shrink-0 w-9 h-9 rounded-lg bg-[#2597B2]/10 flex items-center justify-center">
                <Eye size={18} weight="duotone" className="text-[#2597B2]" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">Needs Your Attention</p>
                <div className="flex flex-wrap gap-3 mt-1.5">
                  {attentionItems.map(item => (
                    <a 
                      key={item.label} 
                      href={item.href} 
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all hover:scale-[1.02]"
                      style={{ color: item.color, backgroundColor: `${item.color}12`, border: `1px solid ${item.color}25` }}
                      data-testid={`attention-${item.href.slice(1)}`}
                    >
                      <item.icon size={13} weight="bold" />
                      {item.label}
                      <ArrowRight size={11} weight="bold" />
                    </a>
                  ))}
                </div>
              </div>
              <Button 
                onClick={downloadPdf} 
                disabled={pdfLoading} 
                data-testid="download-pdf-report"
                className="iv-btn-secondary text-xs h-9"
                size="sm"
              >
                <DownloadSimple size={14} weight="bold" />
                {pdfLoading ? "Generating..." : "Export Report"}
              </Button>
            </div>
          </div>
        )}

        {/* 4 Key Metrics */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="key-metrics">
          {/* Compliance Score */}
          <div className="iv-card p-5" data-testid="metric-compliance-score">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Compliance</p>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-3xl font-bold text-gray-900 dark:text-gray-100">{overallScore}%</span>
                  <span 
                    className="text-xs font-bold px-2 py-0.5 rounded"
                    style={{ color: gradeStyle.text, backgroundColor: gradeStyle.bg }}
                  >
                    {overallGrade}
                  </span>
                </div>
                <p className="text-xs text-gray-400 mt-1">{execSummary?.total_mapped || 0} of {execSummary?.total_controls || 0} controls</p>
              </div>
              <div className="relative w-14 h-14">
                <svg viewBox="0 0 48 48" className="w-full h-full -rotate-90">
                  <circle cx="24" cy="24" r="20" fill="none" stroke="#F1F5F9" strokeWidth="4" className="dark:stroke-gray-800" />
                  <circle cx="24" cy="24" r="20" fill="none" stroke={gradeStyle.border} strokeWidth="4" strokeLinecap="round" strokeDasharray={`${(overallScore / 100) * 125.6} 125.6`} />
                </svg>
              </div>
            </div>
          </div>

          {/* Open Risks */}
          <div className="iv-card p-5" data-testid="metric-open-risks">
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Open Risks</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-bold text-gray-900 dark:text-gray-100">{openRisks}</span>
              {execSummary?.risk_summary?.high > 0 && (
                <span className="text-xs font-bold px-2 py-0.5 rounded text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400">
                  {execSummary.risk_summary.high} high
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400 mt-1">{execSummary?.risk_summary?.total || 0} total risks</p>
            <a href="/risks" className="text-xs text-[#2597B2] font-medium flex items-center gap-1 mt-2 hover:text-[#1B839F] transition-colors" data-testid="review-risks-link">
              Review <ArrowRight size={11} weight="bold" />
            </a>
          </div>

          {/* Active Tasks */}
          <div className="iv-card p-5" data-testid="metric-active-tasks">
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Tasks</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-bold text-gray-900 dark:text-gray-100">{execSummary?.task_summary?.total || 0}</span>
              {overdueTasks > 0 && (
                <span className="text-xs font-bold px-2 py-0.5 rounded text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400">
                  {overdueTasks} overdue
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400 mt-1">{execSummary?.task_summary?.done || 0} completed</p>
            <a href="/tasks" className="text-xs text-[#2597B2] font-medium flex items-center gap-1 mt-2 hover:text-[#1B839F] transition-colors" data-testid="manage-tasks-link">
              Manage <ArrowRight size={11} weight="bold" />
            </a>
          </div>

          {/* Control Effectiveness */}
          <div className="iv-card p-5" data-testid="metric-effectiveness">
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Control Health</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-bold text-gray-900 dark:text-gray-100">{effectivenessScore}</span>
              <span className="text-sm text-gray-400">/100</span>
            </div>
            <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden mt-2">
              <div className="h-full rounded-full transition-all duration-700" style={{ 
                width: `${effectivenessScore}%`, 
                backgroundColor: effectivenessScore >= 75 ? "#10B981" : effectivenessScore >= 50 ? "#2597B2" : effectivenessScore >= 25 ? "#F59E0B" : "#EF4444" 
              }} />
            </div>
            <p className="text-xs text-gray-400 mt-1">{controlHealth?.total_frameworks || 0} frameworks, {controlHealth?.total_controls_sampled || 0} controls</p>
          </div>
        </div>

        {/* Charts Row — Framework Compliance + Risk Heatmap */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Framework Compliance */}
          <div className="iv-card p-6" data-testid="framework-compliance-chart">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Framework Compliance</h3>
              <a href="/frameworks" className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium flex items-center gap-1 transition-colors">View all <CaretRight size={12} weight="bold" /></a>
            </div>
            {frameworkChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={frameworkChartData} layout="vertical" margin={{ left: 5, right: 20, top: 5, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E2E8F010" />
                  <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="name" width={120} fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip 
                    formatter={(v, n, p) => [`${p.payload.mapped}/${p.payload.total} controls (${v}%)`, "Coverage"]}
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E2E8F0", boxShadow: "0 4px 12px rgba(0,0,0,0.06)" }}
                  />
                  <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={14}>
                    {frameworkChartData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-56 flex items-center justify-center text-gray-400 text-sm">
                <div className="text-center">
                  <ChartBar size={28} weight="duotone" className="mx-auto mb-2" />
                  <p>No framework data</p>
                </div>
              </div>
            )}
          </div>

          {/* Risk Heatmap */}
          <div className="iv-card p-6" data-testid="risk-distribution-chart">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Risk Heatmap</h3>
              <a href="/risks" className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium flex items-center gap-1 transition-colors">View risks <CaretRight size={12} weight="bold" /></a>
            </div>
            <div className="flex justify-center">
              <div>
                <div className="text-xs text-gray-400 mb-1 text-center font-medium">Likelihood (Y) vs Impact (X)</div>
                {[5,4,3,2,1].map(y => (
                  <div key={y} className="flex items-center gap-1">
                    <span className="w-5 text-xs text-gray-400 text-right">{y}</span>
                    {[1,2,3,4,5].map(x => {
                      const cell = heatmap.find(c => c.likelihood === y && c.impact === x);
                      const count = cell?.count || 0;
                      return (
                        <div
                          key={`${x}-${y}`}
                          className="w-10 h-10 flex items-center justify-center text-xs font-bold rounded-lg border border-white/60 dark:border-gray-700/60 transition-all hover:scale-105"
                          style={{ backgroundColor: heatmapColor(count), color: count > 0 ? "#1E293B" : "#CBD5E1" }}
                          data-testid={`heatmap-${x}-${y}`}
                        >
                          {count > 0 ? count : ""}
                        </div>
                      );
                    })}
                  </div>
                ))}
                <div className="flex gap-1 ml-6 mt-1">{[1,2,3,4,5].map(x => <span key={x} className="w-10 text-center text-xs text-gray-400">{x}</span>)}</div>
                <div className="flex items-center justify-center gap-4 mt-3">
                  {[{ l: "None", c: "#F1F5F9" }, { l: "1", c: "#FDE68A" }, { l: "2", c: "#FB923C" }, { l: "3+", c: "#EF4444" }].map(d => (
                    <span key={d.l} className="flex items-center gap-1.5 text-[10px] text-gray-500">
                      <span className="w-2.5 h-2.5 rounded" style={{ backgroundColor: d.c }} />{d.l}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Compliance Trend + Control Effectiveness */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Compliance Trend */}
          <div className="iv-card p-6" data-testid="compliance-trend-section">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Compliance Trend</h3>
              <span className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500">{trendData.length} data points</span>
            </div>
            {trendData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={trendData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                  <defs>
                    <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#2597B2" stopOpacity={0.15} />
                      <stop offset="100%" stopColor="#2597B2" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F010" />
                  <XAxis dataKey="date" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 100]} fontSize={10} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E2E8F0" }} />
                  <Area type="monotone" dataKey="score" stroke="#2597B2" strokeWidth={2} fill="url(#trendGrad)" />
                  {trendData[0]?.effectiveness !== undefined && (
                    <Area type="monotone" dataKey="effectiveness" stroke="#F59E0B" strokeWidth={2} fill="none" strokeDasharray="4 4" />
                  )}
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-48 flex items-center justify-center text-gray-400 text-sm">No trend data yet</div>
            )}
          </div>

          {/* Control Effectiveness by Framework */}
          {controlHealth && controlHealth.total_frameworks > 0 && (
            <div className="iv-card p-6" data-testid="control-health-widget">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Gauge size={16} weight="duotone" className="text-[#2597B2]" />
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Control Effectiveness</h3>
                </div>
                <a href="/frameworks" className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium flex items-center gap-1 transition-colors">Details <CaretRight size={12} weight="bold" /></a>
              </div>
              <div className="flex items-center gap-5 mb-4">
                <div className="relative w-20 h-20 flex-shrink-0">
                  <svg viewBox="0 0 80 80" className="w-full h-full -rotate-90">
                    <circle cx="40" cy="40" r="34" fill="none" stroke="#F1F5F9" strokeWidth="7" className="dark:stroke-gray-800" />
                    <circle cx="40" cy="40" r="34" fill="none" stroke={effectivenessScore >= 75 ? "#10B981" : effectivenessScore >= 50 ? "#2597B2" : effectivenessScore >= 25 ? "#F59E0B" : "#EF4444"} strokeWidth="7" strokeLinecap="round" strokeDasharray={`${(effectivenessScore / 100) * 213.6} 213.6`} />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-lg font-bold text-gray-900 dark:text-gray-100" data-testid="control-health-score">{effectivenessScore}</span>
                  </div>
                </div>
                <div className="flex-1">
                  <span className="text-xs font-semibold px-2 py-0.5 rounded" style={{
                    color: effectivenessScore >= 75 ? "#059669" : effectivenessScore >= 50 ? "#0891B2" : effectivenessScore >= 25 ? "#D97706" : "#DC2626",
                    backgroundColor: effectivenessScore >= 75 ? "#D1FAE5" : effectivenessScore >= 50 ? "#CFFAFE" : effectivenessScore >= 25 ? "#FEF3C7" : "#FEE2E2",
                  }} data-testid="control-health-grade">{controlHealth.overall_grade}</span>
                  <div className="flex h-1.5 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-800 mt-2.5">
                    {[
                      { key: "excellent", color: "#059669", val: controlHealth.distribution.excellent },
                      { key: "good", color: "#06B6D4", val: controlHealth.distribution.good },
                      { key: "fair", color: "#F59E0B", val: controlHealth.distribution.fair },
                      { key: "needs_improvement", color: "#F97316", val: controlHealth.distribution.needs_improvement },
                      { key: "critical", color: "#EF4444", val: controlHealth.distribution.critical },
                    ].filter(d => d.val > 0).map(d => (
                      <div key={d.key} className="h-full" style={{ width: `${(d.val / controlHealth.total_controls_sampled) * 100}%`, backgroundColor: d.color }} data-testid={`distribution-bar-${d.key}`} />
                    ))}
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1">{controlHealth.total_controls_sampled} controls across {controlHealth.total_frameworks} frameworks</p>
                </div>
              </div>
              <div className="space-y-1.5 max-h-[140px] overflow-y-auto">
                {controlHealth.frameworks.sort((a, b) => b.average_score - a.average_score).slice(0, 8).map(fw => {
                  const scoreColor = fw.average_score >= 75 ? "#10B981" : fw.average_score >= 50 ? "#2597B2" : fw.average_score >= 25 ? "#F59E0B" : "#EF4444";
                  return (
                    <div key={fw.framework_id} className="flex items-center gap-3" data-testid={`fw-health-${fw.framework_id}`}>
                      <span className="text-[11px] text-gray-600 dark:text-gray-400 w-[130px] truncate">{fw.framework_name}</span>
                      <div className="flex-1 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${fw.average_score}%`, backgroundColor: scoreColor }} />
                      </div>
                      <span className="text-[11px] font-semibold w-7 text-right" style={{ color: scoreColor }}>{fw.average_score}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Activity Center — Tabbed */}
        <div className="iv-card overflow-hidden" data-testid="activity-center">
          <div className="flex items-center border-b border-gray-100 dark:border-gray-800">
            {[
              { key: "overdue", label: "Overdue", icon: Warning, count: analytics?.overdue_tasks?.length || 0, color: "#EF4444" },
              { key: "upcoming", label: "Upcoming", icon: Clock, count: analytics?.upcoming_deadlines?.length || 0, color: "#2597B2" },
              { key: "activity", label: "Activity", icon: Lightning, count: analytics?.recent_activity?.length || 0, color: "#6366F1" },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setActivityTab(tab.key)}
                className={`flex items-center gap-2 px-5 py-3.5 text-sm font-medium transition-all border-b-2 ${
                  activityTab === tab.key 
                    ? "border-[#2597B2] text-[#2597B2]" 
                    : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                }`}
                data-testid={`activity-tab-${tab.key}`}
              >
                <tab.icon size={15} weight={activityTab === tab.key ? "fill" : "regular"} />
                {tab.label}
                {tab.count > 0 && (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full" style={{ 
                    backgroundColor: activityTab === tab.key ? `${tab.color}15` : "#F1F5F9",
                    color: activityTab === tab.key ? tab.color : "#71717A",
                  }}>{tab.count}</span>
                )}
              </button>
            ))}
            <div className="flex-1" />
            <a href={activityTab === "activity" ? "/activity" : "/tasks"} className="px-4 text-xs text-[#2597B2] hover:text-[#1B839F] font-medium flex items-center gap-1 transition-colors">View all <CaretRight size={11} weight="bold" /></a>
          </div>
          <div className="p-5 min-h-[180px]">
            {/* Overdue Tab */}
            {activityTab === "overdue" && (
              !(analytics?.overdue_tasks?.length) ? (
                <div className="py-8 text-center">
                  <ListChecks size={28} weight="duotone" className="text-green-400 mx-auto mb-2" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">All clear — no overdue tasks</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {analytics.overdue_tasks.map(t => (
                    <div key={t.id} className="flex items-center justify-between p-3 bg-red-50/50 dark:bg-red-900/10 border border-red-100/70 dark:border-red-900/20 rounded-xl" data-testid={`overdue-task-${t.id}`}>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{t.title}</p>
                        <p className="text-xs text-red-500 mt-0.5">Due: {t.due_date}</p>
                      </div>
                      <span className="ml-3 px-2 py-0.5 rounded text-xs font-semibold" style={{ color: priorityStyles[t.priority]?.text, backgroundColor: priorityStyles[t.priority]?.bg }}>{t.priority}</span>
                    </div>
                  ))}
                </div>
              )
            )}
            {/* Upcoming Tab */}
            {activityTab === "upcoming" && (
              !(analytics?.upcoming_deadlines?.length) ? (
                <div className="py-8 text-center">
                  <Clock size={28} weight="duotone" className="text-gray-400 mx-auto mb-2" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">No upcoming deadlines</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {analytics.upcoming_deadlines.map(t => (
                    <div key={t.id} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-700 rounded-xl" data-testid={`upcoming-task-${t.id}`}>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{t.title}</p>
                        <p className="text-xs text-gray-500 mt-0.5">Due: {t.due_date}</p>
                      </div>
                      <span className="ml-3 px-2 py-0.5 rounded text-xs font-semibold" style={{ color: priorityStyles[t.priority]?.text, backgroundColor: priorityStyles[t.priority]?.bg }}>{t.priority}</span>
                    </div>
                  ))}
                </div>
              )
            )}
            {/* Activity Tab */}
            {activityTab === "activity" && (
              !(analytics?.recent_activity?.length) ? (
                <div className="py-8 text-center">
                  <Lightning size={28} weight="duotone" className="text-gray-400 mx-auto mb-2" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">No recent activity</p>
                </div>
              ) : (
                <div className="space-y-0.5">
                  {analytics.recent_activity.slice(0, 8).map(a => {
                    const ActIcon = actionIconMap[a.action] || ChartBar;
                    return (
                      <div key={a.id} className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors" data-testid={`activity-item-${a.id}`}>
                        <div className="w-7 h-7 rounded-lg bg-[#2597B2]/10 dark:bg-[#2597B2]/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <ActIcon size={13} weight="duotone" className="text-[#2597B2]" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-gray-700 dark:text-gray-300 leading-relaxed">{a.details}</p>
                          <p className="text-[10px] text-gray-400 mt-0.5">{a.user_name} · {formatTimeAgo(a.timestamp)}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="iv-card p-5" data-testid="quick-actions">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Quick Actions</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {[
              { href: "/policies", title: "New Policy", icon: FileText, color: "#2597B2" },
              { href: "/mappings", title: "AI Mapping", icon: GitBranch, color: "#06B6D4" },
              { href: "/tasks", title: "Create Task", icon: ListChecks, color: "#6366F1" },
              { href: "/risks", title: "Assess Risk", icon: Warning, color: "#F59E0B" },
              { href: "/evidence", title: "Upload Evidence", icon: FolderOpen, color: "#10B981" },
            ].map(item => (
              <a 
                key={item.href} 
                href={item.href} 
                className="group flex items-center gap-3 p-3 border border-gray-100 dark:border-gray-800 rounded-xl hover:border-[#2597B2]/30 hover:bg-[#2597B2]/[0.02] transition-all"
                data-testid={`quick-action-${item.href.slice(1)}`}
              >
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${item.color}12` }}>
                  <item.icon size={16} weight="duotone" style={{ color: item.color }} />
                </div>
                <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 group-hover:text-[#2597B2] transition-colors">{item.title}</span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  );
};

function formatTimeAgo(ts) {
  if (!ts) return "";
  const now = new Date(), t = new Date(ts), diff = Math.floor((now - t) / 60000);
  if (diff < 1) return "just now";
  if (diff < 60) return `${diff}m ago`;
  const hr = Math.floor(diff / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return t.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default Dashboard;
