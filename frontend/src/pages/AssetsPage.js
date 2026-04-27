import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Desktop, MagnifyingGlass, Plus, Warning, ShieldCheck,
  Cube, Lightning, Bug, ArrowsClockwise
} from "@phosphor-icons/react";
import Layout from "@/components/Layout";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const CRITICALITY_STYLES = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high: "bg-orange-100 text-orange-700 border-orange-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

const ENV_STYLES = {
  production: "bg-blue-50 text-blue-700",
  staging: "bg-violet-50 text-violet-700",
  development: "bg-slate-100 text-slate-700",
  test: "bg-slate-100 text-slate-700",
  dr: "bg-pink-50 text-pink-700",
  unknown: "bg-gray-100 text-gray-600",
};

export default function AssetsPage() {
  const [assets, setAssets] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filterCrit, setFilterCrit] = useState("");
  const [filterEnv, setFilterEnv] = useState("");
  const [filterVulns, setFilterVulns] = useState(""); // "" | "true" | "false"
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const fetchAssets = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterCrit) params.set("criticality", filterCrit);
      if (filterEnv) params.set("environment", filterEnv);
      if (filterVulns) params.set("has_open_vulns", filterVulns);
      if (search) params.set("search", search);
      const [a, s] = await Promise.all([
        axios.get(`${API}/assets?${params}`),
        axios.get(`${API}/assets/stats`),
      ]);
      setAssets(a.data);
      setStats(s.data);
    } catch (e) {
      toast.error("Failed to load assets");
    } finally {
      setLoading(false);
    }
  }, [filterCrit, filterEnv, filterVulns, search]);

  useEffect(() => { fetchAssets(); }, [fetchAssets]);

  const backfill = async () => {
    try {
      const r = await axios.post(`${API}/assets/backfill-from-tenable`);
      toast.success(r.data.message);
      fetchAssets();
    } catch {
      toast.error("Backfill failed");
    }
  };

  return (
    <Layout>
      <div className="space-y-6" data-testid="assets-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Asset Inventory</h1>
            <p className="text-sm text-gray-500 mt-1">Hardware, software, and vulnerability tracking per asset</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={backfill} data-testid="backfill-assets-btn">
              <ArrowsClockwise size={16} className="mr-1.5" /> Backfill from Tenable
            </Button>
            <Button onClick={() => setShowCreate(true)} className="bg-[#1B839F] hover:bg-[#156a82]" data-testid="create-asset-btn">
              <Plus size={16} className="mr-1.5" /> Add Asset
            </Button>
          </div>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4" data-testid="asset-stats">
            <StatCard icon={Cube} label="Total Assets" value={stats.total_assets} color="#1B839F" />
            <StatCard icon={Bug} label="With Open Vulns" value={stats.vulnerable_assets} color="#dc2626" />
            <StatCard icon={Warning} label="Critical Assets" value={stats.by_criticality.critical} color="#dc2626" />
            <StatCard icon={ShieldCheck} label="High Criticality" value={stats.by_criticality.high} color="#ea580c" />
            <StatCard icon={Lightning} label="Production" value={stats.by_environment.production || 0} color="#2563eb" />
          </div>
        )}

        {/* Filters */}
        <div className="iv-card p-4 flex flex-wrap gap-3 items-center" data-testid="asset-filters">
          <div className="relative flex-1 min-w-[220px]">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input
              placeholder="Search hostname, FQDN, owner, tag..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
              data-testid="asset-search-input"
            />
          </div>
          <Select value={filterCrit || "all"} onValueChange={(v) => setFilterCrit(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[160px]" data-testid="filter-criticality"><SelectValue placeholder="Criticality" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Criticality</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="low">Low</SelectItem>
            </SelectContent>
          </Select>
          <Select value={filterEnv || "all"} onValueChange={(v) => setFilterEnv(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[160px]" data-testid="filter-environment"><SelectValue placeholder="Environment" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Environments</SelectItem>
              <SelectItem value="production">Production</SelectItem>
              <SelectItem value="staging">Staging</SelectItem>
              <SelectItem value="development">Development</SelectItem>
              <SelectItem value="test">Test</SelectItem>
              <SelectItem value="dr">DR</SelectItem>
            </SelectContent>
          </Select>
          <Select value={filterVulns || "all"} onValueChange={(v) => setFilterVulns(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[180px]" data-testid="filter-vulns"><SelectValue placeholder="Vulnerability" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Assets</SelectItem>
              <SelectItem value="true">Has Open Vulns</SelectItem>
              <SelectItem value="false">No Open Vulns</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Asset Table */}
        <div className="iv-card overflow-hidden" data-testid="asset-table">
          {loading ? (
            <div className="p-12 text-center text-gray-400">Loading assets...</div>
          ) : assets.length === 0 ? (
            <div className="p-12 text-center text-gray-400">
              No assets found. Run a Tenable sync or click "Add Asset" to create one manually.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                <tr className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-3">Hostname</th>
                  <th className="px-4 py-3">OS / System</th>
                  <th className="px-4 py-3">Environment</th>
                  <th className="px-4 py-3">Criticality</th>
                  <th className="px-4 py-3">Software</th>
                  <th className="px-4 py-3">Open Vulns</th>
                  <th className="px-4 py-3">Owner</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
                {assets.map(a => (
                  <tr key={a.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors" data-testid={`asset-row-${a.id}`}>
                    <td className="px-4 py-3">
                      <Link to={`/assets/${a.id}`} className="flex items-center gap-2 font-medium text-[#1B839F] hover:underline">
                        <Desktop size={16} />
                        {a.hostname}
                      </Link>
                      {a.fqdn && <p className="text-xs text-gray-400 ml-6">{a.fqdn}</p>}
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-gray-900 dark:text-gray-100">{a.operating_system || "—"}</p>
                      <p className="text-xs text-gray-400 capitalize">{a.system_type || "server"}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ENV_STYLES[a.environment] || ENV_STYLES.unknown}`}>
                        {a.environment}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full border text-xs font-semibold capitalize ${CRITICALITY_STYLES[a.criticality] || CRITICALITY_STYLES.medium}`}>
                        {a.criticality}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{a.software_count || 0} apps</td>
                    <td className="px-4 py-3">
                      {a.vuln_summary?.total_open > 0 ? (
                        <div className="flex items-center gap-1.5">
                          {a.vuln_summary.open_critical > 0 && (
                            <span className="px-1.5 py-0.5 rounded bg-red-600 text-white text-[10px] font-bold">
                              {a.vuln_summary.open_critical}C
                            </span>
                          )}
                          {a.vuln_summary.open_high > 0 && (
                            <span className="px-1.5 py-0.5 rounded bg-orange-500 text-white text-[10px] font-bold">
                              {a.vuln_summary.open_high}H
                            </span>
                          )}
                          {a.vuln_summary.open_medium > 0 && (
                            <span className="px-1.5 py-0.5 rounded bg-amber-400 text-white text-[10px] font-bold">
                              {a.vuln_summary.open_medium}M
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-emerald-600 text-xs">Clean</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{a.owner || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showCreate && <CreateAssetModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); fetchAssets(); }} />}
    </Layout>
  );
}

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <div className="iv-card p-4" data-testid={`stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg" style={{ background: `${color}15` }}>
          <Icon size={20} weight="duotone" style={{ color }} />
        </div>
        <div>
          <p className="text-xs text-gray-500">{label}</p>
          <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{value}</p>
        </div>
      </div>
    </div>
  );
}

function CreateAssetModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    hostname: "",
    fqdn: "",
    ip_addresses: "",
    operating_system: "",
    system_type: "server",
    criticality: "medium",
    environment: "production",
    owner: "",
  });
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!form.hostname.trim()) return toast.error("Hostname is required");
    setSaving(true);
    try {
      await axios.post(`${API}/assets`, {
        hostname: form.hostname.trim(),
        fqdn: form.fqdn.trim() || null,
        ip_addresses: form.ip_addresses.split(",").map(s => s.trim()).filter(Boolean),
        operating_system: form.operating_system.trim() || null,
        system_type: form.system_type,
        criticality: form.criticality,
        environment: form.environment,
        owner: form.owner.trim() || null,
      });
      toast.success("Asset created");
      onCreated();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to create asset");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="create-asset-modal">
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl w-full max-w-lg p-6 space-y-4">
        <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">Add Asset</h3>
        <div className="grid grid-cols-2 gap-3">
          <LabeledInput label="Hostname *" value={form.hostname} onChange={v => setForm({ ...form, hostname: v })} testid="form-hostname" />
          <LabeledInput label="FQDN" value={form.fqdn} onChange={v => setForm({ ...form, fqdn: v })} testid="form-fqdn" />
          <LabeledInput label="IP Addresses (comma-separated)" value={form.ip_addresses} onChange={v => setForm({ ...form, ip_addresses: v })} testid="form-ips" />
          <LabeledInput label="Operating System" value={form.operating_system} onChange={v => setForm({ ...form, operating_system: v })} testid="form-os" />
          <LabeledInput label="Owner" value={form.owner} onChange={v => setForm({ ...form, owner: v })} testid="form-owner" />
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">System Type</label>
            <select value={form.system_type} onChange={e => setForm({ ...form, system_type: e.target.value })} className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm" data-testid="form-system-type">
              <option value="server">Server</option>
              <option value="workstation">Workstation</option>
              <option value="container">Container</option>
              <option value="network-device">Network Device</option>
              <option value="mobile">Mobile</option>
              <option value="iot">IoT</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Criticality</label>
            <select value={form.criticality} onChange={e => setForm({ ...form, criticality: e.target.value })} className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm" data-testid="form-criticality">
              <option value="critical">Critical (Crown Jewel)</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Environment</label>
            <select value={form.environment} onChange={e => setForm({ ...form, environment: e.target.value })} className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm" data-testid="form-environment">
              <option value="production">Production</option>
              <option value="staging">Staging</option>
              <option value="development">Development</option>
              <option value="test">Test</option>
              <option value="dr">DR</option>
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose} data-testid="cancel-create-asset">Cancel</Button>
          <Button onClick={submit} disabled={saving} className="bg-[#1B839F] hover:bg-[#156a82]" data-testid="submit-create-asset">
            {saving ? "Saving..." : "Create Asset"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function LabeledInput({ label, value, onChange, testid }) {
  return (
    <div>
      <label className="text-xs font-semibold text-gray-600 mb-1 block">{label}</label>
      <Input value={value} onChange={e => onChange(e.target.value)} data-testid={testid} />
    </div>
  );
}
