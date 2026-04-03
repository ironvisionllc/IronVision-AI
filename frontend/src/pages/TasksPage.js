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
import { Plus, CheckCircle, Clock, Eye, Trash, PencilSimple, FunnelSimple, ArrowsClockwise } from "@phosphor-icons/react";

const STATUSES = [
  { value: "todo", label: "To Do", color: "#9CA3AF", bg: "bg-gray-100" },
  { value: "in_progress", label: "In Progress", color: "#60A5FA", bg: "bg-blue-50" },
  { value: "review", label: "Review", color: "#FB923C", bg: "bg-orange-50" },
  { value: "done", label: "Done", color: "#4ADE80", bg: "bg-green-50" },
];

const PRIORITIES = [
  { value: "low", label: "Low", color: "#4ADE80" },
  { value: "medium", label: "Medium", color: "#60A5FA" },
  { value: "high", label: "High", color: "#FB923C" },
  { value: "critical", label: "Critical", color: "#EF4444" },
];

const TasksPage = () => {
  const { user } = useContext(AuthContext);
  const { isDemo, guardDemo } = useDemo();
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editTask, setEditTask] = useState(null);
  const [filterStatus, setFilterStatus] = useState("all");
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
    <div className="space-y-4">
      <div>
        <Label className="text-sm font-semibold text-gray-700">Title *</Label>
        <Input value={form.title} onChange={e => setForm({...form, title: e.target.value})} className="mt-1" placeholder="Task title" data-testid="task-title-input" />
      </div>
      <div>
        <Label className="text-sm font-semibold text-gray-700">Description</Label>
        <textarea value={form.description} onChange={e => setForm({...form, description: e.target.value})} className="mt-1 w-full min-h-[80px] rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="Describe the task..." data-testid="task-description-input" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label className="text-sm font-semibold text-gray-700">Status</Label>
          <Select value={form.status} onValueChange={v => setForm({...form, status: v})}>
            <SelectTrigger className="mt-1" data-testid="task-status-select"><SelectValue /></SelectTrigger>
            <SelectContent>{STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-sm font-semibold text-gray-700">Priority</Label>
          <Select value={form.priority} onValueChange={v => setForm({...form, priority: v})}>
            <SelectTrigger className="mt-1" data-testid="task-priority-select"><SelectValue /></SelectTrigger>
            <SelectContent>{PRIORITIES.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label className="text-sm font-semibold text-gray-700">Assignee</Label>
          <Select value={form.assignee_id} onValueChange={v => setForm({...form, assignee_id: v})}>
            <SelectTrigger className="mt-1" data-testid="task-assignee-select"><SelectValue placeholder="Unassigned" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Unassigned</SelectItem>
              {users.map(u => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-sm font-semibold text-gray-700">Due Date</Label>
          <Input type="date" value={form.due_date} onChange={e => setForm({...form, due_date: e.target.value})} className="mt-1" data-testid="task-duedate-input" />
        </div>
      </div>
      <div>
        <Label className="text-sm font-semibold text-gray-700">Tags</Label>
        <Input value={form.tags} onChange={e => setForm({...form, tags: e.target.value})} className="mt-1" placeholder="compliance, audit, urgent" data-testid="task-tags-input" />
      </div>
      <Button onClick={onSubmit} className="w-full bg-[#2597B2] hover:bg-[#1B839F] text-white" data-testid="task-submit-button">{submitLabel}</Button>
    </div>
  );

  if (loading) return <Layout><div className="flex items-center justify-center h-64"><p className="text-gray-500">Loading tasks...</p></div></Layout>;

  return (
    <Layout>
      <div data-testid="tasks-page">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Tasks</h1>
            <p className="text-sm text-gray-600 mt-2">Manage compliance tasks and remediation workflows</p>
          </div>
          <Dialog open={showCreate} onOpenChange={v => { if (v && guardDemo()) return; setShowCreate(v); if (!v) resetForm(); }}>
            <DialogTrigger asChild>
              <Button className="bg-[#2597B2] hover:bg-[#1B839F] text-white flex items-center gap-2" data-testid="create-task-button">
                <Plus size={18} weight="bold" /> New Task
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader><DialogTitle className="text-xl font-bold text-gray-900" style={{fontFamily: 'Inter, sans-serif'}}>Create Task</DialogTitle></DialogHeader>
              <TaskForm onSubmit={handleCreate} submitLabel="Create Task" />
            </DialogContent>
          </Dialog>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            {[
              { label: "Total", val: stats.total, icon: FunnelSimple, color: "#2597B2" },
              { label: "To Do", val: stats.todo, icon: Clock, color: "#9CA3AF" },
              { label: "In Progress", val: stats.in_progress, icon: ArrowsClockwise, color: "#60A5FA" },
              { label: "Done", val: stats.done, icon: CheckCircle, color: "#4ADE80" },
              { label: "Overdue", val: stats.overdue, icon: Clock, color: "#EF4444" },
            ].map(s => (
              <div key={s.label} className="bg-white rounded-lg border border-gray-200 p-4" data-testid={`task-stat-${s.label.toLowerCase().replace(' ', '-')}`}>
                <div className="flex items-center gap-2">
                  <s.icon size={18} weight="duotone" style={{ color: s.color }} />
                  <span className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-500">{s.label}</span>
                </div>
                <p className="text-2xl font-bold text-gray-900 mt-1">{s.val}</p>
              </div>
            ))}
          </div>
        )}

        {/* Filter */}
        <div className="flex items-center gap-2 mb-4">
          <span className="text-sm text-gray-500">Filter:</span>
          {[{ value: "all", label: "All" }, ...STATUSES].map(s => (
            <button key={s.value} onClick={() => setFilterStatus(s.value)}
              className={`px-3 py-1 rounded-full text-xs font-semibold transition-all duration-200 ${filterStatus === s.value ? "bg-[#2597B2] text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
              data-testid={`filter-${s.value}`}>{s.label}</button>
          ))}
        </div>

        {/* Task List */}
        <div className="space-y-3">
          {filtered.length === 0 ? (
            <div className="bg-white rounded-lg border border-gray-200 p-12 text-center" data-testid="no-tasks">
              <p className="text-gray-400 mb-2">No tasks found</p>
              <p className="text-sm text-gray-400">Create your first task to get started</p>
            </div>
          ) : filtered.map(task => {
            const priority = getPriorityStyle(task.priority);
            const status = getStatusStyle(task.status);
            const isOverdue = task.due_date && task.due_date < new Date().toISOString().slice(0, 10) && task.status !== "done";
            return (
              <div key={task.id} className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-sm hover:-translate-y-[1px] transition-all duration-200" data-testid={`task-card-${task.id}`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: priority.color }}></span>
                      <h3 className="font-semibold text-gray-900 truncate">{task.title}</h3>
                      {isOverdue && <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-semibold rounded-full">Overdue</span>}
                    </div>
                    {task.description && <p className="text-sm text-gray-500 line-clamp-1 ml-4">{task.description}</p>}
                    <div className="flex items-center gap-3 mt-2 ml-4">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${status.bg}`} style={{ color: status.color }}>{status.label}</span>
                      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-50" style={{ color: priority.color }}>{priority.label}</span>
                      {task.assignee_name && <span className="text-xs text-gray-500">{task.assignee_name}</span>}
                      {task.due_date && <span className="text-xs text-gray-400">{task.due_date}</span>}
                      {(task.tags || []).map(tag => <span key={tag} className="px-2 py-0.5 bg-gray-100 text-gray-500 rounded text-xs">{tag}</span>)}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-4">
                    {task.status !== "done" && (
                      <Select value={task.status} onValueChange={v => handleStatusChange(task, v)}>
                        <SelectTrigger className="h-8 w-[120px] text-xs" data-testid={`task-status-change-${task.id}`}><SelectValue /></SelectTrigger>
                        <SelectContent>{STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
                      </Select>
                    )}
                    <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(task)} data-testid={`task-edit-${task.id}`}><PencilSimple size={16} /></Button>
                    {isAdmin && <Button variant="ghost" size="icon" className="h-8 w-8 text-red-500 hover:text-red-700" onClick={() => handleDelete(task.id)} data-testid={`task-delete-${task.id}`}><Trash size={16} /></Button>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Edit Dialog */}
        <Dialog open={!!editTask} onOpenChange={v => { if (!v) { setEditTask(null); resetForm(); } }}>
          <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle className="text-xl font-bold text-gray-900" style={{fontFamily: 'Inter, sans-serif'}}>Edit Task</DialogTitle></DialogHeader>
            <TaskForm onSubmit={handleUpdate} submitLabel="Save Changes" />
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default TasksPage;
