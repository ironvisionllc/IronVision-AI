import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Files, ListBullets, MagnifyingGlass, CaretRight } from "@phosphor-icons/react";
import ControlDetailPage from "@/pages/ControlDetailPage";

const FrameworksPage = () => {
  const [frameworks, setFrameworks] = useState([]);
  const [controlCounts, setControlCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formData, setFormData] = useState({ name: "", description: "", version: "" });

  // Detail view state
  const [detailFramework, setDetailFramework] = useState(null);
  const [detailControls, setDetailControls] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailSearch, setDetailSearch] = useState("");
  const [detailCategory, setDetailCategory] = useState("all");

  // Control detail state
  const [selectedControl, setSelectedControl] = useState(null);

  useEffect(() => {
    fetchFrameworks();
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

  const openDetail = async (framework) => {
    setDetailFramework(framework);
    setDetailSearch("");
    setDetailCategory("all");
    setSelectedControl(null);
    setDetailLoading(true);
    try {
      const res = await axios.get(`${API}/controls/${framework.id}`);
      setDetailControls(res.data);
    } catch {
      toast.error("Failed to load controls");
      setDetailControls([]);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setDetailFramework(null);
    setDetailControls([]);
    setDetailSearch("");
    setDetailCategory("all");
  };

  // Derive categories and filtered controls for detail view
  const categories = [...new Set(detailControls.map(c => c.category))].sort();
  const filteredControls = detailControls.filter(c => {
    const matchesSearch = !detailSearch ||
      c.control_id.toLowerCase().includes(detailSearch.toLowerCase()) ||
      c.title.toLowerCase().includes(detailSearch.toLowerCase()) ||
      c.description.toLowerCase().includes(detailSearch.toLowerCase());
    const matchesCat = detailCategory === "all" || c.category === detailCategory;
    return matchesSearch && matchesCat;
  });

  // Control detail view
  if (selectedControl && detailFramework) {
    return (
      <ControlDetailPage
        frameworkId={detailFramework.id}
        controlId={selectedControl}
        frameworkName={detailFramework.name}
        onBack={() => setSelectedControl(null)}
      />
    );
  }

  // Detail view
  if (detailFramework) {
    return (
      <Layout>
        <div data-testid="framework-detail-page">
          <button
            onClick={closeDetail}
            className="flex items-center gap-1 text-sm text-[#2597B2] hover:text-[#1B839F] font-medium mb-6 transition-colors"
            data-testid="back-to-frameworks-btn"
          >
            <CaretRight size={14} weight="bold" className="rotate-180" />
            Back to Frameworks
          </button>

          <div className="flex items-start justify-between mb-6">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <div className="w-10 h-10 bg-[#2597B2] bg-opacity-10 rounded-lg flex items-center justify-center">
                  <Files size={22} weight="duotone" className="text-[#2597B2]" />
                </div>
                <div>
                  <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>{detailFramework.name}</h1>
                  <p className="text-sm text-gray-600 mt-1">{detailFramework.description}</p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <span className="px-3 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-700">
                v{detailFramework.version}
              </span>
              <span className="px-3 py-1 text-xs font-medium rounded-full bg-[#2597B2] bg-opacity-10 text-[#2597B2]" data-testid="detail-control-count">
                {detailControls.length} Controls
              </span>
            </div>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-3 mb-5">
            <div className="relative flex-1 max-w-sm">
              <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <Input
                placeholder="Search controls..."
                value={detailSearch}
                onChange={(e) => setDetailSearch(e.target.value)}
                className="pl-9 h-9 text-sm"
                data-testid="detail-search-input"
              />
            </div>
            <select
              value={detailCategory}
              onChange={(e) => setDetailCategory(e.target.value)}
              className="h-9 px-3 text-sm border border-gray-200 rounded-md bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-[#2597B2]"
              data-testid="detail-category-filter"
            >
              <option value="all">All Categories ({detailControls.length})</option>
              {categories.map(cat => (
                <option key={cat} value={cat}>{cat} ({detailControls.filter(c => c.category === cat).length})</option>
              ))}
            </select>
            <span className="text-xs text-gray-500 ml-auto">
              Showing {filteredControls.length} of {detailControls.length}
            </span>
          </div>

          {/* Controls Table */}
          {detailLoading ? (
            <div className="flex items-center justify-center h-40">
              <p className="text-gray-500 text-sm">Loading controls...</p>
            </div>
          ) : filteredControls.length === 0 ? (
            <div className="text-center py-12 text-gray-500 text-sm">No controls match your filter.</div>
          ) : (
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden" data-testid="controls-table">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 w-[140px]">Control ID</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600">Title</th>
                    <th className="text-left py-3 px-4 font-semibold text-gray-600 w-[160px]">Category</th>
                    <th className="text-right py-3 px-4 font-semibold text-gray-600 w-[80px]"></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredControls.map((ctrl, i) => (
                    <tr
                      key={ctrl.id || i}
                      className="border-b border-gray-100 last:border-0 hover:bg-[#2597B2]/[0.03] transition-colors cursor-pointer group"
                      data-testid={`control-row-${ctrl.control_id}`}
                      onClick={() => setSelectedControl(ctrl.control_id)}
                    >
                      <td className="py-3 px-4">
                        <span className="font-mono text-xs font-semibold text-[#2597B2] bg-[#2597B2]/8 px-2 py-0.5 rounded">{ctrl.control_id}</span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="font-medium text-gray-900">{ctrl.title}</div>
                        {ctrl.description && (
                          <div className="text-xs text-gray-500 mt-0.5 line-clamp-1">{ctrl.description}</div>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-xs text-gray-600 bg-gray-100 px-2 py-0.5 rounded">{ctrl.category}</span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <span className="text-xs font-medium text-[#2597B2] opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-end gap-1">
                          Details <CaretRight size={12} weight="bold" />
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Layout>
    );
  }

  // Grid view
  return (
    <Layout>
      <div data-testid="frameworks-page">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Compliance Frameworks</h1>
            <p className="text-sm text-gray-600 mt-2">Manage compliance frameworks for your organization</p>
          </div>
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

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <p className="text-gray-500">Loading frameworks...</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="frameworks-grid">
            {frameworks.map((framework) => (
              <div
                key={framework.id}
                className="bg-white rounded-lg border border-gray-200 p-6 hover:shadow-sm hover:-translate-y-[1px] transition-all duration-200 flex flex-col"
                data-testid={`framework-card-${framework.id}`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="w-12 h-12 bg-[#2597B2] bg-opacity-10 rounded-lg flex items-center justify-center">
                    <Files size={24} weight="duotone" className="text-[#2597B2]" />
                  </div>
                  <span className={`px-2 py-1 text-xs rounded-full ${
                    framework.type === 'standard' ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'
                  }`}>
                    {framework.type === 'standard' ? 'Standard' : 'Custom'}
                  </span>
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">{framework.name}</h3>
                <p className="text-sm text-gray-600 mb-4 line-clamp-2">{framework.description}</p>

                <div className="mt-auto pt-4 border-t border-gray-100 flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-sm text-gray-700">
                    <ListBullets size={16} weight="bold" className="text-[#2597B2]" />
                    <span className="font-semibold" data-testid={`control-count-${framework.id}`}>
                      {controlCounts[framework.id] !== undefined ? controlCounts[framework.id] : "..."}
                    </span>
                    <span className="text-gray-500">Controls</span>
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
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
};

export default FrameworksPage;
