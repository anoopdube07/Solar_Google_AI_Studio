import React, { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/ui-bits";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

const FIELDS = [
  ["email", "Email"],
  ["address", "Address"],
  ["location_link", "Location Link"],
  ["item", "Item"],
  ["quantity", "Quantity"],
  ["project_price", "Project Price"],
];

export default function LeadFieldConfig() {
  const [fields, setFields] = useState({});
  const load = () => api.get("/lead-field-config").then((r) => setFields(r.data.fields || {}));
  useEffect(() => { load(); }, []);

  const save = async () => {
    try { await api.put("/lead-field-config", { fields }); toast.success("Mandatory fields saved"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <PageHeader title="Lead Field Rules" subtitle="Choose which Lead fields are mandatory at creation. Name & Phone are always required." />
      <div className="p-4 lg:p-8 max-w-xl">
        <Card className="p-6 space-y-1">
          <div className="flex items-center justify-between py-2 border-b">
            <span className="font-medium text-slate-500">Name / Phone</span>
            <span className="text-xs font-mono uppercase text-slate-400">Always required</span>
          </div>
          {FIELDS.map(([key, label]) => (
            <div key={key} className="flex items-center justify-between py-3 border-b last:border-0">
              <span className="font-medium text-slate-800">{label}</span>
              <Switch data-testid={`field-req-${key}`} checked={!!fields[key]} onCheckedChange={(v) => setFields({ ...fields, [key]: v })} />
            </div>
          ))}
          <div className="pt-4">
            <Button data-testid="field-config-save" onClick={save} className="bg-sky-600 hover:bg-sky-700">Save Rules</Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
