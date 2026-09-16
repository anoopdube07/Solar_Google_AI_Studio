import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/ui-bits";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";

export default function SiteVisits() {
  const { user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const statusParam = new URLSearchParams(loc.search).get("status") || "ALL";
  const [visits, setVisits] = useState([]);
  const [installers, setInstallers] = useState([]);
  const [assignDlg, setAssignDlg] = useState(null);
  const [completeDlg, setCompleteDlg] = useState(null);
  const [af, setAf] = useState({});
  const [survey, setSurvey] = useState({ structure_height: "", earthing_cable_length: "", dc_cable_length: "", ac_cable_length: "", surveyor_name: "", extra_materials: [] });
  const [items, setItems] = useState([]);
  const [photos, setPhotos] = useState([]);
  const RESET = { structure_height: "", earthing_cable_length: "", dc_cable_length: "", ac_cable_length: "", surveyor_name: "", extra_materials: [] };
  const statusFilter = statusParam;
  const setStatusFilter = (v) => nav(v === "ALL" ? "/site-visits" : `/site-visits?status=${v}`);

  const load = () => api.get("/site-visits").then((r) => setVisits(r.data));
  useEffect(() => {
    load();
    if (user.role === "INSTALLATION_MANAGER" || user.role === "MANAGER" || user.role === "OWNER") {
      api.get("/users/team/INSTALLATION_MEMBER").then((r) => setInstallers(r.data)).catch(() => {});
      api.get("/users/team/INSTALLATION").then((r) => setInstallers((prev) => [...prev, ...r.data])).catch(() => {});
    }
    api.get("/items?active_only=true").then((r) => setItems(r.data)).catch(() => {});
  }, []);

  const openComplete = (v) => {
    setCompleteDlg(v); setSurvey(RESET);
    api.get(`/site-visits/${v.id}/photos`).then((r) => setPhotos(r.data.photos || [])).catch(() => setPhotos([]));
  };
  const uploadPhoto = (file) => {
    if (!file) return;
    if (photos.length >= 3) { toast.error("Maximum 3 photos"); return; }
    const send = (lat, lng) => {
      const fd = new FormData(); fd.append("file", file);
      if (lat != null) { fd.append("lat", lat); fd.append("lng", lng); }
      api.post(`/site-visits/${completeDlg.id}/photos`, fd, { headers: { "Content-Type": "multipart/form-data" } })
        .then((r) => { setPhotos((p) => [...p, r.data]); toast.success(lat != null ? "Photo added (geo-tagged)" : "Photo added (no location)"); })
        .catch((e) => toast.error(apiError(e.response?.data?.detail)));
    };
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition((pos) => send(pos.coords.latitude, pos.coords.longitude),
        () => { toast.message("Location unavailable — uploading without geo"); send(null, null); }, { timeout: 8000 });
    } else { send(null, null); }
  };
  const addMat = () => setSurvey((s) => ({ ...s, extra_materials: [...s.extra_materials, { item_id: "", item_name: "", quantity: "", unit: "" }] }));
  const setMat = (i, patch) => setSurvey((s) => { const m = [...s.extra_materials]; m[i] = { ...m[i], ...patch }; return { ...s, extra_materials: m }; });
  const rmMat = (i) => setSurvey((s) => ({ ...s, extra_materials: s.extra_materials.filter((_, x) => x !== i) }));

  const canAssign = user.role === "INSTALLATION_MANAGER" || user.role === "OWNER";
  const canComplete = user.role === "INSTALLATION" || user.role === "INSTALLATION_MEMBER" || user.role === "OWNER";
  const shownVisits = visits.filter((v) => statusFilter === "ALL" || v.status === statusFilter);

  const doAssign = async () => {
    try { await api.post(`/site-visits/${assignDlg.id}/assign`, af); toast.success("Assigned"); setAssignDlg(null); setAf({}); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const doComplete = async () => {
    const payload = { ...survey, extra_materials: survey.extra_materials.filter((m) => m.item_name && m.quantity).map((m) => ({ ...m, quantity: Number(m.quantity) })) };
    try { await api.post(`/site-visits/${completeDlg.id}/complete`, payload); toast.success("Site visit completed"); setCompleteDlg(null); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <PageHeader title="Site Visits" subtitle="Lead qualification site visits (not ECP installation)" />
      <div className="p-4 lg:p-8">
        <div className="flex items-center gap-3 mb-4">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger data-testid="sv-status-filter" className="w-48"><SelectValue /></SelectTrigger>
            <SelectContent>
              {["ALL", "REQUESTED", "ASSIGNED", "DONE"].map((s) => <SelectItem key={s} value={s} data-testid={`sv-status-${s}`}>{s === "ALL" ? "All" : s === "DONE" ? "Completed" : s.charAt(0) + s.slice(1).toLowerCase()}</SelectItem>)}
            </SelectContent>
          </Select>
          <span className="text-xs text-slate-400 font-mono">{shownVisits.length} visit(s)</span>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow><TableHead>Lead</TableHead><TableHead>Status</TableHead><TableHead>Assigned To</TableHead><TableHead>Visit Date</TableHead><TableHead>Survey</TableHead><TableHead>Action</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {shownVisits.map((v) => (
                <TableRow key={v.id} data-testid={`sv-row-${v.id}`}>
                  <TableCell className="font-semibold">{v.lead_name}</TableCell>
                  <TableCell><span className="text-xs font-semibold px-2 py-0.5 rounded-full border bg-slate-100">{v.status}</span></TableCell>
                  <TableCell className="text-sm">{v.assigned_user_name || "—"}</TableCell>
                  <TableCell className="text-sm">{v.visit_date?.slice(0, 10) || "—"}</TableCell>
                  <TableCell className="text-xs text-slate-500 max-w-[200px] truncate">{v.survey_info ? (typeof v.survey_info === "object" ? `H:${v.survey_info.structure_height || "-"}` : v.survey_info) : "—"}</TableCell>
                  <TableCell>
                    {canAssign && (v.status === "REQUESTED" || v.status === "ASSIGNED") && <Button size="sm" data-testid={`assign-sv-${v.id}`} onClick={() => { setAssignDlg(v); setAf({ visit_date: "" }); }}>Assign</Button>}
                    {canComplete && v.status === "ASSIGNED" && <Button size="sm" className="ml-2 bg-emerald-600 hover:bg-emerald-700" data-testid={`complete-sv-${v.id}`} onClick={() => openComplete(v)}>Complete</Button>}
                  </TableCell>
                </TableRow>
              ))}
              {shownVisits.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-slate-400 py-10">No site visits.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={!!assignDlg} onOpenChange={(o) => !o && setAssignDlg(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Assign Site Visit</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Installation Employee *</Label>
              <Select value={af.assigned_user} onValueChange={(v) => setAf({ ...af, assigned_user: v })}>
                <SelectTrigger data-testid="assign-employee-select"><SelectValue placeholder="Select employee" /></SelectTrigger>
                <SelectContent>{installers.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Visit Date *</Label><Input data-testid="assign-date-input" type="date" value={af.visit_date || ""} onChange={(e) => setAf({ ...af, visit_date: e.target.value })} /></div>
          </div>
          <DialogFooter><Button data-testid="assign-submit" onClick={doAssign} className="bg-sky-600 hover:bg-sky-700">Assign</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!completeDlg} onOpenChange={(o) => !o && setCompleteDlg(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Complete Site Visit — Survey</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Surveyor Name *</Label><Input data-testid="survey-name" value={survey.surveyor_name} onChange={(e) => setSurvey({ ...survey, surveyor_name: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Structure Height *</Label><Input data-testid="survey-height" value={survey.structure_height} onChange={(e) => setSurvey({ ...survey, structure_height: e.target.value })} /></div>
              <div><Label>Earthing Cable Length *</Label><Input data-testid="survey-earthing" value={survey.earthing_cable_length} onChange={(e) => setSurvey({ ...survey, earthing_cable_length: e.target.value })} /></div>
              <div><Label>DC Cable Length *</Label><Input data-testid="survey-dc" value={survey.dc_cable_length} onChange={(e) => setSurvey({ ...survey, dc_cable_length: e.target.value })} /></div>
              <div><Label>AC Cable Length *</Label><Input data-testid="survey-ac" value={survey.ac_cable_length} onChange={(e) => setSurvey({ ...survey, ac_cable_length: e.target.value })} /></div>
            </div>
            <p className="text-xs text-slate-400">Measurements are mandatory. Photos (max 3) &amp; extra materials are optional.</p>

            <div className="border-t pt-3">
              <div className="flex items-center justify-between mb-2">
                <Label>Extra Materials (from Item Master)</Label>
                <Button type="button" size="sm" variant="outline" data-testid="add-material-btn" onClick={addMat}>+ Add</Button>
              </div>
              {survey.extra_materials.map((m, i) => (
                <div key={i} className="flex gap-2 mb-2 items-center" data-testid={`material-row-${i}`}>
                  <Select value={m.item_id} onValueChange={(v) => { const it = items.find((x) => x.id === v); setMat(i, { item_id: v, item_name: it?.name || "", unit: it?.unit || "" }); }}>
                    <SelectTrigger data-testid={`material-item-${i}`} className="flex-1"><SelectValue placeholder="Item" /></SelectTrigger>
                    <SelectContent>{items.map((it) => <SelectItem key={it.id} value={it.id}>{it.name} ({it.unit})</SelectItem>)}</SelectContent>
                  </Select>
                  <Input data-testid={`material-qty-${i}`} type="number" placeholder="Qty" className="w-20" value={m.quantity} onChange={(e) => setMat(i, { quantity: e.target.value })} />
                  <span className="text-xs text-slate-400 w-12">{m.unit || "unit"}</span>
                  <Button type="button" size="sm" variant="ghost" onClick={() => rmMat(i)}>✕</Button>
                </div>
              ))}
            </div>

            <div className="border-t pt-3">
              <div className="flex items-center justify-between mb-2">
                <Label>Site Photos ({photos.length}/3, geo-tagged when allowed)</Label>
                {photos.length < 3 && (
                  <label className="text-sm text-sky-600 underline cursor-pointer" data-testid="sv-photo-label">
                    + Add Photo
                    <input type="file" accept="image/jpeg,image/png" capture="environment" className="hidden" data-testid="sv-photo-input" onChange={(e) => { uploadPhoto(e.target.files[0]); e.target.value = ""; }} />
                  </label>
                )}
              </div>
              <div className="flex gap-2 flex-wrap">
                {photos.map((p) => (
                  <span key={p.id} className="text-xs bg-slate-100 rounded px-2 py-1" data-testid={`sv-photo-${p.id}`}>
                    📷 {p.geo ? `${p.geo.lat.toFixed(3)},${p.geo.lng.toFixed(3)}` : "no location"}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter><Button data-testid="complete-submit" onClick={doComplete} className="bg-emerald-600 hover:bg-emerald-700">Mark Done · Return to Lead Team</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
