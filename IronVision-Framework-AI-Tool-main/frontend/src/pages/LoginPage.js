import React, { useState, useContext, useEffect } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { AuthContext, API } from "@/App";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { UserCircle, Crown } from "@phosphor-icons/react";

const SAVED_CREDS_KEY = "grc_saved_credentials";

const LoginPage = () => {
  const { login } = useContext(AuthContext);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(SAVED_CREDS_KEY);
      if (saved) { const { email: e, password: p } = JSON.parse(saved); if (e) setEmail(e); if (p) setPassword(p); setRememberMe(true); }
    } catch {}
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await axios.post(`${API}/auth/login`, { email, password });
      if (rememberMe) localStorage.setItem(SAVED_CREDS_KEY, JSON.stringify({ email, password }));
      else localStorage.removeItem(SAVED_CREDS_KEY);
      login(response.data.token, response.data.user);
      toast.success("Successfully logged in!");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Login failed");
    } finally { setLoading(false); }
  };

  const handleDemoLogin = async (role) => {
    setDemoLoading(role);
    const creds = role === "admin"
      ? { email: "demo-admin@grc.com", password: "DemoAdmin123!" }
      : { email: "demo-user@grc.com", password: "DemoUser123!" };
    try {
      const response = await axios.post(`${API}/auth/login`, creds);
      login(response.data.token, response.data.user);
      toast.success(`Logged in as Demo ${role === "admin" ? "Admin" : "User"}!`);
    } catch { toast.error("Demo login failed."); } finally { setDemoLoading(null); }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4 relative">
      {/* Background gradient blobs - IronVision style */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-1/3 left-1/3 w-[44rem] h-[44rem] bg-gradient-to-r from-[#2597B2]/10 to-[#1B839F]/10 rounded-full blur-3xl animate-pulse" style={{ animationDuration: "10s" }} />
        <div className="absolute bottom-1/3 right-1/3 w-[36rem] h-[36rem] bg-gradient-to-r from-[#47a7bf]/10 to-[#2597B2]/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: "1s", animationDuration: "12s" }} />
      </div>

      <div className="relative z-10 w-full max-w-md">
        <div className="bg-white/80 backdrop-blur-sm rounded-3xl shadow-xl border border-gray-200/50 overflow-hidden">
          {/* Logo */}
          <div className="p-8 pb-4">
            <div className="flex flex-col items-center justify-center mb-6">
              <img src="/ironvision-logo.png" alt="IronVision AI" className="h-10 w-auto mx-auto" data-testid="login-logo" />
              <p className="mt-4 text-center text-sm text-gray-500">Governance, Risk & Compliance Platform</p>
            </div>
          </div>

          <div className="px-8 pb-8">
            {/* Demo Access */}
            <div className="space-y-3 mb-6" data-testid="demo-access-section">
              <p className="text-[0.625rem] font-bold uppercase tracking-[0.2em] text-gray-400 text-center">Quick Demo Access</p>
              <div className="grid grid-cols-2 gap-3">
                <Button type="button" variant="outline"
                  className="h-11 border-[#2597B2] text-[#2597B2] hover:bg-[#2597B2] hover:text-white rounded-xl transition-all flex items-center justify-center gap-2"
                  onClick={() => handleDemoLogin("admin")} disabled={demoLoading !== null}
                  data-testid="demo-admin-login-button">
                  <Crown size={18} weight="duotone" />
                  {demoLoading === "admin" ? "Logging in..." : "Demo Admin"}
                </Button>
                <Button type="button" variant="outline"
                  className="h-11 border-gray-300 text-gray-600 hover:bg-gray-100 rounded-xl transition-all flex items-center justify-center gap-2"
                  onClick={() => handleDemoLogin("viewer")} disabled={demoLoading !== null}
                  data-testid="demo-user-login-button">
                  <UserCircle size={18} weight="duotone" />
                  {demoLoading === "viewer" ? "Logging in..." : "Demo User"}
                </Button>
              </div>
              <div className="relative">
                <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-200" /></div>
                <div className="relative flex justify-center text-xs"><span className="bg-white/80 px-3 text-gray-400">or sign in with your account</span></div>
              </div>
            </div>

            <form className="space-y-5" onSubmit={handleLogin} data-testid="login-form">
              <div className="space-y-4">
                <div>
                  <Label htmlFor="email" className="text-sm font-medium text-gray-700">Email address</Label>
                  <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                    className="mt-1.5 h-11 rounded-xl border-gray-200 focus:border-[#2597B2] focus:ring-[#2597B2]"
                    placeholder="you@company.com" data-testid="login-email-input" />
                </div>
                <div>
                  <Label htmlFor="password" className="text-sm font-medium text-gray-700">Password</Label>
                  <Input id="password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                    className="mt-1.5 h-11 rounded-xl border-gray-200 focus:border-[#2597B2] focus:ring-[#2597B2]"
                    placeholder="Enter password" data-testid="login-password-input" />
                </div>
              </div>

              <div className="flex items-center gap-2" data-testid="remember-me-section">
                <Checkbox id="remember-me" checked={rememberMe}
                  onCheckedChange={(c) => { setRememberMe(c); if (!c) localStorage.removeItem(SAVED_CREDS_KEY); }}
                  data-testid="remember-me-checkbox" />
                <Label htmlFor="remember-me" className="text-sm text-gray-500 cursor-pointer select-none">Remember me</Label>
              </div>

              <Button type="submit"
                className="w-full h-11 bg-[#2597B2] hover:bg-[#1B839F] text-white rounded-xl transition-all shadow-sm"
                disabled={loading} data-testid="login-submit-button">
                {loading ? "Signing in..." : "Sign in"}
              </Button>

              <p className="text-center text-sm text-gray-500">
                Don't have an account?{" "}
                <Link to="/register" className="font-semibold text-[#2597B2] hover:text-[#1B839F]" data-testid="register-link">Register</Link>
              </p>
            </form>
          </div>
        </div>

        <p className="text-center text-xs text-gray-400 mt-6">IronVision AI &middot; Enterprise GRC Platform</p>
      </div>
    </div>
  );
};

export default LoginPage;
