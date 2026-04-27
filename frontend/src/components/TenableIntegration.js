import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  CaretLeft, ArrowsClockwise, ShieldCheck, Warning, CheckCircle,
  XCircle, Lightning, Bug, Key, Eye, EyeSlash, Plugs, CaretRight,
  Trash, Desktop, ChartBar, GitBranch, FileText, ListChecks, Clock
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const SEV_COLORS = {
  critical: "bg-red-600 text-white",
  high: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

const STATE_COLORS = {
  open: "text-red-600 bg-red-50",
  reopened: "text-orange-600 bg-orange-50",
  fixed: "text-emerald-600 bg-emerald-50",
};

const TenableIntegration = () => {
  const [tab, setTab] = useState("dashboard"); // dashboard | vulns | compliance | poam | settings
  const [settings, setSettings] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [findings, setFindings] = useState([]);
  const [poamEntries, setPoamEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generatingPoam, setGeneratingPoam] = useState(false);
  const [lastAssessResult, setLastAssessResult] = useState(null);
  const [lastPolicyResult, setLastPolicyResult] = useState(null);
  const [assetMap, setAssetMap] = useState({});

  // Settings form
  const [accessKey, setAccessKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/tenable/settings`);
      setSettings(res.data);
    } catch { /* ignore */ }
  }, []);

  const fetchDashboard = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/tenable/dashboard`);
      setDashboard(res.data);
    } catch { /* ignore */ }
  }, []);

  const fetchFindings = useCallback(async (type) => {
    try {
      const params = type ? `?finding_type=${type}` : "";
      const res = await axios.get(`${API}/tenable/findings${params}`);
      setFindings(res.data);
    } catch {
      toast.error("Failed to load findings");
    }
  }, []);

  const fetchPoam = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/tenable/poam`);
      setPoamEntries(res.data);
    } catch {
      toast.error("Failed to load POA&M");
    }
  }, []);

  const fetchAssetMap = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/assets`);
      const map = {};
      res.data.forEach(a => { if (a.hostname) map[a.hostname] = a.id; });
      setAssetMap(map);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchSettings(), fetchDashboard(), fetchAssetMap()]);
      setLoading(false);
    };
    init();
  }, [fetchSettings, fetchDashboard, fetchAssetMap]);

  useEffect(() => {
    if (tab === "vulns") fetchFindings("vulnerability");
    if (tab === "compliance") fetchFindings("compliance");
    if (tab === "poam") fetchPoam();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const autoAssess = async () => {
    setAssessing(true);
    try {
      const res = await axios.post(`${API}/tenable/auto-assess`);
      toast.success(res.data.message);
      setLastAssessResult(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Auto-assess failed");
    } finally {
      setAssessing(false);
    }
  };

  const generatePolicies = async () => {
    setGenerating(true);
    try {
      const res = await axios.post(`${API}/tenable/generate-policies`);
      toast.success(res.data.message);
      setLastPolicyResult(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Policy generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const generatePoam = async () => {
    setGeneratingPoam(true);
    try {
      const res = await axios.post(`${API}/tenable/generate-poam`);
      toast.success(res.data.message);
      if (tab === "poam") fetchPoam();
    } catch (err) {
      toast.error(err.response?.data?.detail || "POA&M generation failed");
    } finally {
      setGeneratingPoam(false);
    }
  };

  const updatePoamStatus = async (entryId, newStatus) => {
    try {
      await axios.put(`${API}/tenable/poam/${entryId}/status`, { status: newStatus });
      toast.success(`POA&M updated to ${newStatus}`);
      fetchPoam();
    } catch {
      toast.error("Failed to update");
    }
  };

  const saveSettings = async () => {
    if (!accessKey || !secretKey) return toast.error("Both keys required");
    setSaving(true);
    try {
      await axios.post(`${API}/tenable/settings`, { access_key: accessKey, secret_key: secretKey });
      toast.success("Tenable credentials saved");
      setAccessKey("");
      setSecretKey("");
      fetchSettings();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const removeSettings = async () => {
    if (!window.confirm("Remove Tenable credentials?")) return;
    try {
      await axios.delete(`${API}/tenable/settings`);
      toast.success("Credentials removed");
      setSettings({ configured: false });
    } catch {
      toast.error("Failed to remove");
    }
  };

  const runSync = async (mode = "auto") => {
    setSyncing(true);
    try {
      const res = await axios.post(`${API}/tenable/sync`, { mode });
      toast.success(res.data.message);
      await fetchDashboard();
      if (tab === "vulns") fetchFindings("vulnerability");
      if (tab === "compliance") fetchFindings("compliance");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  if (loading) return <div className="text-center py-16 text-gray-400"><ArrowsClockwise size={32} className="mx-auto animate-spin mb-3" />Loading Tenable data...</div>;

  const d = dashboard || {};
  const v = d.vulnerabilities || {};
  const c = d.compliance || {};

  return (
    <div data-testid="tenable-integration">

      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-[#00b388] rounded-lg flex items-center justify-center">
              <ShieldCheck size={22} className="text-white" weight="fill" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Tenable VM Integration</h2>
              <p className="text-sm text-gray-500 mt-0.5">Vulnerability and compliance data mapped to NIST 800-53 controls</p>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setTab("settings")} data-testid="settings-btn">
            <Key size={15} className="mr-1.5" /> Settings
          </Button>
          <Button onClick={() => runSync("auto")} disabled={syncing} className="bg-[#00b388] hover:bg-[#009973]" data-testid="sync-btn">
            {syncing ? <><ArrowsClockwise size={16} className="animate-spin mr-2" /> Syncing...</> : <><ArrowsClockwise size={16} className="mr-2" /> Sync Now</>}
          </Button>
        </div>
      </div>

      {/* Action Bar */}
      {d.total_findings > 0 && tab === "dashboard" && (
        <div className="flex gap-2 mb-6 flex-wrap" data-testid="action-bar">
          <Button onClick={autoAssess} disabled={assessing} variant="outline" size="sm" className="h-9 text-xs border-blue-200 text-blue-700 hover:bg-blue-50" data-testid="auto-assess-btn">
            {assessing ? <><ArrowsClockwise size={14} className="animate-spin mr-1.5" /> Assessing...</> : <><ShieldCheck size={14} className="mr-1.5" /> Auto-Assess NIST Controls</>}
          </Button>
          <Button onClick={generatePolicies} disabled={generating} variant="outline" size="sm" className="h-9 text-xs border-purple-200 text-purple-700 hover:bg-purple-50" data-testid="generate-policies-btn">
            {generating ? <><ArrowsClockwise size={14} className="animate-spin mr-1.5" /> Generating...</> : <><FileText size={14} className="mr-1.5" /> Generate Remediation Policies</>}
          </Button>
          <Button onClick={generatePoam} disabled={generatingPoam} variant="outline" size="sm" className="h-9 text-xs border-amber-200 text-amber-700 hover:bg-amber-50" data-testid="generate-poam-btn">
            {generatingPoam ? <><ArrowsClockwise size={14} className="animate-spin mr-1.5" /> Creating...</> : <><ListChecks size={14} className="mr-1.5" /> Generate POA&M</>}
          </Button>
        </div>
      )}

      {/* Assessment Result */}
      {lastAssessResult && tab === "dashboard" && (
        <div className="iv-card p-4 mb-4 border-l-4 border-blue-500 bg-blue-50/50 dark:bg-blue-900/10" data-testid="assess-result">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck size={18} weight="fill" className="text-blue-600" />
            <span className="text-sm font-semibold text-blue-700">{lastAssessResult.message}</span>
          </div>
          <div className="flex gap-2 flex-wrap">
            {lastAssessResult.assessments?.slice(0, 8).map(a => (
              <span key={a.control_id} className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${a.status === "compliant" ? "bg-emerald-100 text-emerald-700" : a.status === "non_compliant" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>
                {a.control_id}: {a.status.replace("_", " ")}
              </span>
            ))}
            {lastAssessResult.assessments?.length > 8 && <span className="text-xs text-gray-400">+{lastAssessResult.assessments.length - 8} more</span>}
          </div>
        </div>
      )}

      {/* Policy Result */}
      {lastPolicyResult && lastPolicyResult.policies?.length > 0 && tab === "dashboard" && (
        <div className="iv-card p-4 mb-4 border-l-4 border-purple-500 bg-purple-50/50 dark:bg-purple-900/10" data-testid="policy-result">
          <div className="flex items-center gap-2 mb-2">
            <FileText size={18} weight="fill" className="text-purple-600" />
            <span className="text-sm font-semibold text-purple-700">{lastPolicyResult.message}</span>
          </div>
          <div className="space-y-1">
            {lastPolicyResult.policies.map(p => (
              <div key={p.id} className="text-xs text-gray-600 flex items-center gap-2">
                <CheckCircle size={12} className="text-purple-500" /> {p.title} ({p.sections_count} sections)
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 p-1 bg-gray-100 dark:bg-gray-800 rounded-lg w-fit" data-testid="tenable-tabs">
        {[
          { key: "dashboard", label: "Dashboard", icon: ChartBar },
          { key: "vulns", label: "Vulnerabilities", icon: Bug },
          { key: "compliance", label: "Compliance Checks", icon: ShieldCheck },
          { key: "poam", label: "POA&M", icon: ListChecks },
          { key: "settings", label: "Settings", icon: Key },
        ].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md transition-colors ${tab === t.key ? "bg-white dark:bg-gray-900 text-[#00b388] shadow-sm" : "text-gray-500 hover:text-gray-700"}`} data-testid={`tab-${t.key}`}>
            <t.icon size={15} weight={tab === t.key ? "fill" : "regular"} /> {t.label}
          </button>
        ))}
      </div>

      {/* Dashboard Tab */}
      {tab === "dashboard" && (
        <div data-testid="tenable-dashboard">
          {d.total_findings === 0 ? (
            <div className="iv-card p-12 text-center">
              <Plugs size={48} className="mx-auto text-gray-300 mb-4" />
              <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No Tenable Data Yet</h3>
              <p className="text-sm text-gray-500 mb-4">Click "Sync Now" to pull vulnerability and compliance data{settings?.configured ? " from Tenable.io" : " (demo mode)"}</p>
              <Button onClick={() => runSync("demo")} disabled={syncing} className="bg-[#00b388] hover:bg-[#009973]" data-testid="demo-sync-btn">
                <ArrowsClockwise size={16} className="mr-2" /> Load Demo Data
              </Button>
            </div>
          ) : (
            <>
              {/* Stats Row */}
              <div className="grid grid-cols-5 gap-3 mb-6">
                <div className="iv-card p-4" data-testid="stat-total"><div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{d.total_findings}</div><div className="text-xs text-gray-500">Total Findings</div></div>
                <div className="iv-card p-4" data-testid="stat-vulns"><div className="text-2xl font-bold text-red-600">{v.open_critical || 0}</div><div className="text-xs text-gray-500">Open Critical Vulns</div></div>
                <div className="iv-card p-4" data-testid="stat-compliance"><div className="text-2xl font-bold text-emerald-600">{c.pass_rate || 0}%</div><div className="text-xs text-gray-500">Compliance Pass Rate</div></div>
                <div className="iv-card p-4" data-testid="stat-controls"><div className="text-2xl font-bold text-[#00b388]">{d.controls_impacted || 0}</div><div className="text-xs text-gray-500">Controls Impacted</div></div>
                <div className="iv-card p-4" data-testid="stat-assets"><div className="text-2xl font-bold text-purple-600">{d.assets_scanned || 0}</div><div className="text-xs text-gray-500">Assets Scanned</div></div>
              </div>

              <div className="grid grid-cols-2 gap-6 mb-6">
                {/* Vulnerability Breakdown */}
                <div className="iv-card p-5">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Vulnerabilities</h3>
                  <div className="space-y-3">
                    {["critical", "high", "medium"].map(sev => (
                      <div key={sev} className="flex items-center gap-3">
                        <span className={`px-2 py-0.5 text-xs font-semibold rounded ${SEV_COLORS[sev]} w-16 text-center`}>{sev.toUpperCase()}</span>
                        <div className="flex-1 h-5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden relative">
                          <div className="h-full rounded-full transition-all" style={{ width: `${(v.by_severity?.[sev] || 0) / Math.max(v.total || 1, 1) * 100}%`, backgroundColor: sev === "critical" ? "#dc2626" : sev === "high" ? "#ea580c" : "#d97706" }} />
                          <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold">{v.by_severity?.[sev] || 0}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="flex gap-4 mt-4 pt-3 border-t border-gray-100 dark:border-gray-800 text-xs text-gray-500">
                    <span className="text-red-500 font-medium">{v.by_state?.open || 0} Open</span>
                    <span className="text-orange-500 font-medium">{v.by_state?.reopened || 0} Reopened</span>
                    <span className="text-emerald-500 font-medium">{v.by_state?.fixed || 0} Fixed</span>
                  </div>
                </div>

                {/* Compliance Breakdown */}
                <div className="iv-card p-5">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Compliance Checks</h3>
                  <div className="flex items-center gap-6">
                    <div className="relative w-24 h-24">
                      <svg viewBox="0 0 100 100" className="w-full h-full">
                        <circle cx="50" cy="50" r="42" fill="none" stroke="#e5e7eb" strokeWidth="8" />
                        <circle cx="50" cy="50" r="42" fill="none" stroke="#059669" strokeWidth="8" strokeLinecap="round" strokeDasharray={`${(c.pass_rate || 0) / 100 * 264} 264`} transform="rotate(-90 50 50)" />
                      </svg>
                      <div className="absolute inset-0 flex items-center justify-center text-lg font-bold text-emerald-600">{c.pass_rate || 0}%</div>
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-2"><CheckCircle size={16} weight="fill" className="text-emerald-500" /> <span className="text-sm font-medium">{c.passed || 0} Passed</span></div>
                      <div className="flex items-center gap-2"><XCircle size={16} weight="fill" className="text-red-500" /> <span className="text-sm font-medium">{c.failed || 0} Failed</span></div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Control Impact */}
              {d.control_impact && Object.keys(d.control_impact).length > 0 && (
                <div className="iv-card p-5 mb-6">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">NIST Control Impact (Top Affected)</h3>
                  <div className="grid grid-cols-4 gap-2">
                    {Object.entries(d.control_impact).slice(0, 12).map(([ctrl, counts]) => (
                      <div key={ctrl} className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
                        <span className="text-xs font-mono font-bold text-[#00b388]">{ctrl}</span>
                        <span className="ml-auto text-[10px]">
                          {counts.non_compliant > 0 && <span className="text-red-500 font-medium mr-1">{counts.non_compliant}F</span>}
                          {counts.compliant > 0 && <span className="text-emerald-500 font-medium">{counts.compliant}P</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Assets */}
              {d.assets?.length > 0 && (
                <div className="iv-card p-5">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Scanned Assets ({d.assets_scanned})</h3>
                  <div className="flex gap-2 flex-wrap">
                    {d.assets.map(a => (
                      <span key={a} className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg text-xs font-medium text-gray-700 dark:text-gray-300">
                        <Desktop size={14} className="text-gray-400" /> {a}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Vulns Tab */}
      {tab === "vulns" && (
        <div className="space-y-2" data-testid="vulns-list">
          {findings.length === 0 ? (
            <div className="text-center py-12 text-gray-400">No vulnerabilities found. Run a sync first.</div>
          ) : findings.map(f => (
            <div key={f.id} className="iv-card p-4" data-testid={`vuln-${f.id}`}>
              <div className="flex items-center gap-3">
                <span className={`px-1.5 py-0.5 text-[10px] font-semibold rounded ${SEV_COLORS[f.severity] || SEV_COLORS.medium}`}>{(f.severity || "").toUpperCase()}</span>
                <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded-full ${STATE_COLORS[f.state] || ""}`}>{(f.state || "").toUpperCase()}</span>
                <span className="text-xs text-gray-400 font-mono">Plugin #{f.tenable_plugin_id}</span>
              </div>
              <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mt-1">{f.title}</h4>
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                {assetMap[f.asset_hostname] ? (
                  <Link to={`/assets/${assetMap[f.asset_hostname]}`} className="flex items-center gap-1 text-[#1B839F] hover:underline font-medium" data-testid={`vuln-asset-link-${f.id}`}>
                    <Desktop size={12} /> {f.asset_hostname}
                  </Link>
                ) : (
                  <span className="flex items-center gap-1"><Desktop size={12} /> {f.asset_hostname}</span>
                )}
                {f.cves?.length > 0 && <span className="text-red-500 font-mono">{f.cves.join(", ")}</span>}
                <span className={f.compliance_status === "compliant" ? "text-emerald-600" : "text-red-600"}>{f.compliance_status}</span>
              </div>
              <div className="flex gap-1 mt-2 flex-wrap">
                {f.control_ids?.map(c => (
                  <span key={c} className="text-[9px] px-1.5 py-0.5 bg-[#00b388]/10 text-[#00b388] rounded font-medium">{c}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Compliance Tab */}
      {tab === "compliance" && (
        <div className="space-y-2" data-testid="compliance-list">
          {findings.length === 0 ? (
            <div className="text-center py-12 text-gray-400">No compliance checks found. Run a sync first.</div>
          ) : findings.map(f => (
            <div key={f.id} className="iv-card p-4" data-testid={`check-${f.id}`}>
              <div className="flex items-center gap-2">
                {f.status === "PASSED" ? <CheckCircle size={18} weight="fill" className="text-emerald-500" /> : <XCircle size={18} weight="fill" className="text-red-500" />}
                <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex-1">{f.title}</h4>
                <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${f.status === "PASSED" ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-600"}`}>{f.status}</span>
              </div>
              <div className="flex gap-6 mt-2 text-xs">
                <span className="text-gray-500">Expected: <span className="font-medium text-gray-700 dark:text-gray-300">{f.expected_value}</span></span>
                <span className="text-gray-500">Actual: <span className={`font-medium ${f.status === "PASSED" ? "text-emerald-600" : "text-red-600"}`}>{f.actual_value}</span></span>
                {assetMap[f.asset_hostname] ? (
                  <Link to={`/assets/${assetMap[f.asset_hostname]}`} className="flex items-center gap-1 text-[#1B839F] hover:underline font-medium" data-testid={`comp-asset-link-${f.id}`}>
                    <Desktop size={12} /> {f.asset_hostname}
                  </Link>
                ) : (
                  <span className="text-gray-500 flex items-center gap-1"><Desktop size={12} /> {f.asset_hostname}</span>
                )}
              </div>
              <div className="flex gap-1 mt-2 flex-wrap">
                {f.control_ids?.map(c => (
                  <span key={c} className="text-[9px] px-1.5 py-0.5 bg-[#00b388]/10 text-[#00b388] rounded font-medium">{c}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}


      {/* POA&M Tab */}
      {tab === "poam" && (
        <div data-testid="poam-tab">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Plan of Action & Milestones</h3>
            <Button onClick={generatePoam} disabled={generatingPoam} variant="outline" size="sm" data-testid="poam-generate-btn">
              {generatingPoam ? <ArrowsClockwise size={14} className="animate-spin mr-1.5" /> : <ListChecks size={14} className="mr-1.5" />}
              Generate POA&M
            </Button>
          </div>
          {poamEntries.length === 0 ? (
            <div className="iv-card p-12 text-center">
              <ListChecks size={48} className="mx-auto text-gray-300 mb-4" />
              <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No POA&M Entries</h3>
              <p className="text-sm text-gray-500 mb-4">Click "Generate POA&M" to create entries from non-compliant Tenable findings</p>
            </div>
          ) : (
            <>
              {/* POA&M Stats */}
              <div className="grid grid-cols-4 gap-3 mb-4">
                <div className="iv-card p-3 text-center"><div className="text-xl font-bold text-gray-900 dark:text-gray-100">{poamEntries.length}</div><div className="text-[10px] text-gray-500">Total</div></div>
                <div className="iv-card p-3 text-center"><div className="text-xl font-bold text-red-600">{poamEntries.filter(e => e.status === "open").length}</div><div className="text-[10px] text-gray-500">Open</div></div>
                <div className="iv-card p-3 text-center"><div className="text-xl font-bold text-amber-600">{poamEntries.filter(e => e.status === "in_progress").length}</div><div className="text-[10px] text-gray-500">In Progress</div></div>
                <div className="iv-card p-3 text-center"><div className="text-xl font-bold text-emerald-600">{poamEntries.filter(e => e.status === "completed").length}</div><div className="text-[10px] text-gray-500">Completed</div></div>
              </div>
              <div className="space-y-2">
                {poamEntries.map(entry => (
                  <div key={entry.id} className="iv-card p-4" data-testid={`poam-${entry.id}`}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono font-bold text-[#00b388]">{entry.poam_id}</span>
                      <span className={`px-1.5 py-0.5 text-[10px] font-semibold rounded ${SEV_COLORS[entry.severity] || "bg-gray-100 text-gray-600"}`}>{(entry.severity || "").toUpperCase()}</span>
                      <span className="text-[10px] font-bold text-gray-500">{entry.priority}</span>
                      <span className={`ml-auto px-2 py-0.5 text-[10px] font-medium rounded-full ${
                        entry.status === "completed" ? "bg-emerald-50 text-emerald-600" :
                        entry.status === "in_progress" ? "bg-amber-50 text-amber-600" :
                        entry.status === "delayed" ? "bg-red-50 text-red-600" :
                        "bg-gray-50 text-gray-600"
                      }`}>{entry.status?.replace("_", " ").toUpperCase()}</span>
                    </div>
                    <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">{entry.title}</h4>
                    <p className="text-xs text-gray-500 mt-1">{entry.description}</p>
                    <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                      <span className="flex items-center gap-1"><Desktop size={12} /> {entry.asset}</span>
                      <span className="flex items-center gap-1"><Clock size={12} /> Due: {new Date(entry.scheduled_completion).toLocaleDateString()}</span>
                      <span>{entry.milestone_days}d timeline</span>
                      {entry.cves?.length > 0 && <span className="text-red-500 font-mono">{entry.cves.join(", ")}</span>}
                    </div>
                    <div className="flex gap-1 mt-2 flex-wrap">
                      {entry.control_ids?.map(c => (
                        <span key={c} className="text-[9px] px-1.5 py-0.5 bg-[#00b388]/10 text-[#00b388] rounded font-medium">{c}</span>
                      ))}
                    </div>
                    <div className="mt-2 text-xs text-gray-500 italic">{entry.remediation_plan}</div>
                    {entry.status !== "completed" && (
                      <div className="flex gap-2 mt-3 pt-2 border-t border-gray-100 dark:border-gray-800">
                        {entry.status === "open" && (
                          <button onClick={() => updatePoamStatus(entry.id, "in_progress")} className="text-xs text-amber-600 font-medium hover:underline" data-testid={`poam-progress-${entry.id}`}>Mark In Progress</button>
                        )}
                        <button onClick={() => updatePoamStatus(entry.id, "completed")} className="text-xs text-emerald-600 font-medium hover:underline" data-testid={`poam-complete-${entry.id}`}>Mark Completed</button>
                        {entry.status !== "delayed" && (
                          <button onClick={() => updatePoamStatus(entry.id, "delayed")} className="text-xs text-red-500 font-medium hover:underline ml-auto">Mark Delayed</button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Settings Tab */}
      {tab === "settings" && (
        <div className="max-w-xl" data-testid="tenable-settings">
          <div className="iv-card p-6 mb-6">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Tenable.io API Credentials</h3>
            {settings?.configured && (
              <div className="mb-4 p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg flex items-center gap-2">
                <CheckCircle size={16} weight="fill" className="text-emerald-500" />
                <span className="text-sm text-emerald-700">Connected — Key: {settings.access_key_masked}</span>
                <button onClick={removeSettings} className="ml-auto text-xs text-red-500 hover:text-red-600 font-medium">Disconnect</button>
              </div>
            )}
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block">Access Key</label>
                <Input value={accessKey} onChange={e => setAccessKey(e.target.value)} placeholder="Enter Tenable access key" data-testid="access-key-input" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block">Secret Key</label>
                <div className="relative">
                  <Input type={showSecret ? "text" : "password"} value={secretKey} onChange={e => setSecretKey(e.target.value)} placeholder="Enter Tenable secret key" data-testid="secret-key-input" />
                  <button onClick={() => setShowSecret(!showSecret)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                    {showSecret ? <EyeSlash size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
              <Button onClick={saveSettings} disabled={saving} className="w-full bg-[#00b388] hover:bg-[#009973]" data-testid="save-settings-btn">
                {saving ? "Saving..." : "Save Credentials"}
              </Button>
            </div>
          </div>

          <div className="iv-card p-5">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Demo Mode</h3>
            <p className="text-xs text-gray-500 mb-3">Load simulated Tenable data (10 vulnerabilities + 12 compliance checks) mapped to NIST controls. No API keys required.</p>
            <Button variant="outline" onClick={() => runSync("demo")} disabled={syncing} data-testid="demo-sync-btn">
              <ArrowsClockwise size={14} className="mr-1.5" /> Load Demo Data
            </Button>
          </div>

          {/* Sync History */}
          {d.sync_history?.length > 0 && (
            <div className="iv-card p-5 mt-6">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Sync History</h3>
              <div className="space-y-2">
                {d.sync_history.map(run => (
                  <div key={run.id} className="flex items-center gap-3 text-xs text-gray-500 py-2 border-b border-gray-100 dark:border-gray-800 last:border-0">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${run.mode === "live" ? "bg-emerald-50 text-emerald-600" : "bg-gray-100 text-gray-600"}`}>{run.mode}</span>
                    <span>{run.vulns_processed} vulns, {run.compliance_processed} checks</span>
                    <span className="ml-auto">{new Date(run.created_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TenableIntegration;
