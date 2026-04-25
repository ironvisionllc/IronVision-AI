import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Files, ListBullets, MagnifyingGlass, CaretRight, Gauge, GearSix, Eye, EyeSlash, CaretUp, CaretDown, DotsSixVertical } from "@phosphor-icons/react";
import FrameworkWorkspace from "@/components/FrameworkWorkspace";

const SCORE_COLORS = {
  excellent: { text: "#059669", bg: "#D1FAE5" },
  good: { text: "#0891B2", bg: "#CFFAFE" },
  fair: { text: "#D97706", bg: "#FEF3C7" },
  needs_improvement: { text: "#EA580C", bg: "#FFEDD5" },
  critical: { text: "#DC2626", bg: "#FEE2E2" },
};

const getScoreStyle = (score) => {
  if (score >= 90) return SCORE_COLORS.excellent;
  if (score >= 75) return SCORE_COLORS.good;
  if (score >= 60) return SCORE_COLORS.fair;
  if (score >= 40) return SCORE_COLORS.needs_improvement;
  return SCORE_COLORS.critical;
};

const FW_PREFS_KEY = "iv_framework_prefs";
const loadFwPrefs = () => { try { const s = localStorage.getItem(FW_PREFS_KEY); if (s) return JSON.parse(s); } catch {} return null; };
const saveFwPrefs = (p) => localStorage.setItem(FW_PREFS_KEY, JSON.stringify(p));

const FrameworksPage = ({ embedded = false }) => {
  const Wrap = embedded ? React.Fragment : Layout;
  const [frameworks, setFrameworks] = useState([]);
  const [controlCounts, setControlCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formData, setFormData] = useState({ name: "", description: "", version: "" });

  // Detail view state
  const [detailFramework, setDetailFramework] = useState(null);
  const [showOrganize, setShowOrganize] = useState(false);
  const [fwPrefs, setFwPrefs] = useState(null); // { order: [...ids], hidden: [...ids] }

  // Effectiveness scores
  const [fwEffectiveness, setFwEffectiveness] = useState({});

  // Initialize preferences when frameworks load
  useEffect(() => {
    if (frameworks.length > 0 && fwPrefs === null) {
      const stored = loadFwPrefs();
      if (stored && stored.order) {
        // Add any new frameworks not in saved prefs
        const newIds = frameworks.map(f => f.id).filter(id => !stored.order.includes(id));
        setFwPrefs({ order: [...stored.order, ...newIds], hidden: stored.hidden || [] });
      } else {
        setFwPrefs({ order: frameworks.map(f => f.id), hidden: [] });
      }
    }
  }, [frameworks, fwPrefs]);

  useEffect(() => { if (fwPrefs) saveFwPrefs(fwPrefs); }, [fwPrefs]);

  const moveFw = (id, dir) => {
    setFwPrefs(prev => {
      const order = [...prev.order];
      const idx = order.indexOf(id);
      const swap = dir === "up" ? idx - 1 : idx + 1;
      if (swap < 0 || swap >= order.length) return prev;
      [order[idx], order[swap]] = [order[swap], order[idx]];
      return { ...prev, order };
    });
  };

  const toggleFwVisibility = (id) => {
    setFwPrefs(prev => ({
      ...prev,
      hidden: prev.hidden.includes(id) ? prev.hidden.filter(h => h !== id) : [...prev.hidden, id],
    }));
  };

  // Sorted/filtered frameworks based on preferences
  const visibleFrameworks = fwPrefs
    ? fwPrefs.order
        .filter(id => !fwPrefs.hidden.includes(id))
        .map(id => frameworks.find(f => f.id === id))
        .filter(Boolean)
    : frameworks;

  useEffect(() => {
    fetchFrameworks();
  }, []);

  // Fetch dashboard effectiveness for framework cards
  useEffect(() => {
    axios.get(`${API}/control-effectiveness/dashboard`).then(res => {
      const map = {};
      (res.data?.frameworks || []).forEach(fw => { map[fw.framework_id] = fw; });
      setFwEffectiveness(map);
    }).catch(() => {});
  }, []);

  const fetchFrameworks = async () => {
    try {
      const response = await axios.get(`${API}/frameworks`);
      setFrameworks(response.data);
      // Fetch control counts for all frameworks in parallel
      const counts = {};
      await Promise.all(
        response.data.map(async (fw) => {
          try {
            const res = await axios.get(`${API}/controls/${fw.id}`);
            counts[fw.id] = res.data.length;
          } catch {
            counts[fw.id] = 0;
          }
        })
      );
      setControlCounts(counts);
    } catch (error) {
      toast.error("Failed to fetch frameworks");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/frameworks`, formData);
      toast.success("Framework created successfully");
      setDialogOpen(false);
      setFormData({ name: "", description: "", version: "" });
      fetchFrameworks();
    } catch (error) {
      toast.error("Failed to create framework");
    }
  };

  const openDetail = (framework) => {
    setDetailFramework(framework);
  };

  const closeDetail = () => {
    setDetailFramework(null);
  };

  // Show workspace when a framework is selected
  if (detailFramework) {
    return (
      <Wrap>
        <FrameworkWorkspace framework={detailFramework} onBack={closeDetail} />
      </Wrap>
    );
  }

  // Grid view
  return (
    <Wrap>
      <div data-testid="frameworks-page">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Compliance Frameworks</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">Manage compliance frameworks for your organization</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="h-9 text-xs" onClick={() => setShowOrganize(!showOrganize)} data-testid="organize-frameworks-btn">
              <GearSix size={14} className="mr-1.5" /> Organize
            </Button>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="create-framework-button">
                  <Plus size={20} weight="bold" className="mr-2" />
                  Create Custom Framework
                </Button>
              </DialogTrigger>
              <DialogContent data-testid="create-framework-dialog">
                <DialogHeader>
                  <DialogTitle>Create Custom Framework</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4 mt-4">
                  <div>
                    <Label htmlFor="name">Framework Name</Label>
                    <Input id="name" value={formData.name} onChange={(e) => setFormData({...formData, name: e.target.value})} required data-testid="framework-name-input" />
                  </div>
                  <div>
                    <Label htmlFor="description">Description</Label>
                    <Input id="description" value={formData.description} onChange={(e) => setFormData({...formData, description: e.target.value})} required data-testid="framework-description-input" />
                  </div>
                  <div>
                    <Label htmlFor="version">Version</Label>
                    <Input id="version" value={formData.version} onChange={(e) => setFormData({...formData, version: e.target.value})} required data-testid="framework-version-input" />
                  </div>
                  <Button type="submit" className="w-full bg-[#2597B2] hover:bg-[#1B839F]" data-testid="submit-framework-button">
                    Create Framework
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {/* Organize Panel */}
        {showOrganize && fwPrefs && (
          <div className="iv-card p-4 mb-6" data-testid="organize-panel">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Organize Frameworks</h3>
              <button onClick={() => setFwPrefs({ order: frameworks.map(f => f.id), hidden: [] })} className="text-xs text-[#2597B2] hover:text-[#1B839F] font-medium" data-testid="reset-fw-prefs-btn">Reset</button>
            </div>
            <div className="space-y-1.5">
              {fwPrefs.order.map((id, idx) => {
                const fw = frameworks.find(f => f.id === id);
                if (!fw) return null;
                const hidden = fwPrefs.hidden.includes(id);
                return (
                  <div key={id} className={`flex items-center gap-3 p-2.5 rounded-lg border transition-colors ${hidden ? "bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700 opacity-50" : "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700"}`} data-testid={`fw-organize-${id}`}>
                    <DotsSixVertical size={14} className="text-gray-300" />
                    <div className="flex flex-col gap-0.5">
                      <button onClick={() => moveFw(id, "up")} disabled={idx === 0} className="text-gray-400 hover:text-gray-600 disabled:opacity-20" data-testid={`fw-move-up-${id}`}><CaretUp size={11} weight="bold" /></button>
                      <button onClick={() => moveFw(id, "down")} disabled={idx === fwPrefs.order.length - 1} className="text-gray-400 hover:text-gray-600 disabled:opacity-20" data-testid={`fw-move-down-${id}`}><CaretDown size={11} weight="bold" /></button>
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{fw.name}</span>
                      <span className="text-xs text-gray-400 ml-2">{controlCounts[fw.id] || 0} controls</span>
                    </div>
                    <button onClick={() => toggleFwVisibility(id)} className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors" data-testid={`fw-toggle-${id}`}>
                      {hidden ? <EyeSlash size={16} className="text-gray-400" /> : <Eye size={16} className="text-[#2597B2]" />}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <p className="text-gray-500">Loading frameworks...</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="frameworks-grid">
            {visibleFrameworks.map((framework) => {
              const eff = fwEffectiveness[framework.id];
              const scoreStyle = eff ? getScoreStyle(eff.average_score) : null;
              return (
              <div
                key={framework.id}
                className="iv-card p-6 flex flex-col"
                data-testid={`framework-card-${framework.id}`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="w-12 h-12 bg-[#2597B2] bg-opacity-10 rounded-lg flex items-center justify-center">
                    <Files size={24} weight="duotone" className="text-[#2597B2]" />
                  </div>
                  <div className="flex items-center gap-2">
                    {eff && (
                      <span
                        className="flex items-center gap-1 px-2 py-1 text-xs font-semibold rounded-full"
                        style={{ color: scoreStyle.text, backgroundColor: scoreStyle.bg }}
                        data-testid={`fw-score-badge-${framework.id}`}
                      >
                        <Gauge size={12} weight="fill" />
                        {eff.average_score}
                      </span>
                    )}
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      framework.type === 'standard' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                    }`}>
                      {framework.type === 'standard' ? 'Standard' : 'Custom'}
                    </span>
                  </div>
                </div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">{framework.name}</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 line-clamp-2">{framework.description}</p>

                {eff && (
                  <div className="mb-4">
                    <div className="flex items-center justify-between text-[10px] text-gray-400 mb-1">
                      <span>Effectiveness</span>
                      <span>{eff.grade}</span>
                    </div>
                    <div className="h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${eff.average_score}%`, backgroundColor: scoreStyle.text }} />
                    </div>
                  </div>
                )}

                <div className="mt-auto pt-4 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300">
                    <ListBullets size={16} weight="bold" className="text-[#2597B2]" />
                    <span className="font-semibold" data-testid={`control-count-${framework.id}`}>
                      {controlCounts[framework.id] !== undefined ? controlCounts[framework.id] : "..."}
                    </span>
                    <span className="text-gray-500 dark:text-gray-400">Controls</span>
                  </div>
                  <button
                    onClick={() => openDetail(framework)}
                    className="flex items-center gap-1 text-sm font-medium text-[#2597B2] hover:text-[#1B839F] transition-colors"
                    data-testid={`view-details-btn-${framework.id}`}
                  >
                    View Details
                    <CaretRight size={14} weight="bold" />
                  </button>
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

export default FrameworksPage;
