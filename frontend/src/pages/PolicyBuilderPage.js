import React, { useState, useEffect, useCallback, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import {
  ShieldCheck, CaretRight, CaretLeft, Check, FileText, Plus, Trash,
  ArrowRight, Pencil, Clock, CheckCircle, FloppyDisk, Lightning
} from "@phosphor-icons/react";

const STEPS = ["framework", "family", "questionnaire", "review"];

const PolicyBuilderPage = ({ embedded = false }) => {
  const { user } = useContext(AuthContext);
  const isAdmin = user?.roles?.[0]?.role === "admin";
  const Wrap = embedded ? React.Fragment : Layout;
  const [step, setStep] = useState("list"); // "list" | "framework" | "family" | "questionnaire" | "review"
  const [drafts, setDrafts] = useState([]);
  const [families, setFamilies] = useState([]);
  const [selectedFamily, setSelectedFamily] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [policyName, setPolicyName] = useState("");
  const [currentDraftId, setCurrentDraftId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [questionsLoading, setQuestionsLoading] = useState(false);

  useEffect(() => { fetchDrafts(); fetchFamilies(); }, []);

  const fetchDrafts = async () => {
    try {
      const res = await axios.get(`${API}/policy-builder/drafts`);
      setDrafts(res.data);
    } catch {} finally { setLoading(false); }
  };

  const fetchFamilies = async () => {
    try {
      const res = await axios.get(`${API}/policy-builder/control-families`);
      setFamilies(res.data);
    } catch {}
  };

  const fetchQuestions = async (familyId) => {
    setQuestionsLoading(true);
    try {
      const res = await axios.get(`${API}/policy-builder/questions/${familyId}`);
      setQuestions(res.data.questions || []);
    } catch {
      toast.error("Failed to load questions");
    } finally { setQuestionsLoading(false); }
  };

  const startNew = () => { setCurrentDraftId(null); setAnswers({}); setPolicyName(""); setSelectedFamily(null); setStep("family"); };

  const selectFamily = (family) => {
    setSelectedFamily(family);
    setPolicyName(`${family.name} Policy`);
    fetchQuestions(family.id);
    setStep("questionnaire");
  };

  const resumeDraft = async (draft) => {
    setCurrentDraftId(draft.id);
    setSelectedFamily({ id: draft.control_family, name: draft.control_family_name });
    setPolicyName(draft.policy_name);
    setAnswers(draft.answers || {});
    await fetchQuestions(draft.control_family);
    setStep("questionnaire");
  };

  const deleteDraft = async (draftId) => {
    try {
      await axios.delete(`${API}/policy-builder/drafts/${draftId}`);
      toast.success("Draft deleted");
      fetchDrafts();
    } catch { toast.error("Failed to delete draft"); }
  };

  const saveDraft = useCallback(async () => {
    if (!selectedFamily || !policyName.trim()) return;
    setSaving(true);
    try {
      if (currentDraftId) {
        await axios.put(`${API}/policy-builder/drafts/${currentDraftId}`, { policy_name: policyName, answers });
      } else {
        const res = await axios.post(`${API}/policy-builder/drafts`, {
          policy_name: policyName,
          framework: "nist-800-53",
          control_family: selectedFamily.id,
          answers,
        });
        setCurrentDraftId(res.data.id);
      }
      toast.success("Draft saved");
      fetchDrafts();
    } catch (err) {
      const msg = err?.response?.data?.detail || "Failed to save";
      toast.error(msg);
    } finally { setSaving(false); }
  }, [currentDraftId, selectedFamily, policyName, answers]);

  const generatePolicy = async () => {
    if (!currentDraftId) {
      await saveDraft();
    }
    setGenerating(true);
    try {
      const draftId = currentDraftId;
      if (!draftId) { toast.error("Please save the draft first"); return; }
      const res = await axios.post(`${API}/policy-builder/generate`, { draft_id: draftId });
      toast.success(res.data.message || "Policy generation started");
      fetchDrafts();
      setStep("list");
    } catch (err) {
      const msg = err?.response?.data?.detail || "Generation failed";
      toast.error(msg);
    } finally { setGenerating(false); }
  };

  const answeredCount = Object.values(answers).filter(v => v && v.trim()).length;
  const progressPct = questions.length > 0 ? Math.round((answeredCount / questions.length) * 100) : 0;
  const qualityLevel = answeredCount < 5 ? { label: "Incomplete", color: "text-red-600 bg-red-50" }
    : answeredCount < 15 ? { label: "Minimal", color: "text-amber-700 bg-amber-50" }
    : answeredCount < 25 ? { label: "Good", color: "text-blue-700 bg-blue-50" }
    : { label: "Excellent", color: "text-green-700 bg-green-50" };

  // ── List View ────────────────────────────────────────────────
  if (step === "list") {
    return (
      <Wrap>
        <div data-testid="policy-builder-page">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">Policy Builder</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5">Create compliance policies with guided questionnaires</p>
            </div>
            {isAdmin && (
              <Button onClick={startNew} className="bg-[#2597B2] hover:bg-[#1B839F] text-white rounded-xl flex items-center gap-2" data-testid="new-policy-btn">
                <Plus size={16} weight="bold" /> New Policy
              </Button>
            )}
          </div>

          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-6 h-6 border-2 border-[#2597B2] border-t-transparent rounded-full animate-spin" />
            </div>
          ) : drafts.length === 0 ? (
            <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-12 text-center shadow-sm" data-testid="no-drafts">
              <FileText size={48} weight="duotone" className="text-gray-300 dark:text-gray-600 mx-auto mb-3" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">No Policy Drafts Yet</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Start creating NIST 800-53 compliance policies</p>
              {isAdmin && (
                <Button onClick={startNew} className="bg-[#2597B2] hover:bg-[#1B839F] text-white rounded-xl">
                  <Plus size={16} weight="bold" className="mr-2" /> Create First Policy
                </Button>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="drafts-list">
              {drafts.map(d => (
                <div key={d.id} className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-5 shadow-sm iv-card" data-testid={`draft-card-${d.id}`}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <FileText size={20} weight="duotone" className="text-[#2597B2]" />
                      <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 truncate">{d.policy_name}</h3>
                    </div>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                      d.status === "draft" ? "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                      : d.status === "generating" ? "bg-amber-50 text-amber-700"
                      : d.status === "submitted" ? "bg-blue-50 text-blue-700"
                      : "bg-green-50 text-green-700"
                    }`}>{d.status}</span>
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1 mb-3">
                    <p>Framework: <span className="font-medium text-gray-700 dark:text-gray-300">NIST 800-53</span></p>
                    <p>Control Family: <span className="font-medium text-gray-700 dark:text-gray-300">{d.control_family_name || d.control_family}</span></p>
                    <p>Questions Answered: <span className="font-medium text-gray-700 dark:text-gray-300">{d.answered_count || 0}</span></p>
                  </div>
                  {/* Progress bar */}
                  <div className="w-full h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full mb-3">
                    <div className="h-full bg-[#2597B2] rounded-full transition-all" style={{ width: `${Math.min(100, (d.answered_count || 0) * 2)}%` }} />
                  </div>
                  <div className="flex items-center gap-2">
                    {d.status === "draft" && isAdmin && (
                      <>
                        <Button size="sm" variant="outline" className="flex-1 rounded-xl text-[#2597B2] border-[#2597B2] hover:bg-[#2597B2] hover:text-white" onClick={() => resumeDraft(d)} data-testid={`resume-draft-${d.id}`}>
                          <Pencil size={14} className="mr-1" /> Resume
                        </Button>
                        <Button size="sm" variant="ghost" className="text-red-500 hover:bg-red-50 rounded-xl" onClick={() => deleteDraft(d.id)} data-testid={`delete-draft-${d.id}`}>
                          <Trash size={14} />
                        </Button>
                      </>
                    )}
                    {d.status !== "draft" && (
                      <span className="text-xs text-gray-400 flex items-center gap-1"><Clock size={12} /> Processing</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Wrap>
    );
  }

  // ── Family Selection ─────────────────────────────────────────
  if (step === "family") {
    return (
      <Wrap>
        <div data-testid="policy-builder-family-step">
          <button onClick={() => setStep("list")} className="flex items-center gap-1 text-sm text-gray-500 hover:text-[#2597B2] mb-4" data-testid="back-to-list">
            <CaretLeft size={14} /> Back to Policies
          </button>
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">Select Control Family</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5">Choose a NIST 800-53 control family for your policy</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3" data-testid="family-grid">
            {families.map(f => (
              <button key={f.id} onClick={() => selectFamily(f)}
                className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-4 text-left hover:border-[#2597B2] hover:shadow-md transition-all shadow-sm group"
                data-testid={`family-btn-${f.id}`}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[#e8f4f7] dark:bg-[#0a3540] flex items-center justify-center text-[#2597B2] font-bold text-sm flex-shrink-0">
                    {f.id}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{f.name}</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">NIST 800-53</p>
                  </div>
                  <CaretRight size={16} className="text-gray-300 group-hover:text-[#2597B2] transition-colors" />
                </div>
              </button>
            ))}
          </div>
        </div>
      </Wrap>
    );
  }

  // ── Questionnaire ────────────────────────────────────────────
  if (step === "questionnaire") {
    return (
      <Wrap>
        <div data-testid="policy-builder-questionnaire">
          <button onClick={() => { setStep("family"); }} className="flex items-center gap-1 text-sm text-gray-500 hover:text-[#2597B2] mb-4" data-testid="back-to-families">
            <CaretLeft size={14} /> Back to Control Families
          </button>

          {/* Header with progress */}
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">{selectedFamily?.name}</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Answer the questions below to generate your policy</p>
            </div>
            <div className="flex items-center gap-3">
              <span className={`px-3 py-1 rounded-full text-xs font-bold ${qualityLevel.color}`}>{qualityLevel.label}</span>
              <Button onClick={saveDraft} disabled={saving} variant="outline" className="rounded-xl border-[#2597B2] text-[#2597B2] hover:bg-[#2597B2] hover:text-white" data-testid="save-draft-btn">
                <FloppyDisk size={14} className="mr-1.5" /> {saving ? "Saving..." : "Save Draft"}
              </Button>
            </div>
          </div>

          {/* Policy Name */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-5 mb-4 shadow-sm">
            <Label className="text-sm font-semibold text-gray-900 dark:text-gray-100">Policy Name</Label>
            <Input value={policyName} onChange={e => setPolicyName(e.target.value)} className="mt-1.5 rounded-xl"
              placeholder="Enter policy name..." data-testid="policy-name-input" />
          </div>

          {/* Progress Bar */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-4 mb-6 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-gray-500 dark:text-gray-400">Progress: {answeredCount} / {questions.length} questions</span>
              <span className="text-xs font-bold text-[#2597B2]">{progressPct}%</span>
            </div>
            <div className="w-full h-2 bg-gray-100 dark:bg-gray-700 rounded-full">
              <div className="h-full bg-gradient-to-r from-[#2597B2] to-[#1B839F] rounded-full transition-all duration-300" style={{ width: `${progressPct}%` }} />
            </div>
          </div>

          {/* Questions */}
          {questionsLoading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-6 h-6 border-2 border-[#2597B2] border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="space-y-3" data-testid="questions-list">
              {questions.map((q, idx) => {
                const key = `q_${idx}`;
                const hasAnswer = answers[key] && answers[key].trim();
                return (
                  <div key={idx} className={`bg-white dark:bg-gray-800 rounded-2xl border p-5 shadow-sm transition-all ${
                    hasAnswer ? "border-[#2597B2]/30" : "border-gray-200/50 dark:border-gray-700/50"
                  }`} data-testid={`question-${idx}`}>
                    <div className="flex items-start gap-3 mb-3">
                      <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 text-xs font-bold ${
                        hasAnswer ? "bg-[#2597B2] text-white" : "bg-gray-100 dark:bg-gray-700 text-gray-400"
                      }`}>
                        {hasAnswer ? <Check size={14} weight="bold" /> : idx + 1}
                      </div>
                      <p className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed flex-1">{q}</p>
                    </div>
                    <Textarea
                      placeholder="Type your answer..."
                      value={answers[key] || ""}
                      onChange={e => setAnswers(prev => ({ ...prev, [key]: e.target.value }))}
                      className="rounded-xl resize-none min-h-[80px] text-sm"
                      data-testid={`answer-${idx}`}
                    />
                  </div>
                );
              })}
            </div>
          )}

          {/* Bottom Action Bar */}
          {questions.length > 0 && (
            <div className="sticky bottom-0 bg-white/90 dark:bg-gray-800/90 backdrop-blur-sm border-t border-gray-200/50 dark:border-gray-700/50 mt-6 -mx-6 lg:-mx-8 px-6 lg:px-8 py-4 flex items-center justify-between">
              <Button onClick={saveDraft} disabled={saving} variant="outline" className="rounded-xl" data-testid="save-draft-bottom">
                <FloppyDisk size={14} className="mr-1.5" /> {saving ? "Saving..." : "Save Draft"}
              </Button>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-400">{answeredCount}/{questions.length} answered</span>
                <Button onClick={() => { saveDraft().then(() => setStep("review")); }}
                  className="bg-[#2597B2] hover:bg-[#1B839F] text-white rounded-xl" data-testid="review-btn">
                  Review & Generate <ArrowRight size={14} className="ml-1.5" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </Wrap>
    );
  }

  // ── Review & Generate ────────────────────────────────────────
  if (step === "review") {
    return (
      <Wrap>
        <div data-testid="policy-builder-review">
          <button onClick={() => setStep("questionnaire")} className="flex items-center gap-1 text-sm text-gray-500 hover:text-[#2597B2] mb-4" data-testid="back-to-questions">
            <CaretLeft size={14} /> Back to Questions
          </button>
          <div className="mb-6">
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">Review & Generate</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Review your answers and generate the policy</p>
          </div>

          {/* Summary Card */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-6 mb-6 shadow-sm">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div><p className="text-[0.625rem] font-bold uppercase tracking-[0.15em] text-gray-400">Policy Name</p><p className="text-sm font-semibold text-gray-900 dark:text-gray-100 mt-1">{policyName}</p></div>
              <div><p className="text-[0.625rem] font-bold uppercase tracking-[0.15em] text-gray-400">Framework</p><p className="text-sm font-semibold text-gray-900 dark:text-gray-100 mt-1">NIST 800-53</p></div>
              <div><p className="text-[0.625rem] font-bold uppercase tracking-[0.15em] text-gray-400">Control Family</p><p className="text-sm font-semibold text-gray-900 dark:text-gray-100 mt-1">{selectedFamily?.name}</p></div>
              <div><p className="text-[0.625rem] font-bold uppercase tracking-[0.15em] text-gray-400">Quality</p><p className={`text-sm font-bold mt-1 px-2 py-0.5 rounded-full inline-block ${qualityLevel.color}`}>{qualityLevel.label} ({answeredCount}/{questions.length})</p></div>
            </div>
          </div>

          {/* Answered Questions Summary */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-5 mb-6 shadow-sm">
            <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 mb-4">Answered Questions ({answeredCount})</h3>
            <div className="space-y-3 max-h-[400px] overflow-y-auto">
              {questions.map((q, idx) => {
                const key = `q_${idx}`;
                const val = answers[key];
                if (!val || !val.trim()) return null;
                return (
                  <div key={idx} className="border-b border-gray-100 dark:border-gray-700 pb-3 last:border-0">
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Q{idx + 1}: {q}</p>
                    <p className="text-sm text-gray-800 dark:text-gray-200">{val}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Generate Button */}
          <div className="flex items-center justify-between">
            <Button variant="outline" onClick={() => setStep("questionnaire")} className="rounded-xl">
              <CaretLeft size={14} className="mr-1.5" /> Edit Answers
            </Button>
            <Button onClick={generatePolicy} disabled={generating || answeredCount < 5}
              className="bg-[#2597B2] hover:bg-[#1B839F] text-white rounded-xl px-6" data-testid="generate-policy-btn">
              <Lightning size={16} weight="bold" className="mr-2" />
              {generating ? "Generating..." : "Generate Policy"}
            </Button>
          </div>
        </div>
      </Wrap>
    );
  }

  return null;
};

export default PolicyBuilderPage;
