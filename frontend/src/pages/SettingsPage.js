import React, { useState, useEffect, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { User, Users, Building, Bell, Shield, Gear, Crown } from "@phosphor-icons/react";
import RBACManager from "@/components/RBACManager";

const SettingsPage = () => {
  const { user } = useContext(AuthContext);
  const [activeTab, setActiveTab] = useState("profile");
  const isAdmin = user?.roles?.[0]?.role === "admin";

  return (
    <Layout>
      <div data-testid="settings-page">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Settings</h1>
          <p className="text-sm text-gray-600 mt-2">Manage your account and {isAdmin ? 'organization' : 'preferences'}</p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2 lg:grid-cols-7 mb-8">
            <TabsTrigger value="profile" className="flex items-center space-x-2">
              <User size={16} weight="duotone" />
              <span>Profile</span>
            </TabsTrigger>
            <TabsTrigger value="notifications" className="flex items-center space-x-2">
              <Bell size={16} weight="duotone" />
              <span>Notifications</span>
            </TabsTrigger>
            {isAdmin && (
              <>
                <TabsTrigger value="trial" className="flex items-center space-x-2">
                  <Shield size={16} weight="duotone" />
                  <span>Trial</span>
                </TabsTrigger>
                <TabsTrigger value="users" className="flex items-center space-x-2">
                  <Users size={16} weight="duotone" />
                  <span>Users</span>
                </TabsTrigger>
                <TabsTrigger value="organization" className="flex items-center space-x-2">
                  <Building size={16} weight="duotone" />
                  <span>Organization</span>
                </TabsTrigger>
                <TabsTrigger value="security" className="flex items-center space-x-2">
                  <Shield size={16} weight="duotone" />
                  <span>Security</span>
                </TabsTrigger>
                <TabsTrigger value="system" className="flex items-center space-x-2">
                  <Gear size={16} weight="duotone" />
                  <span>System</span>
                </TabsTrigger>
                <TabsTrigger value="rbac" className="flex items-center space-x-2" data-testid="rbac-tab">
                  <Crown size={16} weight="duotone" />
                  <span>Roles</span>
                </TabsTrigger>
              </>
            )}
          </TabsList>

          <TabsContent value="profile">
            <ProfileSettings user={user} />
          </TabsContent>

          <TabsContent value="notifications">
            <NotificationSettings user={user} />
          </TabsContent>

          {isAdmin && (
            <>
              <TabsContent value="trial">
                <TrialManagement />
              </TabsContent>

              <TabsContent value="users">
                <UserManagement />
              </TabsContent>

              <TabsContent value="organization">
                <OrganizationSettings />
              </TabsContent>

              <TabsContent value="security">
                <SecuritySettings />
              </TabsContent>

              <TabsContent value="system">
                <SystemSettings />
              </TabsContent>
              <TabsContent value="rbac">
                <RBACManager />
              </TabsContent>
            </>
          )}
        </Tabs>
      </div>
    </Layout>
  );
};

// Profile Settings Component
const ProfileSettings = ({ user }) => {
  const [formData, setFormData] = useState({
    name: user?.name || "",
    email: user?.email || "",
    currentPassword: "",
    newPassword: "",
    confirmPassword: ""
  });

  const handleProfileUpdate = async (e) => {
    e.preventDefault();
    try {
      await axios.put(`${API}/users/profile`, {
        name: formData.name,
        email: formData.email
      });
      toast.success("Profile updated successfully");
    } catch (error) {
      toast.error("Failed to update profile");
    }
  };

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    if (formData.newPassword !== formData.confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    try {
      await axios.post(`${API}/users/change-password`, {
        current_password: formData.currentPassword,
        new_password: formData.newPassword
      });
      toast.success("Password changed successfully");
      setFormData({ ...formData, currentPassword: "", newPassword: "", confirmPassword: "" });
    } catch (error) {
      toast.error("Failed to change password");
    }
  };

  return (
    <div className="space-y-6" data-testid="profile-settings">
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-xl font-semibold text-gray-900 mb-4" style={{fontFamily: 'Inter, sans-serif'}}>Personal Information</h3>
        <form onSubmit={handleProfileUpdate} className="space-y-4">
          <div>
            <Label htmlFor="name">Full Name</Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              data-testid="profile-name-input"
            />
          </div>
          <div>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              data-testid="profile-email-input"
            />
          </div>
          <div>
            <Label>Role</Label>
            <Input value={user?.roles?.[0]?.role || "N/A"} disabled className="capitalize" />
          </div>
          <Button type="submit" className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="update-profile-button">
            Update Profile
          </Button>
        </form>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-xl font-semibold text-gray-900 mb-4" style={{fontFamily: 'Inter, sans-serif'}}>Change Password</h3>
        <form onSubmit={handlePasswordChange} className="space-y-4">
          <div>
            <Label htmlFor="currentPassword">Current Password</Label>
            <Input
              id="currentPassword"
              type="password"
              value={formData.currentPassword}
              onChange={(e) => setFormData({ ...formData, currentPassword: e.target.value })}
              data-testid="current-password-input"
            />
          </div>
          <div>
            <Label htmlFor="newPassword">New Password</Label>
            <Input
              id="newPassword"
              type="password"
              value={formData.newPassword}
              onChange={(e) => setFormData({ ...formData, newPassword: e.target.value })}
              data-testid="new-password-input"
            />
          </div>
          <div>
            <Label htmlFor="confirmPassword">Confirm New Password</Label>
            <Input
              id="confirmPassword"
              type="password"
              value={formData.confirmPassword}
              onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
              data-testid="confirm-password-input"
            />
          </div>
          <Button type="submit" className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="change-password-button">
            Change Password
          </Button>
        </form>
      </div>
    </div>
  );
};

// Notification Settings Component
const NotificationSettings = ({ user }) => {
  const [settings, setSettings] = useState({
    emailNotifications: true,
    riskAlerts: true,
    policyUpdates: true,
    auditReminders: true,
    weeklyReports: false,
    complianceAlerts: true
  });

  const handleToggle = (key) => {
    setSettings({ ...settings, [key]: !settings[key] });
    toast.success("Notification settings updated");
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6" data-testid="notification-settings">
      <h3 className="text-xl font-semibold text-gray-900 mb-4" style={{fontFamily: 'Inter, sans-serif'}}>Notification Preferences</h3>
      <div className="space-y-4">
        {Object.entries({
          emailNotifications: "Email Notifications",
          riskAlerts: "High Risk Alerts",
          policyUpdates: "Policy Updates",
          auditReminders: "Audit Reminders",
          weeklyReports: "Weekly Compliance Reports",
          complianceAlerts: "Compliance Score Alerts"
        }).map(([key, label]) => (
          <div key={key} className="flex items-center justify-between py-3 border-b border-gray-100">
            <div>
              <p className="font-semibold text-gray-900">{label}</p>
              <p className="text-sm text-gray-500">Receive notifications for {label.toLowerCase()}</p>
            </div>
            <Switch
              checked={settings[key]}
              onCheckedChange={() => handleToggle(key)}
              data-testid={`toggle-${key}`}
            />
          </div>
        ))}
      </div>
    </div>
  );
};

// Trial Management Component (Admin Only)
const TrialManagement = () => {
  const [trialStatus, setTrialStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [grantEmail, setGrantEmail] = useState("");
  const [grantDays, setGrantDays] = useState(14);

  useEffect(() => {
    fetchTrialStatus();
  }, []);

  const fetchTrialStatus = async () => {
    try {
      const response = await axios.get(`${API}/admin/trial/status`);
      setTrialStatus(response.data);
    } catch (error) {
      console.error("Failed to fetch trial status", error);
    } finally {
      setLoading(false);
    }
  };

  const handleGrantTrial = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/admin/trial/grant`, {
        email: grantEmail,
        days: grantDays
      });
      toast.success(`Trial granted to ${grantEmail} for ${grantDays} days`);
      setGrantEmail("");
      setGrantDays(14);
      fetchTrialStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to grant trial");
    }
  };

  const handleExtendTrial = async () => {
    try {
      await axios.post(`${API}/admin/trial/extend`, { days: 14 });
      toast.success("Trial extended by 14 days");
      fetchTrialStatus();
    } catch (error) {
      toast.error("Failed to extend trial");
    }
  };

  const handleActivateSubscription = async () => {
    if (!window.confirm("Activate full subscription? This will end the trial period.")) return;
    try {
      await axios.post(`${API}/admin/trial/activate-subscription`);
      toast.success("Subscription activated successfully");
      fetchTrialStatus();
    } catch (error) {
      toast.error("Failed to activate subscription");
    }
  };

  if (loading) {
    return <div className="bg-white rounded-lg border border-gray-200 p-6"><p>Loading trial information...</p></div>;
  }

  const getStatusColor = (status) => {
    switch (status) {
      case "trial": return trialStatus?.is_trial_active ? "bg-blue-100 text-blue-700" : "bg-red-100 text-red-700";
      case "active": return "bg-green-100 text-green-700";
      case "expired": return "bg-red-100 text-red-700";
      default: return "bg-gray-100 text-gray-700";
    }
  };

  return (
    <div className="space-y-6" data-testid="trial-management">
      {/* Current Status */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-xl font-semibold text-gray-900 mb-4" style={{fontFamily: 'Inter, sans-serif'}}>Current Trial Status</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <p className="text-sm text-gray-500 mb-1">Organization</p>
            <p className="text-lg font-semibold text-gray-900">{trialStatus?.organization_name}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500 mb-1">Subscription Status</p>
            <span className={`px-3 py-1 text-sm rounded-full capitalize ${getStatusColor(trialStatus?.subscription_status)}`}>
              {trialStatus?.subscription_status}
            </span>
          </div>
          {trialStatus?.is_trial_active && (
            <>
              <div>
                <p className="text-sm text-gray-500 mb-1">Days Remaining</p>
                <p className="text-2xl font-bold text-[#2597B2]">{trialStatus?.days_remaining}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500 mb-1">Trial End Date</p>
                <p className="text-lg font-semibold text-gray-900">
                  {trialStatus?.trial_end_date ? new Date(trialStatus.trial_end_date).toLocaleDateString() : "N/A"}
                </p>
              </div>
            </>
          )}
        </div>

        {trialStatus?.is_trial_active && (
          <div className="mt-6 flex space-x-3">
            <Button 
              onClick={handleExtendTrial} 
              className="bg-blue-600 hover:bg-blue-700"
              data-testid="extend-trial-button"
            >
              Extend Trial +14 Days
            </Button>
            <Button 
              onClick={handleActivateSubscription} 
              className="bg-green-600 hover:bg-green-700"
              data-testid="activate-subscription-button"
            >
              Activate Full Subscription
            </Button>
          </div>
        )}

        {trialStatus?.is_expired && (
          <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-red-800 font-semibold">Trial has expired. Activate subscription to continue using the platform.</p>
            <Button 
              onClick={handleActivateSubscription} 
              className="mt-3 bg-green-600 hover:bg-green-700"
            >
              Activate Subscription Now
            </Button>
          </div>
        )}
      </div>

      {/* Grant Trial to User */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-xl font-semibold text-gray-900 mb-4" style={{fontFamily: 'Inter, sans-serif'}}>Grant Trial to User</h3>
        <form onSubmit={handleGrantTrial} className="space-y-4">
          <div>
            <Label htmlFor="grantEmail">User Email</Label>
            <Input
              id="grantEmail"
              type="email"
              value={grantEmail}
              onChange={(e) => setGrantEmail(e.target.value)}
              placeholder="user@example.com"
              required
              data-testid="grant-email-input"
            />
          </div>
          <div>
            <Label htmlFor="grantDays">Trial Duration (days)</Label>
            <Input
              id="grantDays"
              type="number"
              min="1"
              max="365"
              value={grantDays}
              onChange={(e) => setGrantDays(parseInt(e.target.value))}
              required
              data-testid="grant-days-input"
            />
          </div>
          <Button type="submit" className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="grant-trial-button">
            Grant Trial Access
          </Button>
        </form>
      </div>

      {/* Trial Info */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h4 className="font-semibold text-blue-900 mb-2">Trial Management Tips</h4>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• New organizations automatically get a 14-day trial</li>
          <li>• Admins can grant trials to any user by their email address</li>
          <li>• Trials can be extended multiple times before activation</li>
          <li>• Activating subscription immediately ends the trial period</li>
          <li>• Users lose access when trial expires until subscription is activated</li>
        </ul>
      </div>
    </div>
  );
};

// User Management Component (Admin Only)
const UserManagement = () => {
  const [users, setUsers] = useState([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    role: "viewer",
    password: ""
  });

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await axios.get(`${API}/admin/users`);
      setUsers(response.data);
    } catch (error) {
      console.error("Failed to fetch users", error);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/admin/users`, formData);
      toast.success("User created successfully");
      setDialogOpen(false);
      setFormData({ name: "", email: "", role: "viewer", password: "" });
      fetchUsers();
    } catch (error) {
      toast.error("Failed to create user");
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!window.confirm("Are you sure you want to delete this user?")) return;
    try {
      await axios.delete(`${API}/admin/users/${userId}`);
      toast.success("User deleted successfully");
      fetchUsers();
    } catch (error) {
      toast.error("Failed to delete user");
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6" data-testid="user-management">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-xl font-semibold text-gray-900" style={{fontFamily: 'Inter, sans-serif'}}>User Management</h3>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="create-user-button">
              <Users size={20} weight="bold" className="mr-2" />
              Add User
            </Button>
          </DialogTrigger>
          <DialogContent data-testid="create-user-dialog">
            <DialogHeader>
              <DialogTitle>Create New User</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateUser} className="space-y-4 mt-4">
              <div>
                <Label htmlFor="userName">Full Name</Label>
                <Input
                  id="userName"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  data-testid="user-name-input"
                />
              </div>
              <div>
                <Label htmlFor="userEmail">Email</Label>
                <Input
                  id="userEmail"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  required
                  data-testid="user-email-input"
                />
              </div>
              <div>
                <Label htmlFor="userRole">Role</Label>
                <Select value={formData.role} onValueChange={(value) => setFormData({ ...formData, role: value })}>
                  <SelectTrigger data-testid="user-role-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">Admin</SelectItem>
                    <SelectItem value="auditor">Auditor</SelectItem>
                    <SelectItem value="manager">Manager</SelectItem>
                    <SelectItem value="viewer">Viewer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="userPassword">Temporary Password</Label>
                <Input
                  id="userPassword"
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  required
                  data-testid="user-password-input"
                />
              </div>
              <Button type="submit" className="w-full bg-[#2597B2] hover:bg-[#1B839F]" data-testid="submit-user-button">
                Create User
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="space-y-3">
        {users.length === 0 ? (
          <p className="text-center text-gray-500 py-8">No users found. Create your first user.</p>
        ) : (
          users.map((user) => (
            <div key={user.id} className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors" data-testid={`user-card-${user.id}`}>
              <div className="flex items-center space-x-4">
                <div className="w-10 h-10 bg-[#2597B2] bg-opacity-10 rounded-full flex items-center justify-center">
                  <User size={20} weight="duotone" className="text-[#2597B2]" />
                </div>
                <div>
                  <p className="font-semibold text-gray-900">{user.name}</p>
                  <p className="text-sm text-gray-500">{user.email}</p>
                </div>
              </div>
              <div className="flex items-center space-x-3">
                <span className="px-3 py-1 bg-blue-100 text-blue-700 text-xs rounded-full capitalize">
                  {user.roles?.[0]?.role || "N/A"}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDeleteUser(user.id)}
                  className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  data-testid={`delete-user-${user.id}`}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

// Organization Settings Component (Admin Only)
const OrganizationSettings = () => {
  const [orgSettings, setOrgSettings] = useState({
    name: "Test Organization",
    industry: "Financial Services",
    size: "51-200",
    country: "United States"
  });

  const handleUpdate = async (e) => {
    e.preventDefault();
    try {
      await axios.put(`${API}/admin/organization`, orgSettings);
      toast.success("Organization settings updated");
    } catch (error) {
      toast.error("Failed to update organization settings");
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6" data-testid="organization-settings">
      <h3 className="text-xl font-semibold text-gray-900 mb-4" style={{fontFamily: 'Inter, sans-serif'}}>Organization Settings</h3>
      <form onSubmit={handleUpdate} className="space-y-4">
        <div>
          <Label htmlFor="orgName">Organization Name</Label>
          <Input
            id="orgName"
            value={orgSettings.name}
            onChange={(e) => setOrgSettings({ ...orgSettings, name: e.target.value })}
            data-testid="org-name-input"
          />
        </div>
        <div>
          <Label htmlFor="industry">Industry</Label>
          <Select value={orgSettings.industry} onValueChange={(value) => setOrgSettings({ ...orgSettings, industry: value })}>
            <SelectTrigger data-testid="industry-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Financial Services">Financial Services</SelectItem>
              <SelectItem value="Healthcare">Healthcare</SelectItem>
              <SelectItem value="Technology">Technology</SelectItem>
              <SelectItem value="Manufacturing">Manufacturing</SelectItem>
              <SelectItem value="Retail">Retail</SelectItem>
              <SelectItem value="Government">Government</SelectItem>
              <SelectItem value="Other">Other</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="size">Company Size</Label>
          <Select value={orgSettings.size} onValueChange={(value) => setOrgSettings({ ...orgSettings, size: value })}>
            <SelectTrigger data-testid="size-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1-10">1-10 employees</SelectItem>
              <SelectItem value="11-50">11-50 employees</SelectItem>
              <SelectItem value="51-200">51-200 employees</SelectItem>
              <SelectItem value="201-500">201-500 employees</SelectItem>
              <SelectItem value="501-1000">501-1000 employees</SelectItem>
              <SelectItem value="1000+">1000+ employees</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="country">Country</Label>
          <Input
            id="country"
            value={orgSettings.country}
            onChange={(e) => setOrgSettings({ ...orgSettings, country: e.target.value })}
            data-testid="country-input"
          />
        </div>
        <Button type="submit" className="bg-[#2597B2] hover:bg-[#1B839F]" data-testid="update-org-button">
          Update Organization
        </Button>
      </form>
    </div>
  );
};

// Security Settings Component (Admin Only)
const SecuritySettings = () => {
  const [securitySettings, setSecuritySettings] = useState({
    mfaRequired: false,
    sessionTimeout: "30",
    passwordExpiry: "90",
    ipWhitelist: false,
    auditLogging: true
  });

  const handleToggle = (key) => {
    setSecuritySettings({ ...securitySettings, [key]: !securitySettings[key] });
    toast.success("Security settings updated");
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6" data-testid="security-settings">
      <h3 className="text-xl font-semibold text-gray-900 mb-4" style={{fontFamily: 'Inter, sans-serif'}}>Security Settings</h3>
      <div className="space-y-6">
        <div className="flex items-center justify-between py-3 border-b border-gray-100">
          <div>
            <p className="font-semibold text-gray-900">Multi-Factor Authentication (MFA)</p>
            <p className="text-sm text-gray-500">Require MFA for all users</p>
          </div>
          <Switch
            checked={securitySettings.mfaRequired}
            onCheckedChange={() => handleToggle('mfaRequired')}
            data-testid="toggle-mfa"
          />
        </div>

        <div>
          <Label htmlFor="sessionTimeout">Session Timeout (minutes)</Label>
          <Input
            id="sessionTimeout"
            type="number"
            value={securitySettings.sessionTimeout}
            onChange={(e) => setSecuritySettings({ ...securitySettings, sessionTimeout: e.target.value })}
            data-testid="session-timeout-input"
          />
        </div>

        <div>
          <Label htmlFor="passwordExpiry">Password Expiry (days)</Label>
          <Input
            id="passwordExpiry"
            type="number"
            value={securitySettings.passwordExpiry}
            onChange={(e) => setSecuritySettings({ ...securitySettings, passwordExpiry: e.target.value })}
            data-testid="password-expiry-input"
          />
        </div>

        <div className="flex items-center justify-between py-3 border-b border-gray-100">
          <div>
            <p className="font-semibold text-gray-900">IP Whitelist</p>
            <p className="text-sm text-gray-500">Restrict access to specific IP addresses</p>
          </div>
          <Switch
            checked={securitySettings.ipWhitelist}
            onCheckedChange={() => handleToggle('ipWhitelist')}
            data-testid="toggle-ip-whitelist"
          />
        </div>

        <div className="flex items-center justify-between py-3 border-b border-gray-100">
          <div>
            <p className="font-semibold text-gray-900">Audit Logging</p>
            <p className="text-sm text-gray-500">Log all user activities</p>
          </div>
          <Switch
            checked={securitySettings.auditLogging}
            onCheckedChange={() => handleToggle('auditLogging')}
            data-testid="toggle-audit-logging"
          />
        </div>
      </div>
    </div>
  );
};

// System Settings Component (Admin Only)
const SystemSettings = () => {
  const [systemSettings, setSystemSettings] = useState({
    autoBackup: true,
    backupFrequency: "daily",
    dataRetention: "365",
    apiRateLimit: "1000"
  });

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6" data-testid="system-settings">
      <h3 className="text-xl font-semibold text-gray-900 mb-4" style={{fontFamily: 'Inter, sans-serif'}}>System Configuration</h3>
      <div className="space-y-6">
        <div className="flex items-center justify-between py-3 border-b border-gray-100">
          <div>
            <p className="font-semibold text-gray-900">Automatic Backups</p>
            <p className="text-sm text-gray-500">Enable automated database backups</p>
          </div>
          <Switch
            checked={systemSettings.autoBackup}
            onCheckedChange={(checked) => {
              setSystemSettings({ ...systemSettings, autoBackup: checked });
              toast.success("System settings updated");
            }}
            data-testid="toggle-auto-backup"
          />
        </div>

        <div>
          <Label htmlFor="backupFrequency">Backup Frequency</Label>
          <Select 
            value={systemSettings.backupFrequency} 
            onValueChange={(value) => setSystemSettings({ ...systemSettings, backupFrequency: value })}
          >
            <SelectTrigger data-testid="backup-frequency-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="hourly">Hourly</SelectItem>
              <SelectItem value="daily">Daily</SelectItem>
              <SelectItem value="weekly">Weekly</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label htmlFor="dataRetention">Data Retention Period (days)</Label>
          <Input
            id="dataRetention"
            type="number"
            value={systemSettings.dataRetention}
            onChange={(e) => setSystemSettings({ ...systemSettings, dataRetention: e.target.value })}
            data-testid="data-retention-input"
          />
        </div>

        <div>
          <Label htmlFor="apiRateLimit">API Rate Limit (requests/hour)</Label>
          <Input
            id="apiRateLimit"
            type="number"
            value={systemSettings.apiRateLimit}
            onChange={(e) => setSystemSettings({ ...systemSettings, apiRateLimit: e.target.value })}
            data-testid="api-rate-limit-input"
          />
        </div>

        <div className="pt-4 border-t border-gray-200">
          <h4 className="font-semibold text-gray-900 mb-3">Danger Zone</h4>
          <Button 
            variant="destructive" 
            className="w-full"
            onClick={() => {
              if (window.confirm("Are you sure you want to reset all settings to default?")) {
                toast.success("Settings reset to default");
              }
            }}
            data-testid="reset-settings-button"
          >
            Reset All Settings to Default
          </Button>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;