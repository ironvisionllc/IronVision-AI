import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import axios from "axios";
import { Toaster } from "@/components/ui/sonner";
import OnboardingTour from "@/components/OnboardingTour";
import { useInactivityLogout } from "@/hooks/use-inactivity-logout";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import Dashboard from "@/pages/Dashboard";
import FrameworksPage from "@/pages/FrameworksPage";
import PoliciesPage from "@/pages/PoliciesPage";
import PolicyLibraryPage from "@/pages/PolicyLibraryPage";
import MappingsPage from "@/pages/MappingsPage";
import RisksPage from "@/pages/RisksPage";
import VendorsPage from "@/pages/VendorsPage";
import AuditsPage from "@/pages/AuditsPage";
import TrainingPage from "@/pages/TrainingPage";
import AnalyticsPage from "@/pages/AnalyticsPage";
import TasksPage from "@/pages/TasksPage";
import ActivityPage from "@/pages/ActivityPage";
import IntegrationsPage from "@/pages/IntegrationsPage";
import EvidencePage from "@/pages/EvidencePage";
import CrossFrameworkPage from "@/pages/CrossFrameworkPage";
import SettingsPage from "@/pages/SettingsPage";
import PolicyBuilderPage from "@/pages/PolicyBuilderPage";
import DocumentsPage from "@/pages/DocumentsPage";
import SIEMPage from "@/pages/SIEMPage";
import ComplianceCopilot from "@/components/ComplianceCopilot";
import "@/index.css";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const AuthContext = React.createContext(null);

function App() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      fetchUser();
    } else {
      setLoading(false);
    }
  }, [token]);

  const fetchUser = async () => {
    try {
      const response = await axios.get(`${API}/auth/me`);
      setUser(response.data);
    } catch (error) {
      console.error("Failed to fetch user", error);
      logout();
    } finally {
      setLoading(false);
    }
  };

  const login = (newToken, userData) => {
    localStorage.setItem("token", newToken);
    setToken(newToken);
    setUser(userData);
    axios.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
    delete axios.defaults.headers.common['Authorization'];
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#F9FAFB]">
        <div className="text-lg text-gray-600">Loading...</div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, token, login, logout }}>
      <BrowserRouter>
        <InactivityGuard />
        <OnboardingTour />
        <Routes>
          <Route path="/login" element={!user ? <LoginPage /> : <Navigate to="/dashboard" />} />
          <Route path="/register" element={!user ? <RegisterPage /> : <Navigate to="/dashboard" />} />
          <Route path="/dashboard" element={user ? <Dashboard /> : <Navigate to="/login" />} />
          <Route path="/frameworks" element={user ? <FrameworksPage /> : <Navigate to="/login" />} />
          <Route path="/policies" element={user ? <PolicyBuilderPage /> : <Navigate to="/login" />} />
          <Route path="/policy-library" element={user ? <PolicyLibraryPage /> : <Navigate to="/login" />} />
          <Route path="/documents" element={user ? <DocumentsPage /> : <Navigate to="/login" />} />
          <Route path="/mappings" element={user ? <MappingsPage /> : <Navigate to="/login" />} />
          <Route path="/risks" element={user ? <RisksPage /> : <Navigate to="/login" />} />
          <Route path="/vendors" element={user ? <VendorsPage /> : <Navigate to="/login" />} />
          <Route path="/audits" element={user ? <AuditsPage /> : <Navigate to="/login" />} />
          <Route path="/training" element={user ? <TrainingPage /> : <Navigate to="/login" />} />
          <Route path="/tasks" element={user ? <TasksPage /> : <Navigate to="/login" />} />
          <Route path="/analytics" element={user ? <AnalyticsPage /> : <Navigate to="/login" />} />
          <Route path="/activity" element={user ? <ActivityPage /> : <Navigate to="/login" />} />
          <Route path="/integrations" element={user ? <IntegrationsPage /> : <Navigate to="/login" />} />
          <Route path="/evidence" element={user ? <EvidencePage /> : <Navigate to="/login" />} />
          <Route path="/siem" element={user ? <SIEMPage /> : <Navigate to="/login" />} />
          <Route path="/cross-framework" element={user ? <CrossFrameworkPage /> : <Navigate to="/login" />} />
          <Route path="/settings" element={user ? <SettingsPage /> : <Navigate to="/login" />} />
          <Route path="/" element={<Navigate to={user ? "/dashboard" : "/login"} />} />
        </Routes>
      </BrowserRouter>
      <ComplianceCopilot />
      <Toaster />
    </AuthContext.Provider>
  );
}

function InactivityGuard() {
  useInactivityLogout();
  return null;
}

export default App;
