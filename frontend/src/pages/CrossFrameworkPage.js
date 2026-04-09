import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  GitBranch, ArrowRight, MagnifyingGlass, ShieldCheck, CaretDown, CaretUp
} from "@phosphor-icons/react";

const REL_STYLES = {
  equivalent: { label: "Equivalent", color: "#4ADE80", bg: "bg-green-50" },
  related: { label: "Related", color: "#60A5FA", bg: "bg-blue-50" },
  partial: { label: "Partial", color: "#FB923C", bg: "bg-orange-50" },
};

const CrossFrameworkPage = ({ embedded = false }) => {
  const Wrap = embedded ? React.Fragment : Layout;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState("all");
  const [targetFilter, setTargetFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [heatmapOpen, setHeatmapOpen] = useState(false);

  useEffect(() => {
    axios.get(`${API}/cross-framework-mappings/matrix`)
      .then(res => setData(res.data))
      .catch(e => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Wrap><div className="flex items-center justify-center h-64"><p className="text-gray-500">Loading cross-framework mappings...</p></div></Wrap>;
  if (!data) return <Wrap><div className="flex items-center justify-center h-64"><p className="text-gray-500">Failed to load data</p></div></Wrap>;

  const frameworks = data.frameworks || [];
  const allMappings = data.mappings || [];

  // Build flat list for filtering
  const flatMappings = allMappings.map(m => ({
    id: m.id,
    srcFw: m.source_framework_name || "",
    srcCtrl: m.source_control_id || "",
    srcTitle: m.source_control_title || "",
    tgtFw: m.target_framework_name || "",
    tgtCtrl: m.target_control_id || "",
    tgtTitle: m.target_control_title || "",
    rel: m.relationship_type || "related",
    conf: m.confidence_score || 0.8,
  }));

  const filtered = flatMappings
    .filter(m => sourceFilter === "all" || m.srcFw === sourceFilter)
    .filter(m => targetFilter === "all" || m.tgtFw === targetFilter)
    .filter(m => {
      if (!search) return true;
      const q = search.toLowerCase();
      return m.srcCtrl.toLowerCase().includes(q) || m.srcTitle.toLowerCase().includes(q)
        || m.tgtCtrl.toLowerCase().includes(q) || m.tgtTitle.toLowerCase().includes(q)
        || m.srcFw.toLowerCase().includes(q) || m.tgtFw.toLowerCase().includes(q);
    });

  // Compute heatmap matrix
  const fwNames = frameworks.map(f => f.name);
  const shortName = (name) => {
    const abbrs = {
      "NIST Cybersecurity Framework": "NIST CSF",
      "NIST SP 800-53": "800-53",
      "NIST SP 800-171": "800-171",
      "ISO 27001": "ISO 27001",
      "GDPR": "GDPR",
      "HIPAA": "HIPAA",
      "SOC 2": "SOC 2",
      "CMMC": "CMMC",
      "NIS2": "NIS2",
      "NIST AI Risk Management Framework": "NIST AI",
      "Financial Services AI Risk Management Framework": "FS AI",
      "StateRAMP": "StateRAMP"
    };
    return abbrs[name] || name.slice(0, 10);
  };

  // Build matrix counts
  const matrixCounts = {};
  let maxCount = 0;
  for (const m of flatMappings) {
    const key = `${m.srcFw}|${m.tgtFw}`;
    matrixCounts[key] = (matrixCounts[key] || 0) + 1;
    if (matrixCounts[key] > maxCount) maxCount = matrixCounts[key];
  }

  const getHeatColor = (count) => {
    if (count === 0) return "bg-gray-50 text-gray-300";
    const ratio = count / Math.max(maxCount, 1);
    if (ratio > 0.6) return "bg-[#2597B2] text-white font-bold";
    if (ratio > 0.3) return "bg-[#2597B2]/60 text-white";
    return "bg-[#2597B2]/20 text-[#2597B2]";
  };

  // Stats
  const equivCount = flatMappings.filter(m => m.rel === "equivalent").length;
  const relatedCount = flatMappings.filter(m => m.rel === "related").length;
  const uniqueFwPairs = new Set(flatMappings.map(m => `${m.srcFw}→${m.tgtFw}`)).size;

  return (
    <Wrap>
      <div data-testid="cross-framework-page">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Cross-Framework Mapping</h1>
          <p className="text-sm text-gray-600 mt-2">See how controls across different frameworks relate to each other</p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          {[
            { label: "Total Mappings", val: flatMappings.length, color: "#2597B2" },
            { label: "Equivalent", val: equivCount, color: "#4ADE80" },
            { label: "Related", val: relatedCount, color: "#60A5FA" },
            { label: "Frameworks", val: frameworks.length, color: "#FB923C" },
            { label: "Framework Pairs", val: uniqueFwPairs, color: "#9333EA" },
          ].map(s => (
            <div key={s.label} className="bg-white rounded-lg border border-gray-200 p-4" data-testid={`xfw-stat-${s.label.toLowerCase().replace(/ /g, '-')}`}>
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-500">{s.label}</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{s.val}</p>
            </div>
          ))}
        </div>

        {/* Heatmap Matrix - Collapsible */}
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 mb-6 overflow-hidden shadow-sm" data-testid="heatmap-matrix">
          <button
            onClick={() => setHeatmapOpen(!heatmapOpen)}
            className="w-full flex items-center justify-between p-6 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors text-left"
            data-testid="heatmap-toggle"
          >
            <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">Framework Relationship Heatmap</h3>
            <div className="flex items-center gap-2 text-gray-400">
              <span className="text-xs">{heatmapOpen ? "Collapse" : "Expand"}</span>
              {heatmapOpen ? <CaretUp size={16} weight="bold" /> : <CaretDown size={16} weight="bold" />}
            </div>
          </button>
          {heatmapOpen && (
            <div className="px-6 pb-6 overflow-x-auto">
          <div className="min-w-[700px]">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="text-left text-xs text-gray-500 font-semibold p-2 w-24">From \ To</th>
                  {fwNames.map(name => (
                    <th key={name} className="text-center text-[10px] text-gray-500 font-semibold p-1 w-16" style={{writingMode: "vertical-rl", transform: "rotate(180deg)", height: 90}}>
                      {shortName(name)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {fwNames.map(srcName => (
                  <tr key={srcName}>
                    <td className="text-xs text-gray-700 dark:text-gray-300 font-semibold p-2 whitespace-nowrap">{shortName(srcName)}</td>
                    {fwNames.map(tgtName => {
                      const count = srcName === tgtName ? null : (matrixCounts[`${srcName}|${tgtName}`] || 0);
                      return (
                        <td key={tgtName} className="p-1 text-center">
                          {count === null ? (
                            <div className="w-full h-8 bg-gray-100 dark:bg-gray-700 rounded flex items-center justify-center">
                              <span className="text-[9px] text-gray-300 dark:text-gray-500">-</span>
                            </div>
                          ) : (
                            <div className={`w-full h-8 rounded flex items-center justify-center text-[10px] ${getHeatColor(count)}`}
                              title={`${shortName(srcName)} → ${shortName(tgtName)}: ${count} mappings`}>
                              {count > 0 ? count : ""}
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-4 mt-4 text-xs text-gray-500 dark:text-gray-400">
            <span>Density:</span>
            <div className="flex items-center gap-1"><div className="w-4 h-4 rounded bg-[#2597B2]/20"></div> Low</div>
            <div className="flex items-center gap-1"><div className="w-4 h-4 rounded bg-[#2597B2]/60"></div> Medium</div>
            <div className="flex items-center gap-1"><div className="w-4 h-4 rounded bg-[#2597B2]"></div> High</div>
          </div>
            </div>
          )}
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <Select value={sourceFilter} onValueChange={setSourceFilter}>
            <SelectTrigger className="w-[220px]" data-testid="xfw-source-filter"><SelectValue placeholder="Source Framework" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Source Frameworks</SelectItem>
              {fwNames.map(n => <SelectItem key={n} value={n}>{shortName(n)}</SelectItem>)}
            </SelectContent>
          </Select>
          <ArrowRight size={16} className="text-gray-400" />
          <Select value={targetFilter} onValueChange={setTargetFilter}>
            <SelectTrigger className="w-[220px]" data-testid="xfw-target-filter"><SelectValue placeholder="Target Framework" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Target Frameworks</SelectItem>
              {fwNames.map(n => <SelectItem key={n} value={n}>{shortName(n)}</SelectItem>)}
            </SelectContent>
          </Select>
          <div className="relative flex-1 max-w-xs">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input value={search} onChange={e => setSearch(e.target.value)} className="pl-9 h-9" placeholder="Search controls..." data-testid="xfw-search-input" />
          </div>
        </div>

        {/* Mapping List */}
        {filtered.length === 0 ? (
          <div className="bg-white rounded-lg border border-gray-200 p-12 text-center" data-testid="no-xfw-mappings">
            <GitBranch size={48} weight="duotone" className="text-gray-300 mx-auto mb-3" />
            <p className="text-gray-400">No cross-framework mappings match your filters</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map(m => {
              const relStyle = REL_STYLES[m.rel] || REL_STYLES.related;
              return (
                <div key={m.id} className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-sm transition-all duration-200" data-testid={`xfw-mapping-${m.id}`}>
                  <div className="flex items-center gap-3">
                    {/* Source */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs font-mono font-semibold">{m.srcCtrl}</span>
                        <span className="text-sm text-gray-700 truncate">{m.srcTitle}</span>
                      </div>
                      <span className="text-xs text-gray-400">{shortName(m.srcFw)}</span>
                    </div>

                    {/* Relationship */}
                    <div className="flex flex-col items-center flex-shrink-0 px-3">
                      <ArrowRight size={18} style={{ color: relStyle.color }} />
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold mt-0.5 ${relStyle.bg}`} style={{ color: relStyle.color }}>
                        {relStyle.label}
                      </span>
                      <span className="text-[10px] text-gray-400 mt-0.5">{Math.round(m.conf * 100)}%</span>
                    </div>

                    {/* Target */}
                    <div className="flex-1 min-w-0 text-right">
                      <div className="flex items-center gap-2 justify-end">
                        <span className="text-sm text-gray-700 truncate">{m.tgtTitle}</span>
                        <span className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs font-mono font-semibold">{m.tgtCtrl}</span>
                      </div>
                      <span className="text-xs text-gray-400">{shortName(m.tgtFw)}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Wrap>
  );
};

export default CrossFrameworkPage;
