import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sun } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { login, user } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  React.useEffect(() => { if (user) nav("/"); }, [user, nav]);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(username.trim(), password);
      toast.success("Welcome back");
      nav("/");
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail) || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="hidden lg:flex command-header text-white flex-col justify-between p-12">
        <div className="flex items-center gap-3">
          <Sun className="text-amber-400" size={30} />
          <span className="font-head text-2xl font-extrabold">ECP Tracker</span>
        </div>
        <div>
          <h2 className="font-head text-4xl font-extrabold leading-tight">Solar Operations<br />Command Center</h2>
          <p className="text-slate-300 mt-4 max-w-md">Track every lead and ECP project — current status, owning team, next action, and delays — in one place.</p>
        </div>
        <div className="text-xs font-mono uppercase tracking-widest text-slate-500">Internal Employee System · V1</div>
      </div>
      <div className="flex items-center justify-center p-8 bg-background">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5">
          <div>
            <h1 className="font-head text-2xl font-bold text-slate-900">Sign in</h1>
            <p className="text-sm text-slate-500 mt-1">Use your assigned username and password.</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="u">Username</Label>
            <Input id="u" data-testid="login-username-input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="e.g. lead" required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="p">Password</Label>
            <Input id="p" data-testid="login-password-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <Button data-testid="login-submit-button" type="submit" disabled={loading} className="w-full bg-sky-600 hover:bg-sky-700">
            {loading ? "Signing in…" : "Sign in"}
          </Button>

          <div className="pt-3 border-t border-slate-200">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Demo Quick Login</div>
            <div className="grid grid-cols-2 gap-1.5 text-xs">
              <button
                type="button"
                onClick={() => { setUsername("anoopdube07@gmail.com"); setPassword("Owner@123"); }}
                className="px-2.5 py-1.5 text-left rounded-md bg-slate-100 hover:bg-sky-50 hover:text-sky-700 font-medium transition-colors"
              >
                👑 Owner
              </button>
              <button
                type="button"
                onClick={() => { setUsername("manager"); setPassword("Manager@123"); }}
                className="px-2.5 py-1.5 text-left rounded-md bg-slate-100 hover:bg-sky-50 hover:text-sky-700 font-medium transition-colors"
              >
                📊 Manager
              </button>
              <button
                type="button"
                onClick={() => { setUsername("lead"); setPassword("Lead@123"); }}
                className="px-2.5 py-1.5 text-left rounded-md bg-slate-100 hover:bg-sky-50 hover:text-sky-700 font-medium transition-colors"
              >
                🎯 Lead Team
              </button>
              <button
                type="button"
                onClick={() => { setUsername("accounts"); setPassword("Acct@123"); }}
                className="px-2.5 py-1.5 text-left rounded-md bg-slate-100 hover:bg-sky-50 hover:text-sky-700 font-medium transition-colors"
              >
                💳 Accounts
              </button>
              <button
                type="button"
                onClick={() => { setUsername("dispatch"); setPassword("Disp@123"); }}
                className="px-2.5 py-1.5 text-left rounded-md bg-slate-100 hover:bg-sky-50 hover:text-sky-700 font-medium transition-colors"
              >
                🚚 Dispatch
              </button>
              <button
                type="button"
                onClick={() => { setUsername("installation"); setPassword("Install@123"); }}
                className="px-2.5 py-1.5 text-left rounded-md bg-slate-100 hover:bg-sky-50 hover:text-sky-700 font-medium transition-colors"
              >
                ⚡ Installation
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
