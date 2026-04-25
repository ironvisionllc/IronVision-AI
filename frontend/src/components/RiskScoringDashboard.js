import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  CaretLeft, ArrowsClockwise, ShieldCheck, Warning, Lightning,
  ChartBar, TrendUp, TrendDown, Bell, CaretRight, GitBranch,
  Files, FileText
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const RISK_COLORS = {
  critical: { bg: "bg-red-600", text: "text-white", ring: "ring-red-600", light: "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400" },
  high: { bg: "bg-orange-500", text: "text-white", ring: "ring-orange-500", light: "bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-400" },
  elevated: { bg: "bg-amber-500", text: "text-white", ring: "ring-amber-500", light: "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400" },
  moderate: { bg: "bg-blue-500", text: "text-white", ring: "ring-blue-500", light: "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400" },
  low: { bg: "bg-emerald-500", text: "text-white", ring: "ring-emerald-500", light: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400" },
};

const ALERT_SEV = {
  critical: { bg: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800", text: "text-red-700 dark:text-red-400", icon: "text-red-500" },
  high: { bg: "bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800", text: "text-orange-700 dark:text-orange-400", icon: "text-orange-500" },
  medium: { bg: "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800", text: "text-amber-700 dark:text-amber-400", icon: "text-amber-500" },
  low: { bg: "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800", text: "text-blue-700 dark:text-blue-400", icon: "text-blue-500" },
};

const FACTOR_ICONS = {
  siem: Lightning,
  compliance: ShieldCheck,
  pipeline: GitBranch,
  ingestion: Files,
  policy: FileText,
};

const RiskScoringDashboard = () => {
  const [orgScore, setOrgScore] = useState(null);
  const [fwScores, setFwScores] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [trend, setTrend] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [orgRes, fwRes, alertRes, trendRes] = await Promise.all([
        axios.get(`${API}/risk-scoring/org-score`),
        axios.get(`${API}/risk-scoring/framework-scores`),
        axios.get(`${API}/risk-scoring/alerts`),
        axios.get(`${API}/risk-scoring/trend?days=30`),
      ]);
      setOrgScore(orgRes.data);
      setFwScores(fwRes.data);
      setAlerts(alertRes.data.alerts || []);
      setTrend(trendRes.data.history || []);
    } catch {
      toast.error("Failed to load risk data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const refresh = async () => {
    setRefreshing(true);
    await fetchAll();
    setRefreshing(false);
    toast.success("Risk scores refreshed");
  };

  if (loading) {
    return (
      <div className="text-center py-16 text-gray-400">
        <ArrowsClockwise size={32} className="mx-auto animate-spin mb-3" />
        Calculating risk scores...
      </div>
    );
  }

  const riskColor = RISK_COLORS[orgScore?.level] || RISK_COLORS.moderate;
  const factors = orgScore?.factors || {};

  return (
    <div data-testid="risk-scoring-dashboard">

      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Dynamic Risk Scoring</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Real-time compliance risk across SIEM, pipelines, checklists, and policies</p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing} data-testid="refresh-btn">
          <ArrowsClockwise size={15} className={`mr-1.5 ${refreshing ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {/* Org Risk Score - Hero */}
      <div className="iv-card p-6 mb-6" data-testid="org-risk-hero">
        <div className="flex items-center gap-8">
          <div className="relative">
            <svg viewBox="0 0 120 120" className="w-32 h-32">
              <circle cx="60" cy="60" r="52" fill="none" stroke="#e5e7eb" strokeWidth="8" className="dark:stroke-gray-700" />
              <circle
                cx="60" cy="60" r="52" fill="none"
                stroke={orgScore?.color || "#2563eb"}
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${(orgScore?.score || 0) / 100 * 327} 327`}
                transform="rotate(-90 60 60)"
                className="transition-all duration-1000"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-bold" style={{ color: orgScore?.color }} data-testid="org-score-value">{orgScore?.score || 0}</span>
              <span className="text-[10px] text-gray-500">/ 100</span>
            </div>
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-3">
              <span className={`px-3 py-1 rounded-full text-sm font-bold ${riskColor.bg} ${riskColor.text}`} data-testid="org-risk-level">
                {orgScore?.label}
              </span>
              {trend.length >= 2 && (
                <span className="flex items-center gap-1 text-sm">
                  {trend[trend.length - 1]?.score <= trend[0]?.score ? (
                    <><TrendDown size={16} className="text-emerald-500" weight="bold" /> <span className="text-emerald-600 font-medium">Improving</span></>
                  ) : (
                    <><TrendUp size={16} className="text-red-500" weight="bold" /> <span className="text-red-600 font-medium">Increasing</span></>
                  )}
                </span>
              )}
            </div>

            {/* Factor Breakdown */}
            <div className="grid grid-cols-5 gap-3">
              {Object.entries(factors).map(([key, factor]) => {
                const FactorIcon = FACTOR_ICONS[key] || ChartBar;
                return (
                  <div key={key} className="p-3 bg-gray-50 dark:bg-gray-800/50 rounded-xl" data-testid={`factor-${key}`}>
                    <div className="flex items-center gap-1.5 mb-1">
                      <FactorIcon size={14} className="text-[#2597B2]" />
                      <span className="text-[10px] font-medium text-gray-500 truncate">{factor.label}</span>
                    </div>
                    <div className="text-lg font-bold" style={{ color: factor.score > 60 ? "#dc2626" : factor.score > 30 ? "#d97706" : "#059669" }}>
                      {factor.score}
                    </div>
                    <div className="h-1 bg-gray-200 dark:bg-gray-700 rounded-full mt-1">
                      <div className="h-full rounded-full transition-all duration-500" style={{
                        width: `${factor.score}%`,
                        backgroundColor: factor.score > 60 ? "#dc2626" : factor.score > 30 ? "#d97706" : "#059669"
                      }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="mb-6" data-testid="alerts-section">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
            <Bell size={16} className="text-amber-500" /> Active Alerts ({alerts.length})
          </h3>
          <div className="space-y-2">
            {alerts.map((alert, i) => {
              const aConf = ALERT_SEV[alert.severity] || ALERT_SEV.medium;
              return (
                <div key={i} className={`p-4 rounded-xl border ${aConf.bg}`} data-testid={`alert-${i}`}>
                  <div className="flex items-start gap-3">
                    <Warning size={18} weight="fill" className={aConf.icon} />
                    <div className="flex-1">
                      <div className={`text-sm font-semibold ${aConf.text}`}>{alert.title}</div>
                      <div className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">{alert.description}</div>
                      <div className="text-xs text-[#2597B2] font-medium mt-1">{alert.action}</div>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${aConf.text}`}>
                      {alert.severity}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Framework Risk Scores */}
      <div data-testid="framework-risk-scores">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Framework Risk Scores</h3>
        <div className="space-y-2">
          {fwScores.map(fw => {
            const fwColor = RISK_COLORS[fw.risk_level] || RISK_COLORS.moderate;
            return (
              <div key={fw.framework_id} className="iv-card p-4 flex items-center gap-4" data-testid={`fw-risk-${fw.framework_id}`}>
                <div className="w-14 text-center">
                  <div className="text-xl font-bold" style={{ color: fw.risk_color }}>{fw.risk_score}</div>
                  <div className="text-[9px] text-gray-400">risk</div>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{fw.framework_name}</div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                    <span>{fw.total_controls} controls</span>
                    <span className="text-emerald-600">{fw.compliant} compliant</span>
                    <span className="text-amber-600">{fw.partial} partial</span>
                    <span className="text-red-600">{fw.non_compliant} non-compliant</span>
                    <span className="text-gray-400">{fw.not_assessed} not assessed</span>
                  </div>
                </div>
                <div className="w-32">
                  <div className="flex justify-between text-[10px] text-gray-400 mb-0.5">
                    <span>Policy Coverage</span>
                    <span>{fw.policy_coverage}%</span>
                  </div>
                  <div className="h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div className="h-full bg-[#2597B2] rounded-full transition-all duration-500" style={{ width: `${fw.policy_coverage}%` }} />
                  </div>
                </div>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${fwColor.light}`}>
                  {fw.risk_label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Trend */}
      {trend.length > 0 && (
        <div className="iv-card p-5 mt-6" data-testid="risk-trend">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Risk Score History</h3>
          <div className="flex items-end gap-1 h-24">
            {trend.slice(-30).map((point, i) => {
              const color = point.score > 60 ? "#dc2626" : point.score > 30 ? "#d97706" : "#059669";
              return (
                <div
                  key={i}
                  className="flex-1 rounded-t transition-all duration-300 group relative"
                  style={{ height: `${Math.max(4, point.score)}%`, backgroundColor: color, opacity: 0.7 + (i / trend.length) * 0.3 }}
                  title={`${point.score} - ${new Date(point.timestamp).toLocaleDateString()}`}
                >
                  <div className="hidden group-hover:block absolute -top-6 left-1/2 -translate-x-1/2 bg-gray-900 text-white text-[9px] px-1.5 py-0.5 rounded whitespace-nowrap">
                    {point.score}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="flex justify-between text-[9px] text-gray-400 mt-1">
            <span>{trend.length > 0 ? new Date(trend[0].timestamp).toLocaleDateString() : ""}</span>
            <span>Today</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default RiskScoringDashboard;
