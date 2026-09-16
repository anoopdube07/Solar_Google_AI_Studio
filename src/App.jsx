import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Leads from "@/pages/Leads";
import LeadDetail from "@/pages/LeadDetail";
import ECPs from "@/pages/ECPs";
import ECPDetail from "@/pages/ECPDetail";
import SiteVisits from "@/pages/SiteVisits";
import Escalations from "@/pages/Escalations";
import Payments from "@/pages/Payments";
import Users from "@/pages/Users";
import SLAConfig from "@/pages/SLAConfig";
import WorkDone from "@/pages/WorkDone";
import ItemMaster from "@/pages/ItemMaster";
import LeadFieldConfig from "@/pages/LeadFieldConfig";
import Complaints from "@/pages/Complaints";

function Protected({ children }) {
  const { user } = useAuth();
  if (user === null) return <div className="min-h-screen flex items-center justify-center text-slate-500">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Protected><Dashboard /></Protected>} />
            <Route path="/leads" element={<Protected><Leads /></Protected>} />
            <Route path="/leads/:id" element={<Protected><LeadDetail /></Protected>} />
            <Route path="/ecps" element={<Protected><ECPs /></Protected>} />
            <Route path="/ecps/:id" element={<Protected><ECPDetail /></Protected>} />
            <Route path="/site-visits" element={<Protected><SiteVisits /></Protected>} />
            <Route path="/escalations" element={<Protected><Escalations /></Protected>} />
            <Route path="/payments" element={<Protected><Payments /></Protected>} />
            <Route path="/users" element={<Protected><Users /></Protected>} />
            <Route path="/sla" element={<Protected><SLAConfig /></Protected>} />
            <Route path="/work-done" element={<Protected><WorkDone /></Protected>} />
            <Route path="/items" element={<Protected><ItemMaster /></Protected>} />
            <Route path="/lead-fields" element={<Protected><LeadFieldConfig /></Protected>} />
            <Route path="/complaints" element={<Protected><Complaints /></Protected>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster richColors position="top-right" />
      </AuthProvider>
    </div>
  );
}

export default App;
