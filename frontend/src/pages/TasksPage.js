import React, { useState, useEffect, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { useDemo } from "@/hooks/use-demo";
import { Plus, CheckCircle, Clock, Trash, PencilSimple, FunnelSimple, ArrowsClockwise, Kanban, List, CalendarBlank, User, Tag } from "@phosphor-icons/react";

const STATUSES = [
  { value: "todo", label: "To Do", color: "#94A3B8", bg: "rgba(148, 163, 184, 0.1)", border: "border-slate-200" },
  { value: "in_progress", label: "In Progress", color: "#3B82F6", bg: "rgba(59, 130, 246, 0.1)", border: "border-blue-200" },
  { value: "review", label: "Review", color: "#F59E0B", bg: "rgba(245, 158, 11, 0.1)", border: "border-amber-200" },
  { value: "done", label: "Done", color: "#10B981", bg: "rgba(16, 185, 129, 0.1)", border: "border-emerald-200" },
];

const PRIORITIES = [
  { value: "low", label: "Low", color: "#10B981", bg: "rgba(16, 185, 129, 0.1)" },
  { value: "medium", label: "Medium", color: "#3B82F6", bg: "rgba(59, 130, 246, 0.1)" },
  { value: "high", label: "High", color: "#F59E0B", bg: "rgba(245, 158, 11, 0.1)" },
  { value: "critical", label: "Critical", color: "#EF4444", bg: "rgba(239, 68, 68, 0.1)" },
];

const TasksPage = () => {
  const { user } = useContext(AuthContext);
  const { guardDemo } = useDemo();
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editTask, setEditTask] = useState(null);
  const [filterStatus, setFilterStatus] = useState("all");
  const [viewMode, setViewMode] = useState("list");
  const [form, setForm] = useState({ title: "", description: "", status: "todo", priority: "medium", assignee_id: "", due_date: "", tags: "" });

  useEffect(() => { fetchData(); }, []);

  const fetchData = async () => {
    try {
      const [tasksRes, statsRes, usersRes] = await Promise.all([
        axios.get(`${API}/tasks`),
        axios.get(`${API}/tasks/stats`),
        axios.get(`${API}/admin/users`).catch(() => ({ data: [] }))
      ]);
      setTasks(tasksRes.data);
      setStats(statsRes.data);
      setUsers(Array.isArray(usersRes.data) ? usersRes.data : []);
    } catch (error) {
      console.error("Failed to fetch tasks", error);
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => setForm({ title: "", description: "", status: "todo", priority: "medium", assignee_id: "", due_date: "", tags: "" });

  const handleCreate = async () => {
    if (guardDemo()) return;
    if (!form.title.trim()) { toast.error("Title is required"); return; }
    try {
      const payload = { ...form, tags: form.tags ? form.tags.split(",").map(t => t.trim()).filter(Boolean) : [] };
      await axios.post(`${API}/tasks`, payload);
      toast.success("Task created");
      setShowCreate(false);
      resetForm();
      fetchData();
    } catch (error) {
      toast.error("Failed to create task");
    }
  };

  const handleUpdate = async () => {
    if (guardDemo()) return;
    try {
      const payload = { ...form, tags: form.tags ? form.tags.split(",").map(t => t.trim()).filter(Boolean) : [] };
      await axios.put(`${API}/tasks/${editTask.id}`, payload);
      toast.success("Task updated");
      setEditTask(null);
      resetForm();
      fetchData();
    } catch (error) {
      toast.error("Failed to update task");
    }
  };

  const handleDelete = async (id) => {
    if (guardDemo()) return;
    try {
      await axios.delete(`${API}/tasks/${id}`);
      toast.success("Task deleted");
      fetchData();
    } catch (error) {
      toast.error("Failed to delete task");
    }
  };

  const handleStatusChange = async (task, newStatus) => {
    if (guardDemo()) return;
    try {
      await axios.put(`${API}/tasks/${task.id}`, { ...task, status: newStatus });
      fetchData();
    } catch (error) {
      toast.error("Failed to update status");
    }
  };

  const openEdit = (task) => {
    setForm({
      title: task.title,
      description: task.description || "",
      status: task.status,
      priority: task.priority,
      assignee_id: task.assignee_id || "",
      due_date: task.due_date || "",
      tags: (task.tags || []).join(", ")
    });
    setEditTask(task);
  };

  const filtered = filterStatus === "all" ? tasks : tasks.filter(t => t.status === filterStatus);
  const isAdmin = user?.roles?.[0]?.role === "admin";

  const getPriorityStyle = (p) => PRIORITIES.find(pr => pr.value === p) || PRIORITIES[1];
  const getStatusStyle = (s) => STATUSES.find(st => st.value === s) || STATUSES[0];

  const TaskForm = ({ onSubmit, submitLabel }) => (
    <div className="space-y-5">
      <div>
        <Label className="text-sm font-medium text-gray-700">Title *</Label>
        <Input value={form.title} onChange={e => setForm({...form, title: e.target.value})} className="mt-1.5 h-11" placeholder="Task title" data-testid="task-title-input" />
      </div>
      <div>
        <Label className="text-sm font-medium text-gray-700">Description</Label>
        <textarea 
          value={form.description} 
          onChange={e => setForm({...form, description: e.target.value})} 
          className="mt-1.5 w-full min-h-[100px] rounded-xl border border-gray-200 px-4 py-3 text-sm focus:border-[#2597B2] focus:ring-2 focus:ring-[#2597B2]/20 transition-all resize-none" 
          placeholder="Describe the task..." 
          data-testid="task-description-input" 
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label className="text-sm font-medium text-gray-700">Status</Label>
          <Select value={form.status} onValueChange={v => setForm({...form, status: v})}>
            <SelectTrigger className="mt-1.5 h-11" data-testid="task-status-select"><SelectValue /></SelectTrigger>
            <SelectContent>{STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-sm font-medium text-gray-700">Priority</Label>
          <Select value={form.priority} onValueChange={v => setForm({...form, priority: v})}>
            <SelectTrigger className="mt-1.5 h-11" data-testid="task-priority-select"><SelectValue /></SelectTrigger>
            <SelectContent>{PRIORITIES.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label className="text-sm font-medium text-gray-700">Assignee</Label>
          <Select value={form.assignee_id} onValueChange={v => setForm({...form, assignee_id: v})}>
            <SelectTrigger className="mt-1.5 h-11" data-testid="task-assignee-select"><SelectValue placeholder="Unassigned" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Unassigned</SelectItem>
              {users.map(u => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-sm font-medium text-gray-700">Due Date</Label>
          <Input type="date" value={form.due_date} onChange={e => setForm({...form, due_date: e.target.value})} className="mt-1.5 h-11" data-testid="task-duedate-input" />
        </div>
      </div>
      <div>
        <Label className="text-sm font-medium text-gray-700">Tags</Label>
        <Input value={form.tags} onChange={e => setForm({...form, tags: e.target.value})} className="mt-1.5 h-11" placeholder="compliance, audit, urgent" data-testid="task-tags-input" />
      </div>
      <Button onClick={onSubmit} className="w-full iv-btn-primary h-11" data-testid="task-submit-button">{submitLabel}</Button>
    </div>
  );

  // Skeleton loader
  const SkeletonCard = () => (
    <div className="iv-card p-4 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="w-3 h-3 rounded-full bg-gray-200 mt-1.5" />
        <div className="flex-1 space-y-2">
          <div className="h-5 bg-gray-200 rounded w-3/4" />
          <div className="h-4 bg-gray-100 rounded w-1/2" />
          <div className="flex gap-2">
            <div className="h-6 bg-gray-100 rounded w-16" />
            <div className="h-6 bg-gray-100 rounded w-20" />
          </div>
        </div>
      </div>
    </div>
  );

  if (loading) return (
    <Layout>
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <div className="space-y-2">
            <div className="h-8 bg-gray-200 rounded w-32 animate-pulse" />
            <div className="h-4 bg-gray-100 rounded w-48 animate-pulse" />
          </div>
        </div>
        <div className="grid grid-cols-5 gap-4">
          {[1,2,3,4,5].map(i => <div key={i} className="h-20 bg-gray-100 rounded-xl animate-pulse" />)}
        </div>
        <div className="space-y-3">
          {[1,2,3].map(i => <SkeletonCard key={i} />)}
        </div>
      </div>
    </Layout>
  );

  return (
    <Layout>
      <div data-testid="tasks-page" className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">Tasks</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Manage compliance tasks and remediation workflows</p>
          </div>
          <Dialog open={showCreate} onOpenChange={v => { if (v && guardDemo()) return; setShowCreate(v); if (!v) resetForm(); }}>
            <DialogTrigger asChild>
              <Button className="iv-btn-primary" data-testid="create-task-button">
                <Plus size={18} weight="bold" /> New Task
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader><DialogTitle className="text-xl font-semibold">Create Task</DialogTitle></DialogHeader>
              <div className="mt-4">
                <TaskForm onSubmit={handleCreate} submitLabel="Create Task" />
              </div>
            </DialogContent>
          </Dialog>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {[
              { label: "Total", val: stats.total, icon: FunnelSimple, color: "#2597B2" },
              { label: "To Do", val: stats.todo, icon: Clock, color: "#94A3B8" },
              { label: "In Progress", val: stats.in_progress, icon: ArrowsClockwise, color: "#3B82F6" },
              { label: "Done", val: stats.done, icon: CheckCircle, color: "#10B981" },
              { label: "Overdue", val: stats.overdue, icon: Clock, color: "#EF4444" },
            ].map(s => (
              <div 
                key={s.label} 
                className="iv-stat-card"
                style={{ '--stat-color': s.color }}
                data-testid={`task-stat-${s.label.toLowerCase().replace(' ', '-')}`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-label">{s.label}</p>
                    <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-1">{s.val}</p>
                  </div>
                  <div 
                    className="w-10 h-10 rounded-xl flex items-center justify-center"
                    style={{ backgroundColor: `${s.color}15` }}
                  >
                    <s.icon size={20} weight="duotone" style={{ color: s.color }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Filter Bar */}
        <div className="iv-card p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 font-medium mr-2">Filter:</span>
              {[{ value: "all", label: "All" }, ...STATUSES].map(s => (
                <button 
                  key={s.value} 
                  onClick={() => setFilterStatus(s.value)}
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all duration-200 ${
                    filterStatus === s.value 
                      ? "bg-[#2597B2] text-white shadow-sm" 
                      : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
                  }`}
                  data-testid={`filter-${s.value}`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">{filtered.length} tasks</span>
              <div className="flex items-center border border-gray-200 rounded-lg overflow-hidden">
                <button 
                  onClick={() => setViewMode("list")}
                  className={`p-2 ${viewMode === 'list' ? 'bg-gray-100 text-[#2597B2]' : 'text-gray-400 hover:bg-gray-50'}`}
                >
                  <List size={18} />
                </button>
                <button 
                  onClick={() => setViewMode("kanban")}
                  className={`p-2 ${viewMode === 'kanban' ? 'bg-gray-100 text-[#2597B2]' : 'text-gray-400 hover:bg-gray-50'}`}
                >
                  <Kanban size={18} />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Task List View */}
        {viewMode === "list" && (
          <div className="space-y-3" data-testid="tasks-list">
            {filtered.length === 0 ? (
              <div className="iv-card p-12">
                <div className="iv-empty-state">
                  <div className="iv-empty-state-icon">
                    <CheckCircle size={28} weight="duotone" className="text-gray-400" />
                  </div>
                  <p className="iv-empty-state-title">No tasks found</p>
                  <p className="iv-empty-state-description">Create your first task to get started</p>
                </div>
              </div>
            ) : filtered.map(task => {
              const priority = getPriorityStyle(task.priority);
              const status = getStatusStyle(task.status);
              const isOverdue = task.due_date && task.due_date < new Date().toISOString().slice(0, 10) && task.status !== "done";
              
              return (
                <div 
                  key={task.id} 
                  className={`iv-card p-4 transition-all duration-200 hover:shadow-md ${status.border}`}
                  data-testid={`task-card-${task.id}`}
                >
                  <div className="flex items-start gap-4">
                    {/* Priority Indicator */}
                    <div 
                      className="w-1.5 h-12 rounded-full flex-shrink-0 mt-0.5"
                      style={{ backgroundColor: priority.color }}
                    />
                    
                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate">{task.title}</h3>
                            {isOverdue && (
                              <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-semibold rounded-full border border-red-200 flex items-center gap-1">
                                <Clock size={10} weight="fill" /> Overdue
                              </span>
                            )}
                          </div>
                          {task.description && (
                            <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-1">{task.description}</p>
                          )}
                          
                          {/* Meta */}
                          <div className="flex flex-wrap items-center gap-2 mt-3">
                            <span 
                              className="iv-badge border"
                              style={{ backgroundColor: status.bg, color: status.color, borderColor: `${status.color}30` }}
                            >
                              {status.label}
                            </span>
                            <span 
                              className="iv-badge border"
                              style={{ backgroundColor: priority.bg, color: priority.color, borderColor: `${priority.color}30` }}
                            >
                              {priority.label}
                            </span>
                            {task.assignee_name && (
                              <span className="iv-badge iv-badge-neutral">
                                <User size={12} /> {task.assignee_name}
                              </span>
                            )}
                            {task.due_date && (
                              <span className="iv-badge iv-badge-neutral">
                                <CalendarBlank size={12} /> {task.due_date}
                              </span>
                            )}
                            {(task.tags || []).map(tag => (
                              <span key={tag} className="iv-badge iv-badge-neutral">
                                <Tag size={10} /> {tag}
                              </span>
                            ))}
                          </div>
                        </div>
                        
                        {/* Actions */}
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {task.status !== "done" && (
                            <Select value={task.status} onValueChange={v => handleStatusChange(task, v)}>
                              <SelectTrigger className="h-9 w-[130px] text-xs" data-testid={`task-status-change-${task.id}`}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                              </SelectContent>
                            </Select>
                          )}
                          <Button 
                            variant="ghost" 
                            size="icon" 
                            className="h-9 w-9 text-gray-400 hover:text-[#2597B2] hover:bg-[#2597B2]/10" 
                            onClick={() => openEdit(task)} 
                            data-testid={`task-edit-${task.id}`}
                          >
                            <PencilSimple size={16} />
                          </Button>
                          {isAdmin && (
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="h-9 w-9 text-gray-400 hover:text-red-500 hover:bg-red-50" 
                              onClick={() => handleDelete(task.id)} 
                              data-testid={`task-delete-${task.id}`}
                            >
                              <Trash size={16} />
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Kanban View */}
        {viewMode === "kanban" && (
          <div className="grid grid-cols-4 gap-4" data-testid="tasks-kanban">
            {STATUSES.map(status => {
              const statusTasks = tasks.filter(t => t.status === status.value);
              return (
                <div key={status.value} className="space-y-3">
                  <div 
                    className="flex items-center justify-between p-3 rounded-xl"
                    style={{ backgroundColor: status.bg }}
                  >
                    <span className="font-semibold text-sm" style={{ color: status.color }}>{status.label}</span>
                    <span 
                      className="text-xs font-bold px-2 py-0.5 rounded-full"
                      style={{ backgroundColor: status.color, color: 'white' }}
                    >
                      {statusTasks.length}
                    </span>
                  </div>
                  <div className="space-y-2 min-h-[200px]">
                    {statusTasks.map(task => {
                      const priority = getPriorityStyle(task.priority);
                      const isOverdue = task.due_date && task.due_date < new Date().toISOString().slice(0, 10) && task.status !== "done";
                      return (
                        <div 
                          key={task.id}
                          className="iv-card p-3 cursor-pointer hover:shadow-md transition-all"
                          onClick={() => openEdit(task)}
                        >
                          <div className="flex items-start gap-2">
                            <div 
                              className="w-1 h-8 rounded-full flex-shrink-0"
                              style={{ backgroundColor: priority.color }}
                            />
                            <div className="flex-1 min-w-0">
                              <h4 className="font-medium text-sm text-gray-900 dark:text-gray-100 line-clamp-2">{task.title}</h4>
                              <div className="flex items-center gap-2 mt-2">
                                <span 
                                  className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
                                  style={{ backgroundColor: priority.bg, color: priority.color }}
                                >
                                  {priority.label}
                                </span>
                                {isOverdue && (
                                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-red-100 text-red-600">
                                    Overdue
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Edit Dialog */}
        <Dialog open={!!editTask} onOpenChange={v => { if (!v) { setEditTask(null); resetForm(); } }}>
          <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle className="text-xl font-semibold">Edit Task</DialogTitle></DialogHeader>
            <div className="mt-4">
              <TaskForm onSubmit={handleUpdate} submitLabel="Save Changes" />
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default TasksPage;
