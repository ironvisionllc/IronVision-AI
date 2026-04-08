import React, { useState, useContext, useEffect } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { AuthContext, API } from "@/App";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { UserCircle, Crown, ShieldCheck, ChartLineUp, GitBranch, Eye, EyeSlash } from "@phosphor-icons/react";

const SAVED_CREDS_KEY = "grc_saved_credentials";

const LoginPage = () => {
  const { login } = useContext(AuthContext);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(null);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(SAVED_CREDS_KEY);
      if (saved) { 
        const { email: e, password: p } = JSON.parse(saved); 
        if (e) setEmail(e); 
        if (p) setPassword(p); 
        setRememberMe(true); 
      }
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
      toast.success("Welcome back!");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Invalid credentials");
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
      toast.success(`Welcome, Demo ${role === "admin" ? "Admin" : "User"}!`);
    } catch { toast.error("Demo login failed."); } finally { setDemoLoading(null); }
  };

  const features = [
    { icon: ShieldCheck, title: "12 Frameworks", desc: "NIST, ISO, SOC 2, HIPAA & more" },
    { icon: ChartLineUp, title: "AI-Powered", desc: "Intelligent control mapping" },
    { icon: GitBranch, title: "Cross-Framework", desc: "Unified compliance view" },
  ];

  return (
    <div className="min-h-screen flex">
      {/* Left Panel - Branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-[#0f172a] via-[#1e293b] to-[#0f172a] relative overflow-hidden">
        {/* Decorative elements */}
        <div className="absolute inset-0">
          <div className="absolute top-1/4 -left-20 w-96 h-96 bg-[#2597B2]/20 rounded-full blur-3xl" />
          <div className="absolute bottom-1/4 -right-20 w-80 h-80 bg-[#06B6D4]/15 rounded-full blur-3xl" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[40rem] h-[40rem] bg-gradient-radial from-[#2597B2]/5 to-transparent rounded-full" />
        </div>
        
        {/* Grid pattern overlay */}
        <div 
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
            backgroundSize: '60px 60px'
          }}
        />
        
        <div className="relative z-10 flex flex-col justify-between p-12 w-full">
          {/* Logo */}
          <div>
            <img src="/ironvision-logo-dark.png" alt="IronVision AI" className="h-10 w-auto" />
          </div>
          
          {/* Center content */}
          <div className="max-w-md">
            <h1 className="text-4xl font-bold text-white leading-tight mb-4">
              Enterprise GRC
              <span className="block text-[#2597B2]">Made Simple</span>
            </h1>
            <p className="text-lg text-gray-400 leading-relaxed mb-10">
              Streamline governance, risk, and compliance with AI-powered policy generation and intelligent control mapping.
            </p>
            
            {/* Features */}
            <div className="space-y-4">
              {features.map((f, i) => (
                <div key={i} className="flex items-center gap-4 group">
                  <div className="w-12 h-12 rounded-xl bg-[#2597B2]/10 border border-[#2597B2]/20 flex items-center justify-center group-hover:bg-[#2597B2]/20 transition-colors">
                    <f.icon size={22} weight="duotone" className="text-[#2597B2]" />
                  </div>
                  <div>
                    <p className="font-semibold text-white text-sm">{f.title}</p>
                    <p className="text-gray-500 text-sm">{f.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
          
          {/* Bottom */}
          <div className="flex items-center gap-8 text-sm text-gray-500">
            <span>Trusted by security teams worldwide</span>
          </div>
        </div>
      </div>
      
      {/* Right Panel - Login Form */}
      <div className="flex-1 flex items-center justify-center p-6 bg-gradient-to-br from-gray-50 to-white">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="lg:hidden flex justify-center mb-8">
            <img src="/ironvision-logo.png" alt="IronVision AI" className="h-9 w-auto" data-testid="login-logo" />
          </div>
          
          {/* Login card */}
          <div className="bg-white rounded-2xl shadow-xl shadow-gray-200/50 border border-gray-100 p-8">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-gray-900">Welcome back</h2>
              <p className="text-gray-500 mt-1">Sign in to your account</p>
            </div>

            {/* Demo Access */}
            <div className="space-y-3 mb-8" data-testid="demo-access-section">
              <p className="text-label text-center">Quick Demo Access</p>
              <div className="grid grid-cols-2 gap-3">
                <Button 
                  type="button" 
                  variant="outline"
                  className="h-12 border-2 border-[#2597B2]/20 text-[#2597B2] hover:bg-[#2597B2] hover:text-white hover:border-[#2597B2] rounded-xl transition-all duration-200 flex items-center justify-center gap-2 font-semibold"
                  onClick={() => handleDemoLogin("admin")} 
                  disabled={demoLoading !== null}
                  data-testid="demo-admin-login-button"
                >
                  <Crown size={18} weight="fill" />
                  {demoLoading === "admin" ? (
                    <span className="flex items-center gap-2">
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    </span>
                  ) : "Demo Admin"}
                </Button>
                <Button 
                  type="button" 
                  variant="outline"
                  className="h-12 border-2 border-gray-200 text-gray-600 hover:bg-gray-100 hover:border-gray-300 rounded-xl transition-all duration-200 flex items-center justify-center gap-2 font-semibold"
                  onClick={() => handleDemoLogin("viewer")} 
                  disabled={demoLoading !== null}
                  data-testid="demo-user-login-button"
                >
                  <UserCircle size={18} weight="fill" />
                  {demoLoading === "viewer" ? (
                    <span className="flex items-center gap-2">
                      <span className="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                    </span>
                  ) : "Demo User"}
                </Button>
              </div>
              
              {/* Divider */}
              <div className="relative py-4">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-200" />
                </div>
                <div className="relative flex justify-center">
                  <span className="bg-white px-4 text-xs text-gray-400 font-medium">or continue with email</span>
                </div>
              </div>
            </div>

            <form className="space-y-5" onSubmit={handleLogin} data-testid="login-form">
              <div className="space-y-4">
                <div>
                  <Label htmlFor="email" className="text-sm font-medium text-gray-700">Email address</Label>
                  <Input 
                    id="email" 
                    type="email" 
                    required 
                    value={email} 
                    onChange={(e) => setEmail(e.target.value)}
                    className="mt-2 h-12 rounded-xl border-gray-200 bg-gray-50/50 focus:bg-white focus:border-[#2597B2] focus:ring-2 focus:ring-[#2597B2]/20 transition-all"
                    placeholder="you@company.com" 
                    data-testid="login-email-input" 
                  />
                </div>
                <div>
                  <Label htmlFor="password" className="text-sm font-medium text-gray-700">Password</Label>
                  <div className="relative mt-2">
                    <Input 
                      id="password" 
                      type={showPassword ? "text" : "password"} 
                      required 
                      value={password} 
                      onChange={(e) => setPassword(e.target.value)}
                      className="h-12 rounded-xl border-gray-200 bg-gray-50/50 focus:bg-white focus:border-[#2597B2] focus:ring-2 focus:ring-[#2597B2]/20 transition-all pr-12"
                      placeholder="Enter password" 
                      data-testid="login-password-input" 
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 transition-colors"
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeSlash size={20} /> : <Eye size={20} />}
                    </button>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between" data-testid="remember-me-section">
                <div className="flex items-center gap-2">
                  <Checkbox 
                    id="remember-me" 
                    checked={rememberMe}
                    onCheckedChange={(c) => { setRememberMe(c); if (!c) localStorage.removeItem(SAVED_CREDS_KEY); }}
                    className="border-gray-300 data-[state=checked]:bg-[#2597B2] data-[state=checked]:border-[#2597B2]"
                    data-testid="remember-me-checkbox" 
                  />
                  <Label htmlFor="remember-me" className="text-sm text-gray-600 cursor-pointer select-none">Remember me</Label>
                </div>
                <a href="#" className="text-sm font-medium text-[#2597B2] hover:text-[#1B839F] transition-colors">
                  Forgot password?
                </a>
              </div>

              <Button 
                type="submit"
                className="w-full h-12 bg-gradient-to-r from-[#2597B2] to-[#1B839F] hover:from-[#1B839F] hover:to-[#15697f] text-white rounded-xl transition-all duration-200 shadow-lg shadow-[#2597B2]/25 hover:shadow-xl hover:shadow-[#2597B2]/30 font-semibold"
                disabled={loading} 
                data-testid="login-submit-button"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Signing in...
                  </span>
                ) : "Sign in"}
              </Button>

              <p className="text-center text-sm text-gray-500 pt-2">
                Don't have an account?{" "}
                <Link to="/register" className="font-semibold text-[#2597B2] hover:text-[#1B839F] transition-colors" data-testid="register-link">
                  Create account
                </Link>
              </p>
            </form>
          </div>
          
          {/* Footer */}
          <p className="text-center text-xs text-gray-400 mt-8">
            © 2026 IronVision AI · Enterprise GRC Platform
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
