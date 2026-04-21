import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  CaretLeft, ArrowsClockwise, Lightning, ShieldCheck, FileText,
  GitBranch, ListChecks, CloudArrowDown, CheckCircle, Clock, Warning,
  Trash, CaretRight, ChartBar, Eye
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const TYPE_CONFIG = {
  siem_snapshot: { label: "SIEM Snapshot", icon: Lightning, color: "bg-purple-500" },
  pipeline_report: { label: "Pipeline Report", icon: GitBranch, color: "bg-cyan-500" },
  policy_document: { label: "Policy Document", icon: FileText, color: "bg-emerald-500" },
  compliance_assessment: { label: "Assessment", icon: ShieldCheck, color: "bg-blue-500" },
  checklist_mapping: { label: "Checklist Mapping", icon: ListChecks, color: "bg-amber-500" },
};

const FRESHNESS_CONFIG = {
  current: { label: "Fresh", color: "text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20" },
  aging: { label: "Aging", color: "text-amber-600 bg-amber-50 dark:bg-amber-900/20" },
  stale: { label: "Stale", color: "text-red-600 bg-red-50 dark:bg-red-900/20" },
};

const AutomatedEvidenceCollection = ({ onBack }) => {
  const [tab, setTab] = useState("dashboard"); // dashboard | artifacts | coverage
  const [stats, setStats] = useState(null);
  const [artifacts, setArtifacts] = useState([]);
  const [coverage, setCoverage] = useState(null);
  const [collecting, setCollecting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expandedArtifact, setExpandedArtifact] = useState(null);

  const fetchStats = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/evidence-collection/stats`);
      setStats(res.data);
    } catch {
      toast.error("Failed to load stats");
    }
  }, []);

  const fetchArtifacts = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/evidence-collection/artifacts`);
      setArtifacts(res.data);
    } catch {
      toast.error("Failed to load artifacts");
    }
  }, []);

  const fetchCoverage = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/evidence-collection/coverage`);
      setCoverage(res.data);
    } catch {
      toast.error("Failed to load coverage");
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await fetchStats();
      setLoading(false);
    };
    init();
  }, [fetchStats]);

  useEffect(() => {
    if (tab === "artifacts" && artifacts.length === 0) fetchArtifacts();
    if (tab === "coverage" && !coverage) fetchCoverage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const runCollection = async () => {
    setCollecting(true);
    try {
      const res = await axios.post(`${API}/evidence-collection/collect`);
      toast.success(res.data.message);
      await fetchStats();
      if (tab === "artifacts") await fetchArtifacts();
      if (tab === "coverage") await fetchCoverage();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Collection failed");
    } finally {
      setCollecting(false);
    }
  };

  const deleteArtifact = async (id) => {
    if (!window.confirm("Delete this evidence artifact?")) return;
    try {
      await axios.delete(`${API}/evidence-collection/artifacts/${id}`);
      toast.success("Artifact deleted");
      setArtifacts(prev => prev.filter(a => a.id !== id));
      fetchStats();
    } catch {
      toast.error("Failed to delete");
    }
  };

  if (loading) return <div className="text-center py-16 text-gray-400"><ArrowsClockwise size={32} className="mx-auto animate-spin mb-3" />Loading evidence data...</div>;

  return (
    <div data-testid="evidence-collection-view">
      {onBack && (
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#2597B2] mb-6 transition-colors" data-testid="back-btn">
          <CaretLeft size={14} weight="bold" /> Back
        </button>
      )}

      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Automated Evidence Collection</h2>
          <p className="text-sm text-gray-500 mt-1">Auto-gather compliance evidence from SIEM, pipelines, policies, and assessments</p>
        </div>
        <Button onClick={runCollection} disabled={collecting} className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="collect-btn">
          {collecting ? <><ArrowsClockwise size={16} className="animate-spin mr-2" /> Collecting...</> : <><CloudArrowDown size={16} className="mr-2" /> Run Collection</>}
        </Button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="iv-card p-4" data-testid="stat-total">
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.total_artifacts}</div>
            <div className="text-xs text-gray-500">Total Artifacts</div>
          </div>
          <div className="iv-card p-4" data-testid="stat-fresh">
            <div className="text-2xl font-bold text-emerald-600">{stats.fresh}</div>
            <div className="text-xs text-gray-500">Fresh (30d)</div>
          </div>
          <div className="iv-card p-4" data-testid="stat-stale">
            <div className="text-2xl font-bold text-amber-600">{stats.stale}</div>
            <div className="text-xs text-gray-500">Stale</div>
          </div>
          <div className="iv-card p-4" data-testid="stat-types">
            <div className="flex gap-1.5 flex-wrap">
              {Object.entries(stats.by_type || {}).map(([type, count]) => {
                const cfg = TYPE_CONFIG[type] || {};
                return <span key={type} className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded-full font-medium">{cfg.label || type}: {count}</span>;
              })}
            </div>
            <div className="text-xs text-gray-500 mt-1">By Type</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 p-1 bg-gray-100 dark:bg-gray-800 rounded-lg w-fit" data-testid="evidence-tabs">
        {[
          { key: "dashboard", label: "Overview", icon: ChartBar },
          { key: "artifacts", label: "Artifacts", icon: FileText },
          { key: "coverage", label: "Coverage", icon: ShieldCheck },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              tab === t.key ? "bg-white dark:bg-gray-900 text-[#2597B2] shadow-sm" : "text-gray-500 hover:text-gray-700"
            }`}
            data-testid={`tab-${t.key}`}
          >
            <t.icon size={15} weight={tab === t.key ? "fill" : "regular"} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Dashboard */}
      {tab === "dashboard" && (
        <div data-testid="evidence-dashboard">
          <div className="iv-card p-5 mb-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Evidence Sources</h3>
            <div className="grid grid-cols-5 gap-3">
              {Object.entries(TYPE_CONFIG).map(([key, cfg]) => {
                const count = stats?.by_type?.[key] || 0;
                const Icon = cfg.icon;
                return (
                  <div key={key} className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 text-center" data-testid={`source-${key}`}>
                    <div className={`w-10 h-10 rounded-full ${cfg.color} flex items-center justify-center mx-auto mb-2`}>
                      <Icon size={18} className="text-white" weight="fill" />
                    </div>
                    <div className="text-lg font-bold text-gray-900 dark:text-gray-100">{count}</div>
                    <div className="text-[10px] text-gray-500">{cfg.label}</div>
                  </div>
                );
              })}
            </div>
          </div>
          {stats?.last_collection && (
            <div className="iv-card p-4 flex items-center gap-3">
              <Clock size={18} className="text-gray-400" />
              <div>
                <div className="text-sm text-gray-700 dark:text-gray-300">Last collection: {new Date(stats.last_collection.created_at).toLocaleString()}</div>
                <div className="text-xs text-gray-500">{stats.last_collection.total_collected} artifacts collected</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Artifacts */}
      {tab === "artifacts" && (
        <div className="space-y-2" data-testid="artifacts-list">
          {artifacts.length === 0 ? (
            <div className="text-center py-12 text-gray-400">No evidence artifacts collected yet. Run collection to get started.</div>
          ) : (
            artifacts.map(a => {
              const cfg = TYPE_CONFIG[a.evidence_type] || {};
              const Icon = cfg.icon || FileText;
              const freshCfg = FRESHNESS_CONFIG[a.freshness] || FRESHNESS_CONFIG.stale;
              const isExpanded = expandedArtifact === a.id;
              return (
                <div key={a.id} className="iv-card overflow-hidden" data-testid={`artifact-${a.id}`}>
                  <div className="p-4 flex items-center gap-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors" onClick={() => setExpandedArtifact(isExpanded ? null : a.id)}>
                    <div className={`w-9 h-9 rounded-lg ${cfg.color || "bg-gray-400"} flex items-center justify-center`}>
                      <Icon size={16} className="text-white" weight="fill" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{a.title}</div>
                      <div className="text-xs text-gray-500 truncate">{a.description}</div>
                    </div>
                    <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${freshCfg.color}`}>{freshCfg.label}</span>
                    <span className="text-xs text-gray-400">{a.control_ids?.length || 0} controls</span>
                    <button onClick={e => { e.stopPropagation(); deleteArtifact(a.id); }} className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500">
                      <Trash size={14} />
                    </button>
                    <CaretRight size={14} className={`text-gray-400 transition-transform ${isExpanded ? "rotate-90" : ""}`} />
                  </div>
                  {isExpanded && (
                    <div className="px-4 pb-4 border-t border-gray-100 dark:border-gray-800 pt-3">
                      <div className="text-xs text-gray-500 mb-2">Source: {a.source} | Collected: {new Date(a.collected_at).toLocaleString()}</div>
                      {a.control_ids?.length > 0 && (
                        <div className="flex gap-1 flex-wrap mb-2">
                          {a.control_ids.slice(0, 15).map(c => (
                            <span key={c} className="text-[9px] px-1.5 py-0.5 bg-[#2597B2]/10 text-[#2597B2] rounded font-medium">{c}</span>
                          ))}
                          {a.control_ids.length > 15 && <span className="text-[9px] text-gray-400">+{a.control_ids.length - 15} more</span>}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Coverage */}
      {tab === "coverage" && (
        <div data-testid="coverage-tab">
          {!coverage ? (
            <div className="text-center py-8 text-gray-400">Loading coverage data...</div>
          ) : (
            <>
              <div className="iv-card p-5 mb-6">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Overall Evidence Coverage</h3>
                  <span className="text-lg font-bold text-[#2597B2]">{coverage.summary?.coverage_pct}%</span>
                </div>
                <div className="h-3 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-full bg-[#2597B2] rounded-full transition-all duration-500" style={{ width: `${coverage.summary?.coverage_pct}%` }} />
                </div>
                <div className="flex justify-between text-xs text-gray-400 mt-2">
                  <span>{coverage.summary?.covered} covered</span>
                  <span>{coverage.summary?.total_controls - coverage.summary?.covered} uncovered</span>
                </div>
              </div>
              <div className="space-y-2">
                {coverage.frameworks?.map(fw => (
                  <div key={fw.framework_id} className="iv-card p-4 flex items-center gap-4" data-testid={`coverage-${fw.framework_id}`}>
                    <div className="w-14 text-center">
                      <div className="text-lg font-bold" style={{ color: fw.coverage_pct > 60 ? "#059669" : fw.coverage_pct > 30 ? "#d97706" : "#dc2626" }}>
                        {fw.coverage_pct}%
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{fw.framework_name}</div>
                      <div className="h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden mt-1">
                        <div className="h-full rounded-full transition-all" style={{
                          width: `${fw.coverage_pct}%`,
                          backgroundColor: fw.coverage_pct > 60 ? "#059669" : fw.coverage_pct > 30 ? "#d97706" : "#dc2626"
                        }} />
                      </div>
                    </div>
                    <div className="text-right text-xs text-gray-500">
                      <div>{fw.covered}/{fw.total_controls}</div>
                      <div className="flex gap-2 mt-0.5">
                        <span className="text-emerald-600">{fw.fresh} fresh</span>
                        <span className="text-amber-600">{fw.stale} stale</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default AutomatedEvidenceCollection;
