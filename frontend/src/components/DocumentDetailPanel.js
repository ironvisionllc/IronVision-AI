import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import {
  FileText, X, Tag, Plus, Pencil, FloppyDisk, Download,
  CaretRight, ShieldCheck, Trash, ArrowsClockwise, Clock
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const CATEGORIES = [
  { value: "policy", label: "Policy" },
  { value: "procedure", label: "Procedure" },
  { value: "evidence", label: "Evidence" },
  { value: "contract", label: "Contract" },
  { value: "training", label: "Training" },
  { value: "other", label: "Other" },
];

const CATEGORY_COLORS = {
  policy: "bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400",
  procedure: "bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-400",
  evidence: "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400",
  contract: "bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400",
  training: "bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-400",
  other: "bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400",
};

/* ══════════════════════════════════════════════════════════
   DOCUMENT DETAIL PANEL
   Shows when clicking an uploaded document in the library.
   ══════════════════════════════════════════════════════════ */
export const DocumentDetailPanel = ({ document, onClose, onUpdate, frameworks, tags, onTagCreate, onTagRemove }) => {
  const [editing, setEditing] = useState(false);
  const [description, setDescription] = useState(document?.description || "");
  const [category, setCategory] = useState(document?.category || "other");
  const [customTags, setCustomTags] = useState(document?.custom_tags || []);
  const [newTag, setNewTag] = useState("");
  const [saving, setSaving] = useState(false);
  const [suggestedTags, setSuggestedTags] = useState([]);
  const [showTagInput, setShowTagInput] = useState(false);
  const [changingStatus, setChangingStatus] = useState(false);
  const [contentEditing, setContentEditing] = useState(false);
  const [contentBuffer, setContentBuffer] = useState(document?.content || "");
  const [titleBuffer, setTitleBuffer] = useState(document?.filename || document?.original_name || "");

  // Framework tag state
  const [showFwTagForm, setShowFwTagForm] = useState(false);
  const [fwTagForm, setFwTagForm] = useState({ framework_id: "", control_ids: "", notes: "" });

  useEffect(() => {
    axios.get(`${API}/documents/custom-tags`).then(r => setSuggestedTags(r.data)).catch(() => {});
  }, []);

  const docTags = (tags || []).filter(t => t.document_id === (document?.job_id || document?.id));

  const save = async () => {
    setSaving(true);
    try {
      const res = await axios.put(`${API}/documents/${document.job_id || document.id}/metadata`, {
        category, custom_tags: customTags, description,
      });
      onUpdate?.(res.data);
      setEditing(false);
      toast.success("Document updated");
    } catch { toast.error("Failed to save"); }
    finally { setSaving(false); }
  };

  const addCustomTag = (tag) => {
    const t = (tag || newTag).trim();
    if (t && !customTags.includes(t)) {
      setCustomTags(prev => [...prev, t]);
      setNewTag("");
    }
  };

  const removeCustomTag = (tag) => {
    setCustomTags(prev => prev.filter(t => t !== tag));
  };

  const addFrameworkTag = async () => {
    if (!fwTagForm.framework_id) { toast.error("Select a framework"); return; }
    const fw = frameworks?.find(f => f.id === fwTagForm.framework_id);
    await onTagCreate?.({
      document_id: document.job_id || document.id,
      document_name: document.filename || document.original_name || "",
      framework_id: fwTagForm.framework_id,
      framework_name: fw?.name || "",
      control_ids: fwTagForm.control_ids.split(",").map(s => s.trim()).filter(Boolean),
      notes: fwTagForm.notes,
    });
    setFwTagForm({ framework_id: "", control_ids: "", notes: "" });
    setShowFwTagForm(false);
  };

  const catColor = CATEGORY_COLORS[category] || CATEGORY_COLORS.other;

  const normalizedStatus = ["draft","under_review","approved"].includes(document?.status) ? document.status : "draft";

  const changeStatus = async (newStatus) => {
    setChangingStatus(true);
    try {
      await axios.put(`${API}/documents/${document.job_id || document.id}/status`, { status: newStatus });
      const labels = { under_review: "Under Review", approved: "Approved", draft: "Draft" };
      toast.success(`Document moved to ${labels[newStatus]}`);
      onUpdate?.({ ...document, status: newStatus });
    } catch (err) { toast.error(err.response?.data?.detail || "Status change failed"); }
    finally { setChangingStatus(false); }
  };

  const saveContent = async () => {
    setSaving(true);
    try {
      const res = await axios.put(`${API}/documents/${document.job_id || document.id}/content`, { content: contentBuffer, title: titleBuffer });
      onUpdate?.(res.data);
      setContentEditing(false);
      toast.success("Content saved");
    } catch { toast.error("Failed to save content"); }
    finally { setSaving(false); }
  };

  const isCreated = document?.file_type === "created";
  const isReadOnly = normalizedStatus === "approved" || normalizedStatus === "under_review";

  return (
    <div data-testid="document-detail-panel">
      <button onClick={onClose} className="flex items-center gap-1 text-sm text-[#2597B2] hover:text-[#1B839F] font-medium mb-4" data-testid="close-doc-detail">
        <CaretRight size={14} weight="bold" className="rotate-180" /> Back to Library
      </button>

      {/* Header */}
      <div className="iv-card p-5 mb-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-lg bg-[#2597B2]/10 flex items-center justify-center">
              <FileText size={22} weight="duotone" className="text-[#2597B2]" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">{document.filename || document.original_name}</h2>
              <p className="text-xs text-gray-400 mt-0.5">
                {document.file_type?.toUpperCase()} &middot; Uploaded {new Date(document.created_at).toLocaleDateString()}
                {document.framework && <> &middot; Mapped to {document.framework}</>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[10px] px-2.5 py-1 rounded-full font-medium ${catColor}`}>{CATEGORIES.find(c => c.value === category)?.label || category}</span>
            {!editing ? (
              <Button size="sm" variant="outline" className="h-8 text-xs gap-1" onClick={() => setEditing(true)} data-testid="edit-doc-btn">
                <Pencil size={12} /> Edit
              </Button>
            ) : (
              <Button size="sm" className="h-8 text-xs bg-[#2597B2] hover:bg-[#1B839F] text-white gap-1" onClick={save} disabled={saving} data-testid="save-doc-btn">
                <FloppyDisk size={12} /> Save
              </Button>
            )}
          </div>
        </div>

        {/* Editable fields */}
        {editing && (
          <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 space-y-3">
            <div>
              <Label className="text-xs">Category</Label>
              <select value={category} onChange={e => setCategory(e.target.value)} className="w-full h-9 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800" data-testid="doc-category-select">
                {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs">Description</Label>
              <Textarea value={description} onChange={e => setDescription(e.target.value)} rows={3} placeholder="Optional description..." className="text-sm" data-testid="doc-description-input" />
            </div>
          </div>
        )}
      </div>

      {/* Approval Workflow Bar */}
      <div className="iv-card p-4 mb-4 flex items-center justify-between flex-wrap gap-3" data-testid="doc-approval-bar">
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border ${
            normalizedStatus === "approved" ? "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800" :
            normalizedStatus === "under_review" ? "bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800" :
            "bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800"
          }`} data-testid="doc-status-badge">
            {normalizedStatus === "approved" ? "Approved" : normalizedStatus === "under_review" ? "Under Review" : "Draft"}
          </span>
          {document.approved_at && normalizedStatus === "approved" && (
            <span className="text-[10px] text-gray-400">Approved {new Date(document.approved_at).toLocaleDateString()}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {normalizedStatus === "draft" && (
            <Button size="sm" className="h-8 text-xs bg-blue-600 hover:bg-blue-700 text-white gap-1.5" onClick={() => changeStatus("under_review")} disabled={changingStatus} data-testid="doc-submit-review-btn">
              Submit for Review
            </Button>
          )}
          {normalizedStatus === "under_review" && (
            <>
              <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={() => changeStatus("draft")} disabled={changingStatus} data-testid="doc-return-draft-btn">Return to Draft</Button>
              <Button size="sm" className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5" onClick={() => changeStatus("approved")} disabled={changingStatus} data-testid="doc-approve-btn">Approve</Button>
            </>
          )}
          {normalizedStatus === "approved" && (
            <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={() => changeStatus("draft")} disabled={changingStatus} data-testid="doc-reopen-btn">Reopen as Draft</Button>
          )}
        </div>
      </div>

      {/* Content Section (for created documents) */}
      {isCreated && (
        <div className="iv-card p-5 mb-4" data-testid="doc-content-section">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <FileText size={16} weight="duotone" className="text-[#2597B2]" /> Document Content
            </h3>
            {!isReadOnly && (
              contentEditing ? (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setContentEditing(false)}>Cancel</Button>
                  <Button size="sm" className="h-7 text-xs bg-[#2597B2] hover:bg-[#1B839F] text-white gap-1" onClick={saveContent} disabled={saving} data-testid="save-content-btn">
                    <FloppyDisk size={12} /> Save
                  </Button>
                </div>
              ) : (
                <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => setContentEditing(true)} data-testid="edit-content-btn">
                  <Pencil size={12} /> Edit Content
                </Button>
              )
            )}
          </div>
          {contentEditing ? (
            <div className="space-y-2">
              <Input value={titleBuffer} onChange={e => setTitleBuffer(e.target.value)} placeholder="Document title" className="text-sm font-medium" data-testid="content-title-input" />
              <Textarea value={contentBuffer} onChange={e => setContentBuffer(e.target.value)} rows={16} className="text-sm font-mono" placeholder="Write your policy or document content here..." data-testid="content-editor" />
            </div>
          ) : (
            <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap" data-testid="content-display">
              {document.content || <span className="text-gray-400 italic">No content yet. Click "Edit Content" to start writing.</span>}
            </div>
          )}
        </div>
      )}

      {isReadOnly && (
        <div className="flex items-center gap-2 px-4 py-2.5 mb-4 rounded-lg bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 text-xs text-gray-500" data-testid="doc-readonly-banner">
          {normalizedStatus === "approved" ? "This document is approved. Reopen as draft to make edits." : "This document is under review. Return to draft to make edits."}
        </div>
      )}

      {/* Custom Tags */}
      <div className="iv-card p-5 mb-4" data-testid="custom-tags-section">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
          <Tag size={16} weight="duotone" className="text-[#2597B2]" /> Custom Labels
        </h3>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {customTags.length === 0 && !showTagInput && (
            <span className="text-xs text-gray-400">No custom labels yet.</span>
          )}
          {customTags.map(tag => (
            <span key={tag} className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-[#2597B2]/10 text-[#2597B2] text-xs font-medium" data-testid={`custom-tag-${tag}`}>
              {tag}
              <button onClick={() => removeCustomTag(tag)} className="hover:text-red-500 transition-colors"><X size={10} /></button>
            </span>
          ))}
          {!showTagInput && (
            <button onClick={() => setShowTagInput(true)} className="flex items-center gap-1 px-2.5 py-1 rounded-full border border-dashed border-gray-300 dark:border-gray-600 text-xs text-gray-500 hover:border-[#2597B2] hover:text-[#2597B2] transition-colors" data-testid="add-custom-tag-btn">
              <Plus size={10} /> Add Label
            </button>
          )}
        </div>
        {showTagInput && (
          <div className="flex items-center gap-2" data-testid="custom-tag-input-row">
            <Input value={newTag} onChange={e => setNewTag(e.target.value)} placeholder="Type a label..." className="h-8 text-sm flex-1" onKeyDown={e => { if (e.key === "Enter") { addCustomTag(); } }} data-testid="custom-tag-input" />
            <Button size="sm" className="h-8 text-xs bg-[#2597B2] hover:bg-[#1B839F] text-white" onClick={() => addCustomTag()} data-testid="confirm-custom-tag-btn">Add</Button>
            <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => setShowTagInput(false)}>Cancel</Button>
          </div>
        )}
        {showTagInput && suggestedTags.length > 0 && (
          <div className="mt-2" data-testid="suggested-tags">
            <p className="text-[10px] text-gray-400 mb-1">Previously used:</p>
            <div className="flex flex-wrap gap-1">
              {suggestedTags.filter(t => !customTags.includes(t)).slice(0, 10).map(t => (
                <button key={t} onClick={() => addCustomTag(t)} className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-[#2597B2]/10 hover:text-[#2597B2] transition-colors">{t}</button>
              ))}
            </div>
          </div>
        )}
        {editing && customTags !== (document?.custom_tags || []) && (
          <p className="text-[10px] text-amber-500 mt-2">Click "Save" above to persist tag changes.</p>
        )}
      </div>

      {/* Framework Tags */}
      <div className="iv-card p-5" data-testid="framework-tags-section">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <ShieldCheck size={16} weight="duotone" className="text-[#2597B2]" /> Framework Control Tags
          </h3>
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => setShowFwTagForm(!showFwTagForm)} data-testid="add-fw-tag-btn">
            <Plus size={10} /> Add Tag
          </Button>
        </div>

        {showFwTagForm && (
          <div className="p-3 bg-gray-50 dark:bg-gray-800/30 rounded-lg border border-gray-200 dark:border-gray-700 mb-3 space-y-2" data-testid="fw-tag-form">
            <select value={fwTagForm.framework_id} onChange={e => setFwTagForm(p => ({...p, framework_id: e.target.value}))} className="w-full h-8 px-2 text-xs border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800">
              <option value="">Select framework...</option>
              {(frameworks || []).map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
            <Input value={fwTagForm.control_ids} onChange={e => setFwTagForm(p => ({...p, control_ids: e.target.value}))} placeholder="Control IDs (AC-2, AC-3...)" className="h-8 text-xs" />
            <Input value={fwTagForm.notes} onChange={e => setFwTagForm(p => ({...p, notes: e.target.value}))} placeholder="Notes (optional)" className="h-8 text-xs" />
            <div className="flex gap-2 justify-end">
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setShowFwTagForm(false)}>Cancel</Button>
              <Button size="sm" className="h-7 text-xs bg-[#2597B2] hover:bg-[#1B839F] text-white" onClick={addFrameworkTag} data-testid="save-fw-tag-btn">Tag</Button>
            </div>
          </div>
        )}

        {docTags.length === 0 ? (
          <p className="text-xs text-gray-400">No framework tags. Click "Add Tag" to link this document to framework controls.</p>
        ) : (
          <div className="space-y-1.5">
            {docTags.map(tag => (
              <div key={tag.id} className="flex items-center justify-between p-2 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700" data-testid={`fw-tag-${tag.id}`}>
                <div className="flex items-center gap-2 text-xs">
                  <ShieldCheck size={13} className="text-[#2597B2] shrink-0" />
                  <span className="font-medium text-[#2597B2]">{tag.framework_name}</span>
                  {tag.control_ids?.length > 0 && (
                    <span className="text-gray-500">{tag.control_ids.join(", ")}</span>
                  )}
                  {tag.notes && <span className="text-gray-400 italic">— {tag.notes}</span>}
                </div>
                <button onClick={() => onTagRemove?.(tag.id)} className="text-gray-400 hover:text-red-500 transition-colors" data-testid={`remove-fw-tag-${tag.id}`}>
                  <Trash size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export { CATEGORIES, CATEGORY_COLORS };
