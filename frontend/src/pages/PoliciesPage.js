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
import { Plus, FileText } from "@phosphor-icons/react";

const PoliciesPage = () => {
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formData, setFormData] = useState({
    title: "",
    content: "",
    version: "1.0",
    status: "draft"
  });

  useEffect(() => {
    fetchPolicies();
  }, []);

  const fetchPolicies = async () => {
    try {
      const response = await axios.get(`${API}/policies`);
      setPolicies(response.data);
    } catch (error) {
      toast.error("Failed to fetch policies");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/policies`, formData);
      toast.success("Policy created successfully");
      setDialogOpen(false);
      setFormData({ title: "", content: "", version: "1.0", status: "draft" });
      fetchPolicies();
    } catch (error) {
      toast.error("Failed to create policy");
    }
  };

  return (
    <Layout>
      <div data-testid="policies-page">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Policy Repository</h1>
            <p className="text-sm text-gray-600 mt-2">Manage organizational policies with version control</p>
          </div>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="create-policy-button">
                <Plus size={20} weight="bold" className="mr-2" />
                Create Policy
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl" data-testid="create-policy-dialog">
              <DialogHeader>
                <DialogTitle>Create New Policy</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleSubmit} className="space-y-4 mt-4">
                <div>
                  <Label htmlFor="title">Policy Title</Label>
                  <Input
                    id="title"
                    value={formData.title}
                    onChange={(e) => setFormData({...formData, title: e.target.value})}
                    required
                    data-testid="policy-title-input"
                  />
                </div>
                <div>
                  <Label htmlFor="content">Policy Content</Label>
                  <Textarea
                    id="content"
                    value={formData.content}
                    onChange={(e) => setFormData({...formData, content: e.target.value})}
                    rows={8}
                    required
                    data-testid="policy-content-input"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="version">Version</Label>
                    <Input
                      id="version"
                      value={formData.version}
                      onChange={(e) => setFormData({...formData, version: e.target.value})}
                      required
                      data-testid="policy-version-input"
                    />
                  </div>
                  <div>
                    <Label htmlFor="status">Status</Label>
                    <Select value={formData.status} onValueChange={(value) => setFormData({...formData, status: value})}>
                      <SelectTrigger data-testid="policy-status-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="draft">Draft</SelectItem>
                        <SelectItem value="active">Active</SelectItem>
                        <SelectItem value="archived">Archived</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <Button type="submit" className="w-full bg-[#2597B2] hover:bg-[#1B839F]" data-testid="submit-policy-button">
                  Create Policy
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <p className="text-gray-500">Loading policies...</p>
          </div>
        ) : (
          <div className="space-y-4" data-testid="policies-list">
            {policies.length === 0 ? (
              <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
                <FileText size={48} weight="duotone" className="text-gray-300 mx-auto mb-4" />
                <p className="text-gray-500">No policies yet. Create your first policy to get started.</p>
              </div>
            ) : (
              policies.map((policy) => (
                <div 
                  key={policy.id} 
                  className="bg-white rounded-lg border border-gray-200 p-6 hover:shadow-sm hover:-translate-y-[1px] transition-all duration-200"
                  data-testid={`policy-card-${policy.id}`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3 mb-2">
                        <h3 className="text-lg font-semibold text-gray-900">{policy.title}</h3>
                        <span className={`px-2 py-1 text-xs rounded-full ${
                          policy.status === 'active' ? 'bg-green-100 text-green-700' :
                          policy.status === 'draft' ? 'bg-yellow-100 text-yellow-700' :
                          'bg-gray-100 text-gray-700'
                        }`}>
                          {policy.status}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 mb-3 line-clamp-2">{policy.content}</p>
                      <div className="flex items-center space-x-4 text-xs text-gray-500">
                        <span>Version {policy.version}</span>
                        <span>•</span>
                        <span>Created {new Date(policy.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <Button variant="outline" size="sm" data-testid={`view-policy-${policy.id}`}>View Details</Button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </Layout>
  );
};

export default PoliciesPage;