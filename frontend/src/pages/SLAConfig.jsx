import React, { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/ui-bits";
import { STAGE_ORDER, STAGE_LABELS } from "@/lib/constants";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

export default function SLAConfig() {
  const [cfg, setCfg] = useState({});

  useEffect(() => { api.get("/sla").then((r) => setCfg(r.data)); }, []);

  const save = async () => {
    try {
      const clean = {};
      STAGE_ORDER.forEach((s) => { clean[s] = parseInt(cfg[s] || 0, 10); });
      const { data } = await api.put("/sla", { config: clean });
      setCfg(data); toast.success("SLA saved");
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <PageHeader title="SLA Configuration" subtitle="Set SLA days per stage. 0 = no SLA (never marked delayed)." />
      <div className="p-6 lg:p-8">
        <Card className="p-6 max-w-xl">
          <div className="space-y-4">
            {STAGE_ORDER.map((s) => (
              <div key={s} className="flex items-center justify-between gap-4">
                <Label className="flex-1">{STAGE_LABELS[s]}</Label>
                <Input data-testid={`sla-input-${s}`} type="number" min="0" className="w-32" value={cfg[s] ?? 0} onChange={(e) => setCfg({ ...cfg, [s]: e.target.value })} />
                <span className="text-sm text-slate-400 w-10">days</span>
              </div>
            ))}
          </div>
          <Button data-testid="sla-save-button" onClick={save} className="mt-6 bg-sky-600 hover:bg-sky-700">Save SLA Config</Button>
        </Card>
      </div>
    </div>
  );
}
