import React, { useState, useEffect, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import Layout from "@/components/Layout";
import {
  FileText, GitBranch, Warning, Calendar, ShieldCheck, ListChecks, Users,
  ArrowRight, Clock, DownloadSimple, CaretRight, Lightning, ChartBar, FolderOpen,
  TrendUp, TrendDown, Minus
} from "@phosphor-icons/react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, Area, AreaChart } from "recharts";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const Dashboard = () => {
  const { user } = useContext(AuthContext);
  const [analytics, setAnalytics] = useState(null);
  const [execSummary, setExecSummary] = useState(null);
  const [trendData, setTrendData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pdfLoading, setPdfLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/analytics/dashboard`).catch(() => ({ data: null })),
      axios.get(`${API}/reports/executive-summary`).catch(() => ({ data: null })),
      axios.get(`${API}/compliance-trends`).catch(() => ({ data: [] })),
    ]).then(([a, e, t]) => {
      setAnalytics(a.data);
      setExecSummary(e.data);
      setTrendData(Array.isArray(t.data) ? t.data : []);
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

  const riskChartData = analytics?.risk_distribution ? [
    { name: "Low", value: analytics.risk_distribution.low, color: "#10B981" },
    { name: "Medium", value: analytics.risk_distribution.medium, color: "#3B82F6" },
    { name: "High", value: analytics.risk_distribution.high, color: "#F59E0B" },
    { name: "Critical", value: analytics.risk_distribution.critical, color: "#EF4444" },
  ] : [];

  const frameworkChartData = (execSummary?.framework_scores || []).filter(f => f.total_controls > 0).slice(0, 6).map(f => ({
    name: f.framework_name.length > 20 ? f.framework_name.slice(0, 20) + "..." : f.framework_name,
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
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
              Dashboard
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Executive overview of your compliance and risk posture
            </p>
          </div>
          <Button 
            onClick={downloadPdf} 
            disabled={pdfLoading} 
            data-testid="download-pdf-report"
            className="iv-btn-primary"
          >
            <DownloadSimple size={16} weight="bold" />
            {pdfLoading ? "Generating..." : "Export PDF"}
          </Button>
        </div>

        {/* Compliance Score Hero */}
        <div className="iv-hero-card p-6" data-testid="compliance-score-hero">
          <div className="flex items-center justify-between relative z-10">
            <div className="flex items-center gap-8">
              {/* Grade Circle */}
              <div 
                className="iv-grade-circle" 
                style={{ 
                  '--grade-color': gradeStyle.border,
                  '--grade-percent': overallScore 
                }}
              >
                <div 
                  className="w-full h-full rounded-full flex items-center justify-center"
                  style={{ backgroundColor: gradeStyle.bg }}
                >
                  <span 
                    className="text-3xl font-bold"
                    style={{ color: gradeStyle.text }}
                  >
                    {overallGrade}
                  </span>
                </div>
              </div>
              
              <div>
                <p className="text-label mb-1">Overall Compliance Score</p>
                <p className="text-4xl font-bold text-gray-900 dark:text-gray-100">{overallScore}%</p>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  {execSummary?.total_mapped || 0} of {execSummary?.total_controls || 0} controls mapped across {execSummary?.total_frameworks || 0} frameworks
                </p>
              </div>
            </div>
            
            {/* Key Metrics */}
            <div className="hidden lg:flex items-center gap-8">
              {[
                { val: execSummary?.risk_summary?.open || 0, label: "Open Risks", color: "#F59E0B", warn: true },
                { val: execSummary?.task_summary?.overdue || 0, label: "Overdue Tasks", color: "#EF4444", warn: (execSummary?.task_summary?.overdue || 0) > 0 },
                { val: execSummary?.vendor_summary?.high_risk || 0, label: "High-Risk Vendors", color: "#6366F1" },
              ].map(m => (
                <div key={m.label} className="text-center">
                  <p 
                    className="text-2xl font-bold"
                    style={{ color: m.warn && m.val > 0 ? m.color : 'inherit' }}
                  >
                    {m.val}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{m.label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {[
            { t: "Policies", v: execSummary?.policies_count, icon: FileText, color: "#2597B2" },
            { t: "Mappings", v: execSummary?.total_mapped, icon: GitBranch, color: "#06B6D4" },
            { t: "Open Risks", v: execSummary?.risk_summary?.open, icon: Warning, color: "#F59E0B" },
            { t: "Audits", v: execSummary?.audit_summary?.total, icon: Calendar, color: "#10B981" },
            { t: "Tasks", v: execSummary?.task_summary?.total, icon: ListChecks, color: "#6366F1", sub: `${execSummary?.task_summary?.done || 0} completed` },
            { t: "Vendors", v: execSummary?.vendor_summary?.total, icon: Users, color: "#64748B" },
          ].map(s => (
            <div 
              key={s.t} 
              className="iv-stat-card"
              style={{ '--stat-color': s.color }}
              data-testid={`stat-${s.t.toLowerCase().replace(/\s/g, "-")}`}
            >
              <div className="flex items-start justify-between relative z-10">
                <div>
                  <p className="text-label">{s.t}</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-1">{s.v ?? 0}</p>
                  {s.sub && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{s.sub}</p>}
                </div>
                <div 
                  className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ backgroundColor: `${s.color}12` }}
                >
                  <s.icon size={20} weight="duotone" style={{ color: s.color }} />
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Framework Compliance */}
          <div className="iv-card p-6" data-testid="framework-compliance-chart">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Framework Compliance</h3>
              <a href="/frameworks" className="text-xs text-[#2597B2] hover:text-[#1B839F] flex items-center gap-1 font-medium transition-colors">
                View all <CaretRight size={12} weight="bold" />
              </a>
            </div>
            {frameworkChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={frameworkChartData} layout="vertical" margin={{ left: 0, right: 20, top: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" horizontal={true} vertical={false} />
                  <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12, fill: "#475569", fontWeight: 500 }} axisLine={false} tickLine={false} />
                  <Tooltip 
                    formatter={(v, _, p) => [`${v}% (${p.payload.mapped}/${p.payload.total} controls)`, "Compliance"]} 
                    contentStyle={{ 
                      fontSize: 12, 
                      borderRadius: 12, 
                      border: "1px solid #E2E8F0",
                      boxShadow: "0 10px 15px -3px rgba(0,0,0,0.06)"
                    }} 
                  />
                  <Bar dataKey="score" radius={[0, 6, 6, 0]} barSize={20}>
                    {frameworkChartData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="iv-empty-state h-64">
                <div className="iv-empty-state-icon">
                  <ChartBar size={28} weight="duotone" className="text-gray-400" />
                </div>
                <p className="iv-empty-state-title">No framework data</p>
                <p className="iv-empty-state-description">Start mapping controls to see compliance scores</p>
              </div>
            )}
          </div>

          {/* Risk Heatmap */}
          <div className="iv-card p-6" data-testid="risk-heatmap">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Risk Heatmap</h3>
              <a href="/risks" className="text-xs text-[#2597B2] hover:text-[#1B839F] flex items-center gap-1 font-medium transition-colors">
                View risks <CaretRight size={12} weight="bold" />
              </a>
            </div>
            {heatmap.length > 0 ? (
              <div className="flex flex-col items-center">
                <div className="flex items-end gap-1.5">
                  <div className="flex flex-col items-end pr-3 gap-1.5">
                    {[5,4,3,2,1].map(l => (
                      <div key={l} className="h-11 flex items-center">
                        <span className="text-xs text-gray-400 font-medium w-4 text-right">{l}</span>
                      </div>
                    ))}
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {[4,3,2,1,0].map(r => (
                      <div key={r} className="flex gap-1.5">
                        {[0,1,2,3,4].map(c => {
                          const count = heatmap[r]?.[c] || 0;
                          return (
                            <div 
                              key={c} 
                              className="w-11 h-11 rounded-lg flex items-center justify-center text-xs font-bold transition-all hover:scale-105 cursor-default"
                              style={{ 
                                backgroundColor: heatmapColor(count), 
                                color: count > 0 ? "#7C2D12" : "#CBD5E1",
                                boxShadow: count > 0 ? "inset 0 -2px 4px rgba(0,0,0,0.1)" : "none"
                              }}
                              title={`Likelihood: ${r+1}, Impact: ${c+1} - ${count} risk(s)`}
                              data-testid={`heatmap-cell-${r}-${c}`}
                            >
                              {count > 0 ? count : ""}
                            </div>
                          );
                        })}
                      </div>
                    ))}
                    <div className="flex gap-1.5 pt-2">
                      {[1,2,3,4,5].map(i => (
                        <div key={i} className="w-11 text-center">
                          <span className="text-xs text-gray-400 font-medium">{i}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-5 mt-4 text-xs text-gray-500">
                  {[["#F1F5F9","None"],["#FDE68A","1"],["#FB923C","2"],["#EF4444","3+"]].map(([bg,lbl]) => (
                    <span key={lbl} className="flex items-center gap-1.5">
                      <span 
                        className="w-4 h-4 rounded" 
                        style={{
                          backgroundColor: bg, 
                          border: bg === "#F1F5F9" ? "1px solid #E2E8F0" : "none",
                          boxShadow: bg !== "#F1F5F9" ? "inset 0 -1px 2px rgba(0,0,0,0.1)" : "none"
                        }} 
                      />
                      {lbl}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-3 font-medium">Likelihood (Y) vs Impact (X)</p>
              </div>
            ) : (
              <div className="iv-empty-state h-64">
                <div className="iv-empty-state-icon">
                  <Warning size={28} weight="duotone" className="text-gray-400" />
                </div>
                <p className="iv-empty-state-title">No risk data</p>
                <p className="iv-empty-state-description">Add risks to visualize the heatmap</p>
              </div>
            )}
          </div>
        </div>

        {/* Compliance Trend Timeline */}
        {trendData.length > 0 && (
          <div className="iv-card p-6" data-testid="compliance-trend-chart">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Compliance Trend</h3>
              <span className="iv-badge iv-badge-neutral">{trendData.length} data points</span>
            </div>
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={trendData.map(s => ({ ...s, label: s.date?.slice(5) || "" }))} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <defs>
                  <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2597B2" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="#2597B2" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} />
                <Tooltip
                  formatter={(v, name) => {
                    if (name === "score") return [`${v}%`, "Compliance Score"];
                    if (name === "open_risks") return [v, "Open Risks"];
                    return [v, name];
                  }}
                  contentStyle={{ 
                    fontSize: 12, 
                    borderRadius: 12, 
                    border: "1px solid #E2E8F0",
                    boxShadow: "0 10px 15px -3px rgba(0,0,0,0.06)"
                  }}
                />
                <Area type="monotone" dataKey="score" stroke="#2597B2" strokeWidth={2.5} fill="url(#trendGradient)" />
                <Line type="monotone" dataKey="open_risks" stroke="#F59E0B" strokeWidth={2} strokeDasharray="6 4" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
            <div className="flex items-center gap-8 mt-4 text-xs text-gray-500">
              <span className="flex items-center gap-2">
                <span className="w-4 h-0.5 rounded bg-[#2597B2]" />
                Compliance Score (%)
              </span>
              <span className="flex items-center gap-2">
                <span className="w-4 h-0.5 rounded" style={{ borderTop: "2px dashed #F59E0B" }} />
                Open Risks
              </span>
            </div>
          </div>
        )}

        {/* Overdue / Upcoming / Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Overdue */}
          <div className="iv-card p-5" data-testid="overdue-tasks-section">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <Warning size={16} weight="fill" className="text-red-500" /> 
                Overdue Tasks
              </h3>
              <a href="/tasks" className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium transition-colors">View all</a>
            </div>
            {!(analytics?.overdue_tasks?.length) ? (
              <div className="py-8 text-center">
                <div className="w-12 h-12 rounded-xl bg-green-50 dark:bg-green-900/20 flex items-center justify-center mx-auto mb-2">
                  <ListChecks size={24} weight="duotone" className="text-green-500" />
                </div>
                <p className="text-sm text-gray-500">No overdue tasks</p>
              </div>
            ) : (
              <div className="space-y-2">
                {(analytics.overdue_tasks).map(t => (
                  <div 
                    key={t.id} 
                    className="flex items-center justify-between p-3 bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/20 rounded-xl transition-all hover:border-red-200"
                    data-testid={`overdue-task-${t.id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{t.title}</p>
                      <p className="text-xs text-red-600 dark:text-red-400 mt-0.5">Due: {t.due_date}</p>
                    </div>
                    <span 
                      className="ml-3 px-2.5 py-1 rounded-full text-xs font-semibold"
                      style={{ 
                        color: priorityStyles[t.priority]?.text, 
                        backgroundColor: priorityStyles[t.priority]?.bg 
                      }}
                    >
                      {t.priority}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
          
          {/* Upcoming */}
          <div className="iv-card p-5" data-testid="upcoming-deadlines-section">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <Clock size={16} weight="duotone" className="text-[#2597B2]" /> 
                Upcoming Deadlines
              </h3>
              <a href="/tasks" className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium transition-colors">View all</a>
            </div>
            {!(analytics?.upcoming_deadlines?.length) ? (
              <div className="py-8 text-center">
                <div className="w-12 h-12 rounded-xl bg-gray-50 dark:bg-gray-800 flex items-center justify-center mx-auto mb-2">
                  <Clock size={24} weight="duotone" className="text-gray-400" />
                </div>
                <p className="text-sm text-gray-500">No upcoming deadlines</p>
              </div>
            ) : (
              <div className="space-y-2">
                {(analytics.upcoming_deadlines).map(t => (
                  <div 
                    key={t.id} 
                    className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-700 rounded-xl transition-all hover:border-gray-200 dark:hover:border-gray-600"
                    data-testid={`upcoming-task-${t.id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{t.title}</p>
                      <p className="text-xs text-gray-500 mt-0.5">Due: {t.due_date}</p>
                    </div>
                    <span 
                      className="ml-3 px-2.5 py-1 rounded-full text-xs font-semibold"
                      style={{ 
                        color: priorityStyles[t.priority]?.text, 
                        backgroundColor: priorityStyles[t.priority]?.bg 
                      }}
                    >
                      {t.priority}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
          
          {/* Recent Activity */}
          <div className="iv-card p-5" data-testid="recent-activity-section">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <Lightning size={16} weight="fill" className="text-[#2597B2]" /> 
                Recent Activity
              </h3>
              <a href="/activity" className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium transition-colors">View all</a>
            </div>
            {!(analytics?.recent_activity?.length) ? (
              <div className="py-8 text-center">
                <div className="w-12 h-12 rounded-xl bg-gray-50 dark:bg-gray-800 flex items-center justify-center mx-auto mb-2">
                  <Lightning size={24} weight="duotone" className="text-gray-400" />
                </div>
                <p className="text-sm text-gray-500">No recent activity</p>
              </div>
            ) : (
              <div className="space-y-1">
                {(analytics.recent_activity).slice(0, 6).map(a => {
                  const ActIcon = actionIconMap[a.action] || ChartBar;
                  return (
                    <div 
                      key={a.id} 
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors cursor-default"
                      data-testid={`activity-item-${a.id}`}
                    >
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#e8f6f9] to-[#d1eef4] dark:from-[#0a3540] dark:to-[#15697f] flex items-center justify-center flex-shrink-0 mt-0.5">
                        <ActIcon size={14} weight="duotone" className="text-[#1B839F]" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-700 dark:text-gray-300 leading-relaxed">{a.details}</p>
                        <p className="text-xs text-gray-400 mt-1">{a.user_name} · {formatTimeAgo(a.timestamp)}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Risk Distribution + Quick Actions */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="iv-card p-6" data-testid="risk-distribution-chart">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-6">Risk Distribution</h3>
            {riskChartData.some(d => d.value > 0) ? (
              <div className="flex items-center justify-center">
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie 
                      data={riskChartData} 
                      cx="50%" 
                      cy="50%" 
                      labelLine={false}
                      label={({name, value, cx, cy, midAngle, innerRadius, outerRadius}) => {
                        if (value === 0) return null;
                        const RADIAN = Math.PI / 180;
                        const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
                        const x = cx + radius * Math.cos(-midAngle * RADIAN);
                        const y = cy + radius * Math.sin(-midAngle * RADIAN);
                        return (
                          <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={12} fontWeight={600}>
                            {value}
                          </text>
                        );
                      }}
                      outerRadius={100}
                      innerRadius={50}
                      dataKey="value"
                      strokeWidth={2}
                      stroke="#fff"
                    >
                      {riskChartData.map((e, i) => <Cell key={i} fill={e.color} />)}
                    </Pie>
                    <Tooltip 
                      formatter={(value, name) => [value, name]}
                      contentStyle={{ 
                        fontSize: 12, 
                        borderRadius: 12, 
                        border: "1px solid #E2E8F0",
                        boxShadow: "0 10px 15px -3px rgba(0,0,0,0.06)"
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="iv-empty-state h-56">
                <div className="iv-empty-state-icon">
                  <Warning size={28} weight="duotone" className="text-gray-400" />
                </div>
                <p className="iv-empty-state-title">No risk data</p>
                <p className="iv-empty-state-description">Add risks to see the distribution</p>
              </div>
            )}
            {riskChartData.some(d => d.value > 0) && (
              <div className="flex items-center justify-center gap-6 mt-4">
                {riskChartData.map(d => (
                  <span key={d.name} className="flex items-center gap-2 text-xs text-gray-500">
                    <span className="w-3 h-3 rounded-full" style={{ backgroundColor: d.color }} />
                    {d.name}: {d.value}
                  </span>
                ))}
              </div>
            )}
          </div>
          
          <div className="iv-card p-6" data-testid="quick-actions">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-6">Quick Actions</h3>
            <div className="grid grid-cols-1 gap-3">
              {[
                { href: "/policies", title: "Create New Policy", desc: "Build compliance policies with AI", icon: FileText, color: "#2597B2" },
                { href: "/mappings", title: "AI-Powered Mapping", desc: "Map policies to controls", icon: GitBranch, color: "#06B6D4" },
                { href: "/tasks", title: "Create Task", desc: "Add a remediation task", icon: ListChecks, color: "#6366F1" },
                { href: "/risks", title: "Assess Risk", desc: "Add or review a risk", icon: Warning, color: "#F59E0B" },
                { href: "/evidence", title: "Upload Evidence", desc: "Add compliance evidence", icon: FolderOpen, color: "#10B981" },
              ].map(item => (
                <a 
                  key={item.href} 
                  href={item.href} 
                  className="group flex items-center justify-between p-4 border border-gray-200/60 dark:border-gray-700/60 rounded-xl hover:border-[#2597B2]/40 hover:bg-gradient-to-r hover:from-[#e8f6f9]/40 hover:to-transparent dark:hover:from-[#0a3540]/30 transition-all duration-200"
                  data-testid={`quick-action-${item.href.slice(1)}`}
                >
                  <div className="flex items-center gap-4">
                    <div 
                      className="w-11 h-11 rounded-xl flex items-center justify-center transition-transform group-hover:scale-105"
                      style={{ backgroundColor: `${item.color}12` }}
                    >
                      <item.icon size={22} weight="duotone" style={{ color: item.color }} />
                    </div>
                    <div>
                      <p className="font-semibold text-gray-900 dark:text-gray-100 text-sm group-hover:text-[#1B839F] transition-colors">{item.title}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{item.desc}</p>
                    </div>
                  </div>
                  <ArrowRight size={16} weight="bold" className="text-gray-300 group-hover:text-[#2597B2] group-hover:translate-x-1 transition-all" />
                </a>
              ))}
            </div>
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
