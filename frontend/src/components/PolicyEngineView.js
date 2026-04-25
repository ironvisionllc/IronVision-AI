import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  CaretLeft, ArrowsClockwise, ShieldCheck, Warning, CheckCircle,
  XCircle, Code, TrendUp, TrendDown, Camera, Play, CaretRight,
  MinusCircle, Plus
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const SEV_COLORS = {
  critical: "bg-red-600 text-white",
  high: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  low: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
};

const PolicyEngineView = () => {
  const [tab, setTab] = useState("evaluate"); // evaluate | rules | drift | history
  const [rules, setRules] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [driftResult, setDriftResult] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(false);

  // Evaluate state
  const [configText, setConfigText] = useState(JSON.stringify({
    "server": {
      "encryption": false,
      "mfa_enabled": false,
      "publicly_accessible": true,
      "logging": true,
      "tls_version": "1.1",
      "backup_enabled": true,
      "tags": { "environment": "prod" },
      "password": "SuperSecret123!"
    }
  }, null, 2));
  const [evalResult, setEvalResult] = useState(null);
  const [evaluating, setEvaluating] = useState(false);

  const fetchRules = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/policy-engine/rules`);
      setRules(res.data);
    } catch {
      toast.error("Failed to load rules");
    }
  }, []);

  const fetchEvaluations = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/policy-engine/evaluations`);
      setEvaluations(res.data);
    } catch {
      toast.error("Failed to load evaluations");
    }
  }, []);

  const fetchSnapshots = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/policy-engine/drift/snapshots`);
      setSnapshots(res.data);
    } catch {
      toast.error("Failed to load snapshots");
    }
  }, []);

  useEffect(() => {
    if (tab === "rules" && !rules) fetchRules();
    if (tab === "history") fetchEvaluations();
    if (tab === "drift") fetchSnapshots();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const runEvaluation = async () => {
    setEvaluating(true);
    try {
      const config = JSON.parse(configText);
      const res = await axios.post(`${API}/policy-engine/evaluate`, {
        config,
        config_type: "generic",
        source: "Manual evaluation",
      });
      setEvalResult(res.data);
      toast.success(`Evaluation complete: ${res.data.violation_count} violations found`);
    } catch (err) {
      if (err instanceof SyntaxError) {
        toast.error("Invalid JSON config");
      } else {
        toast.error(err.response?.data?.detail || "Evaluation failed");
      }
    } finally {
      setEvaluating(false);
    }
  };

  const createSnapshot = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API}/policy-engine/drift/snapshot`);
      toast.success(res.data.message);
      fetchSnapshots();
    } catch {
      toast.error("Failed to create snapshot");
    } finally {
      setLoading(false);
    }
  };

  const detectDrift = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/policy-engine/drift/detect`);
      setDriftResult(res.data);
    } catch {
      toast.error("Failed to detect drift");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="policy-engine-view">

      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Policy-as-Code & Drift Detection</h2>
          <p className="text-sm text-gray-500 mt-1">Evaluate configs against compliance policies, detect drift from baseline</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 p-1 bg-gray-100 dark:bg-gray-800 rounded-lg w-fit" data-testid="engine-tabs">
        {[
          { key: "evaluate", label: "Evaluate Config", icon: Play },
          { key: "rules", label: "Policy Rules", icon: Code },
          { key: "drift", label: "Drift Detection", icon: TrendUp },
          { key: "history", label: "History", icon: ShieldCheck },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              tab === t.key
                ? "bg-white dark:bg-gray-900 text-[#2597B2] shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
            data-testid={`tab-${t.key}`}
          >
            <t.icon size={15} weight={tab === t.key ? "fill" : "regular"} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Evaluate Tab */}
      {tab === "evaluate" && (
        <div className="grid grid-cols-2 gap-6" data-testid="evaluate-tab">
          <div>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Infrastructure Config (JSON)</h3>
            <textarea
              value={configText}
              onChange={e => setConfigText(e.target.value)}
              className="w-full h-80 font-mono text-xs p-4 border border-gray-200 dark:border-gray-700 rounded-xl bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-200 resize-none"
              data-testid="config-input"
            />
            <Button onClick={runEvaluation} disabled={evaluating} className="mt-3 bg-[#2597B2] hover:bg-[#1B839F] w-full" data-testid="run-evaluation-btn">
              {evaluating ? <><ArrowsClockwise size={16} className="animate-spin mr-2" /> Evaluating...</> : <><Play size={16} className="mr-2" /> Run Policy Evaluation</>}
            </Button>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Results</h3>
            {evalResult ? (
              <div>
                <div className={`p-4 rounded-xl mb-4 ${evalResult.pass ? "bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200" : "bg-red-50 dark:bg-red-900/20 border border-red-200"}`} data-testid="eval-result-status">
                  <div className="flex items-center gap-2">
                    {evalResult.pass ? <CheckCircle size={24} weight="fill" className="text-emerald-500" /> : <XCircle size={24} weight="fill" className="text-red-500" />}
                    <span className={`text-lg font-bold ${evalResult.pass ? "text-emerald-700" : "text-red-700"}`}>
                      {evalResult.pass ? "All Checks Passed" : `${evalResult.violation_count} Violation${evalResult.violation_count > 1 ? "s" : ""} Found`}
                    </span>
                  </div>
                  {!evalResult.pass && (
                    <div className="flex gap-3 mt-2 text-xs">
                      {Object.entries(evalResult.severity_counts).filter(([, v]) => v > 0).map(([sev, count]) => (
                        <span key={sev} className={`px-2 py-0.5 rounded-full font-medium ${SEV_COLORS[sev]}`}>
                          {count} {sev}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="space-y-2 max-h-64 overflow-y-auto" data-testid="violations-list">
                  {evalResult.violations?.map((v, i) => (
                    <div key={i} className="p-3 iv-card" data-testid={`violation-${i}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`px-1.5 py-0.5 text-[10px] font-semibold rounded ${SEV_COLORS[v.severity]}`}>{v.severity.toUpperCase()}</span>
                        <span className="text-xs font-mono text-[#2597B2]">{v.rule_id}</span>
                      </div>
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{v.name}</div>
                      <div className="text-xs text-red-600 mt-1">{v.violation}</div>
                      {v.control_ids?.length > 0 && (
                        <div className="flex gap-1 mt-2 flex-wrap">
                          {v.control_ids.map(c => (
                            <span key={c} className="text-[9px] px-1.5 py-0.5 bg-[#2597B2]/10 text-[#2597B2] rounded font-medium">{c}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-80 text-gray-400 text-sm">
                Paste config JSON and run evaluation to see results
              </div>
            )}
          </div>
        </div>
      )}

      {/* Rules Tab */}
      {tab === "rules" && (
        <div data-testid="rules-tab">
          {!rules ? (
            <div className="text-center py-8 text-gray-400">Loading rules...</div>
          ) : (
            <div className="space-y-2">
              <div className="text-sm text-gray-500 mb-3">{rules.total} policy rules ({rules.builtin_rules?.length || 0} built-in, {rules.custom_rules?.length || 0} custom)</div>
              {rules.builtin_rules?.map(r => (
                <div key={r.id} className="iv-card p-4" data-testid={`rule-${r.id}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono text-[#2597B2] font-semibold">{r.id}</span>
                    <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${SEV_COLORS[r.severity]}`}>{r.severity.toUpperCase()}</span>
                    <span className="text-xs text-gray-400">{r.category}</span>
                  </div>
                  <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{r.name}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{r.description}</div>
                  {r.control_ids?.length > 0 && (
                    <div className="flex gap-1 mt-2 flex-wrap">
                      {r.control_ids.map(c => (
                        <span key={c} className="text-[9px] px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-600 rounded">{c}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Drift Tab */}
      {tab === "drift" && (
        <div data-testid="drift-tab">
          <div className="flex gap-3 mb-6">
            <Button onClick={createSnapshot} disabled={loading} className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="create-snapshot-btn">
              <Camera size={16} className="mr-2" /> Create Baseline Snapshot
            </Button>
            <Button variant="outline" onClick={detectDrift} disabled={loading} data-testid="detect-drift-btn">
              <TrendUp size={16} className="mr-2" /> Detect Drift
            </Button>
          </div>

          {driftResult && (
            <div className="mb-6" data-testid="drift-result">
              <div className={`p-5 rounded-xl mb-4 ${driftResult.drift_detected ? "bg-amber-50 dark:bg-amber-900/20 border border-amber-200" : "bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200"}`}>
                <div className="flex items-center gap-2 mb-2">
                  {driftResult.drift_detected ? <Warning size={24} weight="fill" className="text-amber-500" /> : <CheckCircle size={24} weight="fill" className="text-emerald-500" />}
                  <span className={`text-lg font-bold ${driftResult.drift_detected ? "text-amber-700" : "text-emerald-700"}`}>
                    {driftResult.drift_detected ? `Compliance Drift Detected (${driftResult.summary?.total_changes} changes)` : "No Drift Detected"}
                  </span>
                </div>
                {driftResult.drift_detected && driftResult.summary && (
                  <div className="flex gap-4 text-sm">
                    <span className="text-emerald-600 flex items-center gap-1"><TrendDown size={14} /> {driftResult.summary.improved} improved</span>
                    <span className="text-red-600 flex items-center gap-1"><TrendUp size={14} /> {driftResult.summary.degraded} degraded</span>
                  </div>
                )}
                {driftResult.baseline_date && (
                  <div className="text-xs text-gray-500 mt-2">Baseline: {new Date(driftResult.baseline_date).toLocaleString()}</div>
                )}
              </div>

              {driftResult.changes?.length > 0 && (
                <div className="space-y-2">
                  {driftResult.changes.map((c, i) => (
                    <div key={i} className="iv-card p-3 flex items-center gap-3" data-testid={`drift-change-${i}`}>
                      {c.direction === "improved" ? (
                        <TrendDown size={18} className="text-emerald-500" />
                      ) : (
                        <TrendUp size={18} className="text-red-500" />
                      )}
                      <div className="flex-1">
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{c.framework_name} — {c.control_id}</div>
                        <div className="text-xs text-gray-500">
                          {c.previous_status} <CaretRight size={10} className="inline" /> {c.current_status}
                        </div>
                      </div>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        c.direction === "improved" ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-600"
                      }`}>
                        {c.direction}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Snapshots List */}
          {snapshots.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Baseline Snapshots</h3>
              <div className="space-y-2">
                {snapshots.map(s => (
                  <div key={s.id} className="iv-card p-3 flex items-center gap-3">
                    <Camera size={16} className="text-[#2597B2]" />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Snapshot {s.id.substring(0, 8)}</div>
                      <div className="text-xs text-gray-500">{new Date(s.created_at).toLocaleString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* History Tab */}
      {tab === "history" && (
        <div data-testid="history-tab">
          {evaluations.length === 0 ? (
            <div className="text-center py-8 text-gray-400">No evaluations yet. Run a policy evaluation first.</div>
          ) : (
            <div className="space-y-2">
              {evaluations.map(e => (
                <div key={e.id} className="iv-card p-4 flex items-center gap-4" data-testid={`eval-${e.id}`}>
                  {e.pass ? <CheckCircle size={20} weight="fill" className="text-emerald-500" /> : <XCircle size={20} weight="fill" className="text-red-500" />}
                  <div className="flex-1">
                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {e.pass ? "All Checks Passed" : `${e.violation_count} Violations`}
                    </div>
                    <div className="text-xs text-gray-500">{e.source || e.config_type} | {new Date(e.created_at).toLocaleString()}</div>
                  </div>
                  <div className="flex gap-2">
                    {Object.entries(e.severity_counts || {}).filter(([, v]) => v > 0).map(([sev, count]) => (
                      <span key={sev} className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${SEV_COLORS[sev]}`}>
                        {count} {sev}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default PolicyEngineView;
