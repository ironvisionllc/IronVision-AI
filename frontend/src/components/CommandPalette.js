import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import {
  House, ShieldCheck, FileText, Warning, Users, Eye, Calendar, ListChecks, Plugs, Gear,
  MagnifyingGlass, ArrowRight, Lightning
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const QUICK_ACTIONS = [
  { id: "dashboard", label: "Dashboard", desc: "Command Center", icon: House, path: "/dashboard" },
  { id: "frameworks", label: "Frameworks", desc: "Compliance frameworks", icon: ShieldCheck, path: "/frameworks" },
  { id: "policies", label: "Policies", desc: "Policy builder & library", icon: FileText, path: "/policies" },
  { id: "risks", label: "Risk Assessment", desc: "Risk register", icon: Warning, path: "/risks" },
  { id: "vendors", label: "Vendors", desc: "Third-party risk", icon: Users, path: "/vendors" },
  { id: "siem", label: "SIEM", desc: "Security events", icon: Eye, path: "/siem" },
  { id: "compliance", label: "Compliance", desc: "Audits & evidence", icon: Calendar, path: "/compliance" },
  { id: "tasks", label: "Tasks", desc: "Task management", icon: ListChecks, path: "/tasks" },
  { id: "integrations", label: "Integrations", desc: "Slack, SIEM connectors", icon: Plugs, path: "/integrations" },
  { id: "settings", label: "Settings", desc: "App configuration", icon: Gear, path: "/settings" },
  { id: "mappings", label: "Control Mappings", desc: "Policy-to-control mapping", icon: Lightning, path: "/policies?tab=mappings" },
  { id: "cross-fw", label: "Cross-Framework", desc: "Framework relationships", icon: ShieldCheck, path: "/policies?tab=cross-framework" },
  { id: "evidence", label: "Evidence Library", desc: "Compliance evidence", icon: Calendar, path: "/compliance?tab=evidence" },
  { id: "docs", label: "Document Analysis", desc: "Upload & analyze docs", icon: FileText, path: "/policies?tab=documents" },
];

const CommandPalette = () => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  // Listen for Cmd+K / Ctrl+K
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(prev => !prev);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setSearchResults([]);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Filter quick actions and search backend
  useEffect(() => {
    if (!query.trim()) {
      setResults(QUICK_ACTIONS.slice(0, 8));
      setSearchResults([]);
      return;
    }

    const q = query.toLowerCase();
    const filtered = QUICK_ACTIONS.filter(a =>
      a.label.toLowerCase().includes(q) || a.desc.toLowerCase().includes(q)
    );
    setResults(filtered);
    setSelectedIndex(0);

    // Search frameworks and controls
    const timer = setTimeout(async () => {
      if (query.length < 2) return;
      setSearching(true);
      try {
        const [fwRes] = await Promise.all([
          axios.get(`${API}/frameworks`).catch(() => ({ data: [] })),
        ]);

        const fwMatches = fwRes.data
          .filter(f => f.name.toLowerCase().includes(q) || f.description?.toLowerCase().includes(q))
          .slice(0, 3)
          .map(f => ({ type: "framework", id: f.id, label: f.name, desc: f.description?.slice(0, 60), path: `/frameworks` }));

        setSearchResults(fwMatches);
      } catch { /* ignore */ } finally {
        setSearching(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  const allResults = [...results, ...searchResults.map(r => ({
    ...r, icon: r.type === "framework" ? ShieldCheck : FileText
  }))];

  const go = useCallback((item) => {
    setOpen(false);
    navigate(item.path);
  }, [navigate]);

  const handleKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, allResults.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && allResults[selectedIndex]) {
      go(allResults[selectedIndex]);
    }
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[9999]" onClick={() => setOpen(false)} />

      {/* Palette */}
      <div className="fixed top-[20%] left-1/2 -translate-x-1/2 w-full max-w-lg z-[10000]" data-testid="command-palette">
        <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          {/* Search Input */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
            <MagnifyingGlass size={18} className="text-gray-400 shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search pages, frameworks, controls..."
              className="flex-1 bg-transparent text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none"
              data-testid="command-palette-input"
            />
            <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium text-gray-400 bg-gray-100 dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700">
              ESC
            </kbd>
          </div>

          {/* Results */}
          <div className="max-h-80 overflow-y-auto py-1" data-testid="command-palette-results">
            {allResults.length === 0 && !searching && (
              <div className="px-4 py-8 text-center text-sm text-gray-500">
                No results found for "{query}"
              </div>
            )}

            {allResults.map((item, i) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id || item.label + i}
                  onClick={() => go(item)}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                    i === selectedIndex
                      ? "bg-[#2597B2]/10 text-[#2597B2]"
                      : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                  }`}
                  data-testid={`command-result-${item.id || i}`}
                >
                  <Icon size={18} weight={i === selectedIndex ? "duotone" : "regular"} className="shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{item.label}</div>
                    {item.desc && <div className="text-xs text-gray-400 truncate">{item.desc}</div>}
                  </div>
                  <ArrowRight size={14} className={`shrink-0 ${i === selectedIndex ? "opacity-100" : "opacity-0"}`} />
                </button>
              );
            })}

            {searching && (
              <div className="px-4 py-3 text-xs text-gray-400 text-center">Searching...</div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center gap-4 px-4 py-2 border-t border-gray-200 dark:border-gray-700 text-[10px] text-gray-400">
            <span className="flex items-center gap-1"><kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-[9px]">↑↓</kbd> Navigate</span>
            <span className="flex items-center gap-1"><kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-[9px]">↵</kbd> Open</span>
            <span className="flex items-center gap-1"><kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-[9px]">Esc</kbd> Close</span>
          </div>
        </div>
      </div>
    </>
  );
};

export default CommandPalette;
