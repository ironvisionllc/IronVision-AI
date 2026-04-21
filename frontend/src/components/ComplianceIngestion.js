import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Upload, FileArrowUp, Trash, ArrowsClockwise, CaretLeft, CaretRight,
  MagnifyingGlass, CheckCircle, Warning, XCircle, MinusCircle,
  Lightning, ChartBar, ShieldCheck, ArrowSquareOut, Funnel, CaretDown
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const SOURCE_TYPES = [
  { value: "stig", label: "STIG", ext: ".xml", desc: "DISA STIG XML (XCCDF)" },
  { value: "cis", label: "CIS", ext: ".yaml,.yml,.csv", desc: "CIS Benchmark YAML/CSV" },
  { value: "pci", label: "PCI DSS", ext: ".json", desc: "PCI DSS Checklist JSON" },
  { value: "questionnaire", label: "Questionnaire", ext: ".csv,.json", desc: "Generic Compliance CSV/JSON" },
  { value: "oscal", label: "OSCAL", ext: ".json", desc: "OSCAL Catalog / Component / Assessment" },
];

const SIEM_STATUS_CONFIG = {
  monitored: { label: "Monitored", color: "text-emerald-600", bg: "bg-emerald-50 dark:bg-emerald-900/20" },
  attention_needed: { label: "Attention", color: "text-amber-600", bg: "bg-amber-50 dark:bg-amber-900/20" },
  critical_findings: { label: "Critical", color: "text-red-600", bg: "bg-red-50 dark:bg-red-900/20" },
  no_events: { label: "No Events", color: "text-gray-500", bg: "bg-gray-50 dark:bg-gray-800" },
  no_mapping: { label: "No SIEM Map", color: "text-gray-400", bg: "bg-gray-50 dark:bg-gray-800" },
};

const SEV_COLORS = {
  high: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  low: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
};

const ComplianceIngestion = ({ onBack }) => {
  const [view, setView] = useState("list"); // list | detail | upload
  const [checklists, setChecklists] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedChecklist, setSelectedChecklist] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [overlapData, setOverlapData] = useState(null);
  const [siemData, setSiemData] = useState(null);
  const [detailTab, setDetailTab] = useState("controls"); // controls | overlap | siem
  const [mapping, setMapping] = useState(false);
  const [search, setSearch] = useState("");
  const [sevFilter, setSevFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  // Upload state
  const [uploadFile, setUploadFile] = useState(null);
  const [sourceType, setSourceType] = useState("stig");
  const [uploading, setUploading] = useState(false);

  const fetchChecklists = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/ingestion/checklists`);
      setChecklists(res.data);
    } catch {
      toast.error("Failed to load checklists");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchChecklists(); }, [fetchChecklists]);

  const handleUpload = async () => {
    if (!uploadFile) return toast.error("Select a file first");
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      let endpoint = `${API}/ingestion/upload`;
      if (sourceType === "oscal") {
        endpoint = `${API}/oscal/import`;
      } else {
        formData.append("source_type", sourceType);
      }
      const res = await axios.post(endpoint, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      toast.success(res.data.message);
      setUploadFile(null);
      setView("list");
      fetchChecklists();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const deleteChecklist = async (id) => {
    if (!window.confirm("Delete this checklist and all its controls?")) return;
    try {
      await axios.delete(`${API}/ingestion/checklists/${id}`);
      toast.success("Checklist deleted");
      fetchChecklists();
      if (selectedChecklist?.id === id) {
        setView("list");
        setSelectedChecklist(null);
      }
    } catch {
      toast.error("Failed to delete");
    }
  };

  const openDetail = async (cl) => {
    setSelectedChecklist(cl);
    setView("detail");
    setDetailTab("controls");
    setOverlapData(null);
    setSiemData(null);
    try {
      const res = await axios.get(`${API}/ingestion/checklists/${cl.id}`);
      setDetailData(res.data);
    } catch {
      toast.error("Failed to load checklist details");
    }
  };

  const runAutoMap = async () => {
    if (!selectedChecklist) return;
    setMapping(true);
    try {
      const res = await axios.post(`${API}/ingestion/checklists/${selectedChecklist.id}/auto-map`);
      toast.success(res.data.message);
      // Refresh detail
      const det = await axios.get(`${API}/ingestion/checklists/${selectedChecklist.id}`);
      setDetailData(det.data);
      fetchChecklists();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Auto-mapping failed");
    } finally {
      setMapping(false);
    }
  };

  const loadOverlap = async () => {
    if (!selectedChecklist) return;
    try {
      const res = await axios.get(`${API}/ingestion/checklists/${selectedChecklist.id}/overlap`);
      setOverlapData(res.data);
    } catch {
      toast.error("Failed to load overlap data");
    }
  };

  const loadSiem = async () => {
    if (!selectedChecklist) return;
    try {
      const res = await axios.get(`${API}/ingestion/checklists/${selectedChecklist.id}/siem-status`);
      setSiemData(res.data);
    } catch {
      toast.error("Failed to load SIEM status");
    }
  };

  useEffect(() => {
    if (detailTab === "overlap" && !overlapData && selectedChecklist) loadOverlap();
    if (detailTab === "siem" && !siemData && selectedChecklist) loadSiem();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detailTab]);

  // ─── UPLOAD VIEW ──────────────
  if (view === "upload") {
    const selectedSource = SOURCE_TYPES.find(s => s.value === sourceType);
    return (
      <div data-testid="ingestion-upload-view">
        <button onClick={() => setView("list")} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#2597B2] mb-6 transition-colors" data-testid="back-to-list-btn">
          <CaretLeft size={14} weight="bold" /> Back to Checklists
        </button>

        <div className="max-w-2xl">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-1">Upload Compliance Checklist</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-8">Parse external checklists into the unified control graph</p>

          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Checklist Type</label>
              <div className="grid grid-cols-2 gap-3">
                {SOURCE_TYPES.map(st => (
                  <button
                    key={st.value}
                    onClick={() => setSourceType(st.value)}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${
                      sourceType === st.value
                        ? "border-[#2597B2] bg-[#2597B2]/5"
                        : "border-gray-200 dark:border-gray-700 hover:border-gray-300"
                    }`}
                    data-testid={`source-type-${st.value}`}
                  >
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{st.label}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{st.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                File ({selectedSource?.ext})
              </label>
              <div
                className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl p-8 text-center hover:border-[#2597B2] transition-colors cursor-pointer"
                onClick={() => document.getElementById("checklist-file-input").click()}
                data-testid="file-drop-zone"
              >
                <FileArrowUp size={40} className="mx-auto text-gray-400 mb-3" />
                {uploadFile ? (
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{uploadFile.name}</p>
                ) : (
                  <p className="text-sm text-gray-500">Click to select or drag a file</p>
                )}
                <input
                  id="checklist-file-input"
                  type="file"
                  accept={selectedSource?.ext}
                  className="hidden"
                  onChange={e => setUploadFile(e.target.files?.[0] || null)}
                  data-testid="checklist-file-input"
                />
              </div>
            </div>

            <Button
              onClick={handleUpload}
              disabled={!uploadFile || uploading}
              className="w-full bg-[#2597B2] hover:bg-[#1B839F] h-11"
              data-testid="upload-checklist-btn"
            >
              {uploading ? (
                <><ArrowsClockwise size={16} className="animate-spin mr-2" /> Parsing...</>
              ) : (
                <><Upload size={16} className="mr-2" /> Upload & Parse</>
              )}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ─── DETAIL VIEW ──────────────
  if (view === "detail" && selectedChecklist) {
    const controls = detailData?.controls || [];
    const stats = detailData?.stats || {};
    const filtered = controls.filter(c => {
      if (search && !c.title.toLowerCase().includes(search.toLowerCase()) && !c.source_id.toLowerCase().includes(search.toLowerCase())) return false;
      if (sevFilter !== "all" && c.severity !== sevFilter) return false;
      if (statusFilter !== "all" && c.status !== statusFilter) return false;
      return true;
    });

    return (
      <div data-testid="ingestion-detail-view">
        <button onClick={() => { setView("list"); setSelectedChecklist(null); setDetailData(null); }} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#2597B2] mb-6 transition-colors" data-testid="back-to-list-btn">
          <CaretLeft size={14} weight="bold" /> Back to Checklists
        </button>

        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{selectedChecklist.name}</h2>
            <div className="flex items-center gap-3 mt-1">
              <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                selectedChecklist.source_type === "stig" ? "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400" :
                selectedChecklist.source_type === "cis" ? "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400" :
                selectedChecklist.source_type === "pci" ? "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400" :
                "bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400"
              }`} data-testid="checklist-source-badge">{selectedChecklist.source_type.toUpperCase()}</span>
              <span className="text-sm text-gray-500">{selectedChecklist.total_controls} controls</span>
              <span className="text-sm text-gray-500">{selectedChecklist.original_filename}</span>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={runAutoMap}
              disabled={mapping}
              className="bg-[#2597B2] hover:bg-[#1B839F]"
              data-testid="auto-map-btn"
            >
              {mapping ? (
                <><ArrowsClockwise size={16} className="animate-spin mr-2" /> Mapping...</>
              ) : (
                <><Lightning size={16} className="mr-2" /> AI Auto-Map</>
              )}
            </Button>
            <Button variant="outline" size="sm" onClick={() => deleteChecklist(selectedChecklist.id)} className="text-red-600 hover:text-red-700 border-red-200" data-testid="delete-checklist-btn">
              <Trash size={16} />
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="iv-card p-4" data-testid="stat-total">
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.total || 0}</div>
            <div className="text-xs text-gray-500">Total Controls</div>
          </div>
          <div className="iv-card p-4" data-testid="stat-mapped">
            <div className="text-2xl font-bold text-emerald-600">{stats.mapped || 0}</div>
            <div className="text-xs text-gray-500">Mapped</div>
          </div>
          <div className="iv-card p-4" data-testid="stat-unmapped">
            <div className="text-2xl font-bold text-amber-600">{stats.unmapped || 0}</div>
            <div className="text-xs text-gray-500">Unmapped</div>
          </div>
          <div className="iv-card p-4" data-testid="stat-severity">
            <div className="flex gap-2 items-baseline">
              <span className="text-lg font-bold text-red-600">{stats.severity?.high || 0}</span>
              <span className="text-lg font-bold text-amber-600">{stats.severity?.medium || 0}</span>
              <span className="text-lg font-bold text-blue-600">{stats.severity?.low || 0}</span>
            </div>
            <div className="text-xs text-gray-500">H / M / L Severity</div>
          </div>
        </div>

        {/* Mapping Progress */}
        {stats.total > 0 && (
          <div className="iv-card p-4 mb-6" data-testid="mapping-progress">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Cross-Framework Mapping Coverage</span>
              <span className="text-sm font-semibold text-[#2597B2]">{Math.round((stats.mapped || 0) / stats.total * 100)}%</span>
            </div>
            <div className="h-2.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-[#2597B2] rounded-full transition-all duration-500" style={{ width: `${(stats.mapped || 0) / stats.total * 100}%` }} />
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 mb-6 p-1 bg-gray-100 dark:bg-gray-800 rounded-lg w-fit" data-testid="detail-tabs">
          {[
            { key: "controls", label: "Control Graph", icon: ShieldCheck },
            { key: "overlap", label: "Framework Overlaps", icon: ChartBar },
            { key: "siem", label: "SIEM Status", icon: Lightning },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setDetailTab(tab.key)}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                detailTab === tab.key
                  ? "bg-white dark:bg-gray-900 text-[#2597B2] shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
              data-testid={`tab-${tab.key}`}
            >
              <tab.icon size={15} weight={detailTab === tab.key ? "fill" : "regular"} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Controls Tab */}
        {detailTab === "controls" && (
          <div>
            <div className="flex gap-3 mb-4">
              <div className="relative flex-1">
                <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <Input placeholder="Search controls..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9 h-9" data-testid="search-controls" />
              </div>
              <select value={sevFilter} onChange={e => setSevFilter(e.target.value)} className="h-9 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900" data-testid="severity-filter">
                <option value="all">All Severity</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
              <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="h-9 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900" data-testid="status-filter">
                <option value="all">All Status</option>
                <option value="mapped">Mapped</option>
                <option value="unmapped">Unmapped</option>
              </select>
            </div>
            <div className="space-y-2" data-testid="controls-list">
              {filtered.length === 0 ? (
                <div className="text-center py-12 text-gray-400">
                  {!detailData ? "Loading controls..." : "No controls match filters"}
                </div>
              ) : (
                filtered.map(ctrl => <ControlRow key={ctrl.id} control={ctrl} />)
              )}
            </div>
            {filtered.length > 0 && (
              <div className="text-xs text-gray-400 mt-4 text-right">Showing {filtered.length} of {controls.length} controls</div>
            )}
          </div>
        )}

        {/* Overlap Tab */}
        {detailTab === "overlap" && (
          <OverlapView data={overlapData} />
        )}

        {/* SIEM Tab */}
        {detailTab === "siem" && (
          <SiemStatusView data={siemData} />
        )}
      </div>
    );
  }

  // ─── LIST VIEW ──────────────
  return (
    <div data-testid="ingestion-list-view">
      {onBack && (
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#2597B2] mb-6 transition-colors" data-testid="back-btn">
          <CaretLeft size={14} weight="bold" /> Back to Frameworks
        </button>
      )}

      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Universal Compliance Ingestion</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Ingest STIG, CIS, PCI, and questionnaire checklists into a unified control graph</p>
        </div>
        <Button onClick={() => setView("upload")} className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="upload-new-btn">
          <FileArrowUp size={18} className="mr-2" /> Upload Checklist
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-40 text-gray-400">Loading checklists...</div>
      ) : checklists.length === 0 ? (
        <div className="iv-card p-12 text-center" data-testid="empty-state">
          <Upload size={48} className="mx-auto text-gray-300 mb-4" />
          <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No Checklists Ingested Yet</h3>
          <p className="text-sm text-gray-500 mb-6">Upload a STIG XML, CIS YAML/CSV, PCI JSON, or compliance questionnaire to get started</p>
          <Button onClick={() => setView("upload")} className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="empty-upload-btn">
            <FileArrowUp size={16} className="mr-2" /> Upload Your First Checklist
          </Button>
        </div>
      ) : (
        <div className="space-y-3" data-testid="checklists-list">
          {checklists.map(cl => (
            <div key={cl.id} className="iv-card p-5 flex items-center gap-5 hover:shadow-md transition-shadow cursor-pointer" onClick={() => openDetail(cl)} data-testid={`checklist-row-${cl.id}`}>
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-white font-bold text-xs ${
                cl.source_type === "stig" ? "bg-purple-500" :
                cl.source_type === "cis" ? "bg-cyan-500" :
                cl.source_type === "pci" ? "bg-orange-500" : "bg-gray-500"
              }`}>
                {cl.source_type.toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{cl.name}</h3>
                <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                  <span>{cl.total_controls} controls</span>
                  <span>{cl.original_filename}</span>
                  <span>{new Date(cl.created_at).toLocaleDateString()}</span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {cl.status === "mapped" ? (
                  <span className="flex items-center gap-1 px-2.5 py-1 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 text-xs font-medium rounded-full" data-testid={`status-${cl.id}`}>
                    <CheckCircle size={14} weight="fill" /> Mapped ({cl.mapped_controls}/{cl.total_controls})
                  </span>
                ) : (
                  <span className="flex items-center gap-1 px-2.5 py-1 bg-amber-50 dark:bg-amber-900/20 text-amber-600 text-xs font-medium rounded-full" data-testid={`status-${cl.id}`}>
                    <MinusCircle size={14} weight="fill" /> Parsed
                  </span>
                )}
                <button onClick={e => { e.stopPropagation(); deleteChecklist(cl.id); }} className="p-1.5 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 text-gray-400 hover:text-red-500 transition-colors" data-testid={`delete-${cl.id}`}>
                  <Trash size={16} />
                </button>
                <CaretRight size={16} className="text-gray-400" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Control Row Component ──────────────
const ControlRow = ({ control }) => {
  const [expanded, setExpanded] = useState(false);
  const mappings = control.framework_mappings || [];

  return (
    <div className="iv-card overflow-hidden" data-testid={`control-${control.source_id}`}>
      <div className="p-4 flex items-center gap-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors" onClick={() => setExpanded(!expanded)}>
        <CaretRight size={14} className={`text-gray-400 transition-transform ${expanded ? "rotate-90" : ""}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-[#2597B2] font-semibold">{control.source_id}</span>
            <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${SEV_COLORS[control.severity]}`}>{control.severity.toUpperCase()}</span>
          </div>
          <h4 className="text-sm text-gray-900 dark:text-gray-100 mt-0.5 truncate">{control.title}</h4>
        </div>
        <div className="flex items-center gap-2">
          {mappings.length > 0 ? (
            <span className="flex items-center gap-1 text-xs text-emerald-600" data-testid={`mapped-badge-${control.source_id}`}>
              <CheckCircle size={14} weight="fill" /> {mappings.length} mapping{mappings.length > 1 ? "s" : ""}
            </span>
          ) : (
            <span className="text-xs text-gray-400">Unmapped</span>
          )}
          {control.siem_categories?.length > 0 && (
            <span className="flex items-center gap-1 text-xs text-[#2597B2]">
              <Lightning size={14} weight="fill" /> SIEM
            </span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 pt-0 border-t border-gray-100 dark:border-gray-800">
          {control.description && (
            <p className="text-xs text-gray-500 mt-3 mb-3 leading-relaxed">{control.description}</p>
          )}
          <div className="text-xs text-gray-400 mb-2">Category: {control.category}</div>

          {mappings.length > 0 && (
            <div className="mt-3">
              <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-2">Framework Mappings</div>
              <div className="space-y-1.5">
                {mappings.map((m, i) => (
                  <div key={i} className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
                    <ShieldCheck size={14} className="text-[#2597B2]" />
                    <span className="text-xs font-medium text-gray-900 dark:text-gray-100">{m.framework_name}</span>
                    <span className="text-xs font-mono text-[#2597B2]">{m.control_id}</span>
                    <span className="text-[10px] text-gray-400 ml-auto">{Math.round((m.confidence || 0) * 100)}% match</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {control.siem_categories?.length > 0 && (
            <div className="mt-3">
              <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">SIEM Categories</div>
              <div className="flex gap-1.5 flex-wrap">
                {control.siem_categories.map(cat => (
                  <span key={cat} className="px-2 py-0.5 text-[10px] bg-[#2597B2]/10 text-[#2597B2] rounded-full font-medium">{cat}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Overlap View ──────────────
const OverlapView = ({ data }) => {
  if (!data) return <div className="text-center py-12 text-gray-400">Loading overlap analysis...</div>;

  const fwCoverage = data.framework_coverage || {};
  const overlapMatrix = data.overlap_matrix || {};
  const multiControls = data.multi_framework_controls || [];
  const sortedFw = Object.entries(fwCoverage).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-6" data-testid="overlap-view">
      {/* Framework Coverage */}
      <div className="iv-card p-5">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">Framework Coverage Distribution</h3>
        <div className="space-y-3">
          {sortedFw.map(([name, count]) => (
            <div key={name} className="flex items-center gap-3">
              <div className="w-48 text-xs font-medium text-gray-700 dark:text-gray-300 truncate">{name}</div>
              <div className="flex-1 h-6 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden relative">
                <div
                  className="h-full bg-[#2597B2] rounded-full transition-all duration-500"
                  style={{ width: `${(count / data.total_controls) * 100}%` }}
                />
                <span className="absolute inset-0 flex items-center justify-center text-[10px] font-semibold">{count} controls</span>
              </div>
              <div className="w-12 text-right text-xs font-semibold text-gray-600">{Math.round((count / data.total_controls) * 100)}%</div>
            </div>
          ))}
        </div>
      </div>

      {/* Overlap Pairs */}
      {Object.keys(overlapMatrix).length > 0 && (
        <div className="iv-card p-5">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">Framework Overlap Pairs</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.entries(overlapMatrix).sort((a, b) => b[1].shared_count - a[1].shared_count).map(([pair, info]) => (
              <div key={pair} className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-800/50 rounded-xl">
                <ArrowSquareOut size={16} className="text-[#2597B2]" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">{pair}</div>
                  <div className="text-[10px] text-gray-400">{info.fw1_total} & {info.fw2_total} total</div>
                </div>
                <span className="text-sm font-bold text-[#2597B2]">{info.shared_count} shared</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Multi-Framework Controls */}
      {multiControls.length > 0 && (
        <div className="iv-card p-5">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">Controls Mapped to Multiple Frameworks</h3>
          <div className="space-y-2">
            {multiControls.slice(0, 20).map((ctrl, i) => (
              <div key={i} className="flex items-center gap-3 px-3 py-2.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
                <span className="text-xs font-medium text-gray-900 dark:text-gray-100 flex-1 truncate">{ctrl.title}</span>
                <div className="flex gap-1 flex-wrap justify-end">
                  {ctrl.frameworks.map(fw => (
                    <span key={fw} className="px-1.5 py-0.5 text-[9px] bg-[#2597B2]/10 text-[#2597B2] rounded font-medium whitespace-nowrap">{fw}</span>
                  ))}
                </div>
                <span className="text-xs font-bold text-[#2597B2] ml-2">{ctrl.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary Stats */}
      <div className="flex gap-4 text-sm text-gray-500">
        <span>{data.total_controls} total controls</span>
        <span>{data.mapped_to_any} mapped to frameworks</span>
        <span>{multiControls.length} cross-mapped</span>
      </div>
    </div>
  );
};

// ─── SIEM Status View ──────────────
const SiemStatusView = ({ data }) => {
  if (!data) return <div className="text-center py-12 text-gray-400">Loading SIEM status...</div>;

  const summary = data.summary || {};
  const controls = data.controls || [];

  return (
    <div className="space-y-6" data-testid="siem-status-view">
      {/* Summary */}
      <div className="grid grid-cols-5 gap-3">
        <div className="iv-card p-4 text-center">
          <div className="text-xl font-bold text-gray-900 dark:text-gray-100">{summary.total || 0}</div>
          <div className="text-[10px] text-gray-500 mt-1">Total Controls</div>
        </div>
        <div className="iv-card p-4 text-center">
          <div className="text-xl font-bold text-emerald-600">{summary.monitored || 0}</div>
          <div className="text-[10px] text-gray-500 mt-1">Monitored</div>
        </div>
        <div className="iv-card p-4 text-center">
          <div className="text-xl font-bold text-amber-600">{summary.attention_needed || 0}</div>
          <div className="text-[10px] text-gray-500 mt-1">Attention</div>
        </div>
        <div className="iv-card p-4 text-center">
          <div className="text-xl font-bold text-red-600">{summary.critical_findings || 0}</div>
          <div className="text-[10px] text-gray-500 mt-1">Critical</div>
        </div>
        <div className="iv-card p-4 text-center">
          <div className="text-xl font-bold text-gray-400">{summary.no_mapping || 0}</div>
          <div className="text-[10px] text-gray-500 mt-1">No Mapping</div>
        </div>
      </div>

      {/* SIEM Events Total */}
      <div className="iv-card p-4 flex items-center gap-3">
        <Lightning size={24} className="text-[#2597B2]" />
        <div>
          <div className="text-lg font-bold text-gray-900 dark:text-gray-100">{summary.total_events || 0}</div>
          <div className="text-xs text-gray-500">Total SIEM events correlated (last 30 days)</div>
        </div>
      </div>

      {/* Controls with SIEM data */}
      <div className="space-y-2">
        {controls.filter(c => c.siem_status !== "no_mapping").length === 0 ? (
          <div className="text-center py-8 text-gray-400">No controls with SIEM mappings. Run AI Auto-Map first.</div>
        ) : (
          controls
            .filter(c => c.siem_status !== "no_mapping")
            .sort((a, b) => b.siem_events_count - a.siem_events_count)
            .slice(0, 50)
            .map(ctrl => {
              const cfg = SIEM_STATUS_CONFIG[ctrl.siem_status] || SIEM_STATUS_CONFIG.no_mapping;
              return (
                <div key={ctrl.source_id} className="iv-card p-4 flex items-center gap-3" data-testid={`siem-control-${ctrl.source_id}`}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-[#2597B2] font-semibold">{ctrl.source_id}</span>
                      <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${SEV_COLORS[ctrl.severity]}`}>{ctrl.severity.toUpperCase()}</span>
                    </div>
                    <div className="text-sm text-gray-900 dark:text-gray-100 truncate mt-0.5">{ctrl.title}</div>
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {ctrl.siem_categories.map(cat => (
                        <span key={cat} className="text-[9px] px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 rounded">{cat}</span>
                      ))}
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${cfg.bg} ${cfg.color}`}>
                      {cfg.label}
                    </span>
                    <div className="text-xs text-gray-500 mt-1">
                      {ctrl.siem_events_count} events
                      {ctrl.siem_critical > 0 && <span className="text-red-500 ml-1">({ctrl.siem_critical} critical)</span>}
                    </div>
                  </div>
                </div>
              );
            })
        )}
      </div>
    </div>
  );
};

export default ComplianceIngestion;
