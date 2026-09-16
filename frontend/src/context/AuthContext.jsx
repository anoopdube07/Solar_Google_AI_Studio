import React, { createContext, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=checking, false=unauth, obj=auth
  useEffect(() => {
    const token = localStorage.getItem("ecp_token");
    if (!token) { setUser(false); return; }
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => { setUser(false); });
  }, []);

  const login = async (username, password) => {
    const { data } = await api.post("/auth/login", { username, password });
    localStorage.setItem("ecp_token", data.token);
    setUser(data.user);
    return data.user;
  };
  const logout = () => { localStorage.removeItem("ecp_token"); setUser(false); };

  return <AuthContext.Provider value={{ user, login, logout, setUser }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
