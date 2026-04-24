import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Layout from "@/components/Layout";
import {
  CaretLeft, Plus, Trash, ShieldCheck, Warning, CheckCircle,
  XCircle, Users, ArrowsClockwise, CaretRight, Buildings,
  ClipboardText, Globe, Envelope
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const RISK_COLORS = {
  critical: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  high: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  low: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  not_assessed: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

const STATUS_COLORS = {
  approved: "bg-emerald-50 text-emerald-600",
  conditional: "bg-amber-50 text-amber-600",
  rejected: "bg-red-50 text-red-600",
  pending: "bg-gray-50 text-gray-500",
  review_needed: "bg-purple-50 text-purple-600",
};

const TPRMPage = () => {
  const [view, setView] = useState("list"); // list | add | assess | detail
  const [vendors, setVendors] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [questionnaire, setQuestionnaire] = useState([]);
  const [selectedVendor, setSelectedVendor] = useState(null);
  const [vendorDetail, setVendorDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  // Add form
  const [newVendor, setNewVendor] = useState({ name: "", contact_email: "", website: "", category: "technology", data_access_level: "low", description: "" });
  // Assessment
  const [answers, setAnswers] = useState({});
  const [assessing, setAssessing] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [vRes, dRes, qRes] = await Promise.all([
        axios.get(`${API}/tprm/vendors`),
        axios.get(`${API}/tprm/dashboard`),
        axios.get(`${API}/tprm/questionnaire`),
      ]);
      setVendors(vRes.data);
      setDashboard(dRes.data);
      setQuestionnaire(qRes.data.questions || []);
    } catch {
      toast.error("Failed to load TPRM data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const addVendor = async () => {
    if (!newVendor.name) return toast.error("Vendor name required");
    try {
      await axios.post(`${API}/tprm/vendors`, newVendor);
      toast.success("Vendor added");
      setNewVendor({ name: "", contact_email: "", website: "", category: "technology", data_access_level: "low", description: "" });
      setView("list");
      fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const deleteVendor = async (id) => {
    if (!window.confirm("Delete this vendor?")) return;
    try { await axios.delete(`${API}/tprm/vendors/${id}`); toast.success("Deleted"); fetchAll(); } catch { toast.error("Failed"); }
  };

  const openDetail = async (v) => {
    setSelectedVendor(v);
    try {
      const res = await axios.get(`${API}/tprm/vendors/${v.id}`);
      setVendorDetail(res.data);
      setView("detail");
    } catch { toast.error("Failed to load vendor"); }
  };

  const startAssessment = (v) => {
    setSelectedVendor(v);
    setAnswers({});
    setView("assess");
  };

  const submitAssessment = async () => {
    if (Object.keys(answers).length < 5) return toast.error("Answer at least 5 questions");
    setAssessing(true);
    try {
      const responses = Object.entries(answers).map(([qid, ans]) => ({ question_id: qid, answer: ans }));
      const res = await axios.post(`${API}/tprm/assess`, { vendor_id: selectedVendor.id, responses });
      toast.success(res.data.message);
      setView("list");
      fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setAssessing(false); }
  };

  const updateStatus = async (vendorId, status) => {
    try { await axios.put(`${API}/tprm/vendors/${vendorId}/status`, { status }); toast.success(`Updated to ${status}`); fetchAll(); } catch { toast.error("Failed"); }
  };

  if (loading) return <Layout><div className="text-center py-16 text-gray-400">Loading TPRM...</div></Layout>;

  // Add Vendor View
  if (view === "add") return (
    <Layout><div data-testid="tprm-add">
      <button onClick={() => setView("list")} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#2597B2] mb-6"><CaretLeft size={14} weight="bold" /> Back</button>
      <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Add Vendor</h2>
      <div className="max-w-lg space-y-4">
        <div><label className="text-xs font-medium text-gray-600 block mb-1">Vendor Name *</label><Input value={newVendor.name} onChange={e => setNewVendor({...newVendor, name: e.target.value})} data-testid="vendor-name" /></div>
        <div><label className="text-xs font-medium text-gray-600 block mb-1">Contact Email</label><Input value={newVendor.contact_email} onChange={e => setNewVendor({...newVendor, contact_email: e.target.value})} data-testid="vendor-email" /></div>
        <div><label className="text-xs font-medium text-gray-600 block mb-1">Website</label><Input value={newVendor.website} onChange={e => setNewVendor({...newVendor, website: e.target.value})} /></div>
        <div><label className="text-xs font-medium text-gray-600 block mb-1">Category</label>
          <select value={newVendor.category} onChange={e => setNewVendor({...newVendor, category: e.target.value})} className="w-full h-9 px-3 text-sm border rounded-md" data-testid="vendor-category">
            <option value="technology">Technology</option><option value="cloud">Cloud Provider</option><option value="consulting">Consulting</option><option value="data_processing">Data Processing</option><option value="other">Other</option>
          </select></div>
        <div><label className="text-xs font-medium text-gray-600 block mb-1">Data Access Level</label>
          <select value={newVendor.data_access_level} onChange={e => setNewVendor({...newVendor, data_access_level: e.target.value})} className="w-full h-9 px-3 text-sm border rounded-md" data-testid="vendor-access">
            <option value="none">None</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option>
          </select></div>
        <div><label className="text-xs font-medium text-gray-600 block mb-1">Description</label><textarea value={newVendor.description} onChange={e => setNewVendor({...newVendor, description: e.target.value})} className="w-full h-20 px-3 py-2 text-sm border rounded-md" /></div>
        <Button onClick={addVendor} className="w-full bg-[#2597B2] hover:bg-[#1B839F]" data-testid="save-vendor-btn"><Plus size={16} className="mr-2" /> Add Vendor</Button>
      </div>
    </div></Layout>
  );

  // Assessment View
  if (view === "assess" && selectedVendor) return (
    <Layout><div data-testid="tprm-assess">
      <button onClick={() => setView("list")} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#2597B2] mb-6"><CaretLeft size={14} weight="bold" /> Back</button>
      <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-1">Risk Assessment: {selectedVendor.name}</h2>
      <p className="text-sm text-gray-500 mb-6">Answer the questionnaire to calculate vendor risk score</p>
      <div className="space-y-3 mb-6">
        {questionnaire.map(q => (
          <div key={q.id} className="iv-card p-4" data-testid={`q-${q.id}`}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-mono text-[#2597B2] font-bold">{q.id}</span>
              <span className="text-xs text-gray-400">{q.category}</span>
            </div>
            <p className="text-sm text-gray-900 dark:text-gray-100 mb-3">{q.question}</p>
            <div className="flex gap-2">
              {["yes", "partial", "no", "n/a"].map(opt => (
                <button key={opt} onClick={() => setAnswers({...answers, [q.id]: opt})}
                  className={`px-4 py-1.5 text-xs font-medium rounded-lg border transition-colors ${answers[q.id] === opt
                    ? opt === "yes" ? "bg-emerald-100 border-emerald-300 text-emerald-700" : opt === "partial" ? "bg-amber-100 border-amber-300 text-amber-700" : opt === "no" ? "bg-red-100 border-red-300 text-red-700" : "bg-gray-100 border-gray-300 text-gray-600"
                    : "border-gray-200 text-gray-500 hover:border-gray-300"}`}
                  data-testid={`ans-${q.id}-${opt}`}
                >{opt.toUpperCase()}</button>
              ))}
            </div>
          </div>
        ))}
      </div>
      <Button onClick={submitAssessment} disabled={assessing} className="w-full bg-[#2597B2] hover:bg-[#1B839F] h-11" data-testid="submit-assessment-btn">
        {assessing ? "Calculating..." : `Submit Assessment (${Object.keys(answers).length}/${questionnaire.length} answered)`}
      </Button>
    </div></Layout>
  );

  // Detail View
  if (view === "detail" && vendorDetail) {
    const v = vendorDetail.vendor;
    const riskColor = RISK_COLORS[v.risk_level] || RISK_COLORS.not_assessed;
    return (
      <Layout><div data-testid="tprm-detail">
        <button onClick={() => setView("list")} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#2597B2] mb-6"><CaretLeft size={14} weight="bold" /> Back</button>
        <div className="flex items-start justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{v.name}</h2>
            <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
              {v.category && <span className="capitalize">{v.category}</span>}
              {v.contact_email && <span className="flex items-center gap-1"><Envelope size={14} /> {v.contact_email}</span>}
              {v.website && <span className="flex items-center gap-1"><Globe size={14} /> {v.website}</span>}
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => startAssessment(v)} data-testid="reassess-btn"><ClipboardText size={14} className="mr-1" /> Assess</Button>
            <select value={v.status} onChange={e => updateStatus(v.id, e.target.value)} className="h-8 px-2 text-xs border rounded-md" data-testid="status-select">
              <option value="pending">Pending</option><option value="approved">Approved</option><option value="conditional">Conditional</option><option value="rejected">Rejected</option><option value="review_needed">Review Needed</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="iv-card p-4 text-center"><div className="text-3xl font-bold" style={{color: v.risk_score > 60 ? "#dc2626" : v.risk_score > 30 ? "#d97706" : "#059669"}}>{v.risk_score ?? "—"}</div><div className="text-xs text-gray-500">Risk Score</div></div>
          <div className="iv-card p-4 text-center"><span className={`inline-block px-3 py-1 rounded-full text-sm font-medium ${riskColor}`}>{(v.risk_level || "").replace("_", " ").toUpperCase()}</span><div className="text-xs text-gray-500 mt-1">Risk Level</div></div>
          <div className="iv-card p-4 text-center"><div className="text-sm font-medium text-gray-700">{v.data_access_level?.toUpperCase()}</div><div className="text-xs text-gray-500">Data Access</div></div>
        </div>
        {vendorDetail.assessments?.length > 0 && (
          <div><h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Assessment History</h3>
            <div className="space-y-2">{vendorDetail.assessments.map(a => (
              <div key={a.id} className="iv-card p-3 flex items-center gap-3">
                <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${RISK_COLORS[a.risk_level]}`}>{a.risk_level}</span>
                <span className="text-sm">Risk: {a.risk_score} | Compliance: {a.compliance_score}</span>
                <span className="text-xs text-gray-400 ml-auto">{new Date(a.created_at).toLocaleString()}</span>
              </div>
            ))}</div>
          </div>
        )}
      </div></Layout>
    );
  }

  // List View
  const d = dashboard || {};
  return (
    <Layout><div data-testid="tprm-page">
      <div className="flex items-center justify-between mb-8">
        <div><h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">Vendor Risk Management</h1>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">Third-party risk assessment and compliance tracking</p></div>
        <Button onClick={() => setView("add")} className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="add-vendor-btn"><Plus size={16} className="mr-2" /> Add Vendor</Button>
      </div>
      {/* Stats */}
      <div className="grid grid-cols-5 gap-3 mb-6">
        <div className="iv-card p-4" data-testid="stat-total"><div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{d.total_vendors || 0}</div><div className="text-xs text-gray-500">Total Vendors</div></div>
        <div className="iv-card p-4"><div className="text-2xl font-bold text-red-600">{d.by_risk_level?.critical || 0}</div><div className="text-xs text-gray-500">Critical Risk</div></div>
        <div className="iv-card p-4"><div className="text-2xl font-bold text-amber-600">{(d.by_risk_level?.high || 0) + (d.by_risk_level?.medium || 0)}</div><div className="text-xs text-gray-500">Elevated Risk</div></div>
        <div className="iv-card p-4"><div className="text-2xl font-bold text-emerald-600">{d.by_risk_level?.low || 0}</div><div className="text-xs text-gray-500">Low Risk</div></div>
        <div className="iv-card p-4"><div className="text-2xl font-bold text-[#2597B2]">{d.average_risk || 0}</div><div className="text-xs text-gray-500">Avg Risk Score</div></div>
      </div>
      {/* Vendor List */}
      <div className="space-y-2" data-testid="vendors-list">
        {vendors.length === 0 ? (
          <div className="iv-card p-12 text-center"><Buildings size={48} className="mx-auto text-gray-300 mb-4" /><h3 className="text-lg font-semibold text-gray-700 mb-2">No Vendors Yet</h3><p className="text-sm text-gray-500 mb-4">Add your first vendor to begin third-party risk assessments</p></div>
        ) : vendors.map(v => {
          const riskColor = RISK_COLORS[v.risk_level] || RISK_COLORS.not_assessed;
          const statusColor = STATUS_COLORS[v.status] || STATUS_COLORS.pending;
          return (
            <div key={v.id} className="iv-card p-4 flex items-center gap-4 hover:shadow-md transition-shadow cursor-pointer" onClick={() => openDetail(v)} data-testid={`vendor-${v.id}`}>
              <div className="w-10 h-10 bg-[#2597B2]/10 rounded-lg flex items-center justify-center"><Buildings size={20} className="text-[#2597B2]" /></div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{v.name}</div>
                <div className="text-xs text-gray-500">{v.category} | Data access: {v.data_access_level}</div>
              </div>
              {v.risk_score !== null && v.risk_score !== undefined && <div className="text-right"><div className="text-lg font-bold" style={{color: v.risk_score > 60 ? "#dc2626" : v.risk_score > 30 ? "#d97706" : "#059669"}}>{v.risk_score}</div><div className="text-[10px] text-gray-400">risk</div></div>}
              <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${riskColor}`}>{(v.risk_level || "").replace("_", " ")}</span>
              <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${statusColor}`}>{(v.status || "").replace("_", " ")}</span>
              <button onClick={e => { e.stopPropagation(); startAssessment(v); }} className="p-1.5 rounded hover:bg-blue-50 text-gray-400 hover:text-[#2597B2]" data-testid={`assess-${v.id}`}><ClipboardText size={16} /></button>
              <button onClick={e => { e.stopPropagation(); deleteVendor(v.id); }} className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-500"><Trash size={16} /></button>
              <CaretRight size={14} className="text-gray-400" />
            </div>
          );
        })}
      </div>
    </div></Layout>
  );
};

export default TPRMPage;
