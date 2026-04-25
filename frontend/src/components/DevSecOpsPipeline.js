import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  CaretLeft, CaretRight, Lightning, ShieldCheck, Warning, CheckCircle,
  XCircle, MinusCircle, ArrowsClockwise, Trash, Key, Copy, GitBranch,
  Code, Bug, Package, Lock, ChartBar, Clock, Eye
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const GATE_CONFIG = {
  pass: { label: "Pass", color: "text-emerald-600", bg: "bg-emerald-50 dark:bg-emerald-900/20", icon: CheckCircle },
  warn: { label: "Warn", color: "text-amber-600", bg: "bg-amber-50 dark:bg-amber-900/20", icon: Warning },
  fail: { label: "Fail", color: "text-red-600", bg: "bg-red-50 dark:bg-red-900/20", icon: XCircle },
};

const SCAN_ICONS = {
  sast: Code, dast: Bug, sca: Package, container: Lock, iac: GitBranch, secret: Key, mixed: Lightning,
};

const SEV_COLORS = {
  critical: "bg-red-600 text-white",
  high: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  low: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  info: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

const DevSecOpsPipeline = () => {
  const [view, setView] = useState("dashboard"); // dashboard | run-detail | api-keys
  const [runs, setRuns] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runDetail, setRunDetail] = useState(null);
  const [apiKeys, setApiKeys] = useState([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [creatingKey, setCreatingKey] = useState(false);
  const [newKeyValue, setNewKeyValue] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [runsRes, statsRes] = await Promise.all([
        axios.get(`${API}/pipeline/runs`),
        axios.get(`${API}/pipeline/stats`),
      ]);
      setRuns(runsRes.data);
      setStats(statsRes.data);
    } catch {
      toast.error("Failed to load pipeline data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openRunDetail = async (run) => {
    setSelectedRun(run);
    setView("run-detail");
    try {
      const res = await axios.get(`${API}/pipeline/runs/${run.id}`);
      setRunDetail(res.data);
    } catch {
      toast.error("Failed to load run details");
    }
  };

  const deleteRun = async (runId) => {
    if (!window.confirm("Delete this pipeline run?")) return;
    try {
      await axios.delete(`${API}/pipeline/runs/${runId}`);
      toast.success("Pipeline run deleted");
      fetchData();
      if (selectedRun?.id === runId) { setView("dashboard"); setSelectedRun(null); }
    } catch {
      toast.error("Failed to delete");
    }
  };

  const fetchApiKeys = async () => {
    try {
      const res = await axios.get(`${API}/pipeline/api-keys`);
      setApiKeys(res.data);
    } catch {
      toast.error("Failed to load API keys");
    }
  };

  const createApiKey = async () => {
    if (!newKeyName.trim()) return toast.error("Enter a key name");
    setCreatingKey(true);
    try {
      const res = await axios.post(`${API}/pipeline/api-keys`, { name: newKeyName });
      setNewKeyValue(res.data.key);
      setNewKeyName("");
      fetchApiKeys();
      toast.success("API key created");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to create key");
    } finally {
      setCreatingKey(false);
    }
  };

  const revokeKey = async (keyId) => {
    if (!window.confirm("Revoke this API key?")) return;
    try {
      await axios.delete(`${API}/pipeline/api-keys/${keyId}`);
      toast.success("API key revoked");
      fetchApiKeys();
    } catch {
      toast.error("Failed to revoke key");
    }
  };

  useEffect(() => {
    if (view === "api-keys") fetchApiKeys();
  }, [view]);

  // ─── API KEYS VIEW ──────────────
  if (view === "api-keys") {
    return (
      <div data-testid="pipeline-api-keys-view">
        <button onClick={() => setView("dashboard")} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#2597B2] mb-6 transition-colors" data-testid="back-to-dashboard-btn">
          <CaretLeft size={14} weight="bold" /> Back to Pipeline Dashboard
        </button>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-1">Pipeline API Keys</h2>
        <p className="text-sm text-gray-500 mb-6">Generate API keys for your CI/CD tools to authenticate with the compliance gate</p>

        {/* Create Key */}
        <div className="iv-card p-5 mb-6">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Create New API Key</h3>
          <div className="flex gap-3">
            <Input placeholder="Key name (e.g., GitHub Actions Prod)" value={newKeyName} onChange={e => setNewKeyName(e.target.value)} className="flex-1" data-testid="api-key-name-input" />
            <Button onClick={createApiKey} disabled={creatingKey} className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="create-api-key-btn">
              <Key size={16} className="mr-2" /> Generate Key
            </Button>
          </div>
          {newKeyValue && (
            <div className="mt-4 p-4 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-xl" data-testid="new-key-display">
              <div className="text-xs font-medium text-emerald-700 dark:text-emerald-400 mb-2">New API Key (copy now — it won't be shown again):</div>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs font-mono bg-white dark:bg-gray-900 p-2 rounded border break-all">{newKeyValue}</code>
                <Button size="sm" variant="outline" onClick={() => { navigator.clipboard.writeText(newKeyValue); toast.success("Copied!"); }} data-testid="copy-key-btn">
                  <Copy size={14} />
                </Button>
              </div>
              <div className="mt-2 text-[10px] text-gray-500">Use as: <code>X-Pipeline-Key: {newKeyValue.substring(0, 12)}...</code></div>
            </div>
          )}
        </div>

        {/* Usage Guide */}
        <div className="iv-card p-5 mb-6">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Integration Guide</h3>
          <pre className="text-xs font-mono bg-gray-50 dark:bg-gray-800 p-4 rounded-lg overflow-x-auto text-gray-700 dark:text-gray-300">{`# Send scan results to IronVision
curl -X POST ${API}/pipeline/webhook \\
  -H "X-Pipeline-Key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "pipeline_name": "my-app-ci",
    "scan_type": "sast",
    "repo": "org/my-app",
    "branch": "main",
    "commit_sha": "abc123",
    "findings": [{
      "title": "SQL Injection in login.py",
      "severity": "critical",
      "category": "sast",
      "file_path": "src/login.py",
      "line_number": 42,
      "cwe_id": "CWE-89"
    }]
  }'

# Evaluate compliance gate
curl -X POST ${API}/pipeline/gate \\
  -H "X-Pipeline-Key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"run_id": "RUN_ID", "policy": "default"}'`}
          </pre>
        </div>

        {/* Existing Keys */}
        <div className="space-y-2">
          {apiKeys.length === 0 ? (
            <div className="text-center py-8 text-gray-400">No API keys created yet</div>
          ) : (
            apiKeys.map(k => (
              <div key={k.id} className="iv-card p-4 flex items-center gap-3" data-testid={`api-key-${k.id}`}>
                <Key size={18} className={k.active ? "text-[#2597B2]" : "text-gray-400"} />
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{k.name}</div>
                  <div className="text-xs text-gray-500">{k.key_prefix} | Created {new Date(k.created_at).toLocaleDateString()} | Used {k.usage_count}x</div>
                </div>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${k.active ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-600"}`}>
                  {k.active ? "Active" : "Revoked"}
                </span>
                {k.active && (
                  <Button size="sm" variant="outline" className="text-red-500 hover:text-red-600 border-red-200" onClick={() => revokeKey(k.id)} data-testid={`revoke-key-${k.id}`}>
                    <Trash size={14} />
                  </Button>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    );
  }

  // ─── RUN DETAIL VIEW ──────────────
  if (view === "run-detail" && selectedRun) {
    const findings = runDetail?.findings || [];
    const run = runDetail?.run || selectedRun;
    const gateConf = GATE_CONFIG[run.gate_result] || {};
    const ScanIcon = SCAN_ICONS[run.scan_type] || Lightning;

    return (
      <div data-testid="pipeline-run-detail">
        <button onClick={() => { setView("dashboard"); setSelectedRun(null); setRunDetail(null); }} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#2597B2] mb-6 transition-colors" data-testid="back-to-dashboard-btn">
          <CaretLeft size={14} weight="bold" /> Back to Pipeline Dashboard
        </button>

        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <ScanIcon size={24} className="text-[#2597B2]" />
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{run.pipeline_name}</h2>
            </div>
            <div className="flex items-center gap-3 mt-1.5 text-sm text-gray-500">
              {run.repo && <span className="flex items-center gap-1"><GitBranch size={14} /> {run.repo}</span>}
              {run.branch && <span>{run.branch}</span>}
              {run.commit_sha && <span className="font-mono text-xs">{run.commit_sha.substring(0, 7)}</span>}
              <span className="flex items-center gap-1"><Clock size={14} /> {new Date(run.created_at).toLocaleString()}</span>
            </div>
          </div>
          {run.gate_result && (
            <div className={`flex items-center gap-2 px-4 py-2 rounded-xl ${gateConf.bg}`} data-testid="gate-result-badge">
              {gateConf.icon && <gateConf.icon size={20} weight="fill" className={gateConf.color} />}
              <span className={`text-lg font-bold ${gateConf.color}`}>Gate: {gateConf.label}</span>
            </div>
          )}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-5 gap-3 mb-6">
          {["critical", "high", "medium", "low", "info"].map(sev => (
            <div key={sev} className="iv-card p-3 text-center" data-testid={`run-sev-${sev}`}>
              <div className="text-xl font-bold" style={{ color: sev === "critical" ? "#dc2626" : sev === "high" ? "#ea580c" : sev === "medium" ? "#d97706" : sev === "low" ? "#2563eb" : "#6b7280" }}>
                {run.severity_counts?.[sev] || 0}
              </div>
              <div className="text-[10px] text-gray-500 capitalize">{sev}</div>
            </div>
          ))}
        </div>

        {/* Risk Score */}
        <div className="iv-card p-4 mb-6 flex items-center gap-4">
          <div className="text-3xl font-bold" style={{ color: run.risk_score > 30 ? "#dc2626" : run.risk_score > 10 ? "#d97706" : "#059669" }} data-testid="risk-score">
            {run.risk_score}
          </div>
          <div>
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">Risk Score</div>
            <div className="text-xs text-gray-500">{run.total_findings} findings from {run.tool_name || run.scan_type} scan</div>
          </div>
          {run.gate_violations?.length > 0 && (
            <div className="ml-auto">
              <div className="text-xs font-medium text-red-600 mb-1">Gate Violations:</div>
              {run.gate_violations.map((v, i) => (
                <div key={i} className="text-xs text-red-500">{v}</div>
              ))}
            </div>
          )}
        </div>

        {/* Findings List */}
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Findings ({findings.length})</h3>
        <div className="space-y-2" data-testid="findings-list">
          {findings.length === 0 ? (
            <div className="text-center py-8 text-gray-400">Loading findings...</div>
          ) : (
            findings.map(f => (
              <div key={f.id} className="iv-card p-4" data-testid={`finding-${f.id}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-1.5 py-0.5 text-[10px] font-semibold rounded ${SEV_COLORS[f.severity]}`}>{f.severity.toUpperCase()}</span>
                  <span className="text-xs text-gray-500 uppercase">{f.category}</span>
                  {f.cwe_id && <span className="text-xs font-mono text-[#2597B2]">{f.cwe_id}</span>}
                  {f.cve_id && <span className="text-xs font-mono text-red-500">{f.cve_id}</span>}
                </div>
                <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">{f.title}</h4>
                {f.description && <p className="text-xs text-gray-500 mt-1">{f.description}</p>}
                <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                  {f.file_path && <span>{f.file_path}{f.line_number ? `:${f.line_number}` : ""}</span>}
                  {f.package_name && <span>{f.package_name}@{f.package_version}</span>}
                  {f.tool && <span>via {f.tool}</span>}
                </div>
                {f.remediation && (
                  <div className="mt-2 text-xs text-emerald-600 bg-emerald-50 dark:bg-emerald-900/10 p-2 rounded">{f.remediation}</div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    );
  }

  // ─── DASHBOARD VIEW ──────────────
  return (
    <div data-testid="pipeline-dashboard">

      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">DevSecOps Pipeline</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">CI/CD compliance gate, scan results, and security findings</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setView("api-keys")} data-testid="manage-keys-btn">
            <Key size={15} className="mr-1.5" /> API Keys
          </Button>
          <Button variant="outline" size="sm" onClick={fetchData} data-testid="refresh-btn">
            <ArrowsClockwise size={15} className="mr-1.5" /> Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading pipeline data...</div>
      ) : (
        <>
          {/* Stats Overview */}
          {stats && (
            <div className="grid grid-cols-5 gap-4 mb-6">
              <div className="iv-card p-4" data-testid="stat-total-runs">
                <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.total_runs}</div>
                <div className="text-xs text-gray-500">Total Runs</div>
              </div>
              <div className="iv-card p-4" data-testid="stat-total-findings">
                <div className="text-2xl font-bold text-amber-600">{stats.total_findings}</div>
                <div className="text-xs text-gray-500">Total Findings</div>
              </div>
              <div className="iv-card p-4" data-testid="stat-pass-rate">
                <div className="text-2xl font-bold text-emerald-600">{stats.pass_rate}%</div>
                <div className="text-xs text-gray-500">Gate Pass Rate</div>
              </div>
              <div className="iv-card p-4" data-testid="stat-avg-risk">
                <div className="text-2xl font-bold" style={{ color: stats.average_risk_score > 30 ? "#dc2626" : stats.average_risk_score > 10 ? "#d97706" : "#059669" }}>
                  {stats.average_risk_score}
                </div>
                <div className="text-xs text-gray-500">Avg Risk Score</div>
              </div>
              <div className="iv-card p-4" data-testid="stat-gate-results">
                <div className="flex gap-2">
                  <span className="text-sm font-bold text-emerald-600">{stats.gate_results?.pass || 0}P</span>
                  <span className="text-sm font-bold text-amber-600">{stats.gate_results?.warn || 0}W</span>
                  <span className="text-sm font-bold text-red-600">{stats.gate_results?.fail || 0}F</span>
                </div>
                <div className="text-xs text-gray-500">Pass / Warn / Fail</div>
              </div>
            </div>
          )}

          {/* Pipeline Runs */}
          {runs.length === 0 ? (
            <div className="iv-card p-12 text-center" data-testid="empty-state">
              <GitBranch size={48} className="mx-auto text-gray-300 mb-4" />
              <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No Pipeline Runs Yet</h3>
              <p className="text-sm text-gray-500 mb-4">Configure your CI/CD pipeline to send scan results to IronVision</p>
              <Button variant="outline" onClick={() => setView("api-keys")} data-testid="setup-keys-btn">
                <Key size={16} className="mr-2" /> Set Up API Keys
              </Button>
            </div>
          ) : (
            <div className="space-y-2" data-testid="pipeline-runs-list">
              {runs.map(run => {
                const gateConf = GATE_CONFIG[run.gate_result] || {};
                const ScanIcon = SCAN_ICONS[run.scan_type] || Lightning;
                return (
                  <div key={run.id} className="iv-card p-4 flex items-center gap-4 hover:shadow-md transition-shadow cursor-pointer" onClick={() => openRunDetail(run)} data-testid={`run-row-${run.id}`}>
                    <div className="w-10 h-10 rounded-xl bg-[#2597B2]/10 flex items-center justify-center">
                      <ScanIcon size={20} className="text-[#2597B2]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{run.pipeline_name}</span>
                        <span className="text-xs text-gray-400 uppercase">{run.scan_type}</span>
                      </div>
                      <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500">
                        {run.repo && <span>{run.repo}</span>}
                        {run.branch && <span>{run.branch}</span>}
                        <span>{new Date(run.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <div className="text-sm font-bold" style={{ color: run.risk_score > 30 ? "#dc2626" : run.risk_score > 10 ? "#d97706" : "#059669" }}>
                          {run.risk_score}
                        </div>
                        <div className="text-[10px] text-gray-400">{run.total_findings} findings</div>
                      </div>
                      {run.gate_result ? (
                        <span className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${gateConf.bg} ${gateConf.color}`} data-testid={`gate-${run.id}`}>
                          {gateConf.icon && <gateConf.icon size={14} weight="fill" />} {gateConf.label}
                        </span>
                      ) : (
                        <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-gray-50 text-gray-500">Pending</span>
                      )}
                      <button onClick={e => { e.stopPropagation(); deleteRun(run.id); }} className="p-1.5 rounded-md hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors" data-testid={`delete-run-${run.id}`}>
                        <Trash size={14} />
                      </button>
                      <CaretRight size={14} className="text-gray-400" />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default DevSecOpsPipeline;
