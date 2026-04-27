import React, { useState, useEffect, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  CaretLeft, Desktop, Cube, ShieldCheck, Bug, Warning, CheckCircle,
  XCircle, GitBranch, Trash, FloppyDisk, Pencil, Tag, User, Calendar
} from "@phosphor-icons/react";
import Layout from "@/components/Layout";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const SEV_COLORS = {
  critical: "bg-red-600 text-white",
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
};

const STATE_COLORS = {
  open: "text-red-600 bg-red-50",
  reopened: "text-orange-600 bg-orange-50",
  fixed: "text-emerald-600 bg-emerald-50",
};

const CRITICALITY_STYLES = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high: "bg-orange-100 text-orange-700 border-orange-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

export default function AssetDetailPage() {
  const { assetId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);

  const fetchAsset = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/assets/${assetId}`);
      setData(r.data);
      setForm({
        criticality: r.data.asset.criticality,
        environment: r.data.asset.environment,
        owner: r.data.asset.owner || "",
        tags: (r.data.asset.tags || []).join(", "),
        notes: r.data.asset.notes || "",
      });
    } catch {
      toast.error("Asset not found");
      navigate("/assets");
    } finally {
      setLoading(false);
    }
  }, [assetId, navigate]);

  useEffect(() => { fetchAsset(); }, [fetchAsset]);

  const save = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/assets/${assetId}`, {
        criticality: form.criticality,
        environment: form.environment,
        owner: form.owner,
        tags: form.tags.split(",").map(t => t.trim()).filter(Boolean),
        notes: form.notes,
      });
      toast.success("Asset updated");
      setEditing(false);
      fetchAsset();
    } catch {
      toast.error("Update failed");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Delete this asset? Vulnerability findings will remain but un-linked.")) return;
    try {
      await axios.delete(`${API}/assets/${assetId}`);
      toast.success("Asset deleted");
      navigate("/assets");
    } catch {
      toast.error("Delete failed");
    }
  };

  if (loading) return <Layout><div className="p-12 text-center text-gray-400">Loading...</div></Layout>;
  if (!data) return null;

  const a = data.asset;
  const summary = data.vulnerabilities.summary;
  const totalOpen = summary.open_critical + summary.open_high + summary.open_medium;

  return (
    <Layout>
      <div className="space-y-6" data-testid="asset-detail-page">
        {/* Back nav */}
        <Link to="/assets" className="inline-flex items-center text-sm text-gray-500 hover:text-[#1B839F]" data-testid="back-to-assets">
          <CaretLeft size={16} /> Back to Asset Inventory
        </Link>

        {/* Header */}
        <div className="iv-card p-6 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Desktop size={28} weight="duotone" className="text-[#1B839F]" />
              <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100" data-testid="asset-hostname">{a.hostname}</h1>
              <span className={`px-2 py-0.5 rounded-full border text-xs font-semibold capitalize ${CRITICALITY_STYLES[a.criticality]}`} data-testid="asset-criticality-badge">
                {a.criticality}
              </span>
            </div>
            <p className="text-sm text-gray-500">{a.fqdn || "—"}</p>
            <div className="flex flex-wrap gap-4 mt-3 text-xs text-gray-500">
              <span><Calendar size={12} className="inline mr-1" />First seen: {a.first_seen?.slice(0, 10)}</span>
              <span><Calendar size={12} className="inline mr-1" />Last seen: {a.last_seen?.slice(0, 10)}</span>
              {(a.sources || []).length > 0 && <span>Sources: {(a.sources || []).join(", ")}</span>}
            </div>
          </div>
          <div className="flex gap-2">
            {!editing ? (
              <>
                <Button variant="outline" onClick={() => setEditing(true)} data-testid="edit-asset-btn">
                  <Pencil size={14} className="mr-1.5" /> Edit
                </Button>
                <Button variant="outline" onClick={remove} className="text-red-600 hover:bg-red-50" data-testid="delete-asset-btn">
                  <Trash size={14} className="mr-1.5" /> Delete
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={() => setEditing(false)} data-testid="cancel-edit-btn">Cancel</Button>
                <Button onClick={save} disabled={saving} className="bg-[#1B839F] hover:bg-[#156a82]" data-testid="save-asset-btn">
                  <FloppyDisk size={14} className="mr-1.5" /> {saving ? "Saving..." : "Save"}
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Vuln Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SummaryCard label="Open Critical" value={summary.open_critical} color="#dc2626" icon={Warning} />
          <SummaryCard label="Open High" value={summary.open_high} color="#ea580c" icon={Bug} />
          <SummaryCard label="Open Medium" value={summary.open_medium} color="#d97706" icon={Bug} />
          <SummaryCard label="Fixed (Verified)" value={summary.fixed_total} color="#059669" icon={CheckCircle} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Hardware + Software */}
          <div className="lg:col-span-1 space-y-4">
            {/* Hardware */}
            <div className="iv-card p-5" data-testid="hardware-section">
              <h3 className="font-bold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                <Cube size={18} weight="duotone" className="text-[#1B839F]" /> Hardware
              </h3>
              <dl className="space-y-2 text-sm">
                <Row label="OS" value={a.operating_system} />
                <Row label="OS Version" value={a.os_version} />
                <Row label="System Type" value={a.system_type} />
                <Row label="IP Addresses" value={(a.ip_addresses || []).join(", ")} />
                <Row label="MAC" value={(a.mac_addresses || []).join(", ")} />
                <Row label="Open Ports" value={(a.open_ports || []).join(", ")} />
              </dl>
            </div>

            {/* Software */}
            <div className="iv-card p-5" data-testid="software-section">
              <h3 className="font-bold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                <GitBranch size={18} weight="duotone" className="text-[#1B839F]" /> Installed Software ({(a.installed_software || []).length})
              </h3>
              {(a.installed_software || []).length === 0 ? (
                <p className="text-sm text-gray-400">No software inventory captured yet.</p>
              ) : (
                <ul className="space-y-1.5 text-sm">
                  {a.installed_software.map((s, i) => (
                    <li key={i} className="flex justify-between items-center py-1 border-b border-gray-100 last:border-b-0" data-testid={`software-${i}`}>
                      <span className="text-gray-900 dark:text-gray-100">{s.name}</span>
                      <span className="text-xs font-mono text-gray-500">{s.version}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Metadata (editable) */}
            <div className="iv-card p-5" data-testid="metadata-section">
              <h3 className="font-bold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                <Tag size={18} weight="duotone" className="text-[#1B839F]" /> Metadata
              </h3>
              {!editing ? (
                <dl className="space-y-2 text-sm">
                  <Row label="Criticality" value={<span className="capitalize">{a.criticality}</span>} />
                  <Row label="Environment" value={<span className="capitalize">{a.environment}</span>} />
                  <Row label="Owner" value={a.owner || "—"} />
                  <Row label="Tags" value={(a.tags || []).length > 0 ? a.tags.join(", ") : "—"} />
                  <Row label="Notes" value={a.notes || "—"} />
                </dl>
              ) : (
                <div className="space-y-3 text-sm">
                  <div>
                    <label className="text-xs font-semibold text-gray-600 mb-1 block">Criticality (drives Risk Score multiplier)</label>
                    <select value={form.criticality} onChange={e => setForm({ ...form, criticality: e.target.value })} className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm" data-testid="edit-criticality">
                      <option value="critical">Critical (Crown Jewel × 2.0)</option>
                      <option value="high">High (× 1.5)</option>
                      <option value="medium">Medium (× 1.0)</option>
                      <option value="low">Low (× 0.5)</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-600 mb-1 block">Environment</label>
                    <select value={form.environment} onChange={e => setForm({ ...form, environment: e.target.value })} className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm" data-testid="edit-environment">
                      <option value="production">Production</option>
                      <option value="staging">Staging</option>
                      <option value="development">Development</option>
                      <option value="test">Test</option>
                      <option value="dr">DR</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-600 mb-1 block">Owner</label>
                    <Input value={form.owner} onChange={e => setForm({ ...form, owner: e.target.value })} data-testid="edit-owner" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-600 mb-1 block">Tags (comma-separated)</label>
                    <Input value={form.tags} onChange={e => setForm({ ...form, tags: e.target.value })} data-testid="edit-tags" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-600 mb-1 block">Notes</label>
                    <Textarea rows={3} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} data-testid="edit-notes" />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right: Vulnerabilities + Compliance */}
          <div className="lg:col-span-2 space-y-4">
            {/* Open Vulnerabilities */}
            <div className="iv-card p-5" data-testid="open-vulns-section">
              <h3 className="font-bold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                <Bug size={18} weight="duotone" className="text-red-500" /> Open Vulnerabilities ({totalOpen})
              </h3>
              {data.vulnerabilities.open.length === 0 ? (
                <p className="text-sm text-emerald-600 flex items-center gap-2"><CheckCircle size={16} weight="fill" /> No open vulnerabilities. Asset is clean.</p>
              ) : (
                <div className="space-y-2">
                  {data.vulnerabilities.open.map(v => (
                    <VulnRow key={v.id} v={v} />
                  ))}
                </div>
              )}
            </div>

            {/* Fixed Vulnerabilities */}
            {data.vulnerabilities.fixed.length > 0 && (
              <div className="iv-card p-5" data-testid="fixed-vulns-section">
                <h3 className="font-bold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                  <CheckCircle size={18} weight="duotone" className="text-emerald-500" /> Remediated Vulnerabilities ({data.vulnerabilities.fixed.length})
                </h3>
                <div className="space-y-2">
                  {data.vulnerabilities.fixed.map(v => (
                    <VulnRow key={v.id} v={v} />
                  ))}
                </div>
              </div>
            )}

            {/* Compliance Checks */}
            {data.compliance_checks.length > 0 && (
              <div className="iv-card p-5" data-testid="compliance-section">
                <h3 className="font-bold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                  <ShieldCheck size={18} weight="duotone" className="text-[#1B839F]" /> Compliance Checks ({data.compliance_checks.length})
                </h3>
                <div className="space-y-2">
                  {data.compliance_checks.map(c => (
                    <div key={c.id} className="flex items-start gap-3 p-3 rounded-lg border border-gray-100 dark:border-gray-700/50" data-testid={`compliance-${c.id}`}>
                      {c.status === "PASSED" ? <CheckCircle size={18} weight="fill" className="text-emerald-500 mt-0.5 flex-shrink-0" /> : <XCircle size={18} weight="fill" className="text-red-500 mt-0.5 flex-shrink-0" />}
                      <div className="flex-1">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{c.title}</p>
                        <p className="text-xs text-gray-500 mt-0.5">Expected: <span className="font-mono">{c.expected_value}</span> · Actual: <span className="font-mono">{c.actual_value}</span></p>
                        <div className="flex gap-1 mt-1.5 flex-wrap">
                          {(c.control_ids || []).map(ctrl => (
                            <span key={ctrl} className="text-[10px] px-1.5 py-0.5 bg-[#1B839F]/10 text-[#1B839F] rounded font-medium">{ctrl}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* POA&M */}
            {data.poam_entries.length > 0 && (
              <div className="iv-card p-5" data-testid="poam-section">
                <h3 className="font-bold text-gray-900 dark:text-gray-100 mb-3">POA&M Entries ({data.poam_entries.length})</h3>
                <div className="space-y-2">
                  {data.poam_entries.map(p => (
                    <div key={p.id} className="p-3 rounded-lg border border-gray-100 text-sm">
                      <p className="font-medium text-gray-900 dark:text-gray-100">{p.poam_id} — {p.title}</p>
                      <p className="text-xs text-gray-500 mt-0.5">Due: {p.scheduled_completion?.slice(0, 10)} · Status: {p.status} · Priority: {p.priority}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
}

function SummaryCard({ label, value, color, icon: Icon }) {
  return (
    <div className="iv-card p-4" data-testid={`summary-${label.toLowerCase().replace(/\s/g, '-').replace(/[()]/g, '')}`}>
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg" style={{ background: `${color}15` }}>
          <Icon size={20} weight="duotone" style={{ color }} />
        </div>
        <div>
          <p className="text-xs text-gray-500">{label}</p>
          <p className="text-2xl font-bold" style={{ color }}>{value}</p>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-xs text-gray-500 flex-shrink-0">{label}</dt>
      <dd className="text-sm text-gray-900 dark:text-gray-100 text-right break-all">{value || "—"}</dd>
    </div>
  );
}

function VulnRow({ v }) {
  return (
    <div className="p-3 rounded-lg border border-gray-100 dark:border-gray-700/50" data-testid={`vuln-${v.id}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`px-1.5 py-0.5 text-[10px] font-semibold rounded ${SEV_COLORS[v.severity] || SEV_COLORS.medium}`}>
          {(v.severity || "").toUpperCase()}
        </span>
        <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded-full ${STATE_COLORS[v.state] || ""}`}>
          {(v.state || "").toUpperCase()}
        </span>
        <span className="text-xs text-gray-400 font-mono">Plugin #{v.tenable_plugin_id}</span>
      </div>
      <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mt-1">{v.title}</p>
      {v.cves?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {v.cves.map(c => <span key={c} className="text-[10px] font-mono text-red-600 bg-red-50 px-1.5 py-0.5 rounded">{c}</span>)}
        </div>
      )}
      <div className="flex gap-1 mt-1.5 flex-wrap">
        {(v.control_ids || []).map(c => (
          <span key={c} className="text-[10px] px-1.5 py-0.5 bg-[#00b388]/10 text-[#00b388] rounded font-medium">{c}</span>
        ))}
      </div>
    </div>
  );
}
