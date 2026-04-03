import React, { useState, useEffect, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import Layout from "@/components/Layout";
import {
  FileText, GitBranch, Warning, Calendar, ShieldCheck, ListChecks, Users,
  ArrowRight, Clock, DownloadSimple, CaretRight, Lightning, ChartBar, FolderOpen
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
      toast.success("Report downloaded");
    } catch { toast.error("Failed to generate report"); } finally { setPdfLoading(false); }
  };

  const riskChartData = analytics?.risk_distribution ? [
    { name: "Low", value: analytics.risk_distribution.low, color: "#4ADE80" },
    { name: "Medium", value: analytics.risk_distribution.medium, color: "#60A5FA" },
    { name: "High", value: analytics.risk_distribution.high, color: "#FB923C" },
    { name: "Critical", value: analytics.risk_distribution.critical, color: "#EF4444" },
  ] : [];

  const frameworkChartData = (execSummary?.framework_scores || []).filter(f => f.total_controls > 0).slice(0, 6).map(f => ({
    name: f.framework_name.length > 18 ? f.framework_name.slice(0, 18) + "..." : f.framework_name,
    score: f.score, mapped: f.mapped_controls, total: f.total_controls,
    fill: f.score >= 80 ? "#4ADE80" : f.score >= 50 ? "#2597B2" : f.score >= 20 ? "#FB923C" : "#EF4444"
  }));

  const overallScore = execSummary?.overall_compliance_score || 0;
  const overallGrade = execSummary?.overall_grade || "F";
  const gradeColor = { A: "#4ADE80", B: "#2597B2", C: "#FB923C", D: "#EF4444", F: "#EF4444" };
  const heatmap = analytics?.risk_heatmap || [];
  const heatmapColor = (c) => c === 0 ? "#F3F4F6" : c === 1 ? "#FDE68A" : c === 2 ? "#FB923C" : "#EF4444";
  const priorityColor = { critical: "#EF4444", high: "#FB923C", medium: "#2597B2", low: "#4ADE80" };
  const actionIconMap = { policy_created: FileText, risk_created: Warning, task_created: ListChecks, task_updated: ListChecks, vendor_created: Users, evidence_added: ShieldCheck, mapping_created: GitBranch };

  if (loading) return (
    <Layout>
      <div className="flex items-center justify-center h-64" data-testid="dashboard-loading">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-[#2597B2] border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-500 dark:text-gray-400 text-sm">Loading dashboard...</p>
        </div>
      </div>
    </Layout>
  );

  return (
    <Layout>
      <div data-testid="dashboard-page">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">Dashboard</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5">Executive overview of your compliance and risk posture</p>
          </div>
          <Button onClick={downloadPdf} disabled={pdfLoading} data-testid="download-pdf-report"
            className="bg-[#2597B2] hover:bg-[#1B839F] text-white rounded-xl flex items-center gap-2 px-4 shadow-sm">
            <DownloadSimple size={16} weight="bold" />
            {pdfLoading ? "Generating..." : "Export PDF"}
          </Button>
        </div>

        {/* Compliance Score Hero */}
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-6 mb-6 shadow-sm" data-testid="compliance-score-hero">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div className="w-20 h-20 rounded-full border-4 flex items-center justify-center" style={{ borderColor: gradeColor[overallGrade] || "#9CA3AF" }}>
                <span className="text-3xl font-bold" style={{ color: gradeColor[overallGrade] }}>{overallGrade}</span>
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">Overall Compliance Score</p>
                <p className="text-4xl font-bold text-gray-900 dark:text-gray-100 mt-1">{overallScore}%</p>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  {execSummary?.total_mapped || 0} of {execSummary?.total_controls || 0} controls mapped across {execSummary?.total_frameworks || 0} frameworks
                </p>
              </div>
            </div>
            <div className="hidden md:flex items-center gap-8">
              {[
                { val: execSummary?.risk_summary?.open || 0, label: "Open Risks", warn: true },
                { val: execSummary?.task_summary?.overdue || 0, label: "Overdue Tasks", warn: (execSummary?.task_summary?.overdue || 0) > 0 },
                { val: execSummary?.vendor_summary?.high_risk || 0, label: "High-Risk Vendors" },
              ].map(m => (
                <div key={m.label} className="text-center">
                  <p className={`text-2xl font-bold ${m.warn ? "text-[#FB923C]" : "text-gray-900 dark:text-gray-100"}`}>{m.val}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{m.label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
          {[
            { t: "Policies", v: execSummary?.policies_count, icon: FileText, color: "#2597B2" },
            { t: "Mappings", v: execSummary?.total_mapped, icon: GitBranch, color: "#1B839F" },
            { t: "Open Risks", v: execSummary?.risk_summary?.open, icon: Warning, color: "#FB923C" },
            { t: "Audits", v: execSummary?.audit_summary?.total, icon: Calendar, color: "#4ADE80" },
            { t: "Tasks", v: execSummary?.task_summary?.total, icon: ListChecks, color: "#2597B2", sub: `${execSummary?.task_summary?.done || 0} done` },
            { t: "Vendors", v: execSummary?.vendor_summary?.total, icon: Users, color: "#8EA7AE" },
          ].map(s => (
            <div key={s.t} className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-5 shadow-sm iv-card" data-testid={`stat-${s.t.toLowerCase().replace(/\s/g, "-")}`}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[0.625rem] font-bold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">{s.t}</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-1">{s.v ?? 0}</p>
                  {s.sub && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{s.sub}</p>}
                </div>
                <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${s.color}15` }}>
                  <s.icon size={18} weight="duotone" style={{ color: s.color }} />
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* Framework Compliance */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-6 shadow-sm" data-testid="framework-compliance-chart">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">Framework Compliance</h3>
              <a href="/frameworks" className="text-xs text-[#2597B2] hover:underline flex items-center gap-1 font-medium">View all <CaretRight size={10} /></a>
            </div>
            {frameworkChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={frameworkChartData} layout="vertical" margin={{ left: 10, right: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                  <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11, fill: "#9CA3AF" }} />
                  <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11, fill: "#6B7280" }} />
                  <Tooltip formatter={(v, _, p) => [`${v}% (${p.payload.mapped}/${p.payload.total})`, "Score"]} contentStyle={{ fontSize: 12, borderRadius: 12, border: "1px solid #E5E7EB" }} />
                  <Bar dataKey="score" radius={[0, 6, 6, 0]} barSize={16}>
                    {frameworkChartData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="h-60 flex items-center justify-center text-gray-400 dark:text-gray-500"><p>No framework data</p></div>}
          </div>

          {/* Risk Heatmap */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-6 shadow-sm" data-testid="risk-heatmap">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">Risk Heatmap</h3>
              <a href="/risks" className="text-xs text-[#2597B2] hover:underline flex items-center gap-1 font-medium">View risks <CaretRight size={10} /></a>
            </div>
            {heatmap.length > 0 ? (
              <div className="flex flex-col items-center">
                <div className="flex items-end gap-1">
                  <div className="flex flex-col items-end pr-2 gap-1">
                    {[5,4,3,2,1].map(l => <div key={l} className="h-10 flex items-center"><span className="text-xs text-gray-400 w-3 text-right">{l}</span></div>)}
                  </div>
                  <div className="flex flex-col gap-1">
                    {[4,3,2,1,0].map(r => (
                      <div key={r} className="flex gap-1">
                        {[0,1,2,3,4].map(c => {
                          const count = heatmap[r]?.[c] || 0;
                          return (
                            <div key={c} className="w-10 h-10 rounded-lg flex items-center justify-center text-xs font-bold transition-all"
                              style={{ backgroundColor: heatmapColor(count), color: count > 0 ? "#7C2D12" : "#D1D5DB" }}
                              title={`L:${r+1} I:${c+1} - ${count} risk(s)`}
                              data-testid={`heatmap-cell-${r}-${c}`}
                            >{count > 0 ? count : ""}</div>
                          );
                        })}
                      </div>
                    ))}
                    <div className="flex gap-1 pt-1">{[1,2,3,4,5].map(i => <div key={i} className="w-10 text-center"><span className="text-xs text-gray-400">{i}</span></div>)}</div>
                  </div>
                </div>
                <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
                  {[["#F3F4F6","None"],["#FDE68A","1"],["#FB923C","2"],["#EF4444","3+"]].map(([bg,lbl]) => (
                    <span key={lbl} className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{backgroundColor:bg, border: bg==="#F3F4F6" ? "1px solid #E5E7EB" : "none"}} />{lbl}</span>
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-2">Likelihood (Y) vs Impact (X)</p>
              </div>
            ) : <div className="h-60 flex items-center justify-center text-gray-400"><p>No risk data</p></div>}
          </div>
        </div>

        {/* Compliance Trend Timeline */}
        {trendData.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-6 mb-6 shadow-sm" data-testid="compliance-trend-chart">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">Compliance Trend</h3>
              <span className="text-xs text-gray-400 dark:text-gray-500">{trendData.length} data points</span>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={trendData.map(s => ({ ...s, label: s.date?.slice(5) || "" }))} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <defs>
                  <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2597B2" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#2597B2" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#9CA3AF" }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "#9CA3AF" }} />
                <Tooltip
                  formatter={(v, name) => {
                    if (name === "score") return [`${v}%`, "Score"];
                    if (name === "open_risks") return [v, "Open Risks"];
                    return [v, name];
                  }}
                  contentStyle={{ fontSize: 12, borderRadius: 12, border: "1px solid #E5E7EB" }}
                />
                <Area type="monotone" dataKey="score" stroke="#2597B2" strokeWidth={2} fill="url(#trendGradient)" />
                <Line type="monotone" dataKey="open_risks" stroke="#FB923C" strokeWidth={1.5} strokeDasharray="4 4" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
            <div className="flex items-center gap-6 mt-2 text-xs text-gray-400">
              <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 rounded bg-[#2597B2]" />Compliance Score (%)</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 rounded bg-[#FB923C]" style={{borderTop: "2px dashed #FB923C"}} />Open Risks</span>
            </div>
          </div>
        )}

        {/* Overdue / Upcoming / Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          {/* Overdue */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-5 shadow-sm" data-testid="overdue-tasks-section">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2"><Warning size={16} weight="duotone" className="text-red-500" /> Overdue Tasks</h3>
              <a href="/tasks" className="text-xs text-[#2597B2] hover:underline font-medium">View all</a>
            </div>
            {!(analytics?.overdue_tasks?.length) ? <p className="text-sm text-gray-400 py-4 text-center">No overdue tasks</p> : (
              <div className="space-y-2">{(analytics.overdue_tasks).map(t => (
                <div key={t.id} className="flex items-center justify-between p-2.5 bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/20 rounded-xl" data-testid={`overdue-task-${t.id}`}>
                  <div className="flex-1 min-w-0"><p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{t.title}</p><p className="text-xs text-red-600 dark:text-red-400">Due: {t.due_date}</p></div>
                  <span className="ml-2 px-2 py-0.5 rounded-full text-xs font-bold" style={{ color: priorityColor[t.priority], backgroundColor: `${priorityColor[t.priority]}15` }}>{t.priority}</span>
                </div>
              ))}</div>
            )}
          </div>
          {/* Upcoming */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-5 shadow-sm" data-testid="upcoming-deadlines-section">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2"><Clock size={16} weight="duotone" className="text-[#2597B2]" /> Upcoming Deadlines</h3>
              <a href="/tasks" className="text-xs text-[#2597B2] hover:underline font-medium">View all</a>
            </div>
            {!(analytics?.upcoming_deadlines?.length) ? <p className="text-sm text-gray-400 py-4 text-center">No upcoming deadlines</p> : (
              <div className="space-y-2">{(analytics.upcoming_deadlines).map(t => (
                <div key={t.id} className="flex items-center justify-between p-2.5 bg-gray-50 dark:bg-gray-700/30 border border-gray-100 dark:border-gray-700 rounded-xl" data-testid={`upcoming-task-${t.id}`}>
                  <div className="flex-1 min-w-0"><p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{t.title}</p><p className="text-xs text-gray-500">Due: {t.due_date}</p></div>
                  <span className="ml-2 px-2 py-0.5 rounded-full text-xs font-bold" style={{ color: priorityColor[t.priority], backgroundColor: `${priorityColor[t.priority]}15` }}>{t.priority}</span>
                </div>
              ))}</div>
            )}
          </div>
          {/* Recent Activity */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-5 shadow-sm" data-testid="recent-activity-section">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2"><Lightning size={16} weight="duotone" className="text-[#2597B2]" /> Recent Activity</h3>
              <a href="/activity" className="text-xs text-[#2597B2] hover:underline font-medium">View all</a>
            </div>
            {!(analytics?.recent_activity?.length) ? <p className="text-sm text-gray-400 py-4 text-center">No recent activity</p> : (
              <div className="space-y-1.5">{(analytics.recent_activity).slice(0, 6).map(a => {
                const ActIcon = actionIconMap[a.action] || ChartBar;
                return (
                  <div key={a.id} className="flex items-start gap-2.5 p-2 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors" data-testid={`activity-item-${a.id}`}>
                    <div className="w-7 h-7 rounded-lg bg-[#e8f4f7] dark:bg-[#0a3540] flex items-center justify-center flex-shrink-0 mt-0.5">
                      <ActIcon size={13} weight="duotone" className="text-[#1B839F]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-gray-800 dark:text-gray-200 leading-relaxed">{a.details}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{a.user_name} &middot; {formatTimeAgo(a.timestamp)}</p>
                    </div>
                  </div>
                );
              })}</div>
            )}
          </div>
        </div>

        {/* Risk Distribution + Quick Actions */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-6 shadow-sm" data-testid="risk-distribution-chart">
            <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 mb-4">Risk Distribution</h3>
            {riskChartData.some(d => d.value > 0) ? (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={riskChartData} cx="50%" cy="50%" labelLine={false}
                    label={({name, value}) => value > 0 ? `${name}: ${value}` : ""}
                    outerRadius={85} fill="#8884d8" dataKey="value">
                    {riskChartData.map((e, i) => <Cell key={i} fill={e.color} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : <div className="h-56 flex items-center justify-center text-gray-400"><p>No risk data</p></div>}
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-6 shadow-sm" data-testid="quick-actions">
            <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 mb-4">Quick Actions</h3>
            <div className="grid grid-cols-1 gap-2.5">
              {[
                { href: "/policies", title: "Create New Policy", desc: "Add a compliance policy", icon: FileText },
                { href: "/mappings", title: "AI-Powered Mapping", desc: "Map policies to controls", icon: GitBranch },
                { href: "/tasks", title: "Create Task", desc: "Add a remediation task", icon: ListChecks },
                { href: "/risks", title: "Assess Risk", desc: "Add or review a risk", icon: Warning },
                { href: "/evidence", title: "Upload Evidence", desc: "Add compliance evidence", icon: FolderOpen },
              ].map(item => (
                <a key={item.href} href={item.href} className="flex items-center justify-between p-3.5 border border-gray-200/50 dark:border-gray-700/50 rounded-xl hover:border-[#2597B2] hover:bg-[#e8f4f7]/30 dark:hover:bg-[#0a3540]/30 transition-all" data-testid={`quick-action-${item.href.slice(1)}`}>
                  <div className="flex items-center gap-3">
                    <item.icon size={20} weight="duotone" className="text-[#2597B2]" />
                    <div>
                      <p className="font-semibold text-gray-900 dark:text-gray-100 text-sm">{item.title}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{item.desc}</p>
                    </div>
                  </div>
                  <ArrowRight size={14} className="text-gray-400" />
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
