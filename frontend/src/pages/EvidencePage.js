import React, { useState, useEffect, useContext, useRef } from "react";
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
  FileArrowUp, 
  File as FileIcon, 
  Trash, 
  MagnifyingGlass,
  FolderOpen,
  Image,
  FileText,
  FilePdf,
  Tag,
  DownloadSimple,
  Paperclip,
  X
} from "@phosphor-icons/react";

const EVIDENCE_TYPES = [
  { value: "document", label: "Document" },
  { value: "screenshot", label: "Screenshot" },
  { value: "log", label: "System Log" },
  { value: "attestation", label: "Attestation" },
  { value: "certificate", label: "Certificate" },
  { value: "report", label: "Report" },
];

const formatFileSize = (bytes) => {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const EvidencePage = ({ embedded = false }) => {
  const { user } = useContext(AuthContext);
  const { isDemo, isDemoViewer, guardDemo } = useDemo();
  const Wrap = embedded ? React.Fragment : Layout;
  const [evidence, setEvidence] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState("all");
  const [form, setForm] = useState({ description: "", evidence_type: "document", tags: "", control_id: "", framework_name: "" });
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => { fetchEvidence(); }, []);

  const fetchEvidence = async () => {
    try {
      const res = await axios.get(`${API}/evidence`);
      setEvidence(res.data);
    } catch (error) {
      console.error("Failed to fetch evidence", error);
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setForm({ description: "", evidence_type: "document", tags: "", control_id: "", framework_name: "" });
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleUpload = async () => {
    if (guardDemo()) return;
    if (!form.description.trim()) { toast.error("Description is required"); return; }
    
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("description", form.description);
      formData.append("evidence_type", form.evidence_type);
      formData.append("control_id", form.control_id);
      formData.append("framework_name", form.framework_name);
      formData.append("tags", form.tags);
      if (selectedFile) {
        formData.append("file", selectedFile);
      }

      await axios.post(`${API}/evidence`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      toast.success("Evidence added to library");
      setShowUpload(false);
      resetForm();
      fetchEvidence();
    } catch (error) {
      const msg = error.response?.data?.detail || "Failed to add evidence";
      toast.error(msg);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id) => {
    if (guardDemo()) return;
    try {
      await axios.delete(`${API}/evidence/${id}`);
      toast.success("Evidence removed");
      fetchEvidence();
    } catch (error) {
      toast.error("Failed to delete evidence");
    }
  };

  const handleDownload = async (item) => {
    try {
      const response = await axios.get(`${API}/evidence/${item.id}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = item.file?.original_name || "download";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      toast.error("Failed to download file");
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) {
      toast.error("File too large. Maximum size is 50MB.");
      return;
    }
    setSelectedFile(file);
  };

  const getTypeIcon = (type) => {
    switch(type) {
      case "screenshot": return Image;
      case "document": case "report": return FileText;
      case "certificate": return FilePdf;
      default: return FileIcon;
    }
  };

  const filtered = evidence
    .filter(e => filterType === "all" || e.evidence_type === filterType)
    .filter(e => !search || e.description.toLowerCase().includes(search.toLowerCase()) || (e.tags || []).some(t => t.toLowerCase().includes(search.toLowerCase())));

  const isAdmin = user?.roles?.[0]?.role === "admin";

  if (loading) return <Wrap><div className="flex items-center justify-center h-64"><p className="text-gray-500">Loading evidence library...</p></div></Wrap>;

  return (
    <Wrap>
      <div data-testid="evidence-page">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Evidence Library</h1>
            <p className="text-sm text-gray-600 mt-2">Central repository for compliance evidence and documentation</p>
          </div>
          <Dialog open={showUpload} onOpenChange={v => { if (v && guardDemo()) return; setShowUpload(v); if (!v) resetForm(); }}>
            <DialogTrigger asChild>
              <Button className="bg-[#2597B2] hover:bg-[#1B839F] text-white flex items-center gap-2" data-testid="add-evidence-button">
                <FileArrowUp size={18} weight="bold" /> Add Evidence
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader><DialogTitle className="text-xl font-bold text-gray-900" style={{fontFamily: 'Inter, sans-serif'}}>Add Evidence</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div>
                  <Label className="text-sm font-semibold text-gray-700">Description *</Label>
                  <textarea value={form.description} onChange={e => setForm({...form, description: e.target.value})} className="mt-1 w-full min-h-[80px] rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#2597B2] focus:border-transparent" placeholder="Describe this evidence..." data-testid="evidence-description-input" />
                </div>
                
                {/* File Upload */}
                <div>
                  <Label className="text-sm font-semibold text-gray-700">Attach File</Label>
                  <div className="mt-1">
                    {!selectedFile ? (
                      <label 
                        className="flex flex-col items-center justify-center w-full h-28 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer bg-gray-50 hover:bg-gray-100 hover:border-[#2597B2] transition-all duration-200"
                        data-testid="evidence-file-dropzone"
                      >
                        <div className="flex flex-col items-center justify-center py-3">
                          <FileArrowUp size={28} weight="duotone" className="text-gray-400 mb-1" />
                          <p className="text-sm text-gray-500">Click to upload a file</p>
                          <p className="text-xs text-gray-400 mt-0.5">PDF, DOC, XLS, PNG, JPG up to 50MB</p>
                        </div>
                        <input 
                          ref={fileInputRef}
                          type="file" 
                          className="hidden" 
                          onChange={handleFileSelect}
                          accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.csv,.txt,.log,.zip"
                          data-testid="evidence-file-input"
                        />
                      </label>
                    ) : (
                      <div className="flex items-center gap-3 p-3 bg-gray-50 border border-gray-200 rounded-lg" data-testid="evidence-file-selected">
                        <Paperclip size={18} className="text-[#2597B2] flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">{selectedFile.name}</p>
                          <p className="text-xs text-gray-500">{formatFileSize(selectedFile.size)}</p>
                        </div>
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="h-7 w-7 text-gray-400 hover:text-red-500"
                          onClick={() => { setSelectedFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                          data-testid="evidence-file-remove"
                        >
                          <X size={14} />
                        </Button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-sm font-semibold text-gray-700">Type</Label>
                    <Select value={form.evidence_type} onValueChange={v => setForm({...form, evidence_type: v})}>
                      <SelectTrigger className="mt-1" data-testid="evidence-type-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{EVIDENCE_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-sm font-semibold text-gray-700">Framework</Label>
                    <Input value={form.framework_name} onChange={e => setForm({...form, framework_name: e.target.value})} className="mt-1" placeholder="e.g. SOC 2" data-testid="evidence-framework-input" />
                  </div>
                </div>
                <div>
                  <Label className="text-sm font-semibold text-gray-700">Control ID</Label>
                  <Input value={form.control_id} onChange={e => setForm({...form, control_id: e.target.value})} className="mt-1" placeholder="e.g. CC6.1" data-testid="evidence-control-input" />
                </div>
                <div>
                  <Label className="text-sm font-semibold text-gray-700">Tags</Label>
                  <Input value={form.tags} onChange={e => setForm({...form, tags: e.target.value})} className="mt-1" placeholder="access-control, encryption, annual-review" data-testid="evidence-tags-input" />
                </div>
                <Button 
                  onClick={handleUpload} 
                  disabled={uploading}
                  className="w-full bg-[#2597B2] hover:bg-[#1B839F] text-white" 
                  data-testid="evidence-submit-button"
                >
                  {uploading ? "Uploading..." : "Add to Library"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>

        {/* Search & Filter */}
        <div className="flex items-center gap-3 mb-6">
          <div className="relative flex-1 max-w-md">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input value={search} onChange={e => setSearch(e.target.value)} className="pl-9" placeholder="Search evidence..." data-testid="evidence-search-input" />
          </div>
          <Select value={filterType} onValueChange={setFilterType}>
            <SelectTrigger className="w-[160px]" data-testid="evidence-filter-type"><SelectValue placeholder="All Types" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              {EVIDENCE_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          {[
            { label: "Total Evidence", val: evidence.length, color: "#2597B2" },
            { label: "With Files", val: evidence.filter(e => e.file).length, color: "#60A5FA" },
            { label: "Documents", val: evidence.filter(e => e.evidence_type === "document").length, color: "#4ADE80" },
            { label: "Reports", val: evidence.filter(e => e.evidence_type === "report").length, color: "#FB923C" },
            { label: "Attestations", val: evidence.filter(e => e.evidence_type === "attestation").length, color: "#9333EA" },
          ].map(s => (
            <div key={s.label} className="bg-white rounded-lg border border-gray-200 p-4" data-testid={`evidence-stat-${s.label.toLowerCase().replace(/ /g, '-')}`}>
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-500">{s.label}</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{s.val}</p>
            </div>
          ))}
        </div>

        {/* Evidence List */}
        {filtered.length === 0 ? (
          <div className="bg-white rounded-lg border border-gray-200 p-12 text-center" data-testid="no-evidence">
            <FolderOpen size={48} weight="duotone" className="text-gray-300 mx-auto mb-3" />
            <p className="text-gray-400 mb-1">No evidence found</p>
            <p className="text-sm text-gray-400">Add your first piece of evidence to get started</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map(item => {
              const TypeIcon = getTypeIcon(item.evidence_type);
              const hasFile = !!item.file;
              return (
                <div key={item.id} className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-sm hover:-translate-y-[1px] transition-all duration-200" data-testid={`evidence-card-${item.id}`}>
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3 flex-1 min-w-0">
                      <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-gray-100 flex-shrink-0">
                        <TypeIcon size={18} weight="duotone" className="text-gray-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-gray-900 text-sm">{item.description}</p>
                        <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                          <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-medium">{item.evidence_type}</span>
                          {item.framework_name && <span className="text-xs text-gray-500">{item.framework_name}</span>}
                          {item.control_id && <span className="text-xs text-gray-400">Control: {item.control_id}</span>}
                          {(item.tags || []).map(tag => <span key={tag} className="px-2 py-0.5 bg-blue-50 text-blue-600 rounded text-xs flex items-center gap-1"><Tag size={10} />{tag}</span>)}
                        </div>
                        {/* File info */}
                        {hasFile && (
                          <div className="flex items-center gap-2 mt-2">
                            <Paperclip size={13} className="text-gray-400" />
                            <span className="text-xs text-gray-500">{item.file.original_name}</span>
                            <span className="text-xs text-gray-400">({formatFileSize(item.file.size)})</span>
                          </div>
                        )}
                        <p className="text-xs text-gray-400 mt-1">
                          {item.uploaded_by_name && `${item.uploaded_by_name} - `}
                          {new Date(item.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 ml-4">
                      {hasFile && (
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="h-8 w-8 text-[#2597B2] hover:text-[#1B839F]" 
                          onClick={() => handleDownload(item)}
                          data-testid={`evidence-download-${item.id}`}
                        >
                          <DownloadSimple size={16} weight="bold" />
                        </Button>
                      )}
                      {isAdmin && !isDemoViewer && (
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-red-500 hover:text-red-700" onClick={() => handleDelete(item.id)} data-testid={`evidence-delete-${item.id}`}>
                          <Trash size={16} />
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Wrap>
  );
};

export default EvidencePage;
