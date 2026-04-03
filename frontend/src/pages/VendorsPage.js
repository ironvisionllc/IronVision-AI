import React, { useState, useEffect, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, Users, Pencil, Trash } from "@phosphor-icons/react";

const VendorsPage = () => {
  const { user } = useContext(AuthContext);
  const isAdmin = user?.roles?.[0]?.role === "admin";
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingVendor, setEditingVendor] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [formData, setFormData] = useState({ name: "", contact_email: "", risk_level: "low", assessment_status: "pending" });

  useEffect(() => { fetchVendors(); }, []);

  const fetchVendors = async () => {
    try {
      const r = await axios.get(`${API}/vendors`);
      setVendors(r.data);
    } catch { toast.error("Failed to fetch vendors"); } finally { setLoading(false); }
  };

  const resetForm = () => {
    setFormData({ name: "", contact_email: "", risk_level: "low", assessment_status: "pending" });
    setEditingVendor(null);
  };

  const openCreate = () => { resetForm(); setDialogOpen(true); };
  const openEdit = (v) => {
    setEditingVendor(v);
    setFormData({ name: v.name, contact_email: v.contact_email, risk_level: v.risk_level, assessment_status: v.assessment_status });
    setDialogOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      if (editingVendor) {
        await axios.put(`${API}/vendors/${editingVendor.id}`, formData);
        toast.success("Vendor updated");
      } else {
        await axios.post(`${API}/vendors`, formData);
        toast.success("Vendor added");
      }
      setDialogOpen(false);
      resetForm();
      fetchVendors();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Operation failed");
    }
  };

  const handleDelete = async (vendorId) => {
    try {
      await axios.delete(`${API}/vendors/${vendorId}`);
      toast.success("Vendor deleted");
      setDeleteConfirm(null);
      fetchVendors();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Delete failed");
    }
  };

  const riskBadge = (level) => {
    const map = {
      low: "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400",
      medium: "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
      high: "bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-400",
      critical: "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400",
    };
    return map[level] || map.low;
  };

  const statusBadge = (status) => {
    const map = {
      pending: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
      in_progress: "bg-blue-50 text-blue-700",
      completed: "bg-green-50 text-green-700",
      failed: "bg-red-50 text-red-700",
    };
    return map[status] || map.pending;
  };

  if (loading) return <Layout><div className="flex items-center justify-center h-64"><div className="w-6 h-6 border-2 border-[#2597B2] border-t-transparent rounded-full animate-spin" /></div></Layout>;

  return (
    <Layout>
      <div data-testid="vendors-page">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">Third-Party Vendors</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5">Manage and assess vendor risk</p>
          </div>
          {isAdmin && (
            <Dialog open={dialogOpen} onOpenChange={(o) => { setDialogOpen(o); if (!o) resetForm(); }}>
              <DialogTrigger asChild>
                <Button onClick={openCreate} className="bg-[#2597B2] hover:bg-[#1B839F] text-white rounded-xl flex items-center gap-2" data-testid="add-vendor-button">
                  <Plus size={16} weight="bold" /> Add Vendor
                </Button>
              </DialogTrigger>
              <DialogContent className="rounded-2xl" aria-describedby="vendor-form-description">
                <DialogHeader>
                  <DialogTitle>{editingVendor ? "Edit Vendor" : "Add Vendor"}</DialogTitle>
                </DialogHeader>
                <p id="vendor-form-description" className="sr-only">{editingVendor ? "Edit vendor details" : "Add a new third-party vendor"}</p>
                <form onSubmit={handleSubmit} className="space-y-4" data-testid="vendor-form">
                  <div>
                    <Label>Company Name</Label>
                    <Input value={formData.name} onChange={(e) => setFormData({...formData, name: e.target.value})} required className="rounded-xl mt-1" data-testid="vendor-name-input" />
                  </div>
                  <div>
                    <Label>Contact Email</Label>
                    <Input type="email" value={formData.contact_email} onChange={(e) => setFormData({...formData, contact_email: e.target.value})} required className="rounded-xl mt-1" data-testid="vendor-email-input" />
                  </div>
                  <div>
                    <Label>Risk Level</Label>
                    <Select value={formData.risk_level} onValueChange={(v) => setFormData({...formData, risk_level: v})}>
                      <SelectTrigger className="rounded-xl mt-1" data-testid="vendor-risk-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="low">Low</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="high">High</SelectItem>
                        <SelectItem value="critical">Critical</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Assessment Status</Label>
                    <Select value={formData.assessment_status} onValueChange={(v) => setFormData({...formData, assessment_status: v})}>
                      <SelectTrigger className="rounded-xl mt-1" data-testid="vendor-status-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="pending">Pending</SelectItem>
                        <SelectItem value="in_progress">In Progress</SelectItem>
                        <SelectItem value="completed">Completed</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <Button type="submit" className="w-full bg-[#2597B2] hover:bg-[#1B839F] text-white rounded-xl" data-testid="vendor-submit-button">
                    {editingVendor ? "Update Vendor" : "Add Vendor"}
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          )}
        </div>

        {vendors.length === 0 ? (
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-12 text-center shadow-sm" data-testid="no-vendors">
            <Users size={48} weight="duotone" className="text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 mb-1">No vendors yet</p>
            <p className="text-sm text-gray-400">Add third-party vendors to track risk</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="vendors-list">
            {vendors.map(v => (
              <div key={v.id} className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 p-5 shadow-sm iv-card" data-testid={`vendor-card-${v.id}`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-xl bg-[#e8f4f7] dark:bg-[#0a3540] flex items-center justify-center">
                      <Users size={18} weight="duotone" className="text-[#2597B2]" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">{v.name}</h3>
                      <p className="text-xs text-gray-400">{v.contact_email}</p>
                    </div>
                  </div>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${riskBadge(v.risk_level)}`}>{v.risk_level}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${statusBadge(v.assessment_status)}`}>{(v.assessment_status || "pending").replace(/_/g, " ")}</span>
                  {isAdmin && (
                    <div className="flex items-center gap-1">
                      <button onClick={() => openEdit(v)} className="p-1.5 rounded-lg text-gray-400 hover:text-[#2597B2] hover:bg-[#e8f4f7] dark:hover:bg-[#0a3540] transition-colors" data-testid={`edit-vendor-${v.id}`} title="Edit">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => setDeleteConfirm(v.id)} className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors" data-testid={`delete-vendor-${v.id}`} title="Delete">
                        <Trash size={14} />
                      </button>
                    </div>
                  )}
                </div>
                {/* Delete confirmation */}
                {deleteConfirm === v.id && (
                  <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-900/30 rounded-xl" data-testid={`delete-confirm-${v.id}`}>
                    <p className="text-xs text-red-700 dark:text-red-400 mb-2">Delete <strong>{v.name}</strong>?</p>
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="destructive" className="rounded-lg text-xs" onClick={() => handleDelete(v.id)} data-testid={`confirm-delete-${v.id}`}>Delete</Button>
                      <Button size="sm" variant="outline" className="rounded-lg text-xs" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
};

export default VendorsPage;
