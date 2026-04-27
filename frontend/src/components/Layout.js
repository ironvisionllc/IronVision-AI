import React, { useContext, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { AuthContext } from "@/App";
import { Button } from "@/components/ui/button";
import axios from "axios";
import { API } from "@/App";
import {
  House,
  FileText,
  Warning,
  Users,
  Calendar,
  SignOut,
  ListChecks,
  Bell,
  CaretLeft,
  CaretRight,
  Moon,
  Sun,
  ShieldCheck,
  Gear,
  Eye,
  Plugs,
  MagnifyingGlass,
  BookOpen,
  GitBranch,
  ChartBar,
  Code,
  CloudArrowDown,
  Upload,
  Bug,
  Buildings,
  HardDrives
} from "@phosphor-icons/react";

const SIDEBAR_NAV = [
  { section: "COMMAND CENTER" },
  { name: "Dashboard", href: "/dashboard", icon: House },
  { section: "GOVERNANCE" },
  { name: "Frameworks", href: "/frameworks", icon: ShieldCheck },
  { name: "Policy Center", href: "/policies", icon: FileText },
  { name: "Compliance Ingestion", href: "/ingestion", icon: Upload },
  { section: "SECURITY" },
  { name: "SIEM", href: "/siem", icon: Eye },
  { name: "Asset Inventory", href: "/assets", icon: HardDrives },
  { name: "DevSecOps Pipeline", href: "/pipeline", icon: GitBranch },
  { name: "Tenable VM", href: "/tenable", icon: Bug },
  { section: "RISK & COMPLIANCE" },
  { name: "Risk Scoring", href: "/risk-scoring", icon: ChartBar },
  { name: "Evidence Collection", href: "/evidence", icon: CloudArrowDown },
  { name: "Policy-as-Code", href: "/policy-engine", icon: Code },
  { name: "Vendor Risk", href: "/vendors", icon: Buildings },
  { section: "OPERATIONS" },
  { name: "Tasks", href: "/tasks", icon: ListChecks },
  { name: "Integrations", href: "/integrations", icon: Plugs },
  { name: "Documentation", href: "/documentation", icon: BookOpen },
  { name: "Settings", href: "/settings", icon: Gear },
];

const Layout = ({ children }) => {
  const { user, logout } = useContext(AuthContext);
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showNotifs, setShowNotifs] = useState(false);
  const [trialStatus, setTrialStatus] = useState(null);

  const isDemo = user?.is_demo;

  useEffect(() => {
    fetchUnreadCount();
    fetchTrialStatus();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (darkMode) document.documentElement.classList.add("dark");
    else document.documentElement.classList.remove("dark");
  }, [darkMode]);

  const fetchTrialStatus = async () => {
    try { const r = await axios.get(`${API}/admin/trial/status`); setTrialStatus(r.data); } catch {}
  };
  const fetchUnreadCount = async () => {
    try { const r = await axios.get(`${API}/notifications/unread-count`); setUnreadCount(r.data.unread_count); } catch {}
  };
  const openNotifications = async () => {
    setShowNotifs(!showNotifs);
    if (!showNotifs) { try { const r = await axios.get(`${API}/notifications`); setNotifications(r.data); } catch {} }
  };
  const markRead = async (id) => {
    await axios.put(`${API}/notifications/${id}/read`).catch(() => {});
    setNotifications(p => p.map(n => n.id === id ? {...n, read: true} : n));
    setUnreadCount(p => Math.max(0, p - 1));
  };
  const markAllRead = async () => {
    await axios.put(`${API}/notifications/read-all`).catch(() => {});
    setNotifications(p => p.map(n => ({...n, read: true})));
    setUnreadCount(0);
  };

  const getUserInitials = () => {
    const n = user?.name || "U";
    return n.split(" ").map(p => p[0]).join("").slice(0, 2).toUpperCase();
  };

  return (
    <div className="min-h-screen bg-[#f8fafb] dark:bg-gray-900 flex">
      {/* Sidebar */}
      <aside
        className={`hidden lg:flex lg:flex-shrink-0 sticky top-0 h-screen flex-col transition-all duration-300 ease-out z-30 ${collapsed ? "w-[72px]" : "w-[260px]"}`}
        data-testid="sidebar"
      >
        <div className="flex flex-1 flex-col overflow-hidden bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm border-r border-gray-200/50 dark:border-gray-700/50">
          {/* Logo */}
          <div className={`flex items-center border-b border-gray-200/50 dark:border-gray-700/50 ${collapsed ? "justify-center px-3 py-4" : "px-5 py-4"}`}>
            <Link to="/dashboard" className="flex items-center hover:opacity-80 transition-opacity">
              {collapsed ? (
                <img src="/ironvision-favicon.png" alt="IV" className="h-8 w-8 rounded" />
              ) : (
                <img
                  src={darkMode ? "/ironvision-logo-dark.png" : "/ironvision-logo.png"}
                  alt="IronVision AI"
                  className="h-9 w-auto"
                  data-testid="ironvision-logo"
                />
              )}
            </Link>
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto pt-3 pb-3 px-3" data-testid="sidebar-nav">
            {SIDEBAR_NAV.map((item, idx) => {
              if (item.section) {
                if (collapsed) return null;
                return (
                  <p key={idx} className="px-3 pt-5 pb-1.5 text-[0.625rem] font-bold uppercase tracking-[0.15em] text-gray-400 dark:text-gray-500">
                    {item.section}
                  </p>
                );
              }
              const isActive = location.pathname === item.href || location.pathname.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  to={item.href}
                  data-testid={`nav-${item.href.slice(1)}`}
                  className={`group flex items-center ${collapsed ? "justify-center px-2" : "px-3"} py-2.5 text-sm rounded-xl transition-all duration-200 ease-out mb-0.5 ${
                    isActive
                      ? "bg-[#e8f4f7] dark:bg-[#0a3540] text-[#1B839F] dark:text-[#47a7bf] font-semibold shadow-sm"
                      : "text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 hover:text-[#1B839F]"
                  }`}
                  title={collapsed ? item.name : undefined}
                >
                  <item.icon
                    size={20}
                    weight={isActive ? "duotone" : "regular"}
                    className={`flex-shrink-0 ${isActive ? "text-[#1B839F]" : "text-gray-400 group-hover:text-[#1B839F]"}`}
                  />
                  {!collapsed && <span className="ml-3 truncate">{item.name}</span>}
                </Link>
              );
            })}
          </nav>

          {/* Bottom Section */}
          <div className="border-t border-gray-200/50 dark:border-gray-700/50 p-3 space-y-2">
            {/* Search shortcut */}
            <button
              onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
              className={`flex items-center ${collapsed ? "justify-center" : ""} w-full px-3 py-2 text-sm rounded-xl text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors`}
              data-testid="search-shortcut-btn"
            >
              <MagnifyingGlass size={18} />
              {!collapsed && <span className="ml-3 flex-1 text-left">Search</span>}
              {!collapsed && <kbd className="text-[10px] text-gray-400 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded border border-gray-200 dark:border-gray-700">⌘K</kbd>}
            </button>
            {/* Dark Mode Toggle */}
            <button
              onClick={() => setDarkMode(!darkMode)}
              className={`flex items-center ${collapsed ? "justify-center" : ""} w-full px-3 py-2 text-sm rounded-xl text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors`}
              data-testid="dark-mode-toggle"
            >
              {darkMode ? <Sun size={18} weight="duotone" /> : <Moon size={18} />}
              {!collapsed && <span className="ml-3">{darkMode ? "Light Mode" : "Dark Mode"}</span>}
            </button>
            {/* Collapse Toggle */}
            <button
              onClick={() => setCollapsed(!collapsed)}
              className={`flex items-center ${collapsed ? "justify-center" : ""} w-full px-3 py-2 text-sm rounded-xl text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors`}
              data-testid="sidebar-collapse-toggle"
            >
              {collapsed ? <CaretRight size={18} /> : <CaretLeft size={18} />}
              {!collapsed && <span className="ml-3">Collapse</span>}
            </button>
            {/* User Info + Logout */}
            <div className={`flex items-center ${collapsed ? "justify-center" : ""} px-2 py-2`}>
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#2597B2] to-[#1B839F] flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                {getUserInitials()}
              </div>
              {!collapsed && (
                <div className="ml-3 flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{user?.name}</p>
                  <p className="text-xs text-gray-400 truncate">{user?.email}</p>
                </div>
              )}
              {!collapsed && (
                <button
                  onClick={logout}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                  data-testid="logout-button"
                  title="Sign Out"
                >
                  <SignOut size={16} />
                </button>
              )}
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-h-screen min-w-0">
        {/* Top Header Bar */}
        <header className="sticky top-0 z-20 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-200/50 dark:border-gray-700/50" data-testid="top-header">
          <div className="flex items-center justify-between h-14 px-6">
            {/* Mobile logo */}
            <div className="lg:hidden">
              <img src="/ironvision-favicon.png" alt="IV" className="h-7 w-7 rounded" />
            </div>
            <div className="hidden lg:block" />

            <div className="flex items-center space-x-3">
              {isDemo && (
                <div className="px-3 py-1 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-full" data-testid="demo-mode-badge">
                  <p className="text-xs font-semibold text-amber-700 dark:text-amber-400">Demo Mode</p>
                </div>
              )}
              {!isDemo && trialStatus?.is_trial_active && (
                <div className="px-3 py-1 bg-blue-50 border border-blue-200 rounded-full" data-testid="trial-badge">
                  <p className="text-xs font-semibold text-blue-700">Trial: {trialStatus.days_remaining}d</p>
                </div>
              )}

              {/* Notification Bell */}
              <div className="relative" data-testid="notifications-wrapper">
                <button
                  onClick={openNotifications}
                  className="relative p-2 rounded-xl text-gray-500 hover:text-[#1B839F] hover:bg-[#e8f4f7] dark:hover:bg-gray-800 transition-colors"
                  data-testid="notifications-bell"
                >
                  <Bell size={20} weight={unreadCount > 0 ? "fill" : "regular"} />
                  {unreadCount > 0 && (
                    <span className="absolute top-0.5 right-0.5 min-w-[16px] h-[16px] bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center" data-testid="notifications-badge">
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  )}
                </button>
                {showNotifs && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setShowNotifs(false)} />
                    <div className="absolute right-0 top-full mt-2 w-80 bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-xl z-50 max-h-[420px] overflow-hidden" data-testid="notifications-dropdown">
                      <div className="flex items-center justify-between p-4 border-b border-gray-100 dark:border-gray-700">
                        <h4 className="text-sm font-bold text-gray-900 dark:text-gray-100">Notifications</h4>
                        {unreadCount > 0 && (
                          <button onClick={markAllRead} className="text-xs text-[#1B839F] hover:underline font-medium" data-testid="mark-all-read">Mark all read</button>
                        )}
                      </div>
                      <div className="overflow-y-auto max-h-[350px]">
                        {notifications.length === 0 ? (
                          <div className="p-8 text-center">
                            <Bell size={28} weight="duotone" className="text-gray-300 mx-auto mb-2" />
                            <p className="text-sm text-gray-400">No notifications yet</p>
                          </div>
                        ) : notifications.map(n => (
                          <div
                            key={n.id}
                            className={`flex items-start gap-3 p-3.5 border-b border-gray-50 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors cursor-pointer ${!n.read ? "bg-[#e8f4f7]/40 dark:bg-[#0a3540]/30" : ""}`}
                            onClick={() => { if (!n.read) markRead(n.id); if (n.link) window.location.href = n.link; }}
                            data-testid={`notification-item-${n.id}`}
                          >
                            <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${!n.read ? "bg-[#2597B2]" : "bg-transparent"}`} />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{n.title}</p>
                              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">{n.message}</p>
                              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{formatNotifTime(n.created_at)}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-6 lg:p-8 max-w-[1400px] w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
};

function formatNotifTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  const now = new Date();
  const diff = Math.floor((now - d) / 60000);
  if (diff < 1) return "just now";
  if (diff < 60) return `${diff}m ago`;
  const hr = Math.floor(diff / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default Layout;
