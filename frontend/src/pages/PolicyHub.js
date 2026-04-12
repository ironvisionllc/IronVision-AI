import React, { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import MappingsPage from "@/pages/MappingsPage";
import CrossFrameworkPage from "@/pages/CrossFrameworkPage";
import {
  FileText, Files, CloudArrowUp, GitBranch, FlowArrow, ShieldCheck,
  Lightning, ArrowRight, CheckCircle, Warning, Plus, MagnifyingGlass,
  Pencil, FloppyDisk, ArrowsClockwise, Tag, Trash, Eye, CaretRight,
  CaretDown, Download, BookOpen, Wrench, Clock
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const TABS = [
  { id: "templates", label: "Policy Templates", icon: BookOpen },
  { id: "upload", label: "Upload & Map", icon: CloudArrowUp },
  { id: "library", label: "Document Library", icon: Files },
  { id: "mappings", label: "Control Mappings", icon: GitBranch },
  { id: "cross-framework", label: "Cross-Framework", icon: FlowArrow },
];

const CATEGORY_COLORS = {
  Security: { bg: "bg-blue-50 dark:bg-blue-900/20", text: "text-blue-700 dark:text-blue-400", border: "border-blue-200 dark:border-blue-800" },
  Governance: { bg: "bg-purple-50 dark:bg-purple-900/20", text: "text-purple-700 dark:text-purple-400", border: "border-purple-200 dark:border-purple-800" },
  Privacy: { bg: "bg-teal-50 dark:bg-teal-900/20", text: "text-teal-700 dark:text-teal-400", border: "border-teal-200 dark:border-teal-800" },
  Operations: { bg: "bg-amber-50 dark:bg-amber-900/20", text: "text-amber-700 dark:text-amber-400", border: "border-amber-200 dark:border-amber-800" },
};

const PolicyHub = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get("tab") || "templates";
  const [activeTab, setActiveTab] = useState(TABS.find(t => t.id === initialTab) ? initialTab : "templates");

  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  return (
    <Layout>
      <div data-testid="policy-hub-page">
        <div className="mb-6">
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
            Policy Center
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5">
            Build policies from templates, upload existing documents, and map everything to compliance frameworks
          </p>
        </div>

        <div className="flex items-center gap-1 border-b border-gray-200 dark:border-gray-700 mb-6 overflow-x-auto" data-testid="policy-hub-tabs">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              data-testid={`policy-tab-${tab.id}`}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap ${
                activeTab === tab.id
                  ? "border-[#2597B2] text-[#2597B2]"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300"
              }`}
            >
              <tab.icon size={16} weight={activeTab === tab.id ? "duotone" : "regular"} />
              {tab.label}
            </button>
          ))}
        </div>

        <div data-testid="policy-hub-content">
          {activeTab === "templates" && <PolicyTemplatesTab />}
          {activeTab === "upload" && <UploadMapTab />}
          {activeTab === "library" && <DocumentLibraryTab />}
          {activeTab === "mappings" && <MappingsPage embedded />}
          {activeTab === "cross-framework" && <CrossFrameworkPage embedded />}
        </div>
      </div>
    </Layout>
  );
};


/* ══════════════════════════════════════════════════════════
   TAB 1: POLICY TEMPLATES
   ══════════════════════════════════════════════════════════ */
const PolicyTemplatesTab = () => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [orgProfile, setOrgProfile] = useState({});
  const [showOrgForm, setShowOrgForm] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [generatedPolicy, setGeneratedPolicy] = useState(null);
  const [generatedPolicies, setGeneratedPolicies] = useState([]);
  const [viewingPolicy, setViewingPolicy] = useState(null);
  const [editingSections, setEditingSections] = useState({});
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/policy-templates`).then(r => setTemplates(r.data)).catch(() => {}),
      axios.get(`${API}/policy-templates/org-profile`).then(r => setOrgProfile(r.data || {})).catch(() => {}),
      axios.get(`${API}/policy-templates/generated`).then(r => setGeneratedPolicies(r.data)).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  const saveOrgProfile = async () => {
    try {
      await axios.post(`${API}/policy-templates/org-profile`, orgProfile);
      toast.success("Organization profile saved");
      setShowOrgForm(false);
    } catch { toast.error("Failed to save profile"); }
  };

  const generatePolicy = async (template) => {
    if (!orgProfile.org_name) { setShowOrgForm(true); toast.info("Please fill in your organization profile first"); return; }
    setSelectedTemplate(template);
    setGenerating(true);
    try {
      const res = await axios.post(`${API}/policy-templates/generate`, {
        template_id: template.id,
        org_profile: orgProfile,
        selected_frameworks: Object.keys(template.frameworks),
      });
      setGeneratedPolicy(res.data);
      setGeneratedPolicies(prev => [res.data, ...prev]);
      toast.success("Policy generated successfully");
    } catch (err) { toast.error(err.response?.data?.detail || "Generation failed"); }
    finally { setGenerating(false); }
  };

  const saveSectionEdit = async (policyId, sectionIdx, newContent) => {
    const policy = viewingPolicy || generatedPolicy;
    if (!policy) return;
    const updated = [...policy.sections];
    updated[sectionIdx] = { ...updated[sectionIdx], content: newContent };
    try {
      await axios.put(`${API}/policy-templates/generated/${policyId}/sections`, { sections: updated });
      const p = { ...policy, sections: updated };
      if (viewingPolicy) setViewingPolicy(p);
      else setGeneratedPolicy(p);
      setEditingSections(prev => ({ ...prev, [sectionIdx]: false }));
      toast.success("Section saved");
    } catch { toast.error("Failed to save"); }
  };

  const filtered = templates.filter(t => {
    if (categoryFilter !== "all" && t.category !== categoryFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return t.title.toLowerCase().includes(q) || t.description.toLowerCase().includes(q);
    }
    return true;
  });

  const categories = [...new Set(templates.map(t => t.category))];

  // Viewing a generated policy
  if (viewingPolicy) {
    return <PolicyViewer policy={viewingPolicy} onBack={() => { setViewingPolicy(null); setEditingSections({}); }} editingSections={editingSections} setEditingSections={setEditingSections} onSave={saveSectionEdit} />;
  }

  // Viewing freshly generated policy
  if (generatedPolicy) {
    return <PolicyViewer policy={generatedPolicy} onBack={() => { setGeneratedPolicy(null); setEditingSections({}); }} editingSections={editingSections} setEditingSections={setEditingSections} onSave={saveSectionEdit} />;
  }

  if (loading) return <div className="flex items-center justify-center h-40"><ArrowsClockwise size={24} className="animate-spin text-[#2597B2]" /></div>;

  return (
    <div data-testid="templates-tab">
      {/* Org Profile Banner */}
      {!orgProfile.org_name ? (
        <div className="iv-card p-5 mb-6 border-l-4 border-l-[#2597B2]" data-testid="org-profile-banner">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Set up your Organization Profile</h3>
              <p className="text-xs text-gray-500 mt-0.5">Complete a short questionnaire so generated policies include your CISO, data owners, and org details.</p>
            </div>
            <Button size="sm" className="bg-[#2597B2] hover:bg-[#1B839F] h-8 text-xs" onClick={() => setShowOrgForm(true)} data-testid="setup-org-btn">
              Get Started <ArrowRight size={14} className="ml-1" />
            </Button>
          </div>
        </div>
      ) : (
        <div className="iv-card p-4 mb-6 flex items-center justify-between" data-testid="org-profile-summary">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#2597B2]/10 flex items-center justify-center"><ShieldCheck size={16} weight="duotone" className="text-[#2597B2]" /></div>
            <div>
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{orgProfile.org_name}</span>
              <span className="text-xs text-gray-400 ml-3">CISO: {orgProfile.ciso_name || "—"} | Policy Owner: {orgProfile.policy_owner || "—"}</span>
            </div>
          </div>
          <button onClick={() => setShowOrgForm(true)} className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium" data-testid="edit-org-btn">Edit Profile</button>
        </div>
      )}

      {/* Org Profile Dialog */}
      <Dialog open={showOrgForm} onOpenChange={setShowOrgForm}>
        <DialogContent className="max-w-lg" data-testid="org-profile-dialog">
          <DialogHeader><DialogTitle>Organization Profile</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div><Label>Organization Name *</Label><Input value={orgProfile.org_name || ""} onChange={e => setOrgProfile(p => ({...p, org_name: e.target.value}))} placeholder="Acme Corp" data-testid="org-name-input" /></div>
            <div><Label>Industry</Label><Input value={orgProfile.industry || ""} onChange={e => setOrgProfile(p => ({...p, industry: e.target.value}))} placeholder="Financial Services, Healthcare..." data-testid="org-industry-input" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>CISO Name</Label><Input value={orgProfile.ciso_name || ""} onChange={e => setOrgProfile(p => ({...p, ciso_name: e.target.value}))} placeholder="Jane Smith" data-testid="ciso-name-input" /></div>
              <div><Label>CISO Title</Label><Input value={orgProfile.ciso_title || "Chief Information Security Officer"} onChange={e => setOrgProfile(p => ({...p, ciso_title: e.target.value}))} data-testid="ciso-title-input" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Data Owner</Label><Input value={orgProfile.data_owner || ""} onChange={e => setOrgProfile(p => ({...p, data_owner: e.target.value}))} placeholder="John Doe" data-testid="data-owner-input" /></div>
              <div><Label>Policy Owner</Label><Input value={orgProfile.policy_owner || ""} onChange={e => setOrgProfile(p => ({...p, policy_owner: e.target.value}))} placeholder="Sarah Johnson" data-testid="policy-owner-input" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Compliance Officer</Label><Input value={orgProfile.compliance_officer || ""} onChange={e => setOrgProfile(p => ({...p, compliance_officer: e.target.value}))} data-testid="compliance-officer-input" /></div>
              <div><Label>Review Frequency</Label><Input value={orgProfile.review_frequency || "Annually"} onChange={e => setOrgProfile(p => ({...p, review_frequency: e.target.value}))} data-testid="review-freq-input" /></div>
            </div>
            <Button className="w-full bg-[#2597B2] hover:bg-[#1B839F]" onClick={saveOrgProfile} data-testid="save-org-btn">Save Profile</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-5">
        <div className="relative flex-1 max-w-sm">
          <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <Input placeholder="Search templates..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9 h-9 text-sm" data-testid="template-search" />
        </div>
        <select value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)} className="h-9 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300" data-testid="template-category-filter">
          <option value="all">All Categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {/* Template Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8" data-testid="template-grid">
        {filtered.map(t => {
          const cat = CATEGORY_COLORS[t.category] || CATEGORY_COLORS.Security;
          return (
            <div key={t.id} className="iv-card p-5 hover:ring-1 hover:ring-[#2597B2]/20 transition-all group" data-testid={`template-card-${t.id}`}>
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 group-hover:text-[#2597B2] transition-colors">{t.title}</h3>
                  <p className="text-xs text-gray-500 mt-1 line-clamp-2">{t.description}</p>
                </div>
                <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${cat.bg} ${cat.text} ${cat.border}`}>{t.category}</span>
              </div>

              <div className="flex flex-wrap gap-1.5 mb-3">
                {Object.entries(t.frameworks).map(([fw, ctrls]) => (
                  <span key={fw} className="text-[10px] px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 font-medium">{fw} ({ctrls.length})</span>
                ))}
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 text-[10px] text-gray-400">
                  <span>{t.control_count} controls</span>
                  <span>{t.sections.length} sections</span>
                  {t.has_siem && <span className="flex items-center gap-0.5 text-blue-500"><Lightning size={10} weight="fill" /> SIEM thresholds</span>}
                </div>
                <Button size="sm" className="h-7 text-xs bg-[#2597B2] hover:bg-[#1B839F]" onClick={() => generatePolicy(t)} disabled={generating && selectedTemplate?.id === t.id} data-testid={`generate-btn-${t.id}`}>
                  {generating && selectedTemplate?.id === t.id ? <><ArrowsClockwise size={12} className="animate-spin mr-1" /> Generating...</> : <>Generate <ArrowRight size={12} className="ml-1" /></>}
                </Button>
              </div>

              {/* SIEM Thresholds Preview */}
              {t.siem_thresholds?.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
                  <p className="text-[10px] font-semibold text-blue-600 dark:text-blue-400 mb-1.5 flex items-center gap-1"><Lightning size={10} weight="fill" /> SIEM Monitoring Thresholds</p>
                  <div className="space-y-1">
                    {t.siem_thresholds.slice(0, 2).map((st, i) => (
                      <div key={i} className="text-[10px] text-gray-500 flex items-start gap-1.5">
                        <span className="font-mono font-bold text-[#2597B2] shrink-0">{st.control_id}</span>
                        <span className="line-clamp-1">{st.threshold}</span>
                      </div>
                    ))}
                    {t.siem_thresholds.length > 2 && <span className="text-[10px] text-gray-400">+{t.siem_thresholds.length - 2} more</span>}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Generated Policies */}
      {generatedPolicies.length > 0 && (
        <div data-testid="generated-policies-section">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Generated Policies</h3>
          <div className="space-y-2">
            {generatedPolicies.map(p => (
              <div key={p.id} className="iv-card p-4 flex items-center justify-between hover:ring-1 hover:ring-[#2597B2]/20 transition-all cursor-pointer" onClick={() => setViewingPolicy(p)} data-testid={`generated-policy-${p.id}`}>
                <div className="flex items-center gap-3">
                  <FileText size={18} weight="duotone" className="text-[#2597B2]" />
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{p.title}</p>
                    <p className="text-[10px] text-gray-400">v{p.version} | {p.sections?.length} sections | {new Date(p.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${p.status === "draft" ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"}`}>{p.status}</span>
                  <CaretRight size={14} className="text-gray-400" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};


/* ── Policy Viewer / Editor ── */
const PolicyViewer = ({ policy, onBack, editingSections, setEditingSections, onSave }) => {
  const [editBuffer, setEditBuffer] = useState({});

  return (
    <div data-testid="policy-viewer">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-[#2597B2] hover:text-[#1B839F] font-medium mb-4" data-testid="back-to-templates">
        <CaretRight size={14} weight="bold" className="rotate-180" /> Back to Templates
      </button>

      <div className="flex items-start justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{policy.title}</h2>
          <p className="text-xs text-gray-400 mt-1">Version {policy.version} | {policy.sections?.length} sections | Created {new Date(policy.created_at).toLocaleDateString()}</p>
        </div>
        <div className="flex items-center gap-2">
          {policy.frameworks_addressed?.map(fw => (
            <span key={fw} className="text-[10px] px-2 py-0.5 rounded bg-[#2597B2]/10 text-[#2597B2] font-medium">{fw}</span>
          ))}
        </div>
      </div>

      <div className="space-y-4" data-testid="policy-sections">
        {(policy.sections || []).map((section, idx) => (
          <div key={idx} className="iv-card" data-testid={`policy-section-${idx}`}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 dark:border-gray-800">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{section.heading}</h3>
              <button
                onClick={() => {
                  if (editingSections[idx]) { setEditingSections(p => ({...p, [idx]: false})); }
                  else { setEditBuffer(p => ({...p, [idx]: section.content})); setEditingSections(p => ({...p, [idx]: true})); }
                }}
                className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium flex items-center gap-1"
                data-testid={`edit-section-btn-${idx}`}
              >
                {editingSections[idx] ? "Cancel" : <><Pencil size={12} /> Edit</>}
              </button>
            </div>
            <div className="p-5">
              {editingSections[idx] ? (
                <div>
                  <Textarea
                    value={editBuffer[idx] || ""}
                    onChange={e => setEditBuffer(p => ({...p, [idx]: e.target.value}))}
                    rows={12}
                    className="text-sm font-mono"
                    data-testid={`section-editor-${idx}`}
                  />
                  <div className="flex justify-end mt-2">
                    <Button size="sm" className="h-7 text-xs bg-[#2597B2] hover:bg-[#1B839F]" onClick={() => onSave(policy.id, idx, editBuffer[idx])} data-testid={`save-section-btn-${idx}`}>
                      <FloppyDisk size={12} className="mr-1" /> Save
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">{section.content}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};


/* ══════════════════════════════════════════════════════════
   TAB 2: UPLOAD & MAP
   ══════════════════════════════════════════════════════════ */
const UploadMapTab = () => {
  const [frameworks, setFrameworks] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [selectedFrameworks, setSelectedFrameworks] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/frameworks`).then(r => setFrameworks(r.data)).catch(() => {}),
      axios.get(`${API}/documents`).then(r => setDocuments(r.data)).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  const toggleFramework = (id) => {
    setSelectedFrameworks(prev => prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]);
  };

  const handleUpload = async (file) => {
    if (!file) return;
    if (selectedFrameworks.length === 0) { toast.error("Select at least one framework to map against"); return; }
    const allowedTypes = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"];
    if (!allowedTypes.includes(file.type)) { toast.error("Only PDF and DOCX files are supported"); return; }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("framework", selectedFrameworks[0]);
      formData.append("control_family", "");
      const res = await axios.post(`${API}/documents/upload`, formData, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Document uploaded. Select it in Document Library to tag to controls.");
      const updated = await axios.get(`${API}/documents`);
      setDocuments(updated.data);
    } catch (err) { toast.error(err.response?.data?.detail || "Upload failed"); }
    finally { setUploading(false); }
  };

  return (
    <div data-testid="upload-tab">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Framework Selection */}
        <div className="iv-card p-5" data-testid="framework-selector">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">Select Target Frameworks</h3>
          <p className="text-[10px] text-gray-400 mb-3">Choose which frameworks to map your document against</p>
          <div className="space-y-1.5 max-h-[400px] overflow-y-auto">
            {frameworks.map(fw => (
              <label key={fw.id} className={`flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer transition-all ${selectedFrameworks.includes(fw.id) ? "bg-[#2597B2]/5 border-[#2597B2]/30 ring-1 ring-[#2597B2]/20" : "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:border-gray-300"}`} data-testid={`fw-select-${fw.id}`}>
                <input type="checkbox" checked={selectedFrameworks.includes(fw.id)} onChange={() => toggleFramework(fw.id)} className="rounded border-gray-300 text-[#2597B2] focus:ring-[#2597B2]" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">{fw.name}</p>
                  <p className="text-[10px] text-gray-400">{fw.control_count || 0} controls</p>
                </div>
                {selectedFrameworks.includes(fw.id) && <CheckCircle size={14} weight="fill" className="text-[#2597B2] shrink-0" />}
              </label>
            ))}
          </div>
          {selectedFrameworks.length > 0 && (
            <p className="text-[10px] text-[#2597B2] font-medium mt-2">{selectedFrameworks.length} framework{selectedFrameworks.length > 1 ? "s" : ""} selected</p>
          )}
        </div>

        {/* Right: Upload Area */}
        <div className="lg:col-span-2">
          <div
            className={`iv-card p-8 text-center border-2 border-dashed transition-all ${dragOver ? "border-[#2597B2] bg-[#2597B2]/5" : "border-gray-200 dark:border-gray-700"}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleUpload(e.dataTransfer.files[0]); }}
            data-testid="upload-dropzone"
          >
            <CloudArrowUp size={40} weight="duotone" className={`mx-auto mb-3 ${dragOver ? "text-[#2597B2]" : "text-gray-300"}`} />
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {uploading ? "Uploading..." : "Drop a policy document here"}
            </p>
            <p className="text-xs text-gray-400 mb-4">PDF or DOCX files supported</p>
            <label className="inline-block">
              <input type="file" accept=".pdf,.docx" onChange={e => handleUpload(e.target.files[0])} className="hidden" />
              <Button variant="outline" size="sm" className="h-8 text-xs" disabled={uploading} asChild>
                <span data-testid="browse-files-btn">{uploading ? <ArrowsClockwise size={14} className="animate-spin mr-1" /> : <Plus size={14} className="mr-1" />} Browse Files</span>
              </Button>
            </label>
          </div>

          {/* Recent Uploads */}
          {documents.length > 0 && (
            <div className="mt-4" data-testid="recent-uploads">
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Recent Uploads</h4>
              <div className="space-y-2">
                {documents.slice(0, 5).map(doc => (
                  <div key={doc.job_id} className="iv-card p-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText size={16} weight="duotone" className="text-[#2597B2]" />
                      <div>
                        <p className="text-xs font-medium text-gray-900 dark:text-gray-100">{doc.filename}</p>
                        <p className="text-[10px] text-gray-400">{doc.framework} | {new Date(doc.created_at).toLocaleDateString()}</p>
                      </div>
                    </div>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${doc.status === "completed" ? "bg-emerald-50 text-emerald-700" : doc.status === "failed" ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"}`}>{doc.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};


/* ══════════════════════════════════════════════════════════
   TAB 3: DOCUMENT LIBRARY
   ══════════════════════════════════════════════════════════ */
const DocumentLibraryTab = () => {
  const [documents, setDocuments] = useState([]);
  const [tags, setTags] = useState([]);
  const [frameworks, setFrameworks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showTagDialog, setShowTagDialog] = useState(false);
  const [tagForm, setTagForm] = useState({ document_id: "", document_name: "", framework_id: "", framework_name: "", control_ids: "", notes: "" });

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/documents`).then(r => setDocuments(r.data)).catch(() => {}),
      axios.get(`${API}/policy-templates/document-tags`).then(r => setTags(r.data)).catch(() => {}),
      axios.get(`${API}/frameworks`).then(r => setFrameworks(r.data)).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  const createTag = async () => {
    if (!tagForm.document_id || !tagForm.framework_id) { toast.error("Select a document and framework"); return; }
    try {
      const fw = frameworks.find(f => f.id === tagForm.framework_id);
      const res = await axios.post(`${API}/policy-templates/document-tags`, {
        ...tagForm,
        framework_name: fw?.name || "",
        control_ids: tagForm.control_ids.split(",").map(s => s.trim()).filter(Boolean),
      });
      setTags(prev => [...prev, res.data]);
      setShowTagDialog(false);
      setTagForm({ document_id: "", document_name: "", framework_id: "", framework_name: "", control_ids: "", notes: "" });
      toast.success("Document tagged to controls");
    } catch { toast.error("Failed to tag document"); }
  };

  const removeTag = async (tagId) => {
    try {
      await axios.delete(`${API}/policy-templates/document-tags/${tagId}`);
      setTags(prev => prev.filter(t => t.id !== tagId));
      toast.success("Tag removed");
    } catch { toast.error("Failed to remove tag"); }
  };

  const filtered = documents.filter(d => {
    if (search) {
      const q = search.toLowerCase();
      return d.filename?.toLowerCase().includes(q);
    }
    return true;
  });

  if (loading) return <div className="flex items-center justify-center h-40"><ArrowsClockwise size={24} className="animate-spin text-[#2597B2]" /></div>;

  return (
    <div data-testid="library-tab">
      <div className="flex items-center justify-between mb-4">
        <div className="relative flex-1 max-w-sm">
          <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <Input placeholder="Search documents..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9 h-9 text-sm" data-testid="library-search" />
        </div>
        <Button size="sm" className="h-8 text-xs bg-[#2597B2] hover:bg-[#1B839F]" onClick={() => setShowTagDialog(true)} data-testid="tag-document-btn">
          <Tag size={14} className="mr-1" /> Tag Document
        </Button>
      </div>

      {/* Tag Dialog */}
      <Dialog open={showTagDialog} onOpenChange={setShowTagDialog}>
        <DialogContent data-testid="tag-dialog">
          <DialogHeader><DialogTitle>Tag Document to Controls</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div>
              <Label>Document</Label>
              <select value={tagForm.document_id} onChange={e => { const d = documents.find(dd => dd.job_id === e.target.value); setTagForm(p => ({...p, document_id: e.target.value, document_name: d?.filename || ""})); }} className="w-full h-9 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800" data-testid="tag-document-select">
                <option value="">Select a document...</option>
                {documents.map(d => <option key={d.job_id} value={d.job_id}>{d.filename}</option>)}
              </select>
            </div>
            <div>
              <Label>Framework</Label>
              <select value={tagForm.framework_id} onChange={e => setTagForm(p => ({...p, framework_id: e.target.value}))} className="w-full h-9 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800" data-testid="tag-framework-select">
                <option value="">Select a framework...</option>
                {frameworks.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            </div>
            <div>
              <Label>Control IDs (comma-separated)</Label>
              <Input value={tagForm.control_ids} onChange={e => setTagForm(p => ({...p, control_ids: e.target.value}))} placeholder="AC-2, AC-3, IA-2" data-testid="tag-controls-input" />
            </div>
            <div>
              <Label>Notes</Label>
              <Input value={tagForm.notes} onChange={e => setTagForm(p => ({...p, notes: e.target.value}))} placeholder="Optional notes..." data-testid="tag-notes-input" />
            </div>
            <Button className="w-full bg-[#2597B2] hover:bg-[#1B839F]" onClick={createTag} data-testid="save-tag-btn">Tag Document</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Documents List */}
      {filtered.length === 0 ? (
        <div className="text-center py-12">
          <Files size={32} className="mx-auto mb-2 text-gray-300" />
          <p className="text-sm text-gray-500">No documents yet. Upload one in the "Upload & Map" tab.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="documents-list">
          {filtered.map(doc => {
            const docTags = tags.filter(t => t.document_id === doc.job_id);
            return (
              <div key={doc.job_id} className="iv-card p-4" data-testid={`doc-${doc.job_id}`}>
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <FileText size={20} weight="duotone" className="text-[#2597B2] shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{doc.filename}</p>
                      <p className="text-[10px] text-gray-400">{doc.framework} | Uploaded {new Date(doc.created_at).toLocaleDateString()}</p>
                    </div>
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${doc.status === "completed" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{doc.status}</span>
                </div>

                {/* Tags */}
                {docTags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-gray-100 dark:border-gray-800">
                    {docTags.map(tag => (
                      <div key={tag.id} className="flex items-center gap-1 px-2 py-1 bg-[#2597B2]/5 border border-[#2597B2]/20 rounded text-[10px]" data-testid={`tag-${tag.id}`}>
                        <Tag size={10} className="text-[#2597B2]" />
                        <span className="font-medium text-[#2597B2]">{tag.framework_name}</span>
                        {tag.control_ids?.length > 0 && <span className="text-gray-400">: {tag.control_ids.join(", ")}</span>}
                        <button onClick={() => removeTag(tag.id)} className="ml-1 text-gray-400 hover:text-red-500"><Trash size={10} /></button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};


export default PolicyHub;
