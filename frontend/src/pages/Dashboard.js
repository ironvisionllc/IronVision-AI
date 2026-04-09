import React, { useState, useEffect, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import Layout from "@/components/Layout";
import {
  FileText, GitBranch, Warning, ShieldCheck, ListChecks,
  ArrowRight, Clock, DownloadSimple, CaretRight, Gauge, Eye,
  TrendUp, Lightning, ChartBar, Sparkle, Target, ArrowsClockwise,
  CheckCircle, XCircle,
} from "@phosphor-icons/react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, AreaChart, Area } from "recharts";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const Dashboard = () => {
  const { user } = useContext(AuthContext);
  const [analytics, setAnalytics] = useState(null);
  const [execSummary, setExecSummary] = useState(null);
  const [trendData, setTrendData] = useState([]);
  const [controlHealth, setControlHealth] = useState(null);
  const [siemDash, setSiemDash] = useState(null);
  const [aiInsight, setAiInsight] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pdfLoading, setPdfLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/analytics/dashboard`).catch(() => ({ data: null })),
      axios.get(`${API}/reports/executive-summary`).catch(() => ({ data: null })),
      axios.get(`${API}/compliance-trends`).catch(() => ({ data: [] })),
      axios.get(`${API}/control-effectiveness/dashboard`).catch(() => ({ data: null })),
      axios.get(`${API}/siem/dashboard?days=7`).catch(() => ({ data: null })),
    ]).then(([a, e, t, ch, s]) => {
      setAnalytics(a.data);
      setExecSummary(e.data);
      setTrendData(Array.isArray(t.data) ? t.data : []);
      setControlHealth(ch.data);
      setSiemDash(s.data);
    }).finally(() => setLoading(false));
  }, []);

  const fetchAiInsight = async () => {
    setAiLoading(true);
    try {
      const context = {
        compliance_score: execSummary?.overall_compliance_score || 0,
        grade: execSummary?.overall_grade || "N/A",
        open_risks: execSummary?.risk_summary?.open || 0,
        high_risks: execSummary?.risk_summary?.high || 0,
        total_policies: execSummary?.total_policies || 0,
        total_controls: execSummary?.total_controls || 0,
        mapped_controls: execSummary?.total_mapped || 0,
        overdue_tasks: execSummary?.task_summary?.overdue || 0,
        effectiveness_score: controlHealth?.overall_score || 0,
        siem_threat_level: siemDash?.threat_level || 0,
        siem_critical_events: siemDash?.severity_distribution?.critical || 0,
        frameworks: (execSummary?.framework_scores || []).map(f => ({ name: f.framework_name, score: f.score })),
      };
      const res = await axios.post(`${API}/copilot/chat`, {
        message: `As a GRC expert, analyze this compliance posture and provide: 1) A brief assessment (2 sentences), 2) Top 3 priority actions, 3) A risk forecast for the next 30 days. Data: ${JSON.stringify(context)}`,
      });
      setAiInsight(res.data.response);
    } catch {
      setAiInsight("Unable to generate AI insights at this time. Please try again.");
    }
    setAiLoading(false);
  };

  const downloadPdf = async () => {
    setPdfLoading(true);
    try {
      const res = await axios.get(`${API}/reports/executive-pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a"); a.href = url; a.download = `compliance_report_${new Date().toISOString().slice(0,10)}.pdf`; document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
      toast.success("Report downloaded");
    } catch { toast.error("Failed to generate report"); }
    setPdfLoading(false);
  };

  if (loading) return (
    <Layout>
      <div className="flex items-center justify-center h-[60vh]" data-testid="dashboard-loading">
        <div className="flex flex-col items-center gap-4">
          <div className="iv-spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
          <p className="text-gray-500 dark:text-gray-400 text-sm font-medium">Loading command center...</p>
        </div>
      </div>
    </Layout>
  );

  const overallScore = execSummary?.overall_compliance_score || 0;
  const overallGrade = execSummary?.overall_grade || "F";
  const effectivenessScore = controlHealth?.overall_score ?? 0;
  const openRisks = execSummary?.risk_summary?.open || 0;
  const highRisks = execSummary?.risk_summary?.high || 0;
  const overdueTasks = execSummary?.task_summary?.overdue || 0;
  const threatLevel = siemDash?.threat_level || 0;
  const totalPolicies = execSummary?.total_policies || 0;
  const totalMapped = execSummary?.total_mapped || 0;
  const totalControls = execSummary?.total_controls || 0;
  const gcol = (s) => s >= 80 ? "#059669" : s >= 60 ? "#0891B2" : s >= 40 ? "#D97706" : "#DC2626";
  const gbg = (s) => s >= 80 ? "#D1FAE5" : s >= 60 ? "#CFFAFE" : s >= 40 ? "#FEF3C7" : "#FEE2E2";
  const frameworkChartData = (execSummary?.framework_scores || []).filter(f => f.total_controls > 0).slice(0, 8).map(f => ({
    name: f.framework_name.length > 20 ? f.framework_name.slice(0, 20) + "…" : f.framework_name,
    score: f.score, mapped: f.mapped_controls, total: f.total_controls,
    fill: f.score >= 80 ? "#10B981" : f.score >= 60 ? "#2597B2" : f.score >= 40 ? "#F59E0B" : "#EF4444"
  }));

  // Heatmap
  const heatmap = analytics?.risk_heatmap || [];
  const hmColor = (c) => c === 0 ? "#F1F5F9" : c === 1 ? "#FDE68A" : c === 2 ? "#FB923C" : "#EF4444";

  return (
    <Layout>
      <div data-testid="dashboard-page" className="space-y-6">

        {/* ===== POSTURE OVERVIEW ===== */}
        <div className="iv-card p-0 overflow-hidden" data-testid="posture-overview">
          <div className="p-6 pb-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">Compliance Posture</h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Real-time view of your organization's GRC health</p>
              </div>
              <div className="flex items-center gap-2">
                <Button onClick={fetchAiInsight} disabled={aiLoading} size="sm" className="iv-btn-primary text-xs h-8" data-testid="ai-insight-btn">
                  <Sparkle size={13} weight="fill" className="mr-1" />
                  {aiLoading ? "Analyzing..." : "AI Analysis"}
                </Button>
                <Button onClick={downloadPdf} disabled={pdfLoading} size="sm" className="iv-btn-secondary text-xs h-8" data-testid="download-pdf-report">
                  <DownloadSimple size={13} className="mr-1" /> Export
                </Button>
              </div>
            </div>

            {/* 5 Key Metrics */}
            <div className="grid grid-cols-5 gap-3" data-testid="key-metrics">
              {/* Compliance */}
              <div className="p-4 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/30" data-testid="metric-compliance-score">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-gray-400">Compliance</p>
                    <div className="flex items-baseline gap-1.5 mt-1">
                      <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">{overallScore}%</span>
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{ color: gcol(overallScore), backgroundColor: gbg(overallScore) }}>{overallGrade}</span>
                    </div>
                    <p className="text-[10px] text-gray-400 mt-0.5">{totalMapped}/{totalControls} controls</p>
                  </div>
                  <div className="relative w-11 h-11">
                    <svg viewBox="0 0 48 48" className="w-full h-full -rotate-90"><circle cx="24" cy="24" r="19" fill="none" stroke="#F1F5F9" strokeWidth="4" className="dark:stroke-gray-700" /><circle cx="24" cy="24" r="19" fill="none" stroke={gcol(overallScore)} strokeWidth="4" strokeLinecap="round" strokeDasharray={`${(overallScore / 100) * 119.4} 119.4`} /></svg>
                  </div>
                </div>
              </div>

              {/* Control Health */}
              <div className="p-4 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/30" data-testid="metric-effectiveness">
                <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-gray-400">Control Health</p>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">{effectivenessScore}</span>
                  <span className="text-xs text-gray-400">/100</span>
                </div>
                <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden mt-1.5">
                  <div className="h-full rounded-full transition-all duration-700" style={{ width: `${effectivenessScore}%`, backgroundColor: gcol(effectivenessScore) }} />
                </div>
                <p className="text-[10px] text-gray-400 mt-0.5">{controlHealth?.total_frameworks || 0} frameworks</p>
              </div>

              {/* Risk */}
              <div className="p-4 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/30" data-testid="metric-open-risks">
                <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-gray-400">Open Risks</p>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">{openRisks}</span>
                  {highRisks > 0 && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400">{highRisks} high</span>}
                </div>
                <a href="/risks" className="text-[10px] text-[#2597B2] font-medium flex items-center gap-0.5 mt-1.5 hover:text-[#1B839F]">Review <ArrowRight size={9} weight="bold" /></a>
              </div>

              {/* Security */}
              <div className="p-4 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/30" data-testid="metric-security">
                <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-gray-400">Threat Level</p>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className="text-2xl font-bold" style={{ color: threatLevel >= 70 ? "#DC2626" : threatLevel >= 40 ? "#D97706" : "#059669" }}>{threatLevel}</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{ color: threatLevel >= 70 ? "#DC2626" : threatLevel >= 40 ? "#D97706" : "#059669", backgroundColor: threatLevel >= 70 ? "#FEE2E2" : threatLevel >= 40 ? "#FEF3C7" : "#D1FAE5" }}>
                    {threatLevel >= 70 ? "Critical" : threatLevel >= 40 ? "Elevated" : "Low"}
                  </span>
                </div>
                <a href="/siem" className="text-[10px] text-[#2597B2] font-medium flex items-center gap-0.5 mt-1.5 hover:text-[#1B839F]">Monitor <ArrowRight size={9} weight="bold" /></a>
              </div>

              {/* Tasks */}
              <div className="p-4 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/30" data-testid="metric-active-tasks">
                <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-gray-400">Tasks</p>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">{execSummary?.task_summary?.total || 0}</span>
                  {overdueTasks > 0 && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400">{overdueTasks} overdue</span>}
                </div>
                <a href="/tasks" className="text-[10px] text-[#2597B2] font-medium flex items-center gap-0.5 mt-1.5 hover:text-[#1B839F]">Manage <ArrowRight size={9} weight="bold" /></a>
              </div>
            </div>
          </div>

          {/* Attention Bar */}
          {(openRisks > 0 || overdueTasks > 0 || effectivenessScore < 50) && (
            <div className="px-6 py-3 bg-amber-50/50 dark:bg-amber-900/10 border-t border-amber-100 dark:border-amber-900/20 flex items-center gap-4" data-testid="command-bar">
              <Warning size={16} weight="fill" className="text-amber-500 flex-shrink-0" />
              <div className="flex flex-wrap gap-3 text-xs">
                {openRisks > 0 && <a href="/risks" className="font-semibold text-amber-700 dark:text-amber-400 hover:underline">{openRisks} open risk{openRisks > 1 ? "s" : ""} need review</a>}
                {overdueTasks > 0 && <a href="/tasks" className="font-semibold text-red-600 dark:text-red-400 hover:underline">{overdueTasks} overdue task{overdueTasks > 1 ? "s" : ""}</a>}
                {effectivenessScore < 50 && <a href="/frameworks" className="font-semibold text-amber-700 dark:text-amber-400 hover:underline">Control health below 50%</a>}
              </div>
            </div>
          )}
        </div>

        {/* ===== AI INSIGHT PANEL ===== */}
        {aiInsight && (
          <div className="iv-card p-5" data-testid="ai-insight-panel" style={{ borderLeft: "4px solid #2597B2" }}>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5" style={{ background: "linear-gradient(135deg, #2597B2, #1B839F)" }}>
                <Sparkle size={16} weight="fill" className="text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-[#2597B2] mb-1.5">AI Compliance Analyst</p>
                <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">{aiInsight}</div>
              </div>
              <button onClick={() => setAiInsight(null)} className="text-gray-400 hover:text-gray-600 p-1"><XCircle size={16} /></button>
            </div>
          </div>
        )}

        {/* ===== FRAMEWORK POSTURE MAP + RISK HEATMAP ===== */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Framework Posture — wider */}
          <div className="lg:col-span-3 iv-card p-6" data-testid="framework-compliance-chart">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Framework Coverage</h3>
                <p className="text-[10px] text-gray-400 mt-0.5">Policy + technical control mapping across frameworks</p>
              </div>
              <a href="/frameworks" className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium flex items-center gap-1">All frameworks <CaretRight size={11} weight="bold" /></a>
            </div>
            {frameworkChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={frameworkChartData} layout="vertical" margin={{ left: 5, right: 20, top: 5, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E2E8F010" />
                  <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="name" width={140} fontSize={10} tickLine={false} axisLine={false} />
                  <Tooltip formatter={(v, n, p) => [`${p.payload.mapped}/${p.payload.total} controls (${v}%)`, "Coverage"]} contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #E2E8F0" }} />
                  <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={16}>
                    {frameworkChartData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-56 flex items-center justify-center text-gray-400 text-sm"><ChartBar size={28} weight="duotone" className="mr-2" />No framework data</div>
            )}
          </div>

          {/* Risk Heatmap — narrower */}
          <div className="lg:col-span-2 iv-card p-6" data-testid="risk-distribution-chart">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Risk Heatmap</h3>
              <a href="/risks" className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium flex items-center gap-1">Details <CaretRight size={11} weight="bold" /></a>
            </div>
            <div className="flex justify-center">
              <div>
                <div className="text-[10px] text-gray-400 mb-1 text-center font-medium">Likelihood vs Impact</div>
                {[5,4,3,2,1].map(y => (
                  <div key={y} className="flex items-center gap-1">
                    <span className="w-4 text-[10px] text-gray-400 text-right">{y}</span>
                    {[1,2,3,4,5].map(x => {
                      const cell = heatmap.find(c => c.likelihood === y && c.impact === x);
                      const count = cell?.count || 0;
                      return <div key={`${x}-${y}`} className="w-9 h-9 flex items-center justify-center text-[10px] font-bold rounded-md border border-white/60 dark:border-gray-700/60" style={{ backgroundColor: hmColor(count), color: count > 0 ? "#1E293B" : "#CBD5E1" }} data-testid={`heatmap-${x}-${y}`}>{count > 0 ? count : ""}</div>;
                    })}
                  </div>
                ))}
                <div className="flex gap-1 ml-5 mt-1">{[1,2,3,4,5].map(x => <span key={x} className="w-9 text-center text-[10px] text-gray-400">{x}</span>)}</div>
              </div>
            </div>
          </div>
        </div>

        {/* ===== TREND + CONTROL EFFECTIVENESS ===== */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Compliance Trend */}
          <div className="iv-card p-6" data-testid="compliance-trend-section">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Compliance Trend</h3>
            </div>
            {trendData.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={trendData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                  <defs><linearGradient id="tg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2597B2" stopOpacity={0.15} /><stop offset="100%" stopColor="#2597B2" stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F010" /><XAxis dataKey="date" fontSize={9} tickLine={false} axisLine={false} /><YAxis domain={[0, 100]} fontSize={9} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #E2E8F0" }} />
                  <Area type="monotone" dataKey="score" stroke="#2597B2" strokeWidth={2} fill="url(#tg)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <div className="h-44 flex items-center justify-center text-gray-400 text-sm">No trend data yet</div>}
          </div>

          {/* Control Effectiveness */}
          {controlHealth && controlHealth.total_frameworks > 0 && (
            <div className="iv-card p-6" data-testid="control-health-widget">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2"><Gauge size={15} weight="duotone" className="text-[#2597B2]" /><h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Control Effectiveness</h3></div>
                <a href="/frameworks" className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium flex items-center gap-1">Details <CaretRight size={11} weight="bold" /></a>
              </div>
              <div className="flex items-center gap-5 mb-3">
                <div className="relative w-16 h-16 flex-shrink-0">
                  <svg viewBox="0 0 64 64" className="w-full h-full -rotate-90"><circle cx="32" cy="32" r="27" fill="none" stroke="#F1F5F9" strokeWidth="6" className="dark:stroke-gray-800" /><circle cx="32" cy="32" r="27" fill="none" stroke={gcol(effectivenessScore)} strokeWidth="6" strokeLinecap="round" strokeDasharray={`${(effectivenessScore / 100) * 169.6} 169.6`} /></svg>
                  <div className="absolute inset-0 flex items-center justify-center"><span className="text-base font-bold text-gray-900 dark:text-gray-100" data-testid="control-health-score">{effectivenessScore}</span></div>
                </div>
                <div className="flex-1">
                  <span className="text-xs font-semibold px-2 py-0.5 rounded" style={{ color: gcol(effectivenessScore), backgroundColor: gbg(effectivenessScore) }} data-testid="control-health-grade">{controlHealth.overall_grade}</span>
                  <div className="flex h-1.5 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-800 mt-2">
                    {["excellent","good","fair","needs_improvement","critical"].map(k => {
                      const v = controlHealth.distribution[k]; const colors = { excellent:"#059669", good:"#06B6D4", fair:"#F59E0B", needs_improvement:"#F97316", critical:"#EF4444" };
                      return v > 0 ? <div key={k} className="h-full" style={{ width: `${(v / controlHealth.total_controls_sampled) * 100}%`, backgroundColor: colors[k] }} data-testid={`distribution-bar-${k}`} /> : null;
                    })}
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1">{controlHealth.total_controls_sampled} controls · {controlHealth.total_frameworks} frameworks</p>
                </div>
              </div>
              <div className="space-y-1.5 max-h-[110px] overflow-y-auto">
                {controlHealth.frameworks.sort((a, b) => b.average_score - a.average_score).slice(0, 6).map(fw => (
                  <div key={fw.framework_id} className="flex items-center gap-3" data-testid={`fw-health-${fw.framework_id}`}>
                    <span className="text-[10px] text-gray-600 dark:text-gray-400 w-[120px] truncate">{fw.framework_name}</span>
                    <div className="flex-1 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden"><div className="h-full rounded-full" style={{ width: `${fw.average_score}%`, backgroundColor: gcol(fw.average_score) }} /></div>
                    <span className="text-[10px] font-semibold w-6 text-right" style={{ color: gcol(fw.average_score) }}>{fw.average_score}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ===== ACTION ITEMS + QUICK ACTIONS ===== */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Overdue */}
          <div className="iv-card p-5" data-testid="overdue-section">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
              <Clock size={14} weight="duotone" className="text-red-500" /> Overdue Tasks
            </h3>
            {!(analytics?.overdue_tasks?.length) ? (
              <div className="py-6 text-center"><CheckCircle size={24} weight="duotone" className="text-green-400 mx-auto mb-1.5" /><p className="text-xs text-gray-400">All clear</p></div>
            ) : (
              <div className="space-y-2">
                {analytics.overdue_tasks.slice(0, 4).map(t => (
                  <div key={t.id} className="flex items-center justify-between p-2.5 bg-red-50/50 dark:bg-red-900/10 border border-red-100/70 dark:border-red-900/20 rounded-lg" data-testid={`overdue-task-${t.id}`}>
                    <div className="flex-1 min-w-0"><p className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">{t.title}</p><p className="text-[10px] text-red-500">Due: {t.due_date}</p></div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Upcoming */}
          <div className="iv-card p-5" data-testid="upcoming-section">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
              <ArrowsClockwise size={14} weight="duotone" className="text-[#2597B2]" /> Upcoming
            </h3>
            {!(analytics?.upcoming_deadlines?.length) ? (
              <div className="py-6 text-center"><Clock size={24} weight="duotone" className="text-gray-300 mx-auto mb-1.5" /><p className="text-xs text-gray-400">No upcoming deadlines</p></div>
            ) : (
              <div className="space-y-2">
                {analytics.upcoming_deadlines.slice(0, 4).map(t => (
                  <div key={t.id} className="flex items-center justify-between p-2.5 bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-700 rounded-lg">
                    <div className="flex-1 min-w-0"><p className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">{t.title}</p><p className="text-[10px] text-gray-500">Due: {t.due_date}</p></div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Actions */}
          <div className="iv-card p-5" data-testid="quick-actions">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
              <Lightning size={14} weight="duotone" className="text-amber-500" /> Quick Actions
            </h3>
            <div className="space-y-2">
              {[
                { href: "/policies", title: "Generate Policy", desc: "AI-powered policy creation", icon: FileText, color: "#2597B2" },
                { href: "/frameworks", title: "Map Controls", desc: "Map policies to frameworks", icon: GitBranch, color: "#06B6D4" },
                { href: "/risks", title: "Assess Risk", desc: "Create or review risks", icon: Warning, color: "#F59E0B" },
                { href: "/tasks", title: "Create Task", desc: "Assign remediation work", icon: ListChecks, color: "#6366F1" },
              ].map(item => (
                <a key={item.href} href={item.href} className="group flex items-center gap-3 p-2.5 border border-gray-100 dark:border-gray-800 rounded-lg hover:border-[#2597B2]/30 hover:bg-[#2597B2]/[0.02] transition-all" data-testid={`quick-action-${item.href.slice(1)}`}>
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: `${item.color}12` }}><item.icon size={14} weight="duotone" style={{ color: item.color }} /></div>
                  <div className="flex-1 min-w-0"><p className="text-xs font-semibold text-gray-700 dark:text-gray-300 group-hover:text-[#2597B2]">{item.title}</p><p className="text-[10px] text-gray-400">{item.desc}</p></div>
                  <ArrowRight size={12} className="text-gray-300 group-hover:text-[#2597B2] transition-colors" />
                </a>
              ))}
            </div>
          </div>
        </div>

      </div>
    </Layout>
  );
};

export default Dashboard;
