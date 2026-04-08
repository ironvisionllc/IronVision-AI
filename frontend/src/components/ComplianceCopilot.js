import React, { useState, useEffect, useRef, useContext } from "react";
import axios from "axios";
import { API, AuthContext } from "@/App";
import { 
  ChatCircleDots, 
  PaperPlaneTilt, 
  X, 
  Trash, 
  Plus, 
  Clock,
  Robot,
  User,
  CaretLeft,
  SpinnerGap
} from "@phosphor-icons/react";

const ComplianceCopilot = () => {
  const { user, token } = useContext(AuthContext);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("chat"); // "chat" | "history"
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  if (!user || !token) return null;

  const fetchSessions = async () => {
    setLoadingSessions(true);
    try {
      const res = await axios.get(`${API}/copilot/sessions`);
      setSessions(res.data);
    } catch {}
    setLoadingSessions(false);
  };

  const loadSession = async (sessionId) => {
    setCurrentSessionId(sessionId);
    setView("chat");
    try {
      const res = await axios.get(`${API}/copilot/sessions/${sessionId}/messages`);
      setMessages(res.data);
    } catch {
      setMessages([]);
    }
  };

  const startNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setInput("");
    setView("chat");
  };

  const deleteSession = async (sessionId, e) => {
    e.stopPropagation();
    try {
      await axios.delete(`${API}/copilot/sessions/${sessionId}`);
      setSessions(prev => prev.filter(s => s.session_id !== sessionId));
      if (currentSessionId === sessionId) startNewChat();
    } catch {}
  };

  const sendMessage = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setSending(true);

    // Optimistic add user message
    setMessages(prev => [...prev, { role: "user", content: text, created_at: new Date().toISOString() }]);

    try {
      const res = await axios.post(`${API}/copilot/chat`, {
        message: text,
        session_id: currentSessionId,
      });
      setCurrentSessionId(res.data.session_id);
      setMessages(prev => [...prev, { role: "assistant", content: res.data.response, created_at: res.data.created_at }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: "assistant", content: "Sorry, I encountered an error. Please try again." }]);
    }
    setSending(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const toggleOpen = () => {
    if (!open) {
      fetchSessions();
    }
    setOpen(!open);
  };

  return (
    <>
      {/* Floating Button */}
      <button
        onClick={toggleOpen}
        data-testid="copilot-fab"
        className="fixed bottom-6 right-6 z-[9999] w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-all duration-300 hover:scale-105 active:scale-95"
        style={{
          background: "linear-gradient(135deg, #2597B2 0%, #1B839F 100%)",
          boxShadow: "0 8px 32px rgba(37, 151, 178, 0.35)",
        }}
      >
        {open ? (
          <X size={24} weight="bold" className="text-white" />
        ) : (
          <ChatCircleDots size={26} weight="fill" className="text-white" />
        )}
      </button>

      {/* Chat Panel */}
      {open && (
        <div
          data-testid="copilot-panel"
          className="fixed bottom-24 right-6 z-[9998] w-[400px] h-[560px] bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-2xl flex flex-col overflow-hidden"
          style={{ boxShadow: "0 25px 50px -12px rgba(0,0,0,0.2)" }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-gray-800 bg-gradient-to-r from-[#2597B2]/5 to-transparent">
            <div className="flex items-center gap-3">
              {view === "history" && (
                <button onClick={() => setView("chat")} className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                  <CaretLeft size={18} weight="bold" className="text-gray-500" />
                </button>
              )}
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "linear-gradient(135deg, #2597B2, #1B839F)" }}>
                <Robot size={18} weight="fill" className="text-white" />
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {view === "history" ? "Chat History" : "Compliance Copilot"}
                </p>
                <p className="text-xs text-gray-400">AI-powered GRC assistant</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {view === "chat" && (
                <>
                  <button
                    onClick={() => { fetchSessions(); setView("history"); }}
                    className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    title="Chat history"
                    data-testid="copilot-history-btn"
                  >
                    <Clock size={16} className="text-gray-400" />
                  </button>
                  <button
                    onClick={startNewChat}
                    className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    title="New chat"
                    data-testid="copilot-new-chat-btn"
                  >
                    <Plus size={16} className="text-gray-400" />
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Body */}
          {view === "history" ? (
            <div className="flex-1 overflow-y-auto p-3">
              {loadingSessions ? (
                <div className="flex items-center justify-center h-40">
                  <SpinnerGap size={24} className="text-[#2597B2] animate-spin" />
                </div>
              ) : sessions.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-40 text-gray-400">
                  <ChatCircleDots size={32} weight="duotone" className="mb-2" />
                  <p className="text-sm">No conversations yet</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {sessions.map(s => (
                    <div
                      key={s.session_id}
                      onClick={() => loadSession(s.session_id)}
                      className={`group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-colors ${
                        currentSessionId === s.session_id ? "bg-[#2597B2]/10" : "hover:bg-gray-50 dark:hover:bg-gray-800"
                      }`}
                      data-testid={`copilot-session-${s.session_id}`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">{s.title}</p>
                        <p className="text-xs text-gray-400 mt-0.5">
                          {new Date(s.updated_at).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </p>
                      </div>
                      <button
                        onClick={(e) => deleteSession(s.session_id, e)}
                        className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                        data-testid={`copilot-delete-session-${s.session_id}`}
                      >
                        <Trash size={14} className="text-red-400" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <>
              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
                {messages.length === 0 && !sending && (
                  <div className="flex flex-col items-center justify-center h-full text-center px-6">
                    <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4" style={{ background: "linear-gradient(135deg, #2597B2/10, #1B839F/10)" }}>
                      <Robot size={32} weight="duotone" className="text-[#2597B2]" />
                    </div>
                    <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                      How can I help with compliance?
                    </p>
                    <p className="text-xs text-gray-400 leading-relaxed">
                      Ask about frameworks, controls, risk management, policy writing, or audit preparation.
                    </p>
                    <div className="mt-4 flex flex-wrap gap-2 justify-center">
                      {[
                        "What is NIST 800-53?",
                        "How to prepare for SOC 2?",
                        "Explain AC-1 control",
                      ].map(q => (
                        <button
                          key={q}
                          onClick={() => { setInput(q); }}
                          className="text-xs px-3 py-1.5 rounded-full border border-[#2597B2]/20 text-[#2597B2] hover:bg-[#2597B2]/5 transition-colors"
                          data-testid={`copilot-suggestion-${q.slice(0, 15)}`}
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {messages.map((msg, idx) => (
                  <div key={idx} className={`flex gap-2.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    {msg.role === "assistant" && (
                      <div className="w-7 h-7 rounded-lg flex-shrink-0 flex items-center justify-center mt-0.5" style={{ background: "linear-gradient(135deg, #2597B2, #1B839F)" }}>
                        <Robot size={14} weight="fill" className="text-white" />
                      </div>
                    )}
                    <div
                      className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                        msg.role === "user"
                          ? "bg-[#2597B2] text-white rounded-br-md"
                          : "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 rounded-bl-md"
                      }`}
                      data-testid={`copilot-message-${idx}`}
                    >
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    </div>
                    {msg.role === "user" && (
                      <div className="w-7 h-7 rounded-lg flex-shrink-0 flex items-center justify-center mt-0.5 bg-gray-200 dark:bg-gray-700">
                        <User size={14} weight="fill" className="text-gray-500" />
                      </div>
                    )}
                  </div>
                ))}
                {sending && (
                  <div className="flex gap-2.5 justify-start">
                    <div className="w-7 h-7 rounded-lg flex-shrink-0 flex items-center justify-center mt-0.5" style={{ background: "linear-gradient(135deg, #2597B2, #1B839F)" }}>
                      <Robot size={14} weight="fill" className="text-white" />
                    </div>
                    <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-bl-md px-4 py-3">
                      <div className="flex gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: "0ms" }} />
                        <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: "150ms" }} />
                        <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: "300ms" }} />
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              <div className="border-t border-gray-100 dark:border-gray-800 p-3">
                <div className="flex items-end gap-2 bg-gray-50 dark:bg-gray-800 rounded-xl px-3 py-2">
                  <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask a compliance question..."
                    rows={1}
                    className="flex-1 resize-none bg-transparent text-sm text-gray-800 dark:text-gray-200 placeholder-gray-400 focus:outline-none max-h-20"
                    data-testid="copilot-input"
                    style={{ minHeight: "24px" }}
                  />
                  <button
                    onClick={sendMessage}
                    disabled={!input.trim() || sending}
                    className="p-2 rounded-lg transition-all disabled:opacity-30"
                    style={{ background: input.trim() && !sending ? "linear-gradient(135deg, #2597B2, #1B839F)" : "transparent" }}
                    data-testid="copilot-send-btn"
                  >
                    <PaperPlaneTilt size={16} weight="fill" className={input.trim() && !sending ? "text-white" : "text-gray-400"} />
                  </button>
                </div>
                <p className="text-[10px] text-gray-400 text-center mt-1.5">
                  Copilot may provide general guidance. Verify with official sources.
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
};

export default ComplianceCopilot;
