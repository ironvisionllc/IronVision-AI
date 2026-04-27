import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import axios from "axios";
import { Toaster } from "@/components/ui/sonner";
import OnboardingTour from "@/components/OnboardingTour";
import { useInactivityLogout } from "@/hooks/use-inactivity-logout";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import Dashboard from "@/pages/Dashboard";
import FrameworkHub from "@/pages/FrameworkHub";
import PolicyHub from "@/pages/PolicyHub";
import ComplianceHub from "@/pages/ComplianceHub";
import RisksPage from "@/pages/RisksPage";
import TPRMPage from "@/pages/TPRMPage";
import TasksPage from "@/pages/TasksPage";
import IntegrationsPage from "@/pages/IntegrationsPage";
import SettingsPage from "@/pages/SettingsPage";
import SIEMPage from "@/pages/SIEMPage";
import DocumentationPage from "@/pages/DocumentationPage";
import IngestionPage from "@/pages/IngestionPage";
import PipelinePage from "@/pages/PipelinePage";
import RiskScoringPage from "@/pages/RiskScoringPage";
import PolicyEnginePage from "@/pages/PolicyEnginePage";
import EvidencePage from "@/pages/EvidencePage";
import TenablePage from "@/pages/TenablePage";
import AssetsPage from "@/pages/AssetsPage";
import AssetDetailPage from "@/pages/AssetDetailPage";
import ComplianceCopilot from "@/components/ComplianceCopilot";
import CommandPalette from "@/components/CommandPalette";
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
          <Route path="/frameworks" element={user ? <FrameworkHub /> : <Navigate to="/login" />} />
          <Route path="/policies" element={user ? <PolicyHub /> : <Navigate to="/login" />} />
          <Route path="/compliance" element={user ? <ComplianceHub /> : <Navigate to="/login" />} />
          <Route path="/risks" element={user ? <RisksPage /> : <Navigate to="/login" />} />
          <Route path="/vendors" element={user ? <TPRMPage /> : <Navigate to="/login" />} />
          <Route path="/tasks" element={user ? <TasksPage /> : <Navigate to="/login" />} />
          <Route path="/integrations" element={user ? <IntegrationsPage /> : <Navigate to="/login" />} />
          <Route path="/siem" element={user ? <SIEMPage /> : <Navigate to="/login" />} />
          <Route path="/ingestion" element={user ? <IngestionPage /> : <Navigate to="/login" />} />
          <Route path="/pipeline" element={user ? <PipelinePage /> : <Navigate to="/login" />} />
          <Route path="/risk-scoring" element={user ? <RiskScoringPage /> : <Navigate to="/login" />} />
          <Route path="/policy-engine" element={user ? <PolicyEnginePage /> : <Navigate to="/login" />} />
          <Route path="/evidence" element={user ? <EvidencePage /> : <Navigate to="/login" />} />
          <Route path="/tenable" element={user ? <TenablePage /> : <Navigate to="/login" />} />
          <Route path="/assets" element={user ? <AssetsPage /> : <Navigate to="/login" />} />
          <Route path="/assets/:assetId" element={user ? <AssetDetailPage /> : <Navigate to="/login" />} />
          <Route path="/documentation" element={user ? <DocumentationPage /> : <Navigate to="/login" />} />
          <Route path="/settings" element={user ? <SettingsPage /> : <Navigate to="/login" />} />
          {/* Redirects from old routes */}
          <Route path="/policy-library" element={<Navigate to="/policies?tab=library" />} />
          <Route path="/documents" element={<Navigate to="/policies?tab=documents" />} />
          <Route path="/mappings" element={<Navigate to="/policies?tab=mappings" />} />
          <Route path="/cross-framework" element={<Navigate to="/policies?tab=cross-framework" />} />
          <Route path="/audits" element={<Navigate to="/compliance?tab=audits" />} />
          <Route path="/analytics" element={<Navigate to="/dashboard" />} />
          <Route path="/activity" element={<Navigate to="/dashboard" />} />
          <Route path="/training" element={<Navigate to="/dashboard" />} />
          <Route path="/" element={<Navigate to={user ? "/dashboard" : "/login"} />} />
        </Routes>
        {user && <CommandPalette />}
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
