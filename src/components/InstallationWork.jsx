import React, { useEffect, useRef, useState } from "react";
import api, { apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/context/AuthContext";
import { Upload, CheckCircle2, XCircle, Camera } from "lucide-react";
import { toast } from "sonner";

const MEMBER = ["INSTALLATION", "INSTALLATION_MEMBER"];
const MANAGER = ["INSTALLATION_MANAGER", "MANAGER", "OWNER"];

export function InstallationWork({ ecp, onChange }) {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [reject, setReject] = useState("");
  const inputs = useRef({});
  const isMember = MEMBER.includes(user.role) && ecp.responsible_user === user.id;
  const isManager = MANAGER.includes(user.role);
  const canAssign = user.role === "INSTALLATION_MANAGER" || user.role === "MANAGER" || user.role === "OWNER";

  const load = () => api.get(`/ecps/${ecp.id}/install-photos`).then((r) => setData(r.data)).catch(() => {});
  useEffect(() => { load(); }, [ecp.id, ecp.install_status]);

  const act = async (action) => {
    try { await api.post(`/ecps/${ecp.id}/installation`, { action }); toast.success("Done"); onChange?.(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const upload = async (type, file) => {
    if (!file) return;
    const fd = new FormData(); fd.append("photo_type", type); fd.append("file", file);
    try { await api.post(`/ecps/${ecp.id}/install-photos`, fd, { headers: { "Content-Type": "multipart/form-data" } }); toast.success("Photo uploaded"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const decide = async (accept) => {
    if (!accept && !reject.trim()) { toast.error("Rejection remarks required"); return; }
    try { await api.post(`/ecps/${ecp.id}/installation/${accept ? "accept" : "reject"}`, { remarks: reject }); toast.success(accept ? "Accepted" : "Rejected"); setReject(""); onChange?.(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const types = data?.types || [];
  const labels = data?.labels || {};
  const have = {}; (data?.photos || []).forEach((p) => (have[p.photo_type] = p));

  return (
    <div className="space-y-3" data-testid="installation-work">
      <div className="text-sm">Status: <b>{ecp.install_status}</b>{ecp.responsible_user_name ? ` · ${ecp.responsible_user_name}` : ""}</div>
      {ecp.install_status === "AWAITING_ASSIGNMENT" && !canAssign && <p className="text-sm text-amber-600">Awaiting Installation Manager to assign a member.</p>}
      {ecp.install_reject_remarks && ecp.install_status === "REJECTED" && (
        <div className="text-sm bg-red-50 border border-red-200 rounded px-3 py-2 text-red-700" data-testid="install-reject-note">Rejected: {ecp.install_reject_remarks}</div>
      )}
      {isMember && ecp.install_status === "READY_TO_INSTALL" && <Button data-testid="install-start-button" onClick={() => act("start")} className="bg-sky-600 hover:bg-sky-700">Start Installation</Button>}
      {isMember && ["IN_PROCESS", "REJECTED"].includes(ecp.install_status) && (
        <div className="space-y-2">
          <div className="text-xs font-mono uppercase text-slate-400">5 Mandatory Photos (JPG/PNG)</div>
          {types.map((t) => (
            <div key={t} className="flex items-center justify-between border rounded-md px-3 py-2" data-testid={`install-photo-row-${t}`}>
              <span className="text-sm flex items-center gap-2">{have[t] ? <CheckCircle2 size={15} className="text-emerald-600" /> : <Camera size={15} className="text-amber-500" />}{labels[t] || t}</span>
              <input ref={(el) => (inputs.current[t] = el)} type="file" accept="image/png,image/jpeg" capture="environment" className="hidden" data-testid={`install-photo-input-${t}`} onChange={(e) => { upload(t, e.target.files[0]); e.target.value = ""; }} />
              <Button size="sm" variant={have[t] ? "outline" : "default"} data-testid={`install-photo-btn-${t}`} onClick={() => inputs.current[t]?.click()}><Upload size={14} className="mr-1" />{have[t] ? "Replace" : "Upload"}</Button>
            </div>
          ))}
          <Button data-testid="install-submit-button" className="bg-emerald-600 hover:bg-emerald-700" onClick={() => act("submit")}>Submit for Acceptance</Button>
        </div>
      )}
      {ecp.install_status === "PENDING_ACCEPTANCE" && (
        <div className="space-y-2">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {(data?.photos || []).map((p) => (
              <a key={p.id} className="text-xs text-sky-600 underline" href="#" data-testid={`install-photo-view-${p.photo_type}`}
                 onClick={async (e) => { e.preventDefault(); const r = await api.get(`/ecps/${ecp.id}/install-photos/${p.id}/download`, { responseType: "blob" }); window.open(window.URL.createObjectURL(r.data), "_blank"); }}>
                {labels[p.photo_type] || p.photo_type}
              </a>
            ))}
          </div>
          {isManager ? (
            <div className="space-y-2 border-t pt-2">
              <Label>Rejection Remarks (required to reject)</Label>
              <Textarea data-testid="install-reject-remarks" value={reject} onChange={(e) => setReject(e.target.value)} />
              <div className="flex gap-2">
                <Button data-testid="install-accept-button" className="bg-emerald-600 hover:bg-emerald-700" onClick={() => decide(true)}>Accept</Button>
                <Button data-testid="install-reject-button" className="bg-red-600 hover:bg-red-700 text-white" onClick={() => decide(false)}>Reject</Button>
              </div>
            </div>
          ) : <p className="text-sm text-amber-600">Submitted — awaiting Installation Manager acceptance.</p>}
        </div>
      )}
    </div>
  );
}
