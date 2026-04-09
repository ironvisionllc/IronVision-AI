import React, { useState, useEffect, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import {
  CloudArrowUp, FileText, MagnifyingGlass, Clock, CheckCircle,
  Warning, ArrowDown, Spinner, Trash, Eye
} from "@phosphor-icons/react";

const DocumentsPage = ({ embedded = false }) => {
  const { user } = useContext(AuthContext);
  const isAdmin = user?.roles?.[0]?.role === "admin";
  const Wrap = embedded ? React.Fragment : Layout;
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [framework, setFramework] = useState("nist-800-53");
  const [controlFamily, setControlFamily] = useState("");
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => { fetchDocuments(); }, []);

  const fetchDocuments = async () => {
    try {
      const res = await axios.get(`${API}/documents`);
      setDocuments(res.data);
    } catch {} finally { setLoading(false); }
  };

  const handleUpload = async (file) => {
    if (!file) return;
    const allowedTypes = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"];
    if (!allowedTypes.includes(file.type)) {
      toast.error("Only PDF and DOCX files are supported");
      return;
    }
    setUploading(true);
    setUploadProgress(0);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("framework", framework);
      formData.append("control_family", controlFamily);

      const res = await axios.post(`${API}/documents/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (e.total) setUploadProgress(Math.round((e.loaded / e.total) * 100));
        },
      });
      toast.success(res.data.message || "Document uploaded");
      fetchDocuments();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const triggerAnalysis = async (jobId) => {
    try {
      const res = await axios.post(`${API}/documents/${jobId}/analyze`);
      toast.success(res.data.message || "Analysis started");
      fetchDocuments();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Analysis failed");
    }
  };

  const statusBadge = (status) => {
    const map = {
      uploaded: { bg: "bg-gray-100 dark:bg-gray-700", text: "text-gray-600 dark:text-gray-300", icon: Clock },
      uploaded_pending_processing: { bg: "bg-amber-50", text: "text-amber-700", icon: Clock },
      preprocessing: { bg: "bg-blue-50", text: "text-blue-700", icon: Spinner },
      preprocessed: { bg: "bg-green-50", text: "text-green-700", icon: CheckCircle },
      analyzing: { bg: "bg-blue-50", text: "text-blue-700", icon: MagnifyingGlass },
      analysis_completed: { bg: "bg-green-50", text: "text-green-700", icon: CheckCircle },
      error: { bg: "bg-red-50", text: "text-red-700", icon: Warning },
    };
    return map[status] || map.uploaded;
  };

  return (
    <Wrap>
      <div data-testid="documents-page">
        <div className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">Document Analysis</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5">Upload compliance documents for AI-powered analysis</p>
        </div>

        {/* Upload Area */}
        {isAdmin && (
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-6 mb-6 shadow-sm" data-testid="upload-section">
            <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 mb-4">Upload Document</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <Label className="text-xs font-medium text-gray-500">Framework</Label>
                <Select value={framework} onValueChange={setFramework}>
                  <SelectTrigger className="rounded-xl mt-1" data-testid="upload-framework-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="nist-800-53">NIST 800-53</SelectItem>
                    <SelectItem value="nist-csf">NIST CSF</SelectItem>
                    <SelectItem value="iso-27001">ISO 27001</SelectItem>
                    <SelectItem value="hipaa">HIPAA</SelectItem>
                    <SelectItem value="soc-2">SOC 2</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs font-medium text-gray-500">Control Family (optional)</Label>
                <Input value={controlFamily} onChange={e => setControlFamily(e.target.value)}
                  placeholder="e.g., AC, AT, AU..." className="rounded-xl mt-1" data-testid="upload-family-input" />
              </div>
            </div>

            <div
              className={`border-2 border-dashed rounded-2xl p-8 text-center transition-all cursor-pointer ${
                dragOver ? "border-[#2597B2] bg-[#e8f4f7]/30" : "border-gray-200 dark:border-gray-700 hover:border-[#2597B2]"
              }`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => document.getElementById("file-upload-input")?.click()}
              data-testid="upload-dropzone"
            >
              <input
                type="file"
                id="file-upload-input"
                className="hidden"
                accept=".pdf,.docx"
                onChange={(e) => { if (e.target.files?.[0]) handleUpload(e.target.files[0]); }}
                data-testid="file-input"
              />
              {uploading ? (
                <div>
                  <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[#e8f4f7] flex items-center justify-center">
                    <div className="w-6 h-6 border-2 border-[#2597B2] border-t-transparent rounded-full animate-spin" />
                  </div>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Uploading... {uploadProgress}%</p>
                  <div className="w-48 mx-auto mt-2 h-1.5 bg-gray-200 rounded-full">
                    <div className="h-full bg-[#2597B2] rounded-full transition-all" style={{ width: `${uploadProgress}%` }} />
                  </div>
                </div>
              ) : (
                <div>
                  <CloudArrowUp size={40} weight="duotone" className="text-gray-300 dark:text-gray-600 mx-auto mb-3" />
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Drop your file here or click to browse</p>
                  <p className="text-xs text-gray-400">Supports PDF and DOCX files</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Documents List */}
        {loading ? (
          <div className="flex items-center justify-center h-32"><div className="w-6 h-6 border-2 border-[#2597B2] border-t-transparent rounded-full animate-spin" /></div>
        ) : documents.length === 0 ? (
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-12 text-center shadow-sm" data-testid="no-documents">
            <FileText size={48} weight="duotone" className="text-gray-300 dark:text-gray-600 mx-auto mb-3" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">No Documents</h3>
            <p className="text-sm text-gray-400">Upload compliance documents for AI analysis</p>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 shadow-sm overflow-hidden" data-testid="documents-list">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100 dark:border-gray-700">
                    <th className="text-left p-4">Document</th>
                    <th className="text-left p-4">Framework</th>
                    <th className="text-left p-4">Status</th>
                    <th className="text-left p-4">Uploaded</th>
                    <th className="text-right p-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map(doc => {
                    const badge = statusBadge(doc.status);
                    const BadgeIcon = badge.icon;
                    return (
                      <tr key={doc.id} className="border-b border-gray-50 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/20 transition-colors" data-testid={`doc-row-${doc.id}`}>
                        <td className="p-4">
                          <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded-xl bg-[#e8f4f7] dark:bg-[#0a3540] flex items-center justify-center">
                              <FileText size={18} weight="duotone" className="text-[#2597B2]" />
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{doc.original_name}</p>
                              <p className="text-xs text-gray-400">{doc.file_type?.toUpperCase()}</p>
                            </div>
                          </div>
                        </td>
                        <td className="p-4 text-sm text-gray-600 dark:text-gray-300">{doc.framework}</td>
                        <td className="p-4">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${badge.bg} ${badge.text}`}>
                            <BadgeIcon size={11} /> {doc.status?.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td className="p-4 text-xs text-gray-400">{doc.created_at ? new Date(doc.created_at).toLocaleDateString() : ""}</td>
                        <td className="p-4 text-right">
                          {doc.status === "preprocessed" && isAdmin && (
                            <Button size="sm" className="bg-[#2597B2] hover:bg-[#1B839F] text-white rounded-lg text-xs" onClick={() => triggerAnalysis(doc.id)} data-testid={`analyze-btn-${doc.id}`}>
                              <MagnifyingGlass size={12} className="mr-1" /> Analyze
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </Wrap>
  );
};

export default DocumentsPage;
