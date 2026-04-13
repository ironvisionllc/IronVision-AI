import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  CaretRight, CaretDown, MagnifyingGlass, ShieldCheck, Warning,
  CheckCircle, XCircle, MinusCircle, Question, Lightning, FileText,
  ArrowsClockwise, PencilSimple, FloppyDisk, CaretLeft, Funnel,
  ArrowsOutSimple, ArrowsInSimple, BookOpen, Wrench, Plus, Trash, LinkSimple, ChartBar
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const STATUS_CONFIG = {
  compliant: { label: "Compliant", color: "text-emerald-700", bg: "bg-emerald-50 dark:bg-emerald-900/20", border: "border-emerald-200 dark:border-emerald-800", icon: CheckCircle, dot: "bg-emerald-500" },
  partial: { label: "Partial", color: "text-amber-700", bg: "bg-amber-50 dark:bg-amber-900/20", border: "border-amber-200 dark:border-amber-800", icon: MinusCircle, dot: "bg-amber-500" },
  non_compliant: { label: "Non-Compliant", color: "text-red-700", bg: "bg-red-50 dark:bg-red-900/20", border: "border-red-200 dark:border-red-800", icon: XCircle, dot: "bg-red-500" },
  not_assessed: { label: "Not Assessed", color: "text-gray-500", bg: "bg-gray-50 dark:bg-gray-800", border: "border-gray-200 dark:border-gray-700", icon: Question, dot: "bg-gray-400" },
};

const FrameworkWorkspace = ({ framework, onBack }) => {
  const [complianceData, setComplianceData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [assessing, setAssessing] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [expandedControl, setExpandedControl] = useState(null);
  const [expandedSet, setExpandedSet] = useState(new Set());
  const [editingNotes, setEditingNotes] = useState({});
  const [siemEvidence, setSiemEvidence] = useState({});
  const [suggestingPolicy, setSuggestingPolicy] = useState(null);
  const [policySuggestions, setPolicySuggestions] = useState({});
  const [implGuidance, setImplGuidance] = useState({});
  const [loadingImpl, setLoadingImpl] = useState({});

  const fetchCompliance = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/control-compliance/${framework.id}`);
      setComplianceData(res.data);
    } catch {
      toast.error("Failed to load compliance data");
    } finally {
      setLoading(false);
    }
  }, [framework.id]);

  useEffect(() => { fetchCompliance(); }, [fetchCompliance]);

  const runAiAssessment = async () => {
    setAssessing(true);
    try {
      const res = await axios.post(`${API}/control-compliance/${framework.id}/ai-assess`, {});
      toast.success(`AI assessed ${res.data.assessed} controls`);
      fetchCompliance();
    } catch (err) {
      toast.error(err.response?.data?.detail || "AI assessment failed");
    } finally {
      setAssessing(false);
    }
  };

  const updateStatus = async (controlId, status) => {
    try {
      await axios.put(`${API}/control-compliance/${framework.id}/${controlId}/status`, { status }, { headers: {} });
      setComplianceData(prev => ({
        ...prev,
        controls: prev.controls.map(c =>
          c.control_id === controlId ? { ...c, status, is_user_override: true } : c
        ),
      }));
      toast.success("Status updated");
    } catch {
      toast.error("Failed to update status");
    }
  };

  const saveNotes = async (controlId) => {
    const notes = editingNotes[controlId];
    if (notes === undefined) return;
    try {
      await axios.put(`${API}/control-compliance/${framework.id}/${controlId}/notes`, { notes });
      setComplianceData(prev => ({
        ...prev,
        controls: prev.controls.map(c =>
          c.control_id === controlId ? { ...c, notes } : c
        ),
      }));
      toast.success("Notes saved");
    } catch {
      toast.error("Failed to save notes");
    }
  };

  const fetchSiemEvidence = async (controlId) => {
    if (siemEvidence[controlId]) return;
    try {
      const res = await axios.get(`${API}/control-compliance/${framework.id}/${controlId}/siem-evidence`);
      setSiemEvidence(prev => ({ ...prev, [controlId]: res.data }));
    } catch {
      toast.error("Failed to load SIEM evidence");
    }
  };

  const suggestPolicy = async (controlId) => {
    setSuggestingPolicy(controlId);
    try {
      const res = await axios.post(`${API}/control-compliance/${framework.id}/${controlId}/suggest-policy`, {});
      setPolicySuggestions(prev => ({ ...prev, [controlId]: res.data }));
    } catch {
      toast.error("Failed to generate suggestion");
    } finally {
      setSuggestingPolicy(null);
    }
  };

  const fetchImplGuidance = async (controlId) => {
    if (implGuidance[controlId] || loadingImpl[controlId]) return;
    setLoadingImpl(prev => ({ ...prev, [controlId]: true }));
    try {
      const res = await axios.post(`${API}/control-compliance/${framework.id}/${controlId}/implementation-guidance`, {});
      setImplGuidance(prev => ({ ...prev, [controlId]: res.data }));
    } catch {
      toast.error("Failed to load guidance");
    } finally {
      setLoadingImpl(prev => ({ ...prev, [controlId]: false }));
    }
  };

  const toggleControl = (controlId) => {
    setExpandedSet(prev => {
      const next = new Set(prev);
      if (next.has(controlId)) {
        next.delete(controlId);
      } else {
        next.add(controlId);
        fetchSiemEvidence(controlId);
      }
      return next;
    });
  };

  const expandAll = () => {
    const allIds = new Set(filtered.map(c => c.control_id));
    setExpandedSet(allIds);
    allIds.forEach(id => fetchSiemEvidence(id));
  };

  const collapseAll = () => {
    setExpandedSet(new Set());
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64" data-testid="workspace-loading">
        <div className="text-center">
          <ArrowsClockwise size={28} className="animate-spin text-[#2597B2] mx-auto mb-2" />
          <p className="text-sm text-gray-500">Loading compliance workspace...</p>
        </div>
      </div>
    );
  }

  const controls = complianceData?.controls || [];
  const summary = complianceData?.summary || {};
  const categories = [...new Set(controls.map(c => c.category))].sort();

  const filtered = controls.filter(c => {
    if (statusFilter !== "all" && c.status !== statusFilter) return false;
    if (categoryFilter !== "all" && c.category !== categoryFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return c.control_id.toLowerCase().includes(q) || c.title.toLowerCase().includes(q) || c.description.toLowerCase().includes(q);
    }
    return true;
  });

  return (
    <div data-testid="framework-workspace">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <button onClick={onBack} className="flex items-center gap-1 text-sm text-[#2597B2] hover:text-[#1B839F] font-medium transition-colors" data-testid="back-to-frameworks">
          <CaretLeft size={14} weight="bold" /> Back
        </button>
      </div>

      <div className="flex items-start justify-between mb-6 mt-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">{framework.name}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{framework.description}</p>
        </div>
        <Button
          onClick={runAiAssessment}
          disabled={assessing}
          className="bg-[#2597B2] hover:bg-[#1B839F] shrink-0"
          data-testid="ai-assess-btn"
        >
          {assessing ? <ArrowsClockwise size={16} className="animate-spin mr-2" /> : <Lightning size={16} weight="fill" className="mr-2" />}
          {assessing ? "Assessing..." : "AI Assess All"}
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-5 gap-3 mb-6" data-testid="compliance-summary">
        <div className="iv-card p-4 text-center">
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100" data-testid="total-controls">{controls.length}</div>
          <div className="text-xs text-gray-500 mt-1">Total Controls</div>
        </div>
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
          <div key={key} className={`rounded-lg border p-4 text-center ${cfg.bg} ${cfg.border}`}>
            <div className={`text-2xl font-bold ${cfg.color}`} data-testid={`count-${key}`}>{summary[key] || 0}</div>
            <div className="text-xs text-gray-500 mt-1">{cfg.label}</div>
          </div>
        ))}
      </div>

      {/* Compliance Progress Bar */}
      <div className="iv-card p-4 mb-6" data-testid="compliance-progress">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Compliance Progress</span>
          <span className="text-sm font-bold text-[#2597B2]">
            {controls.length > 0 ? Math.round(((summary.compliant || 0) / controls.length) * 100) : 0}%
          </span>
        </div>
        <div className="h-3 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden flex">
          {controls.length > 0 && (
            <>
              <div className="h-full bg-emerald-500 transition-all" style={{ width: `${((summary.compliant || 0) / controls.length) * 100}%` }} />
              <div className="h-full bg-amber-500 transition-all" style={{ width: `${((summary.partial || 0) / controls.length) * 100}%` }} />
              <div className="h-full bg-red-500 transition-all" style={{ width: `${((summary.non_compliant || 0) / controls.length) * 100}%` }} />
            </>
          )}
        </div>
        <div className="flex gap-4 mt-2 text-[10px] text-gray-400">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> Compliant</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500 inline-block" /> Partial</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> Non-Compliant</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-gray-400 inline-block" /> Not Assessed</span>
        </div>
      </div>

      {/* Policy Coverage Summary */}
      {(() => {
        const withPolicy = controls.filter(c => c.policy_count > 0).length;
        const coveragePct = controls.length > 0 ? Math.round((withPolicy / controls.length) * 100) : 0;
        return (
          <div className="iv-card p-4 mb-6 flex items-center justify-between" data-testid="policy-coverage-summary">
            <div className="flex items-center gap-3">
              <FileText size={18} weight="duotone" className="text-purple-500" />
              <div>
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Policy Coverage</span>
                <p className="text-[10px] text-gray-400">{withPolicy} of {controls.length} controls have linked policies ({coveragePct}%)</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-32 h-2.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                <div className="h-full bg-purple-500 rounded-full transition-all" style={{ width: `${coveragePct}%` }} />
              </div>
              <span className="text-xs font-bold text-purple-600">{coveragePct}%</span>
            </div>
          </div>
        );
      })()}

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4" data-testid="workspace-filters">
        <div className="relative flex-1 max-w-sm">
          <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <Input
            placeholder="Search controls..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 h-9 text-sm"
            data-testid="workspace-search"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2597B2]"
          data-testid="status-filter"
        >
          <option value="all">All Statuses ({controls.length})</option>
          {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
            <option key={key} value={key}>{cfg.label} ({summary[key] || 0})</option>
          ))}
        </select>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="h-9 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2597B2]"
          data-testid="category-filter"
        >
          <option value="all">All Categories</option>
          {categories.map(cat => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>
        <span className="text-xs text-gray-500 ml-auto">
          {filtered.length} of {controls.length} controls
        </span>
        <Button variant="outline" size="sm" className="h-9 text-xs ml-2" onClick={expandedSet.size > 0 ? collapseAll : expandAll} data-testid="expand-collapse-all-btn">
          {expandedSet.size > 0 ? <><ArrowsInSimple size={14} className="mr-1" /> Collapse All</> : <><ArrowsOutSimple size={14} className="mr-1" /> Expand All</>}
        </Button>
      </div>

      {/* Controls List */}
      <div className="space-y-2" data-testid="controls-list">
        {filtered.map(ctrl => {
          const cfg = STATUS_CONFIG[ctrl.status] || STATUS_CONFIG.not_assessed;
          const isExpanded = expandedSet.has(ctrl.control_id);
          const Icon = cfg.icon;

          return (
            <div key={ctrl.control_id} className={`iv-card overflow-hidden transition-all ${isExpanded ? "ring-1 ring-[#2597B2]/30" : ""}`} data-testid={`control-row-${ctrl.control_id}`}>
              {/* Control Row Header */}
              <div
                className="flex items-center gap-3 p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                onClick={() => toggleControl(ctrl.control_id)}
                data-testid={`control-toggle-${ctrl.control_id}`}
              >
                {isExpanded ? <CaretDown size={14} className="text-gray-400 shrink-0" /> : <CaretRight size={14} className="text-gray-400 shrink-0" />}

                <span className="font-mono text-xs font-bold text-[#2597B2] bg-[#2597B2]/8 px-2 py-0.5 rounded shrink-0 w-[80px]">{ctrl.control_id}</span>

                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{ctrl.title}</span>
                </div>

                {/* Status Badge */}
                <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium shrink-0 ${cfg.bg} ${cfg.color} border ${cfg.border}`} data-testid={`status-badge-${ctrl.control_id}`}>
                  <Icon size={12} weight="fill" />
                  {cfg.label}
                  {ctrl.is_user_override && <PencilSimple size={10} />}
                </div>

                {/* Technical indicator */}
                {ctrl.is_technical && (
                  <div className="flex items-center gap-1 text-xs text-blue-600 bg-blue-50 dark:bg-blue-900/20 px-2 py-1 rounded shrink-0" data-testid={`siem-badge-${ctrl.control_id}`}>
                    <Lightning size={10} weight="fill" />
                    {ctrl.siem_events_count} events
                  </div>
                )}

                {/* Policy count */}
                {ctrl.policy_count > 0 && (
                  <div className="flex items-center gap-1 text-xs text-purple-600 bg-purple-50 dark:bg-purple-900/20 px-2 py-1 rounded shrink-0">
                    <FileText size={10} weight="fill" />
                    {ctrl.policy_count}
                  </div>
                )}

                <span className="text-[10px] text-gray-400 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded shrink-0">{ctrl.category}</span>
              </div>

              {/* Expanded Detail Panel */}
              {isExpanded && (
                <ControlDetailPanel
                  ctrl={ctrl}
                  framework={framework}
                  onStatusChange={(status) => updateStatus(ctrl.control_id, status)}
                  notes={editingNotes[ctrl.control_id] !== undefined ? editingNotes[ctrl.control_id] : ctrl.notes}
                  onNotesChange={(val) => setEditingNotes(prev => ({ ...prev, [ctrl.control_id]: val }))}
                  onSaveNotes={() => saveNotes(ctrl.control_id)}
                  siemData={siemEvidence[ctrl.control_id]}
                  policySuggestion={policySuggestions[ctrl.control_id]}
                  onSuggestPolicy={() => suggestPolicy(ctrl.control_id)}
                  suggestingPolicy={suggestingPolicy === ctrl.control_id}
                  implGuidance={implGuidance[ctrl.control_id]}
                  loadingImpl={loadingImpl[ctrl.control_id]}
                  onFetchGuidance={() => fetchImplGuidance(ctrl.control_id)}
                  onRefresh={fetchCompliance}
                />
              )}
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="text-center py-12 text-gray-500 text-sm">No controls match your filters.</div>
        )}
      </div>
    </div>
  );
};


const ControlDetailPanel = ({ ctrl, framework, onStatusChange, notes, onNotesChange, onSaveNotes, siemData, policySuggestion, onSuggestPolicy, suggestingPolicy, implGuidance, loadingImpl, onFetchGuidance, onRefresh }) => {
  const [activeDetailTab, setActiveDetailTab] = useState("overview");
  const [showLinkDialog, setShowLinkDialog] = useState(false);
  const [libraryDocs, setLibraryDocs] = useState([]);
  const [libraryPolicies, setLibraryPolicies] = useState([]);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [analyzingDoc, setAnalyzingDoc] = useState(null);
  const [coverageResults, setCoverageResults] = useState({});

  const DETAIL_TABS = [
    { id: "overview", label: "Overview" },
    { id: "implementation", label: "Implementation & Guidelines" },
    { id: "siem", label: `SIEM Evidence (${ctrl.siem_events_count})`, show: ctrl.is_technical },
    { id: "policies", label: `Policies (${ctrl.policy_count})` },
    { id: "notes", label: "Notes" },
  ].filter(t => t.show !== false);

  return (
    <div className="border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/30" data-testid={`detail-panel-${ctrl.control_id}`}>
      {/* Detail Tabs */}
      <div className="flex gap-1 px-4 pt-3 border-b border-gray-100 dark:border-gray-800">
        {DETAIL_TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveDetailTab(tab.id)}
            className={`px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${
              activeDetailTab === tab.id
                ? "border-[#2597B2] text-[#2597B2]"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
            data-testid={`detail-tab-${tab.id}-${ctrl.control_id}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="p-4">
        {/* Overview Tab */}
        {activeDetailTab === "overview" && (
          <div className="space-y-4" data-testid={`overview-${ctrl.control_id}`}>
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Description</h4>
              <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{ctrl.description}</p>
            </div>

            {/* Status Editor */}
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Compliance Status</h4>
              <div className="flex gap-2" data-testid={`status-editor-${ctrl.control_id}`}>
                {Object.entries(STATUS_CONFIG).map(([key, cfg]) => {
                  const Icon = cfg.icon;
                  return (
                    <button
                      key={key}
                      onClick={() => onStatusChange(key)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                        ctrl.status === key
                          ? `${cfg.bg} ${cfg.color} ${cfg.border} ring-1 ring-offset-1`
                          : "bg-white dark:bg-gray-800 text-gray-500 border-gray-200 dark:border-gray-700 hover:border-gray-300"
                      }`}
                      style={ctrl.status === key ? { ringColor: cfg.dot?.replace("bg-", "") } : {}}
                      data-testid={`set-status-${key}-${ctrl.control_id}`}
                    >
                      <Icon size={12} weight={ctrl.status === key ? "fill" : "regular"} />
                      {cfg.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* AI Assessment */}
            {ctrl.ai_assessment && (
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                <h4 className="text-xs font-semibold text-blue-700 dark:text-blue-400 mb-1 flex items-center gap-1">
                  <Lightning size={12} weight="fill" /> AI Assessment
                </h4>
                <p className="text-xs text-blue-600 dark:text-blue-300">{ctrl.ai_assessment}</p>
              </div>
            )}

            {/* Policy Suggestion - Enhanced with WHERE requirements are satisfied */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-gray-500 uppercase">AI Policy Analysis</h4>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={onSuggestPolicy}
                  disabled={suggestingPolicy}
                  data-testid={`suggest-policy-btn-${ctrl.control_id}`}
                >
                  {suggestingPolicy ? <ArrowsClockwise size={12} className="animate-spin mr-1" /> : <Lightning size={12} className="mr-1" />}
                  {suggestingPolicy ? "Analyzing..." : "Analyze Policy Coverage"}
                </Button>
              </div>
              {(policySuggestion || ctrl.policy_suggestion) && (() => {
                let ps = policySuggestion;
                if (!ps && ctrl.policy_suggestion) {
                  try { ps = JSON.parse(ctrl.policy_suggestion); } catch { return null; }
                }
                if (!ps) return null;
                return (
                  <div className="space-y-3" data-testid={`policy-suggestion-${ctrl.control_id}`}>
                    <div className="p-3 bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800 rounded-lg">
                      <p className="text-sm font-medium text-purple-700 dark:text-purple-400 mb-2">{ps.title}</p>
                      <ul className="space-y-1">
                        {(ps.statements || []).map((s, i) => (
                          <li key={i} className="text-xs text-purple-600 dark:text-purple-300 flex items-start gap-2">
                            <CheckCircle size={12} weight="fill" className="shrink-0 mt-0.5 text-purple-400" />
                            {s}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* WHERE requirements ARE being satisfied */}
                    {ps.satisfied?.length > 0 && (
                      <div className="p-3 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg">
                        <h5 className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 mb-1.5 flex items-center gap-1"><CheckCircle size={12} weight="fill" /> Where Requirements Are Met</h5>
                        <ul className="space-y-1">
                          {ps.satisfied.map((s, i) => (
                            <li key={i} className="text-xs text-emerald-600 dark:text-emerald-300 flex items-start gap-2">
                              <span className="w-1 h-1 bg-emerald-400 rounded-full shrink-0 mt-1.5" />
                              {s}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* WHERE requirements are NOT met (gaps) */}
                    {ps.gaps?.length > 0 && (
                      <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                        <h5 className="text-xs font-semibold text-red-700 dark:text-red-400 mb-1.5 flex items-center gap-1"><XCircle size={12} weight="fill" /> Gaps - Requirements Not Met</h5>
                        <ul className="space-y-1">
                          {ps.gaps.map((s, i) => (
                            <li key={i} className="text-xs text-red-600 dark:text-red-300 flex items-start gap-2">
                              <span className="w-1 h-1 bg-red-400 rounded-full shrink-0 mt-1.5" />
                              {s}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {ps.guidance && (
                      <p className="text-xs text-gray-500 italic">{ps.guidance}</p>
                    )}
                  </div>
                );
              })()}
            </div>
          </div>
        )}

        {/* Implementation & Guidelines Tab */}
        {activeDetailTab === "implementation" && (
          <div data-testid={`implementation-${ctrl.control_id}`}>
            {!implGuidance && !loadingImpl && (
              <div className="text-center py-8">
                <BookOpen size={28} className="mx-auto mb-2 text-gray-300" />
                <p className="text-sm text-gray-500 mb-3">Generate implementation guidance for this control</p>
                <Button size="sm" className="bg-[#2597B2] hover:bg-[#1B839F] h-8 text-xs" onClick={onFetchGuidance} data-testid={`fetch-guidance-btn-${ctrl.control_id}`}>
                  <Wrench size={14} className="mr-1" /> Generate Guidance
                </Button>
              </div>
            )}
            {loadingImpl && (
              <div className="text-center py-8 text-gray-500 text-sm"><ArrowsClockwise size={20} className="animate-spin mx-auto mb-2" /> Generating implementation guidance...</div>
            )}
            {implGuidance && (
              <div className="space-y-4">
                {implGuidance.implementation_steps?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2 flex items-center gap-1"><Wrench size={12} /> Implementation Steps</h4>
                    <ol className="space-y-1.5">
                      {implGuidance.implementation_steps.map((s, i) => (
                        <li key={i} className="text-xs text-gray-700 dark:text-gray-300 flex items-start gap-2">
                          <span className="w-5 h-5 rounded-full bg-[#2597B2]/10 text-[#2597B2] flex items-center justify-center shrink-0 text-[10px] font-bold">{i + 1}</span>
                          {s}
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
                {implGuidance.technical_guidelines?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Technical Guidelines</h4>
                    <ul className="space-y-1.5">
                      {implGuidance.technical_guidelines.map((s, i) => (
                        <li key={i} className="text-xs text-gray-700 dark:text-gray-300 flex items-start gap-2 p-2 bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 rounded-lg">
                          <Lightning size={12} weight="fill" className="shrink-0 mt-0.5 text-blue-500" />
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {implGuidance.assessment_criteria?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Assessment Criteria</h4>
                    <ul className="space-y-1">
                      {implGuidance.assessment_criteria.map((s, i) => (
                        <li key={i} className="text-xs text-gray-700 dark:text-gray-300 flex items-start gap-2">
                          <CheckCircle size={12} weight="fill" className="shrink-0 mt-0.5 text-emerald-500" />
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {implGuidance.common_pitfalls?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Common Pitfalls</h4>
                    <ul className="space-y-1">
                      {implGuidance.common_pitfalls.map((s, i) => (
                        <li key={i} className="text-xs text-amber-700 dark:text-amber-300 flex items-start gap-2 p-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800 rounded-lg">
                          <Warning size={12} weight="fill" className="shrink-0 mt-0.5" />
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* SIEM Evidence Tab */}
        {activeDetailTab === "siem" && (
          <div data-testid={`siem-evidence-${ctrl.control_id}`}>
            {!siemData ? (
              <div className="text-center py-6 text-gray-500 text-sm">
                <ArrowsClockwise size={20} className="animate-spin mx-auto mb-2" />
                Loading SIEM evidence...
              </div>
            ) : siemData.events?.length === 0 ? (
              <div className="text-center py-6 text-gray-500 text-sm">
                No SIEM events found for this control in the last 30 days.
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs text-gray-500">Categories: {siemData.categories?.join(", ")}</span>
                  <span className="text-xs text-gray-400">|</span>
                  <span className="text-xs text-gray-500">{siemData.count} events (30d)</span>
                </div>
                {siemData.events?.slice(0, 10).map((ev, i) => (
                  <div key={i} className={`flex items-start gap-3 p-3 rounded-lg border text-xs ${
                    ev.severity === "critical" ? "bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800" :
                    ev.severity === "high" ? "bg-orange-50 border-orange-200 dark:bg-orange-900/20 dark:border-orange-800" :
                    "bg-white border-gray-200 dark:bg-gray-800 dark:border-gray-700"
                  }`}>
                    <span className={`px-1.5 py-0.5 rounded font-medium shrink-0 ${
                      ev.severity === "critical" ? "bg-red-100 text-red-700" :
                      ev.severity === "high" ? "bg-orange-100 text-orange-700" :
                      ev.severity === "medium" ? "bg-yellow-100 text-yellow-700" :
                      "bg-gray-100 text-gray-600"
                    }`}>{ev.severity}</span>
                    <div className="flex-1 min-w-0">
                      <span className="font-medium text-gray-900 dark:text-gray-100">{ev.event_type}</span>
                      <p className="text-gray-500 mt-0.5 line-clamp-2">{ev.details}</p>
                    </div>
                    <span className="text-gray-400 shrink-0">{new Date(ev.timestamp).toLocaleDateString()}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Policies Tab */}
        {activeDetailTab === "policies" && (
          <div data-testid={`policies-panel-${ctrl.control_id}`}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-gray-500">{ctrl.policy_mappings?.length || 0} linked document{(ctrl.policy_mappings?.length || 0) !== 1 ? "s" : ""}</span>
              <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={async () => {
                setShowLinkDialog(true);
                setLoadingLibrary(true);
                try {
                  const [docs, pols] = await Promise.all([
                    axios.get(`${API}/documents`).then(r => r.data),
                    axios.get(`${API}/policy-templates/generated`).then(r => r.data),
                  ]);
                  setLibraryDocs(docs);
                  setLibraryPolicies(pols);
                } catch {}
                finally { setLoadingLibrary(false); }
              }} data-testid={`link-doc-btn-${ctrl.control_id}`}>
                <Plus size={10} /> Link Document
              </Button>
            </div>

            {ctrl.policy_mappings?.length > 0 ? (
              <div className="space-y-2">
                {ctrl.policy_mappings.map((pm, i) => {
                  const coverage = coverageResults[pm.source_document_id || pm.source_policy_id];
                  return (
                    <div key={pm.id || i} className="p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <FileText size={16} weight="duotone" className="text-[#2597B2]" />
                          <div>
                            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{pm.policy_name || "Unnamed"}</span>
                            <div className="text-[10px] text-gray-500">Source: {pm.source} | Confidence: {Math.round((pm.confidence_score || 0) * 100)}%</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Button size="sm" variant="outline" className="h-6 text-[10px] px-2 gap-1" disabled={analyzingDoc === (pm.source_document_id || pm.source_policy_id)} onClick={async () => {
                            const docId = pm.source_document_id || pm.source_policy_id;
                            if (!docId) { toast.error("No document ID"); return; }
                            setAnalyzingDoc(docId);
                            try {
                              const res = await axios.post(`${API}/control-compliance/${framework.id}/${ctrl.control_id}/analyze-coverage`, { document_id: docId });
                              setCoverageResults(prev => ({ ...prev, [docId]: res.data }));
                              toast.success("Coverage analyzed");
                              onRefresh?.();
                            } catch (err) { toast.error(err.response?.data?.detail || "Analysis failed"); }
                            finally { setAnalyzingDoc(null); }
                          }} data-testid={`analyze-btn-${ctrl.control_id}-${i}`}>
                            {analyzingDoc === (pm.source_document_id || pm.source_policy_id) ? <ArrowsClockwise size={10} className="animate-spin" /> : <ChartBar size={10} />}
                            Analyze
                          </Button>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                            pm.status === "approved" ? "bg-emerald-100 dark:bg-emerald-900/20 text-emerald-700" :
                            pm.status === "linked" ? "bg-blue-100 dark:bg-blue-900/20 text-blue-700" :
                            "bg-gray-100 text-gray-600"
                          }`}>{pm.status}</span>
                          {pm.id && (
                            <button onClick={async () => {
                              try {
                                await axios.delete(`${API}/control-compliance/${framework.id}/${ctrl.control_id}/unlink-document/${pm.id}`);
                                toast.success("Document unlinked");
                                onRefresh?.();
                              } catch { toast.error("Failed to unlink"); }
                            }} className="text-gray-400 hover:text-red-500" data-testid={`unlink-btn-${ctrl.control_id}-${i}`}>
                              <Trash size={12} />
                            </button>
                          )}
                        </div>
                      </div>
                      {/* Coverage Analysis Results */}
                      {(coverage || pm.coverage_analysis) && (() => {
                        const ca = coverage || pm.coverage_analysis;
                        return (
                          <div className="mt-2 pt-2 border-t border-gray-100 dark:border-gray-800" data-testid={`coverage-result-${ctrl.control_id}-${i}`}>
                            <div className="flex items-center gap-3 mb-1.5">
                              <span className={`text-xs font-bold ${ca.coverage_score >= 70 ? "text-emerald-600" : ca.coverage_score >= 40 ? "text-amber-600" : "text-red-600"}`}>{ca.coverage_score}% Coverage</span>
                              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                                ca.coverage_level === "full" ? "bg-emerald-100 text-emerald-700" :
                                ca.coverage_level === "partial" ? "bg-amber-100 text-amber-700" :
                                "bg-red-100 text-red-700"
                              }`}>{ca.coverage_level}</span>
                            </div>
                            {ca.gaps?.length > 0 && (
                              <div className="text-[10px] text-gray-500">
                                <span className="font-semibold text-red-500">Gaps: </span>{ca.gaps.slice(0, 2).join("; ")}
                                {ca.gaps.length > 2 && ` (+${ca.gaps.length - 2} more)`}
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-6 text-gray-500 text-sm">
                <FileText size={24} className="mx-auto mb-2 text-gray-300" />
                No documents linked to this control.
              </div>
            )}

            {/* Link Document Picker */}
            {showLinkDialog && (
              <div className="mt-3 p-3 border border-[#2597B2]/20 rounded-lg bg-[#2597B2]/5" data-testid={`link-picker-${ctrl.control_id}`}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Select a document to link</span>
                  <button onClick={() => setShowLinkDialog(false)} className="text-xs text-gray-400 hover:text-gray-600">Close</button>
                </div>
                {loadingLibrary ? (
                  <div className="flex justify-center py-4"><ArrowsClockwise size={16} className="animate-spin text-[#2597B2]" /></div>
                ) : (
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {[
                      ...libraryPolicies.map(p => ({ id: p.id, name: p.title, type: "generated", status: p.status })),
                      ...libraryDocs.map(d => ({ id: d.job_id || d.id, name: d.filename || d.original_name, type: "uploaded", status: d.status })),
                    ].map(doc => {
                      const alreadyLinked = ctrl.policy_mappings?.some(pm => pm.source_document_id === doc.id || pm.source_policy_id === doc.id);
                      return (
                        <button
                          key={doc.id}
                          disabled={alreadyLinked}
                          onClick={async () => {
                            try {
                              await axios.post(`${API}/control-compliance/${framework.id}/${ctrl.control_id}/link-document`, { document_id: doc.id, document_name: doc.name, document_type: doc.type });
                              toast.success(`Linked "${doc.name}"`);
                              setShowLinkDialog(false);
                              onRefresh?.();
                            } catch (err) { toast.error(err.response?.data?.detail || "Link failed"); }
                          }}
                          className={`w-full flex items-center justify-between p-2 rounded text-xs hover:bg-white dark:hover:bg-gray-800 transition-colors ${alreadyLinked ? "opacity-50 cursor-not-allowed" : ""}`}
                          data-testid={`link-option-${doc.id}`}
                        >
                          <div className="flex items-center gap-2">
                            <FileText size={12} className="text-[#2597B2]" />
                            <span className="text-gray-700 dark:text-gray-300 truncate max-w-[250px]">{doc.name}</span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500">{doc.type === "generated" ? "Policy" : "Upload"}</span>
                            {alreadyLinked && <span className="text-[9px] text-[#2597B2]">Linked</span>}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Notes Tab */}
        {activeDetailTab === "notes" && (
          <div data-testid={`notes-panel-${ctrl.control_id}`}>
            <textarea
              value={notes}
              onChange={(e) => onNotesChange(e.target.value)}
              placeholder="Add notes about this control, implementation details, exceptions, or compliance context..."
              className="w-full p-3 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-[#2597B2] resize-none"
              rows={5}
              data-testid={`notes-textarea-${ctrl.control_id}`}
            />
            <div className="flex justify-end mt-2">
              <Button size="sm" className="bg-[#2597B2] hover:bg-[#1B839F] h-8 text-xs" onClick={onSaveNotes} data-testid={`save-notes-btn-${ctrl.control_id}`}>
                <FloppyDisk size={14} className="mr-1" /> Save Notes
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default FrameworkWorkspace;
