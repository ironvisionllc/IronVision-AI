import React, { useState, useContext } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { AuthContext, API } from "@/App";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { ShieldCheck } from "@phosphor-icons/react";

const RegisterPage = () => {
  const { login } = useContext(AuthContext);
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    organization_name: ""
  });
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await axios.post(`${API}/auth/register`, formData);
      login(response.data.token, response.data.user);
      toast.success("Account created successfully!");
      
      // Initialize frameworks
      await axios.post(`${API}/init/seed-frameworks`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8 bg-[#F9FAFB]">
        <div className="max-w-md w-full space-y-8">
          <div>
            <div className="flex items-center justify-center mb-6">
              <div className="w-16 h-16 bg-[#2597B2] rounded-lg flex items-center justify-center">
                <ShieldCheck size={32} weight="duotone" className="text-white" />
              </div>
            </div>
            <h2 className="text-4xl font-bold text-center text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Create your account</h2>
            <p className="mt-2 text-center text-sm text-gray-600">
              Start managing compliance across your organization
            </p>
          </div>
          <form className="mt-8 space-y-6" onSubmit={handleRegister} data-testid="register-form">
            <div className="space-y-4">
              <div>
                <Label htmlFor="name" className="text-sm font-semibold text-gray-700">Full name</Label>
                <Input
                  id="name"
                  name="name"
                  type="text"
                  required
                  value={formData.name}
                  onChange={handleChange}
                  className="mt-1 h-11"
                  placeholder="John Doe"
                  data-testid="register-name-input"
                />
              </div>
              <div>
                <Label htmlFor="email" className="text-sm font-semibold text-gray-700">Email address</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  required
                  value={formData.email}
                  onChange={handleChange}
                  className="mt-1 h-11"
                  placeholder="you@company.com"
                  data-testid="register-email-input"
                />
              </div>
              <div>
                <Label htmlFor="password" className="text-sm font-semibold text-gray-700">Password</Label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  required
                  value={formData.password}
                  onChange={handleChange}
                  className="mt-1 h-11"
                  placeholder="••••••••"
                  data-testid="register-password-input"
                />
              </div>
              <div>
                <Label htmlFor="organization_name" className="text-sm font-semibold text-gray-700">Organization name</Label>
                <Input
                  id="organization_name"
                  name="organization_name"
                  type="text"
                  required
                  value={formData.organization_name}
                  onChange={handleChange}
                  className="mt-1 h-11"
                  placeholder="Acme Corporation"
                  data-testid="register-org-input"
                />
              </div>
            </div>

            <Button
              type="submit"
              className="w-full h-11 bg-[#2597B2] hover:bg-[#1B839F] text-white transition-all duration-200"
              disabled={loading}
              data-testid="register-submit-button"
            >
              {loading ? "Creating account..." : "Create account"}
            </Button>

            <p className="text-center text-sm text-gray-600">
              Already have an account?{" "}
              <Link to="/login" className="font-semibold text-[#2597B2] hover:text-[#1B839F]" data-testid="login-link">
                Sign in
              </Link>
            </p>
          </form>
        </div>
      </div>
      <div 
        className="hidden lg:block flex-1 bg-cover bg-center relative"
        style={{backgroundImage: `url('https://static.prod-images.emergentagent.com/jobs/d3d6bacb-05bb-4303-9e94-9a373ce18c48/images/fafae4b31d4b9d74a7d4c6c5ad8919e3e6e1bd1beb97a04a7f16ec1987c7d237.png')`}}
      >
        <div className="absolute inset-0 bg-[#2597B2] bg-opacity-70"></div>
      </div>
    </div>
  );
};

export default RegisterPage;