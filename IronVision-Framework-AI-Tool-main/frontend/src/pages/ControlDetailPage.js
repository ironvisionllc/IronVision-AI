import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Input } from "@/components/ui/input";
import {
  CaretRight,
  Files,
  ListBullets,
  MagnifyingGlass,
  ArrowRight,
  ShieldCheck,
  FileText
} from "@phosphor-icons/react";

const RELATIONSHIP_COLORS = {
  equivalent: { bg: "bg-emerald-100", text: "text-emerald-700", label: "Equivalent" },
  related: { bg: "bg-blue-100", text: "text-blue-700", label: "Related" },
  partial: { bg: "bg-amber-100", text: "text-amber-700", label: "Partial" },
};

const CCI_TYPE_COLORS = {
  policy: { bg: "bg-violet-50", text: "text-violet-700", border: "border-violet-200" },
  procedure: { bg: "bg-sky-50", text: "text-sky-700", border: "border-sky-200" },
  implementation: { bg: "bg-teal-50", text: "text-teal-700", border: "border-teal-200" },
  technical: { bg: "bg-indigo-50", text: "text-indigo-700", border: "border-indigo-200" },
  review: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" },
  monitoring: { bg: "bg-rose-50", text: "text-rose-700", border: "border-rose-200" },
};

const ControlDetailPage = ({ frameworkId, controlId, frameworkName, onBack }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [cciFilter, setCciFilter] = useState("");
  const [cciTypeFilter, setCciTypeFilter] = useState("all");

  useEffect(() => {
    fetchDetail();
  }, [frameworkId, controlId]);

  const fetchDetail = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/controls/${frameworkId}/detail/${controlId}`);
      setData(res.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-64">
          <p className="text-gray-500 text-sm">Loading control details...</p>
        </div>
      </Layout>
    );
  }

  if (!data || !data.control) {
    return (
      <Layout>
        <div className="text-center py-16">
          <p className="text-gray-500">Control not found.</p>
          <button onClick={onBack} className="text-sm text-[#2597B2] mt-4 hover:underline">Go back</button>
        </div>
      </Layout>
    );
  }

  const { control, ccis, cci_count, cross_framework_mappings, policy_mappings } = data;

  const cciTypes = [...new Set(ccis.map(c => c.type))].sort();
  const filteredCcis = ccis.filter(c => {
    const matchesSearch = !cciFilter ||
      c.cci_id.toLowerCase().includes(cciFilter.toLowerCase()) ||
      c.definition.toLowerCase().includes(cciFilter.toLowerCase());
    const matchesType = cciTypeFilter === "all" || c.type === cciTypeFilter;
    return matchesSearch && matchesType;
  });

  return (
    <Layout>
      <div data-testid="control-detail-page">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1.5 text-sm text-gray-500 mb-6">
          <button onClick={onBack} className="hover:text-[#2597B2] transition-colors" data-testid="breadcrumb-frameworks">
            Frameworks
          </button>
          <CaretRight size={12} weight="bold" />
          <button onClick={onBack} className="hover:text-[#2597B2] transition-colors" data-testid="breadcrumb-framework-name">
            {frameworkName}
          </button>
          <CaretRight size={12} weight="bold" />
          <span className="text-gray-900 font-medium">{control.control_id}</span>
        </nav>

        {/* Control Header */}
        <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6" data-testid="control-header">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-[#2597B2]/10 rounded-lg flex items-center justify-center">
                <ShieldCheck size={24} weight="duotone" className="text-[#2597B2]" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-[#2597B2] bg-[#2597B2]/8 px-2.5 py-0.5 rounded">{control.control_id}</span>
                  <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">{control.category}</span>
                </div>
                <h1 className="text-2xl font-bold text-gray-900 mt-1" style={{fontFamily: 'Inter, sans-serif'}}>{control.title}</h1>
              </div>
            </div>
            <div className="flex gap-2 shrink-0">
              {cci_count > 0 && (
                <span className="px-3 py-1 text-xs font-medium rounded-full bg-[#2597B2]/10 text-[#2597B2]" data-testid="cci-count-badge">
                  {cci_count} CCIs
                </span>
              )}
              <span className="px-3 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-700">
                {frameworkName}
              </span>
            </div>
          </div>
          <p className="text-sm text-gray-600 leading-relaxed">{control.description}</p>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-white border border-gray-200 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-[#2597B2]" data-testid="stat-ccis">{cci_count}</div>
            <div className="text-xs text-gray-500 mt-1">CCIs</div>
          </div>
          <div className="bg-white border border-gray-200 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-blue-600" data-testid="stat-cross-mappings">{cross_framework_mappings.length}</div>
            <div className="text-xs text-gray-500 mt-1">Cross-Framework Mappings</div>
          </div>
          <div className="bg-white border border-gray-200 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-emerald-600" data-testid="stat-policy-mappings">{policy_mappings.length}</div>
            <div className="text-xs text-gray-500 mt-1">Policy Mappings</div>
          </div>
        </div>

        {/* CCIs Section */}
        {cci_count > 0 && (
          <div className="mb-6" data-testid="ccis-section">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">Control Correlation Identifiers (CCIs)</h2>
              <span className="text-xs text-gray-500">Showing {filteredCcis.length} of {cci_count}</span>
            </div>

            {/* CCI Filters */}
            <div className="flex items-center gap-3 mb-4">
              <div className="relative flex-1 max-w-sm">
                <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <Input
                  placeholder="Search CCIs..."
                  value={cciFilter}
                  onChange={(e) => setCciFilter(e.target.value)}
                  className="pl-9 h-9 text-sm"
                  data-testid="cci-search-input"
                />
              </div>
              <select
                value={cciTypeFilter}
                onChange={(e) => setCciTypeFilter(e.target.value)}
                className="h-9 px-3 text-sm border border-gray-200 rounded-md bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-[#2597B2]"
                data-testid="cci-type-filter"
              >
                <option value="all">All Types ({cci_count})</option>
                {cciTypes.map(t => (
                  <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)} ({ccis.filter(c => c.type === t).length})</option>
                ))}
              </select>
            </div>

            {/* CCI Cards */}
            <div className="space-y-2">
              {filteredCcis.map((cci) => {
                const typeStyle = CCI_TYPE_COLORS[cci.type] || CCI_TYPE_COLORS.implementation;
                return (
                  <div
                    key={cci.cci_id}
                    className={`bg-white border rounded-lg p-4 flex items-start gap-4 ${typeStyle.border}`}
                    data-testid={`cci-card-${cci.cci_id}`}
                  >
                    <div className="shrink-0">
                      <span className="font-mono text-xs font-bold text-gray-800 bg-gray-100 px-2 py-1 rounded block whitespace-nowrap">{cci.cci_id}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-700 leading-relaxed">{cci.definition}</p>
                    </div>
                    <div className="shrink-0">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded ${typeStyle.bg} ${typeStyle.text}`}>
                        {cci.type}
                      </span>
                    </div>
                  </div>
                );
              })}
              {filteredCcis.length === 0 && (
                <div className="text-center py-8 text-gray-500 text-sm">No CCIs match your filter.</div>
              )}
            </div>
          </div>
        )}

        {cci_count === 0 && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center mb-6">
            <ListBullets size={32} className="text-gray-400 mx-auto mb-2" />
            <p className="text-sm text-gray-500">No CCIs available for this control.</p>
            <p className="text-xs text-gray-400 mt-1">CCIs are currently defined for NIST SP 800-53 controls.</p>
          </div>
        )}

        {/* Cross-Framework Mappings */}
        {cross_framework_mappings.length > 0 && (
          <div className="mb-6" data-testid="cross-mappings-section">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Cross-Framework Mappings</h2>
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left py-3 px-4 font-semibold text-gray-600">Source</th>
                    <th className="text-center py-3 px-4 font-semibold text-gray-600 w-[100px]">Relationship</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600">Target</th>
                    <th className="text-right py-3 px-4 font-semibold text-gray-600 w-[100px]">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {cross_framework_mappings.map((m, i) => {
                    const rel = RELATIONSHIP_COLORS[m.relationship_type] || RELATIONSHIP_COLORS.related;
                    return (
                      <tr key={i} className="border-b border-gray-100 last:border-0 hover:bg-gray-50/60 transition-colors">
                        <td className="py-3 px-4">
                          <span className="font-mono text-xs font-semibold text-[#2597B2]">{m.source_control_id}</span>
                          <span className="text-xs text-gray-500 ml-2">{m.source_framework_name}</span>
                          {m.source_control_title && <div className="text-xs text-gray-400 mt-0.5">{m.source_control_title}</div>}
                        </td>
                        <td className="py-3 px-4 text-center">
                          <div className="flex items-center justify-center gap-1">
                            <ArrowRight size={12} className="text-gray-400" />
                            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${rel.bg} ${rel.text}`}>{rel.label}</span>
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <span className="font-mono text-xs font-semibold text-blue-600">{m.target_control_id}</span>
                          <span className="text-xs text-gray-500 ml-2">{m.target_framework_name}</span>
                          {m.target_control_title && <div className="text-xs text-gray-400 mt-0.5">{m.target_control_title}</div>}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <span className="text-xs font-medium text-gray-700">{Math.round((m.confidence_score || 0) * 100)}%</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Policy Mappings */}
        {policy_mappings.length > 0 && (
          <div className="mb-6" data-testid="policy-mappings-section">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Policy Mappings</h2>
            <div className="space-y-2">
              {policy_mappings.map((pm, i) => (
                <div key={i} className="bg-white border border-gray-200 rounded-lg p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <FileText size={20} weight="duotone" className="text-[#2597B2]" />
                    <div>
                      <div className="text-sm font-medium text-gray-900">{pm.policy_name || "Policy"}</div>
                      <div className="text-xs text-gray-500">Source: {pm.source} | Status: {pm.status}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-600">{Math.round((pm.confidence_score || 0) * 100)}%</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${pm.status === 'approved' ? 'bg-emerald-100 text-emerald-700' : pm.status === 'pending' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
                      {pm.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
};

export default ControlDetailPage;
