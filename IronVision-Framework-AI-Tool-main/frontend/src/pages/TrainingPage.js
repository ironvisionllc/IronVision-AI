import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import {
  GraduationCap,
  BookOpen,
  CheckCircle,
  Clock,
  ArrowLeft,
  CaretRight,
  Trophy,
  XCircle,
  ShieldCheck,
  Desktop,
  ListChecks,
  MagnifyingGlass
} from "@phosphor-icons/react";

const CATEGORIES = [
  { key: "all", label: "All Modules" },
  { key: "grc", label: "GRC Knowledge", icon: ShieldCheck },
  { key: "platform", label: "Platform Training", icon: Desktop },
];

const DIFFICULTY_COLORS = {
  beginner: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  intermediate: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  advanced: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

// ─── Module Card ─────────────────────────────────────────
const ModuleCard = ({ mod, onClick }) => {
  const lessonsDone = (mod.completed_lessons || []).length;
  const totalLessons = mod.total_lessons || 0;
  const progressPct = totalLessons > 0 ? Math.round((lessonsDone / totalLessons) * 100) : 0;

  return (
    <div
      onClick={onClick}
      data-testid={`training-module-${mod.id}`}
      className="group bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-5 cursor-pointer hover:border-[#2597B2]/40 hover:shadow-lg transition-all duration-200"
    >
      <div className="flex items-start justify-between mb-3">
        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${DIFFICULTY_COLORS[mod.difficulty] || DIFFICULTY_COLORS.beginner}`}>
          {mod.difficulty}
        </span>
        {mod.completed && mod.quiz_passed && (
          <div className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
            <Trophy size={16} weight="fill" />
            <span className="text-xs font-bold">{mod.quiz_score}%</span>
          </div>
        )}
      </div>

      <h3 className="text-base font-bold text-gray-900 dark:text-gray-100 mb-1.5 group-hover:text-[#1B839F] transition-colors leading-snug">
        {mod.title}
      </h3>
      <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 mb-4 leading-relaxed">
        {mod.description}
      </p>

      <div className="flex items-center gap-3 text-xs text-gray-400 dark:text-gray-500 mb-3">
        <span className="flex items-center gap-1"><Clock size={13} /> {mod.duration_minutes} min</span>
        <span className="flex items-center gap-1"><BookOpen size={13} /> {totalLessons} lessons</span>
      </div>

      {/* Progress bar */}
      <div className="w-full h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${mod.completed && mod.quiz_passed ? "bg-emerald-500" : "bg-[#2597B2]"}`}
          style={{ width: `${progressPct}%` }}
        />
      </div>
      <p className="text-[10px] text-gray-400 mt-1.5">
        {mod.completed && mod.quiz_passed ? "Completed" : `${lessonsDone}/${totalLessons} lessons`}
      </p>
    </div>
  );
};

// ─── Lesson Viewer ───────────────────────────────────────
const LessonViewer = ({ module, onBack, onRefresh }) => {
  const [activeLesson, setActiveLesson] = useState(0);
  const [completedLessons, setCompletedLessons] = useState(module.completed_lessons || []);
  const [showQuiz, setShowQuiz] = useState(false);
  const [quiz, setQuiz] = useState(null);
  const [quizAnswers, setQuizAnswers] = useState([]);
  const [quizResult, setQuizResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const lessons = module.lessons || [];
  const currentLesson = lessons[activeLesson];
  const allLessonsComplete = lessons.every(l => completedLessons.includes(l.id));

  const markComplete = async () => {
    if (!currentLesson || completedLessons.includes(currentLesson.id)) return;
    try {
      await axios.post(`${API}/training/${module.id}/lesson/${currentLesson.id}/complete`);
      setCompletedLessons(prev => [...prev, currentLesson.id]);
    } catch {}
  };

  const goNext = async () => {
    await markComplete();
    if (activeLesson < lessons.length - 1) {
      setActiveLesson(activeLesson + 1);
    }
  };

  const startQuiz = async () => {
    try {
      const r = await axios.get(`${API}/training/${module.id}/quiz`);
      setQuiz(r.data);
      setQuizAnswers(new Array(r.data.questions.length).fill(-1));
      setShowQuiz(true);
      setQuizResult(null);
    } catch {
      setQuiz(null);
    }
  };

  const submitQuiz = async () => {
    setSubmitting(true);
    try {
      const r = await axios.post(`${API}/training/${module.id}/quiz/submit`, { answers: quizAnswers });
      setQuizResult(r.data);
      onRefresh();
    } catch {} finally {
      setSubmitting(false);
    }
  };

  // Quiz view
  if (showQuiz && quiz) {
    return (
      <div data-testid="quiz-view">
        <button onClick={() => setShowQuiz(false)} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#1B839F] mb-5 transition-colors" data-testid="quiz-back-btn">
          <ArrowLeft size={16} /> Back to Lessons
        </button>

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-[#e8f4f7] dark:bg-[#0a3540] flex items-center justify-center">
              <ListChecks size={22} className="text-[#1B839F]" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">Knowledge Assessment</h2>
              <p className="text-xs text-gray-500">{quiz.total_questions} questions | Passing score: {quiz.passing_score}%</p>
            </div>
          </div>

          {!quizResult ? (
            <>
              {quiz.questions.map((q, qi) => (
                <div key={qi} className="mb-6" data-testid={`quiz-question-${qi}`}>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">
                    <span className="text-[#1B839F] mr-2">{qi + 1}.</span>{q.question}
                  </p>
                  <div className="space-y-2 pl-5">
                    {q.options.map((opt, oi) => (
                      <label
                        key={oi}
                        className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all text-sm ${
                          quizAnswers[qi] === oi
                            ? "border-[#2597B2] bg-[#e8f4f7] dark:bg-[#0a3540]"
                            : "border-gray-200 dark:border-gray-700 hover:border-gray-300"
                        }`}
                      >
                        <input
                          type="radio"
                          name={`q-${qi}`}
                          checked={quizAnswers[qi] === oi}
                          onChange={() => setQuizAnswers(prev => { const n = [...prev]; n[qi] = oi; return n; })}
                          className="accent-[#2597B2]"
                        />
                        <span className="text-gray-700 dark:text-gray-300">{opt}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
              <button
                onClick={submitQuiz}
                disabled={submitting || quizAnswers.includes(-1)}
                className="w-full mt-4 py-3 rounded-xl bg-[#2597B2] text-white font-semibold hover:bg-[#1B839F] disabled:opacity-40 transition-colors"
                data-testid="submit-quiz-btn"
              >
                {submitting ? "Submitting..." : "Submit Answers"}
              </button>
            </>
          ) : (
            <div data-testid="quiz-result">
              <div className={`text-center py-8 mb-6 rounded-2xl ${quizResult.passed ? "bg-emerald-50 dark:bg-emerald-900/20" : "bg-red-50 dark:bg-red-900/20"}`}>
                {quizResult.passed ? (
                  <Trophy size={48} weight="fill" className="text-emerald-500 mx-auto mb-3" />
                ) : (
                  <XCircle size={48} weight="fill" className="text-red-500 mx-auto mb-3" />
                )}
                <p className={`text-3xl font-black ${quizResult.passed ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                  {quizResult.score}%
                </p>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  {quizResult.correct_answers}/{quizResult.total_questions} correct | {quizResult.passed ? "Passed!" : `Need ${quizResult.passing_score}% to pass`}
                </p>
              </div>

              {/* Show answer review */}
              {quizResult.results.map((r, ri) => (
                <div key={ri} className={`mb-3 p-3 rounded-xl border text-sm ${r.is_correct ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-800 dark:bg-emerald-900/10" : "border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-900/10"}`}>
                  <div className="flex items-start gap-2">
                    {r.is_correct ? <CheckCircle size={18} weight="fill" className="text-emerald-500 mt-0.5 flex-shrink-0" /> : <XCircle size={18} weight="fill" className="text-red-500 mt-0.5 flex-shrink-0" />}
                    <div>
                      <p className="font-medium text-gray-800 dark:text-gray-200">{r.question}</p>
                      {!r.is_correct && (
                        <p className="text-xs text-gray-500 mt-1">Correct: {quiz.questions[ri]?.options[r.correct_answer]}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              <div className="flex gap-3 mt-6">
                {!quizResult.passed && (
                  <button
                    onClick={() => { setQuizResult(null); setQuizAnswers(new Array(quiz.questions.length).fill(-1)); }}
                    className="flex-1 py-3 rounded-xl border border-[#2597B2] text-[#2597B2] font-semibold hover:bg-[#e8f4f7] transition-colors"
                    data-testid="retry-quiz-btn"
                  >
                    Retry Quiz
                  </button>
                )}
                <button
                  onClick={() => setShowQuiz(false)}
                  className="flex-1 py-3 rounded-xl bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-semibold hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  Back to Lessons
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Lesson view
  return (
    <div data-testid="lesson-view">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#1B839F] mb-5 transition-colors" data-testid="back-to-modules">
        <ArrowLeft size={16} /> All Modules
      </button>

      <div className="flex items-start gap-3 mb-6">
        <div className="w-10 h-10 rounded-xl bg-[#e8f4f7] dark:bg-[#0a3540] flex items-center justify-center flex-shrink-0">
          <GraduationCap size={22} weight="duotone" className="text-[#1B839F]" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">{module.title}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{module.duration_minutes} min | {lessons.length} lessons</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-5">
        {/* Sidebar — lesson list */}
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-3 h-fit lg:sticky lg:top-20" data-testid="lesson-sidebar">
          <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 px-3 pt-2 pb-2">Lessons</p>
          {lessons.map((les, idx) => {
            const done = completedLessons.includes(les.id);
            const active = idx === activeLesson;
            return (
              <button
                key={les.id}
                onClick={() => setActiveLesson(idx)}
                data-testid={`lesson-nav-${idx}`}
                className={`w-full text-left flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm transition-all mb-0.5 ${
                  active
                    ? "bg-[#e8f4f7] dark:bg-[#0a3540] text-[#1B839F] font-semibold"
                    : "text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50"
                }`}
              >
                {done ? (
                  <CheckCircle size={16} weight="fill" className="text-emerald-500 flex-shrink-0" />
                ) : (
                  <span className={`w-4 h-4 rounded-full border-2 flex-shrink-0 ${active ? "border-[#2597B2]" : "border-gray-300 dark:border-gray-600"}`} />
                )}
                <span className="truncate">{les.title}</span>
              </button>
            );
          })}

          {/* Quiz button */}
          <div className="border-t border-gray-200 dark:border-gray-700 mt-2 pt-2">
            <button
              onClick={startQuiz}
              disabled={!allLessonsComplete}
              data-testid="take-quiz-btn"
              className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                allLessonsComplete
                  ? "text-[#2597B2] bg-[#e8f4f7]/60 hover:bg-[#e8f4f7] dark:bg-[#0a3540]/40 dark:hover:bg-[#0a3540]"
                  : "text-gray-400 cursor-not-allowed"
              }`}
            >
              <Trophy size={16} weight={allLessonsComplete ? "fill" : "regular"} />
              Take Quiz
            </button>
            {!allLessonsComplete && (
              <p className="text-[10px] text-gray-400 px-3 mt-1">Complete all lessons first</p>
            )}
          </div>
        </div>

        {/* Main content — lesson reader */}
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-6" data-testid="lesson-content">
          {currentLesson ? (
            <>
              <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{currentLesson.title}</h2>
              <div className="prose prose-sm dark:prose-invert max-w-none">
                {currentLesson.content.split("\n\n").map((para, pi) => (
                  <div key={pi} className="mb-4">
                    {para.split("\n").map((line, li) => {
                      const trimmed = line.trim();
                      if (!trimmed) return null;
                      // Check for header-like lines (ends with : and is short, or starts with a number followed by dot)
                      const isHeading = (trimmed.endsWith(":") && trimmed.length < 80 && !trimmed.startsWith("-")) || /^\d+\.\s+[A-Z]/.test(trimmed);
                      const isBullet = trimmed.startsWith("- ") || trimmed.startsWith("* ");
                      if (isHeading) {
                        return <p key={li} className="font-semibold text-gray-800 dark:text-gray-200 mt-3 mb-1 text-sm">{trimmed}</p>;
                      }
                      if (isBullet) {
                        return (
                          <div key={li} className="flex items-start gap-2 ml-2 mb-1">
                            <span className="text-[#2597B2] mt-1 text-xs flex-shrink-0">&#9679;</span>
                            <span className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{trimmed.slice(2)}</span>
                          </div>
                        );
                      }
                      return <p key={li} className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{trimmed}</p>;
                    })}
                  </div>
                ))}
              </div>

              {/* Navigation */}
              <div className="flex items-center justify-between mt-8 pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => setActiveLesson(Math.max(0, activeLesson - 1))}
                  disabled={activeLesson === 0}
                  className="text-sm text-gray-500 hover:text-[#1B839F] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  Previous
                </button>
                {activeLesson < lessons.length - 1 ? (
                  <button
                    onClick={goNext}
                    className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-[#2597B2] text-white text-sm font-semibold hover:bg-[#1B839F] transition-colors"
                    data-testid="next-lesson-btn"
                  >
                    Next Lesson <CaretRight size={14} weight="bold" />
                  </button>
                ) : (
                  <button
                    onClick={async () => { await markComplete(); if (allLessonsComplete || (!completedLessons.includes(currentLesson.id) && completedLessons.length + 1 === lessons.length)) startQuiz(); }}
                    className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 transition-colors"
                    data-testid="finish-and-quiz-btn"
                  >
                    Finish & Take Quiz <Trophy size={14} weight="fill" />
                  </button>
                )}
              </div>
            </>
          ) : (
            <p className="text-gray-400">Select a lesson to begin.</p>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── Main Page ───────────────────────────────────────────
const TrainingPage = () => {
  const [modules, setModules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedModule, setSelectedModule] = useState(null);
  const [moduleDetail, setModuleDetail] = useState(null);

  const fetchModules = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/training`);
      setModules(r.data);
    } catch {} finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchModules(); }, [fetchModules]);

  const openModule = async (mod) => {
    try {
      const r = await axios.get(`${API}/training/${mod.id}`);
      setModuleDetail(r.data);
      setSelectedModule(mod.id);
    } catch {}
  };

  const filtered = modules.filter(m => {
    if (category !== "all" && m.category !== category) return false;
    if (search && !m.title.toLowerCase().includes(search.toLowerCase()) && !m.description.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const completedCount = modules.filter(m => m.completed && m.quiz_passed).length;

  if (selectedModule && moduleDetail) {
    return (
      <Layout>
        <div data-testid="training-page">
          <LessonViewer
            module={moduleDetail}
            onBack={() => { setSelectedModule(null); setModuleDetail(null); fetchModules(); }}
            onRefresh={fetchModules}
          />
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div data-testid="training-page">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between mb-6 gap-4">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight" style={{ fontFamily: "Inter, sans-serif" }}>
              Training & Awareness
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">GRC compliance knowledge and platform training modules</p>
          </div>
          {modules.length > 0 && (
            <div className="flex items-center gap-2 px-4 py-2 bg-[#e8f4f7] dark:bg-[#0a3540] rounded-xl" data-testid="progress-summary">
              <Trophy size={18} weight="fill" className="text-[#1B839F]" />
              <span className="text-sm font-semibold text-[#1B839F]">{completedCount}/{modules.length} completed</span>
            </div>
          )}
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-3 mb-6">
          <div className="flex gap-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-1" data-testid="category-tabs">
            {CATEGORIES.map(cat => (
              <button
                key={cat.key}
                onClick={() => setCategory(cat.key)}
                data-testid={`tab-${cat.key}`}
                className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${
                  category === cat.key
                    ? "bg-[#2597B2] text-white shadow-sm"
                    : "text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50"
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
          <div className="relative flex-1 max-w-xs">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search modules..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-[#2597B2]/30 focus:border-[#2597B2]"
              data-testid="training-search"
            />
          </div>
        </div>

        {/* Module Grid */}
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <p className="text-gray-500">Loading training modules...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-12 text-center">
            <GraduationCap size={48} weight="duotone" className="text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">No modules match your filters</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="module-grid">
            {filtered.map(mod => (
              <ModuleCard key={mod.id} mod={mod} onClick={() => openModule(mod)} />
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
};

export default TrainingPage;
