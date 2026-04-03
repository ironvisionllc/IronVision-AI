import React, { useState, useEffect, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { useDemo } from "@/hooks/use-demo";
import {
  GitBranch, Plus, Robot, MagnifyingGlass, CheckCircle, XCircle, Clock,
  Trash, FunnelSimple, FileText, ArrowsClockwise
} from "@phosphor-icons/react";

const STATUS_CONFIG = {
  pending: { label: "Pending", color: "#FB923C", bg: "bg-orange-50", icon: Clock },
  approved: { label: "Approved", color: "#4ADE80", bg: "bg-green-50", icon: CheckCircle },
  rejected: { label: "Rejected", color: "#EF4444", bg: "bg-red-50", icon: XCircle },
};

const MappingsPage = () => {
  const { user } = useContext(AuthContext);
  const { guardDemo } = useDemo();
  const [mappings, setMappings] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [frameworks, setFrameworks] = useState([]);
  const [controls, setControls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState("all");
  const [search, setSearch] = useState("");

  // Manual mapping
  const [showManual, setShowManual] = useState(false);
  const [manualForm, setManualForm] = useState({ policy_id: "", framework_id: "", control_id: "", notes: "" });
  const [filteredControls, setFilteredControls] = useState([]);

  // AI mapping
  const [showAI, setShowAI] = useState(false);
  const [aiPolicyId, setAiPolicyId] = useState("");
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [bulkCreating, setBulkCreating] = useState(false);

  useEffect(() => { fetchData(); }, []);

  const fetchData = async () => {
    try {
      const [mapRes, polRes, fwRes] = await Promise.all([
        axios.get(`${API}/mappings`),
        axios.get(`${API}/policies`),
        axios.get(`${API}/frameworks`),
      ]);
      setMappings(mapRes.data);
      setPolicies(polRes.data);
      setFrameworks(fwRes.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  // Load controls when framework changes in manual form
  useEffect(() => {
    if (manualForm.framework_id) {
      axios.get(`${API}/controls/${manualForm.framework_id}`).then(res => setFilteredControls(res.data)).catch(() => setFilteredControls([]));
    } else {
      setFilteredControls([]);
    }
  }, [manualForm.framework_id]);

  const handleManualCreate = async () => {
    if (guardDemo()) return;
    if (!manualForm.policy_id || !manualForm.framework_id || !manualForm.control_id) {
      toast.error("Policy, framework, and control are required"); return;
    }
    try {
      await axios.post(`${API}/mappings`, manualForm);
      toast.success("Mapping created");
      setShowManual(false);
      setManualForm({ policy_id: "", framework_id: "", control_id: "", notes: "" });
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to create mapping"); }
  };

  const handleAIAnalyze = async () => {
    if (guardDemo()) return;
    if (!aiPolicyId) { toast.error("Select a policy to analyze"); return; }
    setAnalyzing(true);
    setAiSuggestions([]);
    try {
      const res = await axios.post(`${API}/mappings/analyze`, { policy_id: aiPolicyId });
      setAiSuggestions(res.data.suggestions || []);
      if ((res.data.suggestions || []).length === 0) {
        toast.info("AI found no strong control matches for this policy");
      } else {
        toast.success(`AI found ${res.data.suggestions.length} potential mappings`);
      }
    } catch (e) { toast.error(e.response?.data?.detail || "AI analysis failed"); }
    finally { setAnalyzing(false); }
  };

  const handleBulkCreate = async () => {
    if (guardDemo()) return;
    if (aiSuggestions.length === 0) return;
    setBulkCreating(true);
    const policy = policies.find(p => p.id === aiPolicyId);
    try {
      const res = await axios.post(`${API}/mappings/bulk-create`, {
        policy_id: aiPolicyId,
        policy_name: policy?.title || "",
        suggestions: aiSuggestions
      });
      toast.success(`Created ${res.data.created} pending mappings`);
      setAiSuggestions([]);
      setShowAI(false);
      setAiPolicyId("");
      fetchData();
    } catch (e) { toast.error("Failed to create mappings"); }
    finally { setBulkCreating(false); }
  };

  const handleStatusUpdate = async (id, status) => {
    if (guardDemo()) return;
    try {
      await axios.put(`${API}/mappings/${id}/status`, { status });
      toast.success(`Mapping ${status}`);
      setMappings(prev => prev.map(m => m.id === id ? { ...m, status } : m));
    } catch (e) { toast.error("Failed to update mapping"); }
  };

  const handleDelete = async (id) => {
    if (guardDemo()) return;
    try {
      await axios.delete(`${API}/mappings/${id}`);
      toast.success("Mapping deleted");
      setMappings(prev => prev.filter(m => m.id !== id));
    } catch (e) { toast.error("Failed to delete mapping"); }
  };

  // Filter & search
  const filtered = mappings
    .filter(m => filterStatus === "all" || m.status === filterStatus)
    .filter(m => {
      if (!search) return true;
      const q = search.toLowerCase();
      return (m.policy_name || "").toLowerCase().includes(q)
        || (m.control_id || "").toLowerCase().includes(q)
        || (m.control_title || "").toLowerCase().includes(q)
        || (m.framework_name || "").toLowerCase().includes(q);
    });

  const stats = {
    total: mappings.length,
    approved: mappings.filter(m => m.status === "approved").length,
    pending: mappings.filter(m => m.status === "pending").length,
    rejected: mappings.filter(m => m.status === "rejected").length,
    ai: mappings.filter(m => m.source === "ai").length,
    manual: mappings.filter(m => m.source === "manual").length,
  };

  if (loading) return <Layout><div className="flex items-center justify-center h-64"><p className="text-gray-500">Loading mappings...</p></div></Layout>;

  return (
    <Layout>
      <div data-testid="mappings-page">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Control Mappings</h1>
            <p className="text-sm text-gray-600 mt-2">Link policies to compliance framework controls manually or with AI</p>
          </div>
          <div className="flex items-center gap-3">
            {/* Manual Mapping Dialog */}
            <Dialog open={showManual} onOpenChange={v => { if (v && guardDemo()) return; setShowManual(v); }}>
              <DialogTrigger asChild>
                <Button variant="outline" className="flex items-center gap-2 border-[#2597B2] text-[#2597B2] hover:bg-[#2597B2] hover:text-white" data-testid="manual-mapping-button">
                  <Plus size={16} weight="bold" /> Manual Mapping
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-lg">
                <DialogHeader><DialogTitle className="text-xl font-bold text-gray-900" style={{fontFamily: 'Inter, sans-serif'}}>Create Manual Mapping</DialogTitle></DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label className="text-sm font-semibold text-gray-700">Policy *</Label>
                    <Select value={manualForm.policy_id} onValueChange={v => setManualForm({...manualForm, policy_id: v})}>
                      <SelectTrigger className="mt-1" data-testid="manual-policy-select"><SelectValue placeholder="Select a policy" /></SelectTrigger>
                      <SelectContent>{policies.map(p => <SelectItem key={p.id} value={p.id}>{p.title}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-sm font-semibold text-gray-700">Framework *</Label>
                    <Select value={manualForm.framework_id} onValueChange={v => setManualForm({...manualForm, framework_id: v, control_id: ""})}>
                      <SelectTrigger className="mt-1" data-testid="manual-framework-select"><SelectValue placeholder="Select a framework" /></SelectTrigger>
                      <SelectContent>{frameworks.map(f => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-sm font-semibold text-gray-700">Control *</Label>
                    <Select value={manualForm.control_id} onValueChange={v => setManualForm({...manualForm, control_id: v})} disabled={!manualForm.framework_id}>
                      <SelectTrigger className="mt-1" data-testid="manual-control-select"><SelectValue placeholder={manualForm.framework_id ? "Select a control" : "Select framework first"} /></SelectTrigger>
                      <SelectContent className="max-h-60">
                        {filteredControls.map(c => (
                          <SelectItem key={c.control_id || c.id} value={c.control_id || c.id}>
                            {c.control_id || c.id}: {c.title}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-sm font-semibold text-gray-700">Notes</Label>
                    <textarea value={manualForm.notes} onChange={e => setManualForm({...manualForm, notes: e.target.value})} className="mt-1 w-full min-h-[60px] rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="Optional notes..." data-testid="manual-notes-input" />
                  </div>
                  <Button onClick={handleManualCreate} className="w-full bg-[#2597B2] hover:bg-[#1B839F] text-white" data-testid="manual-submit-button">Create Mapping</Button>
                </div>
              </DialogContent>
            </Dialog>

            {/* AI Mapping Dialog */}
            <Dialog open={showAI} onOpenChange={v => { if (v && guardDemo()) return; setShowAI(v); if (!v) { setAiSuggestions([]); setAiPolicyId(""); } }}>
              <DialogTrigger asChild>
                <Button className="bg-[#2597B2] hover:bg-[#1B839F] text-white flex items-center gap-2" data-testid="ai-mapping-button">
                  <Robot size={16} weight="bold" /> AI Mapping
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="text-xl font-bold text-gray-900" style={{fontFamily: 'Inter, sans-serif'}}>AI-Powered Control Mapping</DialogTitle></DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label className="text-sm font-semibold text-gray-700">Select Policy to Analyze</Label>
                    <Select value={aiPolicyId} onValueChange={setAiPolicyId}>
                      <SelectTrigger className="mt-1" data-testid="ai-policy-select"><SelectValue placeholder="Choose a policy with text content" /></SelectTrigger>
                      <SelectContent>
                        {policies.filter(p => p.content).map(p => (
                          <SelectItem key={p.id} value={p.id}>{p.title}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {aiPolicyId && (
                      <div className="mt-2 p-3 bg-gray-50 rounded-lg border border-gray-200">
                        <p className="text-xs text-gray-500 font-semibold mb-1">Policy Preview:</p>
                        <p className="text-sm text-gray-700 line-clamp-3">{policies.find(p => p.id === aiPolicyId)?.content}</p>
                      </div>
                    )}
                  </div>

                  <Button
                    onClick={handleAIAnalyze}
                    disabled={analyzing || !aiPolicyId}
                    className="w-full bg-[#2597B2] hover:bg-[#1B839F] text-white flex items-center justify-center gap-2"
                    data-testid="ai-analyze-button"
                  >
                    {analyzing ? <><ArrowsClockwise size={16} className="animate-spin" /> Analyzing with GPT-5.2...</> : <><Robot size={16} /> Analyze Policy</>}
                  </Button>

                  {/* AI Suggestions */}
                  {aiSuggestions.length > 0 && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold text-gray-900">{aiSuggestions.length} Suggested Mappings</p>
                        <Button
                          onClick={handleBulkCreate}
                          disabled={bulkCreating}
                          size="sm"
                          className="bg-[#2597B2] hover:bg-[#1B839F] text-white text-xs"
                          data-testid="ai-bulk-create-button"
                        >
                          {bulkCreating ? "Creating..." : "Create All as Pending"}
                        </Button>
                      </div>
                      {aiSuggestions.map((s, i) => (
                        <div key={i} className="p-3 bg-white border border-gray-200 rounded-lg" data-testid={`ai-suggestion-${i}`}>
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-semibold text-gray-900">{s.control_id}</span>
                                <span className="text-xs text-gray-500">{s.framework_name}</span>
                              </div>
                              <p className="text-sm text-gray-700 mt-0.5">{s.control_title}</p>
                              {s.reason && <p className="text-xs text-gray-500 mt-1">{s.reason}</p>}
                            </div>
                            <div className="ml-3 flex-shrink-0">
                              <div className={`px-2 py-1 rounded text-xs font-bold ${s.confidence >= 0.85 ? 'bg-green-50 text-green-700' : s.confidence >= 0.7 ? 'bg-blue-50 text-blue-700' : 'bg-orange-50 text-orange-700'}`}>
                                {Math.round(s.confidence * 100)}%
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-6">
          {[
            { label: "Total", val: stats.total, color: "#2597B2" },
            { label: "Approved", val: stats.approved, color: "#4ADE80" },
            { label: "Pending", val: stats.pending, color: "#FB923C" },
            { label: "Rejected", val: stats.rejected, color: "#EF4444" },
            { label: "AI Mapped", val: stats.ai, color: "#60A5FA" },
            { label: "Manual", val: stats.manual, color: "#9CA3AF" },
          ].map(s => (
            <div key={s.label} className="bg-white rounded-lg border border-gray-200 p-4" data-testid={`mapping-stat-${s.label.toLowerCase()}`}>
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-500">{s.label}</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{s.val}</p>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">Status:</span>
            {[{ value: "all", label: "All" }, ...Object.entries(STATUS_CONFIG).map(([k, v]) => ({ value: k, label: v.label }))].map(s => (
              <button key={s.value} onClick={() => setFilterStatus(s.value)}
                className={`px-3 py-1 rounded-full text-xs font-semibold transition-all duration-200 ${filterStatus === s.value ? "bg-[#2597B2] text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
                data-testid={`filter-${s.value}`}>{s.label}
              </button>
            ))}
          </div>
          <div className="relative w-72">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input value={search} onChange={e => setSearch(e.target.value)} className="pl-9 h-9" placeholder="Search policies, controls, frameworks..." data-testid="mapping-search-input" />
          </div>
        </div>

        {/* Mappings List */}
        {filtered.length === 0 ? (
          <div className="bg-white rounded-lg border border-gray-200 p-12 text-center" data-testid="no-mappings">
            <GitBranch size={48} weight="duotone" className="text-gray-300 mx-auto mb-3" />
            <p className="text-gray-400 mb-1">No mappings found</p>
            <p className="text-sm text-gray-400">Use Manual or AI Mapping to link policies to controls</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.slice(0, 50).map(m => {
              const statusCfg = STATUS_CONFIG[m.status] || STATUS_CONFIG.pending;
              const StatusIcon = statusCfg.icon;
              return (
                <div key={m.id} className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-sm transition-all duration-200" data-testid={`mapping-card-${m.id}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4 flex-1 min-w-0">
                      {/* Status */}
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${statusCfg.bg}`}>
                        <StatusIcon size={16} weight="fill" style={{ color: statusCfg.color }} />
                      </div>
                      {/* Policy */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <FileText size={14} className="text-gray-400 flex-shrink-0" />
                          <span className="text-sm font-semibold text-gray-900 truncate">{m.policy_name || m.policy_id}</span>
                        </div>
                      </div>
                      {/* Arrow */}
                      <GitBranch size={16} className="text-gray-300 flex-shrink-0" />
                      {/* Control */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs font-mono font-semibold flex-shrink-0">{m.control_id}</span>
                          <span className="text-sm text-gray-600 truncate">{m.control_title}</span>
                        </div>
                        <span className="text-xs text-gray-400">{m.framework_name}</span>
                      </div>
                      {/* Confidence */}
                      <div className="flex-shrink-0">
                        <span className={`px-2 py-0.5 rounded text-xs font-bold ${m.confidence_score >= 0.85 ? 'bg-green-50 text-green-700' : m.confidence_score >= 0.7 ? 'bg-blue-50 text-blue-700' : 'bg-orange-50 text-orange-700'}`}>
                          {Math.round(m.confidence_score * 100)}%
                        </span>
                      </div>
                      {/* Source badge */}
                      <span className={`px-2 py-0.5 rounded text-xs font-medium flex-shrink-0 ${m.source === 'ai' ? 'bg-purple-50 text-purple-700' : 'bg-gray-50 text-gray-600'}`}>
                        {m.source === 'ai' ? 'AI' : 'Manual'}
                      </span>
                    </div>
                    {/* Actions */}
                    <div className="flex items-center gap-1 ml-4">
                      {m.status === "pending" && (
                        <>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-green-600 hover:text-green-800 hover:bg-green-50" onClick={() => handleStatusUpdate(m.id, "approved")} data-testid={`approve-${m.id}`} title="Approve">
                            <CheckCircle size={18} weight="bold" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-red-500 hover:text-red-700 hover:bg-red-50" onClick={() => handleStatusUpdate(m.id, "rejected")} data-testid={`reject-${m.id}`} title="Reject">
                            <XCircle size={18} weight="bold" />
                          </Button>
                        </>
                      )}
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-gray-400 hover:text-red-500" onClick={() => handleDelete(m.id)} data-testid={`delete-mapping-${m.id}`} title="Delete">
                        <Trash size={16} />
                      </Button>
                    </div>
                  </div>
                  {m.ai_reason && m.source === "ai" && (
                    <p className="text-xs text-gray-500 mt-2 ml-12">{m.ai_reason}</p>
                  )}
                </div>
              );
            })}
            {filtered.length > 50 && (
              <p className="text-center text-sm text-gray-400 py-4">Showing 50 of {filtered.length} mappings. Use search or filters to narrow results.</p>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
};

export default MappingsPage;
