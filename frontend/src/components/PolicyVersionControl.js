import React, { useState, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import {
  Clock, CheckCircle, ArrowsClockwise, CaretDown, CaretRight,
  GitBranch, FloppyDisk, Eye, ShieldCheck, PaperPlaneTilt
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

/* ── Status Config ── */
const STATUS_CONFIG = {
  draft: { label: "Draft", bg: "bg-amber-50 dark:bg-amber-900/20", text: "text-amber-700 dark:text-amber-400", border: "border-amber-200 dark:border-amber-800", icon: Clock },
  under_review: { label: "Under Review", bg: "bg-blue-50 dark:bg-blue-900/20", text: "text-blue-700 dark:text-blue-400", border: "border-blue-200 dark:border-blue-800", icon: Eye },
  approved: { label: "Approved", bg: "bg-emerald-50 dark:bg-emerald-900/20", text: "text-emerald-700 dark:text-emerald-400", border: "border-emerald-200 dark:border-emerald-800", icon: ShieldCheck },
};

/* ══════════════════════════════════════════════════════════
   APPROVAL STATUS BAR
   ══════════════════════════════════════════════════════════ */
export const PolicyApprovalBar = ({ policy, onStatusChange, onSaveVersion, versionCount, onOpenHistory }) => {
  const [changingStatus, setChangingStatus] = useState(false);
  const status = policy?.status || "draft";
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  const StatusIcon = cfg.icon;

  const changeStatus = async (newStatus) => {
    setChangingStatus(true);
    try {
      await axios.put(`${API}/policy-templates/generated/${policy.id}/status`, { status: newStatus });
      onStatusChange(newStatus);
      const labels = { under_review: "Under Review", approved: "Approved", draft: "Draft" };
      toast.success(`Policy moved to ${labels[newStatus]}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Status change failed");
    } finally { setChangingStatus(false); }
  };

  return (
    <div className="iv-card p-4 mb-5 flex items-center justify-between flex-wrap gap-3" data-testid="policy-approval-bar">
      <div className="flex items-center gap-3">
        <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border ${cfg.bg} ${cfg.text} ${cfg.border}`} data-testid="policy-status-badge">
          <StatusIcon size={14} weight="fill" />
          {cfg.label}
        </div>
        {status === "approved" && policy.approved_at && (
          <span className="text-[10px] text-gray-400">
            Approved {new Date(policy.approved_at).toLocaleDateString()}{policy.approved_by_name ? ` by ${policy.approved_by_name}` : ""}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {status === "draft" && (
          <>
            <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={onSaveVersion} data-testid="save-version-btn">
              <FloppyDisk size={13} /> Save Version
            </Button>
            <Button size="sm" className="h-8 text-xs bg-blue-600 hover:bg-blue-700 text-white gap-1.5" onClick={() => changeStatus("under_review")} disabled={changingStatus} data-testid="submit-review-btn">
              <PaperPlaneTilt size={13} /> Submit for Review
            </Button>
          </>
        )}
        {status === "under_review" && (
          <>
            <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={() => changeStatus("draft")} disabled={changingStatus} data-testid="return-draft-btn">
              Return to Draft
            </Button>
            <Button size="sm" className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5" onClick={() => changeStatus("approved")} disabled={changingStatus} data-testid="approve-btn">
              <CheckCircle size={13} weight="fill" /> Approve
            </Button>
          </>
        )}
        {status === "approved" && (
          <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={() => changeStatus("draft")} disabled={changingStatus} data-testid="reopen-draft-btn">
            Reopen as Draft
          </Button>
        )}
        <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={onOpenHistory} data-testid="version-history-btn">
          <GitBranch size={13} /> History
          {versionCount > 0 && <span className="ml-0.5 bg-gray-100 dark:bg-gray-800 px-1.5 rounded-full text-[10px]">{versionCount}</span>}
        </Button>
      </div>
    </div>
  );
};


/* ══════════════════════════════════════════════════════════
   VERSION HISTORY DIALOG
   ══════════════════════════════════════════════════════════ */
export const VersionHistoryDialog = ({ open, onOpenChange, policyId, onRestore, onVersionSaved }) => {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [compareSelection, setCompareSelection] = useState([]);
  const [diffData, setDiffData] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [savingVersion, setSavingVersion] = useState(false);
  const [changeSummary, setChangeSummary] = useState("");
  const [showSaveForm, setShowSaveForm] = useState(false);

  const loadVersions = useCallback(async () => {
    if (!policyId) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API}/policy-templates/generated/${policyId}/versions`);
      setVersions(res.data);
    } catch { toast.error("Failed to load versions"); }
    finally { setLoading(false); }
  }, [policyId]);

  React.useEffect(() => {
    if (open) { loadVersions(); setCompareSelection([]); setDiffData(null); }
  }, [open, loadVersions]);

  const toggleCompare = (versionId) => {
    setCompareSelection(prev => {
      if (prev.includes(versionId)) return prev.filter(id => id !== versionId);
      if (prev.length >= 2) return [prev[1], versionId];
      return [...prev, versionId];
    });
    setDiffData(null);
  };

  const runDiff = async () => {
    if (compareSelection.length !== 2) return;
    setDiffLoading(true);
    try {
      const res = await axios.post(`${API}/policy-templates/generated/${policyId}/versions/diff`, {
        version_id_1: compareSelection[0],
        version_id_2: compareSelection[1],
      });
      setDiffData(res.data);
    } catch { toast.error("Failed to compute diff"); }
    finally { setDiffLoading(false); }
  };

  const handleRestore = async (versionId, versionNumber) => {
    if (!window.confirm(`Restore policy to version ${versionNumber}? Current edits will be replaced and a new version will be created.`)) return;
    try {
      await axios.put(`${API}/policy-templates/generated/${policyId}/versions/${versionId}/restore`);
      toast.success(`Restored to version ${versionNumber}`);
      onRestore?.();
      loadVersions();
    } catch { toast.error("Restore failed"); }
  };

  const saveVersion = async () => {
    setSavingVersion(true);
    try {
      await axios.post(`${API}/policy-templates/generated/${policyId}/versions`, { change_summary: changeSummary || "Manual save" });
      toast.success("Version saved");
      setChangeSummary("");
      setShowSaveForm(false);
      loadVersions();
      onVersionSaved?.();
    } catch { toast.error("Failed to save version"); }
    finally { setSavingVersion(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col" data-testid="version-history-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitBranch size={18} weight="duotone" className="text-[#2597B2]" />
            Version History
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto mt-2 space-y-3 pr-1">
          {/* Save New Version */}
          {!showSaveForm ? (
            <button
              onClick={() => setShowSaveForm(true)}
              className="w-full p-3 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-500 hover:text-[#2597B2] hover:border-[#2597B2]/30 transition-all"
              data-testid="new-version-btn"
            >
              + Save Current State as New Version
            </button>
          ) : (
            <div className="p-3 border border-[#2597B2]/20 rounded-lg bg-[#2597B2]/5" data-testid="save-version-form">
              <Input
                placeholder="What changed? (e.g., Updated enforcement section)"
                value={changeSummary}
                onChange={e => setChangeSummary(e.target.value)}
                className="text-sm mb-2"
                data-testid="version-summary-input"
              />
              <div className="flex gap-2 justify-end">
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setShowSaveForm(false)}>Cancel</Button>
                <Button size="sm" className="h-7 text-xs bg-[#2597B2] hover:bg-[#1B839F] text-white" onClick={saveVersion} disabled={savingVersion} data-testid="confirm-save-version-btn">
                  {savingVersion ? <ArrowsClockwise size={12} className="animate-spin mr-1" /> : <FloppyDisk size={12} className="mr-1" />}
                  Save Version
                </Button>
              </div>
            </div>
          )}

          {/* Compare Bar */}
          {compareSelection.length > 0 && (
            <div className="flex items-center justify-between p-2.5 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800" data-testid="compare-bar">
              <span className="text-xs text-blue-700 dark:text-blue-400 font-medium">
                {compareSelection.length}/2 versions selected for comparison
              </span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setCompareSelection([]); setDiffData(null); }}>Clear</Button>
                <Button size="sm" className="h-7 text-xs bg-blue-600 hover:bg-blue-700 text-white" onClick={runDiff} disabled={compareSelection.length !== 2 || diffLoading} data-testid="run-diff-btn">
                  {diffLoading ? <ArrowsClockwise size={12} className="animate-spin mr-1" /> : null}
                  Compare
                </Button>
              </div>
            </div>
          )}

          {/* Diff Results */}
          {diffData && <DiffView data={diffData} />}

          {/* Version List */}
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <ArrowsClockwise size={20} className="animate-spin text-[#2597B2]" />
            </div>
          ) : versions.length === 0 ? (
            <div className="text-center py-8 text-sm text-gray-400">No versions yet. Save your first version above.</div>
          ) : (
            <div className="space-y-2" data-testid="version-list">
              {versions.map((v, idx) => (
                <div
                  key={v.id}
                  className={`p-3.5 rounded-lg border transition-all ${compareSelection.includes(v.id) ? "border-blue-400 bg-blue-50/50 dark:bg-blue-900/10" : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"}`}
                  data-testid={`version-item-${v.version_number}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${idx === 0 ? "bg-[#2597B2]/10 text-[#2597B2]" : "bg-gray-100 dark:bg-gray-800 text-gray-500"}`}>
                        v{v.version_number}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                            Version {v.version_number}
                          </span>
                          {idx === 0 && <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[#2597B2]/10 text-[#2597B2] font-semibold">LATEST</span>}
                          {v.version_number === 1 && versions.length > 1 && idx === versions.length - 1 && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500 font-semibold">INITIAL</span>
                          )}
                        </div>
                        <p className="text-[11px] text-gray-500 mt-0.5">{v.change_summary}</p>
                        <p className="text-[10px] text-gray-400 mt-0.5">
                          {v.created_by_name && <span>{v.created_by_name} &middot; </span>}
                          {new Date(v.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        onClick={() => toggleCompare(v.id)}
                        className={`px-2 py-1 text-[10px] rounded border transition-all ${compareSelection.includes(v.id) ? "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border-blue-300 dark:border-blue-700" : "text-gray-500 border-gray-200 dark:border-gray-700 hover:border-gray-300"}`}
                        data-testid={`compare-toggle-${v.version_number}`}
                      >
                        {compareSelection.includes(v.id) ? "Selected" : "Compare"}
                      </button>
                      {idx > 0 && (
                        <button
                          onClick={() => handleRestore(v.id, v.version_number)}
                          className="px-2 py-1 text-[10px] text-gray-500 border border-gray-200 dark:border-gray-700 rounded hover:text-amber-600 hover:border-amber-300 transition-all"
                          data-testid={`restore-btn-${v.version_number}`}
                        >
                          Restore
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};


/* ══════════════════════════════════════════════════════════
   DIFF VIEW (inline unified diff)
   ══════════════════════════════════════════════════════════ */
const DiffView = ({ data }) => {
  const [expandedSections, setExpandedSections] = useState({});

  const toggleSection = (idx) => {
    setExpandedSections(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden" data-testid="diff-view">
      <div className="px-4 py-2.5 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
          v{data.version_1.version_number} &rarr; v{data.version_2.version_number}
        </span>
        <span className="text-[10px] text-gray-400">
          {data.total_changes} section{data.total_changes !== 1 ? "s" : ""} changed
        </span>
      </div>
      <div className="divide-y divide-gray-100 dark:divide-gray-800">
        {data.sections.map((section, idx) => (
          <div key={idx}>
            <button
              onClick={() => toggleSection(idx)}
              className={`w-full flex items-center justify-between px-4 py-2 text-xs hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors ${section.has_changes ? "text-gray-900 dark:text-gray-100" : "text-gray-400"}`}
              data-testid={`diff-section-toggle-${idx}`}
            >
              <div className="flex items-center gap-2">
                {expandedSections[idx] ? <CaretDown size={12} /> : <CaretRight size={12} />}
                <span className="font-medium">{section.heading_v2 || section.heading_v1}</span>
              </div>
              {section.has_changes ? (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400 font-medium">Changed</span>
              ) : (
                <span className="text-[10px] text-gray-300 dark:text-gray-600">No changes</span>
              )}
            </button>
            {expandedSections[idx] && section.has_changes && (
              <div className="px-4 pb-3 font-mono text-[11px] leading-5 overflow-x-auto max-h-64 overflow-y-auto" data-testid={`diff-content-${idx}`}>
                {section.diff_lines.map((line, i) => {
                  if (line.startsWith("@@")) return <div key={i} className="text-blue-500 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/10 px-2 py-0.5 my-1 rounded">{line}</div>;
                  if (line.startsWith("---") || line.startsWith("+++")) return null;
                  if (line.startsWith("+")) return <div key={i} className="text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/10 px-2">{line}</div>;
                  if (line.startsWith("-")) return <div key={i} className="text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/10 px-2">{line}</div>;
                  return <div key={i} className="text-gray-500 px-2">{line}</div>;
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
