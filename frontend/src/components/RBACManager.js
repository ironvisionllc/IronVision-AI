import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  CaretLeft, ShieldCheck, Users, UserCircle, Crown, Eye, Wrench,
  ClipboardText, CaretDown
} from "@phosphor-icons/react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const ROLE_ICONS = {
  admin: Crown,
  auditor: ClipboardText,
  system_owner: ShieldCheck,
  remediation_engineer: Wrench,
  viewer: Eye,
};

const ROLE_COLORS = {
  admin: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  auditor: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  system_owner: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  remediation_engineer: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  viewer: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

const RBACManager = () => {
  const [roles, setRoles] = useState({});
  const [users, setUsers] = useState([]);
  const [myPerms, setMyPerms] = useState(null);
  const [loading, setLoading] = useState(true);
  const [changingRole, setChangingRole] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [rolesRes, usersRes, permsRes] = await Promise.all([
        axios.get(`${API}/rbac/roles`),
        axios.get(`${API}/rbac/users`),
        axios.get(`${API}/rbac/my-permissions`),
      ]);
      setRoles(rolesRes.data);
      setUsers(usersRes.data);
      setMyPerms(permsRes.data);
    } catch {
      toast.error("Failed to load RBAC data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const assignRole = async (userId, newRole) => {
    setChangingRole(userId);
    try {
      await axios.put(`${API}/rbac/assign`, { user_id: userId, role: newRole });
      toast.success(`Role updated to ${newRole}`);
      fetchAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to assign role");
    } finally {
      setChangingRole(null);
    }
  };

  const isAdmin = myPerms?.role === "admin";

  if (loading) return <div className="text-center py-12 text-gray-400">Loading...</div>;

  return (
    <div data-testid="rbac-manager">
      <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-1">Role-Based Access Control</h3>
      <p className="text-sm text-gray-500 mb-6">Manage user roles and permissions across the platform</p>

      {/* Role Cards */}
      <div className="grid grid-cols-5 gap-3 mb-8" data-testid="role-cards">
        {Object.entries(roles).map(([key, role]) => {
          const Icon = ROLE_ICONS[key] || Users;
          const userCount = users.filter(u => u.role === key).length;
          return (
            <div key={key} className="iv-card p-4 text-center" data-testid={`role-card-${key}`}>
              <Icon size={24} className="mx-auto text-[#2597B2] mb-2" weight="duotone" />
              <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{role.label}</div>
              <div className="text-[10px] text-gray-500 mt-1 line-clamp-2">{role.description}</div>
              <div className="flex justify-center gap-2 mt-2">
                <span className="text-xs text-gray-400">{role.permission_count} perms</span>
                <span className="text-xs font-medium text-[#2597B2]">{userCount} users</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Users Table */}
      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Users</h4>
      <div className="space-y-2" data-testid="users-list">
        {users.map(user => {
          const roleColor = ROLE_COLORS[user.role] || ROLE_COLORS.viewer;
          const RoleIcon = ROLE_ICONS[user.role] || Eye;
          const isMe = user.id === myPerms?.user_id;
          return (
            <div key={user.id} className="iv-card p-4 flex items-center gap-4" data-testid={`user-row-${user.id}`}>
              <UserCircle size={32} className="text-gray-400" weight="duotone" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {user.name || user.email} {isMe && <span className="text-xs text-[#2597B2] ml-1">(You)</span>}
                </div>
                <div className="text-xs text-gray-500">{user.email}</div>
              </div>
              <span className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${roleColor}`}>
                <RoleIcon size={14} weight="fill" />
                {roles[user.role]?.label || user.role}
              </span>
              {isAdmin && !isMe && (
                <select
                  value={user.role}
                  onChange={e => assignRole(user.id, e.target.value)}
                  disabled={changingRole === user.id}
                  className="h-8 px-2 text-xs border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900"
                  data-testid={`role-select-${user.id}`}
                >
                  {Object.entries(roles).map(([key, r]) => (
                    <option key={key} value={key}>{r.label}</option>
                  ))}
                </select>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default RBACManager;
