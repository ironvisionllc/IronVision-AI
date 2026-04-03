import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { ClockCounterClockwise, FileText, Warning, CheckCircle, Shield, ArrowsClockwise, Users, GitBranch, FolderOpen, GraduationCap } from "@phosphor-icons/react";

const ACTION_ICONS = {
  task_created: { icon: CheckCircle, color: "#4ADE80", label: "Task Created" },
  task_updated: { icon: ArrowsClockwise, color: "#60A5FA", label: "Task Updated" },
  policy_created: { icon: FileText, color: "#2597B2", label: "Policy Created" },
  policy_updated: { icon: FileText, color: "#2597B2", label: "Policy Updated" },
  risk_created: { icon: Warning, color: "#FB923C", label: "Risk Created" },
  risk_updated: { icon: Warning, color: "#FB923C", label: "Risk Updated" },
  audit_created: { icon: Shield, color: "#60A5FA", label: "Audit Created" },
  vendor_created: { icon: Users, color: "#9333EA", label: "Vendor Added" },
  evidence_added: { icon: FolderOpen, color: "#2597B2", label: "Evidence Added" },
  mapping_created: { icon: GitBranch, color: "#60A5FA", label: "Mapping Created" },
  training_completed: { icon: GraduationCap, color: "#4ADE80", label: "Training Done" },
  default: { icon: ClockCounterClockwise, color: "#9CA3AF", label: "Action" },
};

const ActivityPage = () => {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterAction, setFilterAction] = useState("all");

  useEffect(() => { fetchActivities(); }, []);

  const fetchActivities = async () => {
    try {
      const res = await axios.get(`${API}/activity`);
      setActivities(res.data);
    } catch (error) {
      console.error("Failed to fetch activities", error);
    } finally {
      setLoading(false);
    }
  };

  const getActionInfo = (action) => ACTION_ICONS[action] || ACTION_ICONS.default;

  const formatTime = (ts) => {
    if (!ts) return "";
    const d = new Date(ts);
    const now = new Date();
    const diff = Math.floor((now - d) / 1000);
    if (diff < 60) return "Just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  };

  const getDateGroup = (ts) => {
    if (!ts) return "Unknown";
    const d = new Date(ts);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return "Today";
    if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
    return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  };

  // Filter
  const actionTypes = [...new Set(activities.map(a => a.action))];
  const filtered = filterAction === "all" ? activities : activities.filter(a => a.action === filterAction);

  // Group by date
  const grouped = {};
  filtered.forEach(a => {
    const group = getDateGroup(a.timestamp);
    if (!grouped[group]) grouped[group] = [];
    grouped[group].push(a);
  });

  if (loading) return <Layout><div className="flex items-center justify-center h-64"><p className="text-gray-500">Loading activity...</p></div></Layout>;

  return (
    <Layout>
      <div data-testid="activity-page">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Audit Trail</h1>
          <p className="text-sm text-gray-600 mt-2">Complete audit trail of all organizational actions</p>
        </div>

        {/* Filter */}
        <div className="flex items-center gap-2 mb-6 flex-wrap">
          <span className="text-sm text-gray-500">Filter:</span>
          <button onClick={() => setFilterAction("all")}
            className={`px-3 py-1 rounded-full text-xs font-semibold transition-all ${filterAction === "all" ? "bg-[#2597B2] text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
            data-testid="activity-filter-all">All</button>
          {actionTypes.map(at => {
            const info = getActionInfo(at);
            return (
              <button key={at} onClick={() => setFilterAction(at)}
                className={`px-3 py-1 rounded-full text-xs font-semibold transition-all ${filterAction === at ? "bg-[#2597B2] text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
                data-testid={`activity-filter-${at}`}>{info.label}</button>
            );
          })}
        </div>

        {filtered.length === 0 ? (
          <div className="bg-white rounded-lg border border-gray-200 p-12 text-center" data-testid="no-activity">
            <ClockCounterClockwise size={48} weight="duotone" className="text-gray-300 mx-auto mb-3" />
            <p className="text-gray-400 mb-1">No activity yet</p>
            <p className="text-sm text-gray-400">Actions performed in the platform will appear here</p>
          </div>
        ) : (
          <div className="space-y-6" data-testid="activity-list">
            {Object.entries(grouped).map(([date, items]) => (
              <div key={date}>
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-400 mb-3">{date}</p>
                <div className="relative pl-6">
                  {/* Timeline line */}
                  <div className="absolute left-[11px] top-0 bottom-0 w-px bg-gray-200"></div>
                  <div className="space-y-0">
                    {items.map((activity) => {
                      const info = getActionInfo(activity.action);
                      const Icon = info.icon;
                      return (
                        <div key={activity.id} className="relative flex items-start gap-3 py-3" data-testid={`activity-item-${activity.id}`}>
                          {/* Timeline dot */}
                          <div className="absolute -left-6 top-3.5 w-[22px] h-[22px] rounded-full flex items-center justify-center bg-white border-2" style={{ borderColor: info.color }}>
                            <Icon size={11} weight="bold" style={{ color: info.color }} />
                          </div>
                          <div className="flex-1 min-w-0 bg-white rounded-lg border border-gray-100 p-3 hover:border-gray-200 transition-colors">
                            <div className="flex items-center justify-between">
                              <p className="text-sm text-gray-900">
                                <span className="font-semibold">{activity.user_name || "System"}</span>{" "}
                                <span className="text-gray-600">{activity.details}</span>
                              </p>
                              <span className="text-xs text-gray-400 ml-3 flex-shrink-0">{formatTime(activity.timestamp)}</span>
                            </div>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ color: info.color, backgroundColor: `${info.color}12` }}>{info.label}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
};

export default ActivityPage;
