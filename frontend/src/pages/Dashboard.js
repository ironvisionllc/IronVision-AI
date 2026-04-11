import React, { useState, useEffect, useContext, useCallback } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { AuthContext } from "@/App";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, AreaChart, Area } from "recharts";
import { toast } from "sonner";
import {
  ShieldCheck, Warning, ListChecks, Lightning, ChartBar, CheckCircle, XCircle,
  Clock, ArrowsClockwise, CaretRight, ArrowRight, Sparkle, Gauge, FileText,
  GitBranch, GearSix, CaretUp, CaretDown, Eye, EyeSlash
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

/* ─── color helpers ─── */
const gcol = s => s >= 80 ? "#059669" : s >= 60 ? "#06B6D4" : s >= 40 ? "#F59E0B" : s >= 20 ? "#F97316" : "#EF4444";
const gbg  = s => s >= 80 ? "#ECFDF5" : s >= 60 ? "#ECFEFF" : s >= 40 ? "#FFFBEB" : s >= 20 ? "#FFF7ED" : "#FEF2F2";
const hmColor = c => c === 0 ? "#F1F5F9" : c <= 2 ? "#FDE68A" : c <= 4 ? "#FDBA74" : "#FCA5A5";

/* ─── widget definitions ─── */
const WIDGET_DEFS = [
  { id: "posture", label: "Posture Overview", desc: "Key metrics and alerts" },
  { id: "ai_insight", label: "AI Insight", desc: "AI compliance analysis" },
  { id: "fw_risk", label: "Framework & Risk", desc: "Coverage chart + heatmap" },
  { id: "trend_health", label: "Trend & Health", desc: "Compliance trend + control effectiveness" },
  { id: "actions", label: "Tasks & Actions", desc: "Overdue, upcoming, quick actions" },
];

const DEFAULT_WIDGET_ORDER = ["posture", "ai_insight", "fw_risk", "trend_health", "actions"];
const STORAGE_KEY = "iv_dashboard_widgets";

const loadWidgetPrefs = () => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch { /* ignore */ }
  return { order: [...DEFAULT_WIDGET_ORDER], hidden: [] };
};

const saveWidgetPrefs = (prefs) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
};

const Dashboard = () => {
  const { user } = useContext(AuthContext);
  const [analytics, setAnalytics] = useState(null);
  const [frameworks, setFrameworks] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [controlHealth, setControlHealth] = useState(null);
  const [aiInsight, setAiInsight] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [widgetPrefs, setWidgetPrefs] = useState(loadWidgetPrefs);
  const [showCustomize, setShowCustomize] = useState(false);

  useEffect(() => { saveWidgetPrefs(widgetPrefs); }, [widgetPrefs]);

  const fetchAll = useCallback(async () => {
    try {
      const [ana, fw, mp, ch] = await Promise.all([
        axios.get(`${API}/analytics`).catch(() => ({ data: {} })),
        axios.get(`${API}/frameworks`).catch(() => ({ data: [] })),
        axios.get(`${API}/mappings`).catch(() => ({ data: [] })),
        axios.get(`${API}/control-effectiveness/dashboard`).catch(() => ({ data: null })),
      ]);
      setAnalytics(ana.data);
      setFrameworks(fw.data);
      setMappings(mp.data);
      if (ch.data) setControlHealth(ch.data);
    } catch { /* */ }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const runAiAnalysis = async () => {
    setAiLoading(true);
    try {
      const res = await axios.post(`${API}/copilot/chat`, { message: "Analyze current compliance posture, risks, and control gaps. Provide actionable recommendations.", session_id: "dashboard-insight" });
      setAiInsight(res.data.response);
    } catch { toast.error("AI analysis failed"); } finally { setAiLoading(false); }
  };

  const toggleWidget = (id) => {
    setWidgetPrefs(prev => {
      const hidden = prev.hidden.includes(id) ? prev.hidden.filter(h => h !== id) : [...prev.hidden, id];
      return { ...prev, hidden };
    });
  };

  const moveWidget = (id, direction) => {
    setWidgetPrefs(prev => {
      const order = [...prev.order];
      const idx = order.indexOf(id);
      if (idx < 0) return prev;
      const swap = direction === "up" ? idx - 1 : idx + 1;
      if (swap < 0 || swap >= order.length) return prev;
      [order[idx], order[swap]] = [order[swap], order[idx]];
      return { ...prev, order };
    });
  };

  /* ─── derived data ─── */
  const totalControls = frameworks.reduce((s, f) => s + (f.control_count || 0), 0);
  const mappedControls = mappings.length;
  const complianceScore = totalControls > 0 ? Math.round((mappedControls / totalControls) * 100) : 0;
  const openRisks = analytics?.open_risks || 0;
  const totalTasks = analytics?.total_tasks || 0;
  const overdueTasks = analytics?.overdue_tasks?.length || 0;
  const effectivenessScore = controlHealth?.overall_score || 0;
  const threatLevel = analytics?.threat_level || "Low";

  const frameworkChartData = frameworks.slice(0, 8).map(fw => {
    const mapped = mappings.filter(m => m.framework_id === fw.id).length;
    const total = fw.control_count || 1;
    const pct = Math.round((mapped / total) * 100);
    return { name: fw.name.length > 22 ? fw.name.slice(0, 20) + "..." : fw.name, score: pct, mapped, total, fill: pct >= 70 ? "#059669" : pct >= 40 ? "#F59E0B" : "#EF4444" };
  });

  const heatmap = [];
  (analytics?.risks || []).forEach(r => {
    const l = r.likelihood || 1, im = r.impact || 1;
    const ex = heatmap.find(h => h.likelihood === l && h.impact === im);
    if (ex) ex.count++; else heatmap.push({ likelihood: l, impact: im, count: 1 });
  });

  const trendData = (analytics?.compliance_trend || []).map(t => ({ date: t.date, score: t.score }));

  /* ─── widget render map ─── */
  const isVisible = (id) => !widgetPrefs.hidden.includes(id);

  const renderWidget = (id) => {
    if (!isVisible(id)) return null;

    switch (id) {
      case "posture": return <PostureWidget key={id} {...{ complianceScore, effectivenessScore, openRisks, threatLevel, totalTasks, overdueTasks, analytics, aiLoading, runAiAnalysis }} />;
      case "ai_insight": return aiInsight ? <AiInsightWidget key={id} insight={aiInsight} onClose={() => setAiInsight(null)} /> : null;
      case "fw_risk": return <FrameworkRiskWidget key={id} {...{ frameworkChartData, heatmap, hmColor }} />;
      case "trend_health": return <TrendHealthWidget key={id} {...{ trendData, controlHealth, effectivenessScore, gcol, gbg }} />;
      case "actions": return <ActionsWidget key={id} analytics={analytics} />;
      default: return null;
    }
  };

  return (
    <Layout>
      <div className="space-y-6 max-w-[1600px] mx-auto" data-testid="dashboard-page">
        {/* Dashboard Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">Command Center</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Welcome back, {user?.name || "Admin"}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => setShowCustomize(!showCustomize)} data-testid="customize-dashboard-btn">
              <GearSix size={14} className="mr-1" /> Customize
            </Button>
            <Button size="sm" className="h-8 text-xs bg-[#2597B2] hover:bg-[#1B839F]" onClick={runAiAnalysis} disabled={aiLoading} data-testid="ai-analysis-btn">
              {aiLoading ? <ArrowsClockwise size={14} className="animate-spin mr-1" /> : <Sparkle size={14} weight="fill" className="mr-1" />}
              AI Analysis
            </Button>
          </div>
        </div>

        {/* Customize Panel */}
        {showCustomize && (
          <div className="iv-card p-4" data-testid="customize-panel">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Customize Dashboard</h3>
              <button onClick={() => { setWidgetPrefs({ order: [...DEFAULT_WIDGET_ORDER], hidden: [] }); }} className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium" data-testid="reset-widgets-btn">Reset to Default</button>
            </div>
            <div className="space-y-1.5">
              {widgetPrefs.order.map((id, idx) => {
                const def = WIDGET_DEFS.find(w => w.id === id);
                if (!def) return null;
                const hidden = widgetPrefs.hidden.includes(id);
                return (
                  <div key={id} className={`flex items-center gap-3 p-2.5 rounded-lg border transition-colors ${hidden ? "bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700 opacity-60" : "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700"}`} data-testid={`widget-config-${id}`}>
                    <div className="flex flex-col gap-0.5">
                      <button onClick={() => moveWidget(id, "up")} disabled={idx === 0} className="text-gray-400 hover:text-gray-600 disabled:opacity-20" data-testid={`move-up-${id}`}><CaretUp size={12} weight="bold" /></button>
                      <button onClick={() => moveWidget(id, "down")} disabled={idx === widgetPrefs.order.length - 1} className="text-gray-400 hover:text-gray-600 disabled:opacity-20" data-testid={`move-down-${id}`}><CaretDown size={12} weight="bold" /></button>
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{def.label}</span>
                      <span className="text-xs text-gray-400 ml-2">{def.desc}</span>
                    </div>
                    <button onClick={() => toggleWidget(id)} className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors" data-testid={`toggle-${id}`}>
                      {hidden ? <EyeSlash size={16} className="text-gray-400" /> : <Eye size={16} className="text-[#2597B2]" />}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Widgets in user order */}
        {widgetPrefs.order.map(id => renderWidget(id))}
      </div>
    </Layout>
  );
};


/* ═══════ WIDGET COMPONENTS ═══════ */

const PostureWidget = ({ complianceScore, effectivenessScore, openRisks, threatLevel, totalTasks, overdueTasks, analytics, aiLoading, runAiAnalysis }) => {
  const threatColors = { Critical: "text-red-600 bg-red-50", High: "text-orange-600 bg-orange-50", Medium: "text-amber-600 bg-amber-50", Low: "text-emerald-600 bg-emerald-50" };
  return (
    <div className="iv-card overflow-hidden" data-testid="posture-widget">
      <div className="p-6">
        <div className="grid grid-cols-5 gap-5" data-testid="metrics-grid">
          <MetricCard label="Compliance Score" value={`${complianceScore}%`} sub={complianceScore >= 70 ? "On track" : "Needs work"} color={complianceScore >= 70 ? "#059669" : "#F59E0B"} icon={ShieldCheck} testId="metric-compliance" />
          <MetricCard label="Control Health" value={effectivenessScore} sub={effectivenessScore >= 60 ? "Healthy" : "At risk"} color={effectivenessScore >= 60 ? "#06B6D4" : "#F97316"} icon={Gauge} testId="metric-health" />
          <MetricCard label="Open Risks" value={openRisks} sub={openRisks > 5 ? "Review needed" : "Manageable"} color={openRisks > 5 ? "#EF4444" : "#059669"} icon={Warning} testId="metric-risks" />
          <MetricCard label="Threat Level" value={threatLevel} sub="SIEM assessment" color={threatLevel === "Low" ? "#059669" : "#F59E0B"} icon={Lightning} testId="metric-threats" extraClass={threatColors[threatLevel] || ""} />
          <MetricCard label="Tasks" value={`${totalTasks - overdueTasks}/${totalTasks}`} sub={overdueTasks > 0 ? `${overdueTasks} overdue` : "All on time"} color={overdueTasks > 0 ? "#EF4444" : "#059669"} icon={ListChecks} testId="metric-tasks" />
        </div>
      </div>
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
  );
};

const MetricCard = ({ label, value, sub, color, icon: Icon, testId, extraClass }) => (
  <div className="text-center" data-testid={testId}>
    <div className="w-9 h-9 rounded-xl mx-auto mb-2 flex items-center justify-center" style={{ backgroundColor: `${color}12` }}>
      <Icon size={18} weight="duotone" style={{ color }} />
    </div>
    <div className={`text-2xl font-bold text-gray-900 dark:text-gray-100 ${extraClass || ""}`} style={!extraClass ? { color } : undefined}>{value}</div>
    <div className="text-[10px] font-medium text-gray-500 mt-0.5">{label}</div>
    <div className="text-[10px] text-gray-400">{sub}</div>
  </div>
);

const AiInsightWidget = ({ insight, onClose }) => (
  <div className="iv-card p-5" data-testid="ai-insight-panel" style={{ borderLeft: "4px solid #2597B2" }}>
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5" style={{ background: "linear-gradient(135deg, #2597B2, #1B839F)" }}>
        <Sparkle size={16} weight="fill" className="text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold text-[#2597B2] mb-1.5">AI Compliance Analyst</p>
        <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">{insight}</div>
      </div>
      <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1"><XCircle size={16} /></button>
    </div>
  </div>
);

const FrameworkRiskWidget = ({ frameworkChartData, heatmap, hmColor }) => (
  <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
    <div className="lg:col-span-3 iv-card p-6" data-testid="framework-compliance-chart">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Framework Coverage</h3>
          <p className="text-[10px] text-gray-400 mt-0.5">Policy + technical control mapping</p>
        </div>
        <a href="/frameworks" className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium flex items-center gap-1">All <CaretRight size={11} weight="bold" /></a>
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
);

const TrendHealthWidget = ({ trendData, controlHealth, effectivenessScore, gcol, gbg }) => (
  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <div className="iv-card p-6" data-testid="compliance-trend-section">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">Compliance Trend</h3>
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
            <p className="text-[10px] text-gray-400 mt-1">{controlHealth.total_controls_sampled} controls</p>
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
);

const ActionsWidget = ({ analytics }) => (
  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <div className="iv-card p-5" data-testid="overdue-section">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2"><Clock size={14} weight="duotone" className="text-red-500" /> Overdue Tasks</h3>
      {!(analytics?.overdue_tasks?.length) ? (
        <div className="py-6 text-center"><CheckCircle size={24} weight="duotone" className="text-green-400 mx-auto mb-1.5" /><p className="text-xs text-gray-400">All clear</p></div>
      ) : (
        <div className="space-y-2">{analytics.overdue_tasks.slice(0, 4).map(t => (
          <div key={t.id} className="flex items-center justify-between p-2.5 bg-red-50/50 dark:bg-red-900/10 border border-red-100/70 dark:border-red-900/20 rounded-lg" data-testid={`overdue-task-${t.id}`}>
            <div className="flex-1 min-w-0"><p className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">{t.title}</p><p className="text-[10px] text-red-500">Due: {t.due_date}</p></div>
          </div>
        ))}</div>
      )}
    </div>
    <div className="iv-card p-5" data-testid="upcoming-section">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2"><ArrowsClockwise size={14} weight="duotone" className="text-[#2597B2]" /> Upcoming</h3>
      {!(analytics?.upcoming_deadlines?.length) ? (
        <div className="py-6 text-center"><Clock size={24} weight="duotone" className="text-gray-300 mx-auto mb-1.5" /><p className="text-xs text-gray-400">No upcoming</p></div>
      ) : (
        <div className="space-y-2">{analytics.upcoming_deadlines.slice(0, 4).map(t => (
          <div key={t.id} className="flex items-center justify-between p-2.5 bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-700 rounded-lg">
            <div className="flex-1 min-w-0"><p className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">{t.title}</p><p className="text-[10px] text-gray-500">Due: {t.due_date}</p></div>
          </div>
        ))}</div>
      )}
    </div>
    <div className="iv-card p-5" data-testid="quick-actions">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2"><Lightning size={14} weight="duotone" className="text-amber-500" /> Quick Actions</h3>
      <div className="space-y-2">
        {[
          { href: "/policies", title: "Generate Policy", desc: "AI-powered creation", icon: FileText, color: "#2597B2" },
          { href: "/frameworks", title: "Map Controls", desc: "Map to frameworks", icon: GitBranch, color: "#06B6D4" },
          { href: "/risks", title: "Assess Risk", desc: "Create or review", icon: Warning, color: "#F59E0B" },
          { href: "/tasks", title: "Create Task", desc: "Assign work", icon: ListChecks, color: "#6366F1" },
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
);

export default Dashboard;
