import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, Warning, ListChecks, TrendUp, TrendDown, Minus, Funnel, MagnifyingGlass, CaretRight, ShieldWarning, Target, User } from "@phosphor-icons/react";

const RisksPage = () => {
  const [risks, setRisks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterCategory, setFilterCategory] = useState("all");
  const [filterStatus, setFilterStatus] = useState("all");
  const [formData, setFormData] = useState({
    title: "",
    description: "",
    category: "compliance",
    likelihood: 3,
    impact: 3,
    status: "open",
    owner: ""
  });

  useEffect(() => {
    fetchRisks();
  }, []);

  const fetchRisks = async () => {
    try {
      const response = await axios.get(`${API}/risks`);
      setRisks(response.data);
    } catch (error) {
      toast.error("Failed to fetch risks");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/risks`, formData);
      toast.success("Risk created successfully");
      setDialogOpen(false);
      setFormData({ title: "", description: "", category: "compliance", likelihood: 3, impact: 3, status: "open", owner: "" });
      fetchRisks();
    } catch (error) {
      toast.error("Failed to create risk");
    }
  };

  const createTaskFromRisk = async (risk) => {
    try {
      const priority = risk.risk_score > 12 ? "critical" : risk.risk_score > 8 ? "high" : "medium";
      await axios.post(`${API}/tasks`, {
        title: `Remediate: ${risk.title}`,
        description: `Risk remediation task auto-created from risk register.\n\nRisk: ${risk.title}\nCategory: ${risk.category}\nScore: ${risk.risk_score} (L:${risk.likelihood} x I:${risk.impact})\nOwner: ${risk.owner}\n\nDescription: ${risk.description}`,
        status: "todo",
        priority,
        tags: ["risk-remediation", risk.category],
      });
      toast.success("Remediation task created");
    } catch (error) {
      const msg = error.response?.data?.detail || "Failed to create task";
      toast.error(msg);
    }
  };

  const getRiskStyle = (score) => {
    if (score <= 5) return { 
      bg: 'bg-gradient-to-br from-emerald-50 to-emerald-100/50', 
      border: 'border-emerald-200',
      text: 'text-emerald-700', 
      badge: 'bg-emerald-100 text-emerald-700 border-emerald-200',
      label: 'Low',
      icon: TrendDown
    };
    if (score <= 12) return { 
      bg: 'bg-gradient-to-br from-blue-50 to-blue-100/50', 
      border: 'border-blue-200',
      text: 'text-blue-700', 
      badge: 'bg-blue-100 text-blue-700 border-blue-200',
      label: 'Medium',
      icon: Minus
    };
    if (score <= 20) return { 
      bg: 'bg-gradient-to-br from-amber-50 to-orange-100/50', 
      border: 'border-amber-200',
      text: 'text-amber-700', 
      badge: 'bg-amber-100 text-amber-700 border-amber-200',
      label: 'High',
      icon: TrendUp
    };
    return { 
      bg: 'bg-gradient-to-br from-red-50 to-red-100/50', 
      border: 'border-red-200',
      text: 'text-red-700', 
      badge: 'bg-red-100 text-red-700 border-red-200',
      label: 'Critical',
      icon: Warning
    };
  };

  const categoryIcons = {
    compliance: ShieldWarning,
    operational: Target,
    financial: TrendUp,
    strategic: Minus,
    security: Warning,
  };

  // Stats
  const totalRisks = risks.length;
  const openRisks = risks.filter(r => r.status === 'open').length;
  const criticalRisks = risks.filter(r => r.risk_score > 20).length;
  const avgScore = totalRisks > 0 ? Math.round(risks.reduce((sum, r) => sum + (r.risk_score || 0), 0) / totalRisks) : 0;

  // Filters
  const categories = [...new Set(risks.map(r => r.category))];
  const filteredRisks = risks.filter(r => {
    const matchesSearch = !searchTerm || 
      r.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      r.description?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = filterCategory === 'all' || r.category === filterCategory;
    const matchesStatus = filterStatus === 'all' || r.status === filterStatus;
    return matchesSearch && matchesCategory && matchesStatus;
  });

  // Skeleton loader
  const SkeletonCard = () => (
    <div className="iv-card p-5 animate-pulse">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-xl bg-gray-200" />
        <div className="flex-1 space-y-3">
          <div className="h-5 bg-gray-200 rounded w-3/4" />
          <div className="h-4 bg-gray-100 rounded w-1/2" />
          <div className="flex gap-2">
            <div className="h-6 bg-gray-100 rounded-full w-16" />
            <div className="h-6 bg-gray-100 rounded-full w-20" />
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <Layout>
      <div data-testid="risks-page" className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
              Risk Management
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Track and manage organizational risks
            </p>
          </div>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="iv-btn-primary" data-testid="create-risk-button">
                <Plus size={18} weight="bold" />
                Add Risk
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-xl" data-testid="create-risk-dialog">
              <DialogHeader>
                <DialogTitle className="text-xl font-semibold">Create New Risk</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleSubmit} className="space-y-5 mt-4">
                <div>
                  <Label className="text-sm font-medium">Risk Title</Label>
                  <Input
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                    placeholder="e.g., Data breach vulnerability"
                    className="mt-1.5 h-11"
                    required
                    data-testid="risk-title-input"
                  />
                </div>
                <div>
                  <Label className="text-sm font-medium">Description</Label>
                  <Textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="Describe the risk and its potential impact..."
                    rows={3}
                    className="mt-1.5"
                    data-testid="risk-description-input"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-sm font-medium">Category</Label>
                    <Select value={formData.category} onValueChange={(v) => setFormData({ ...formData, category: v })}>
                      <SelectTrigger className="mt-1.5 h-11" data-testid="risk-category-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="compliance">Compliance</SelectItem>
                        <SelectItem value="operational">Operational</SelectItem>
                        <SelectItem value="financial">Financial</SelectItem>
                        <SelectItem value="strategic">Strategic</SelectItem>
                        <SelectItem value="security">Security</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-sm font-medium">Status</Label>
                    <Select value={formData.status} onValueChange={(v) => setFormData({ ...formData, status: v })}>
                      <SelectTrigger className="mt-1.5 h-11" data-testid="risk-status-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="open">Open</SelectItem>
                        <SelectItem value="mitigating">Mitigating</SelectItem>
                        <SelectItem value="closed">Closed</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-sm font-medium">Likelihood (1-5)</Label>
                    <Select value={formData.likelihood.toString()} onValueChange={(v) => setFormData({ ...formData, likelihood: parseInt(v) })}>
                      <SelectTrigger className="mt-1.5 h-11" data-testid="risk-likelihood-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {[1,2,3,4,5].map(n => <SelectItem key={n} value={n.toString()}>{n} - {['Rare','Unlikely','Possible','Likely','Almost Certain'][n-1]}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-sm font-medium">Impact (1-5)</Label>
                    <Select value={formData.impact.toString()} onValueChange={(v) => setFormData({ ...formData, impact: parseInt(v) })}>
                      <SelectTrigger className="mt-1.5 h-11" data-testid="risk-impact-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {[1,2,3,4,5].map(n => <SelectItem key={n} value={n.toString()}>{n} - {['Insignificant','Minor','Moderate','Major','Severe'][n-1]}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div>
                  <Label className="text-sm font-medium">Risk Owner</Label>
                  <Input
                    value={formData.owner}
                    onChange={(e) => setFormData({ ...formData, owner: e.target.value })}
                    placeholder="e.g., John Smith"
                    className="mt-1.5 h-11"
                    data-testid="risk-owner-input"
                  />
                </div>
                <div className="flex justify-end gap-3 pt-2">
                  <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                  <Button type="submit" className="iv-btn-primary" data-testid="risk-submit-button">Create Risk</Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Risks', value: totalRisks, color: '#64748B', icon: Warning },
            { label: 'Open Risks', value: openRisks, color: '#F59E0B', icon: ShieldWarning },
            { label: 'Critical', value: criticalRisks, color: '#EF4444', icon: TrendUp },
            { label: 'Avg Score', value: avgScore, color: '#2597B2', icon: Target },
          ].map((stat) => (
            <div 
              key={stat.label} 
              className="iv-stat-card"
              style={{ '--stat-color': stat.color }}
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-label">{stat.label}</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-1">{stat.value}</p>
                </div>
                <div 
                  className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ backgroundColor: `${stat.color}12` }}
                >
                  <stat.icon size={20} weight="duotone" style={{ color: stat.color }} />
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="iv-card p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex-1 min-w-[200px] max-w-md relative">
              <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <Input
                placeholder="Search risks..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 h-10"
                data-testid="risk-search-input"
              />
            </div>
            <Select value={filterCategory} onValueChange={setFilterCategory}>
              <SelectTrigger className="w-[160px] h-10" data-testid="filter-category">
                <Funnel size={16} className="mr-2 text-gray-400" />
                <SelectValue placeholder="Category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Categories</SelectItem>
                {categories.map(c => (
                  <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger className="w-[140px] h-10" data-testid="filter-status">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="open">Open</SelectItem>
                <SelectItem value="mitigating">Mitigating</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
              </SelectContent>
            </Select>
            <span className="text-sm text-gray-500">
              {filteredRisks.length} of {totalRisks} risks
            </span>
          </div>
        </div>

        {/* Risk Cards */}
        {loading ? (
          <div className="grid gap-4">
            {[1,2,3].map(i => <SkeletonCard key={i} />)}
          </div>
        ) : filteredRisks.length === 0 ? (
          <div className="iv-card p-12">
            <div className="iv-empty-state">
              <div className="iv-empty-state-icon">
                <Warning size={28} weight="duotone" className="text-gray-400" />
              </div>
              <p className="iv-empty-state-title">No risks found</p>
              <p className="iv-empty-state-description">
                {searchTerm || filterCategory !== 'all' || filterStatus !== 'all' 
                  ? 'Try adjusting your filters'
                  : 'Create your first risk to get started'}
              </p>
            </div>
          </div>
        ) : (
          <div className="grid gap-4" data-testid="risks-list">
            {filteredRisks.map((risk) => {
              const style = getRiskStyle(risk.risk_score);
              const CategoryIcon = categoryIcons[risk.category] || Warning;
              const TrendIcon = style.icon;
              
              return (
                <div 
                  key={risk.id} 
                  className={`iv-card p-5 ${style.bg} ${style.border} hover:shadow-lg transition-all duration-200`}
                  data-testid={`risk-card-${risk.id}`}
                >
                  <div className="flex items-start gap-4">
                    {/* Score Circle */}
                    <div 
                      className={`w-14 h-14 rounded-2xl flex flex-col items-center justify-center ${style.badge} border`}
                    >
                      <span className="text-lg font-bold">{risk.risk_score}</span>
                      <span className="text-[9px] font-semibold uppercase tracking-wider opacity-70">Score</span>
                    </div>
                    
                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                            {risk.title}
                          </h3>
                          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">
                            {risk.description || 'No description provided'}
                          </p>
                        </div>
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => createTaskFromRisk(risk)}
                          className="flex-shrink-0 hover:bg-[#2597B2] hover:text-white hover:border-[#2597B2] transition-colors"
                          data-testid={`create-task-from-risk-${risk.id}`}
                        >
                          <ListChecks size={16} className="mr-1.5" />
                          Create Task
                        </Button>
                      </div>
                      
                      {/* Tags & Meta */}
                      <div className="flex flex-wrap items-center gap-2 mt-3">
                        <span className={`iv-badge ${style.badge} border`}>
                          <TrendIcon size={12} weight="bold" />
                          {style.label}
                        </span>
                        <span className="iv-badge iv-badge-neutral capitalize">
                          <CategoryIcon size={12} />
                          {risk.category}
                        </span>
                        <span className={`iv-badge ${
                          risk.status === 'open' ? 'iv-badge-warning' : 
                          risk.status === 'mitigating' ? 'iv-badge-brand' : 
                          'iv-badge-success'
                        }`}>
                          {risk.status}
                        </span>
                        {risk.owner && (
                          <span className="iv-badge iv-badge-neutral">
                            <User size={12} />
                            {risk.owner}
                          </span>
                        )}
                        <span className="text-xs text-gray-400 ml-auto">
                          L:{risk.likelihood} × I:{risk.impact}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Layout>
  );
};

export default RisksPage;
