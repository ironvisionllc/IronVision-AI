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
import { Plus, Warning, ListChecks } from "@phosphor-icons/react";

const RisksPage = () => {
  const [risks, setRisks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
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

  const getRiskColor = (score) => {
    if (score <= 5) return { bg: 'bg-green-100', text: 'text-green-700', label: 'Low' };
    if (score <= 12) return { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Medium' };
    if (score <= 20) return { bg: 'bg-orange-100', text: 'text-orange-700', label: 'High' };
    return { bg: 'bg-red-100', text: 'text-red-700', label: 'Critical' };
  };

  return (
    <Layout>
      <div data-testid="risks-page">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Risk Management</h1>
            <p className="text-sm text-gray-600 mt-2">Track and manage organizational risks</p>
          </div>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="create-risk-button">
                <Plus size={20} weight="bold" className="mr-2" />
                Add Risk
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-xl" data-testid="create-risk-dialog">
              <DialogHeader>
                <DialogTitle>Create New Risk</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleSubmit} className="space-y-4 mt-4">
                <div>
                  <Label htmlFor="title">Risk Title</Label>
                  <Input id="title" value={formData.title} onChange={(e) => setFormData({...formData, title: e.target.value})} required data-testid="risk-title-input" />
                </div>
                <div>
                  <Label htmlFor="description">Description</Label>
                  <Textarea id="description" value={formData.description} onChange={(e) => setFormData({...formData, description: e.target.value})} rows={4} required data-testid="risk-description-input" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="category">Category</Label>
                    <Select value={formData.category} onValueChange={(value) => setFormData({...formData, category: value})}>
                      <SelectTrigger data-testid="risk-category-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="operational">Operational</SelectItem>
                        <SelectItem value="compliance">Compliance</SelectItem>
                        <SelectItem value="security">Security</SelectItem>
                        <SelectItem value="financial">Financial</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label htmlFor="owner">Risk Owner</Label>
                    <Input id="owner" value={formData.owner} onChange={(e) => setFormData({...formData, owner: e.target.value})} required data-testid="risk-owner-input" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="likelihood">Likelihood (1-5)</Label>
                    <Input id="likelihood" type="number" min="1" max="5" value={formData.likelihood} onChange={(e) => setFormData({...formData, likelihood: parseInt(e.target.value)})} required data-testid="risk-likelihood-input" />
                  </div>
                  <div>
                    <Label htmlFor="impact">Impact (1-5)</Label>
                    <Input id="impact" type="number" min="1" max="5" value={formData.impact} onChange={(e) => setFormData({...formData, impact: parseInt(e.target.value)})} required data-testid="risk-impact-input" />
                  </div>
                </div>
                <Button type="submit" className="w-full bg-[#2597B2] hover:bg-[#1B839F]" data-testid="submit-risk-button">
                  Create Risk
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <p className="text-gray-500">Loading risks...</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="risks-list">
            {risks.map((risk) => {
              const riskLevel = getRiskColor(risk.risk_score);
              return (
                <div key={risk.id} className="bg-white rounded-lg border border-gray-200 p-6 hover:shadow-sm hover:-translate-y-[1px] transition-all duration-200" data-testid={`risk-card-${risk.id}`}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center space-x-2">
                      <Warning size={24} weight="duotone" className="text-[#FB923C]" />
                      <h3 className="text-lg font-semibold text-gray-900">{risk.title}</h3>
                    </div>
                    <span className={`px-2 py-1 text-xs rounded-full ${riskLevel.bg} ${riskLevel.text}`}>
                      {riskLevel.label}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mb-4">{risk.description}</p>
                  <div className="grid grid-cols-2 gap-4 text-xs mb-3">
                    <div>
                      <p className="text-gray-500">Category</p>
                      <p className="font-semibold text-gray-900 capitalize">{risk.category}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Risk Score</p>
                      <p className="font-semibold text-gray-900">{risk.risk_score} (L:{risk.likelihood} × I:{risk.impact})</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Owner</p>
                      <p className="font-semibold text-gray-900">{risk.owner}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Status</p>
                      <p className="font-semibold text-gray-900 capitalize">{risk.status}</p>
                    </div>
                  </div>
                  {risk.status === "open" && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full mt-1 text-[#2597B2] border-[#2597B2] hover:bg-[#2597B2] hover:text-white flex items-center justify-center gap-2"
                      onClick={() => createTaskFromRisk(risk)}
                      data-testid={`create-task-from-risk-${risk.id}`}
                    >
                      <ListChecks size={14} weight="bold" /> Create Remediation Task
                    </Button>
                  )}
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