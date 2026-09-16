import React, { useEffect, useRef, useState } from "react";
import api, { apiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DOC_LABELS } from "@/lib/constants";
import { Upload, FileCheck2, FileWarning, Download, Loader2 } from "lucide-react";
import { toast } from "sonner";

const SINGLES = ["PAN", "AADHAAR", "ELECTRICITY_BILL"];
const BANK = ["BANK_PASSBOOK", "BANK_STATEMENT", "CANCELLED_CHEQUE"];
const FINANCE = ["PROPERTY_PAPER", "TAX_RECEIPT"];

export function DocumentsPanel({ leadId, canUpload, onChange }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState("");
  const inputs = useRef({});

  const load = () =>
    api.get(`/leads/${leadId}/documents`).then((r) => setData(r.data))
      .catch((e) => toast.error(apiError(e.response?.data?.detail)));
  useEffect(() => { load(); }, [leadId]);

  if (!data) return <Card className="p-5" data-testid="documents-panel"><div className="text-sm text-slate-400">Loading documents…</div></Card>;

  const { documents, documents_status: st } = data;
  const byType = {};
  documents.forEach((d) => { byType[d.doc_type] = d; });
  const financing = st.financing_required;

  const upload = async (docType, file) => {
    if (!file) return;
    setBusy(docType);
    const fd = new FormData();
    fd.append("doc_type", docType);
    fd.append("file", file);
    try {
      const r = await api.post(`/leads/${leadId}/documents`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`${DOC_LABELS[docType]} uploaded`);
      if (r.data.released) toast.success("All documents complete — released to Registration 1");
      await load();
      onChange && onChange();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(""); }
  };

  const view = async (doc) => {
    try {
      const r = await api.get(`/leads/${leadId}/documents/${doc.id}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(r.data);
      window.open(url, "_blank");
      setTimeout(() => window.URL.revokeObjectURL(url), 30000);
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const Row = ({ type }) => {
    const doc = byType[type];
    return (
      <div className="flex items-center justify-between gap-3 border rounded-md px-3 py-2" data-testid={`doc-row-${type}`}>
        <div className="flex items-center gap-2 min-w-0">
          {doc ? <FileCheck2 size={16} className="text-emerald-600 shrink-0" /> : <FileWarning size={16} className="text-amber-500 shrink-0" />}
          <div className="min-w-0">
            <div className="text-sm font-medium text-slate-800">{DOC_LABELS[type]}</div>
            {doc
              ? <div className="text-xs text-slate-500 truncate" data-testid={`doc-meta-${type}`}>{doc.original_filename} · {doc.uploaded_by_name} · {doc.uploaded_at?.slice(0, 10)}</div>
              : <div className="text-xs text-amber-600">Not uploaded</div>}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {doc && <Button size="sm" variant="ghost" data-testid={`doc-view-${type}`} onClick={() => view(doc)}><Download size={15} /></Button>}
          {canUpload && (
            <>
              <input ref={(el) => (inputs.current[type] = el)} type="file" accept=".jpg,.jpeg,.png,.pdf" className="hidden"
                data-testid={`doc-input-${type}`} onChange={(e) => { upload(type, e.target.files[0]); e.target.value = ""; }} />
              <Button size="sm" variant={doc ? "outline" : "default"} data-testid={`doc-upload-${type}`} disabled={busy === type}
                className={doc ? "" : "bg-sky-600 hover:bg-sky-700"} onClick={() => inputs.current[type]?.click()}>
                {busy === type ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} className="mr-1" />}{doc ? "Replace" : "Upload"}
              </Button>
            </>
          )}
        </div>
      </div>
    );
  };

  return (
    <Card className="p-5" data-testid="documents-panel">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-head font-semibold">Documents</h3>
        <span data-testid="documents-overall-status"
          className={`px-2.5 py-1 rounded-full text-xs font-bold ${st.complete ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
          {st.complete ? "DOCUMENTS COMPLETE" : "DOCUMENTS INCOMPLETE"}
        </span>
      </div>
      <div className="space-y-2">
        {SINGLES.map((t) => <Row key={t} type={t} />)}
        <div className="text-xs font-mono uppercase tracking-wide text-slate-400 pt-2">Bank Proof — at least one</div>
        {BANK.map((t) => <Row key={t} type={t} />)}
        {financing && (
          <>
            <div className="text-xs font-mono uppercase tracking-wide text-slate-400 pt-2">Finance Proof — at least one</div>
            {FINANCE.map((t) => <Row key={t} type={t} />)}
          </>
        )}
      </div>
      {!st.complete && st.missing?.length > 0 && (
        <div className="mt-3 text-sm bg-amber-50 border border-amber-200 rounded-md px-3 py-2 text-amber-800" data-testid="documents-missing">
          Missing: {st.missing.join(", ")}
        </div>
      )}
      {st.complete && (
        <div className="mt-3 text-sm bg-emerald-50 border border-emerald-200 rounded-md px-3 py-2 text-emerald-800">
          All required documents are uploaded.
        </div>
      )}
    </Card>
  );
}
