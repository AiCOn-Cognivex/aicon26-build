"use client";

import { useEffect, useState } from "react";
import { Check, Info, LoaderCircle } from "lucide-react";
import { PageHeader, PageLoader } from "@/components/shell";
import { Button, Card, ErrorNote, WalletBadge, cx } from "@/components/ui";
import { api } from "@/lib/client";
import { useApi } from "@/lib/useApi";

type W = { id: number; code: string; name: string; period: string; limits: Record<string, number>; auto_approve: boolean; per_claim_cap: number; max_age_days: number; description: string };

export default function PoliciesPage() {
  const { data, error, reload } = useApi<{ wallets: W[] }>("/admin/wallets");
  return (
    <>
      <PageHeader title="Allowance policy" sub="Limits by grade, and which claims the AI may approve on its own" />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!data && !error && <PageLoader />}
      <Card className="mb-5 flex gap-3 p-5 text-[13px] leading-relaxed text-ink-2">
        <Info size={18} className="mt-0.5 shrink-0 text-brand" />
        <p>
          Instant AI approval should only be on for receipt types the model has been tested on. Ours was trained and validated on restaurant and café receipts
          (CORD v2), so it is on for Meals only. Fuel, medical and other receipts always go to a person until the model is measured on them.
        </p>
      </Card>
      <div className="grid gap-5 lg:grid-cols-2">
        {data?.wallets.map((w, i) => (
          <WalletEditor key={w.id} w={w} delay={i * 50} />
        ))}
      </div>
    </>
  );
}

function WalletEditor({ w, delay }: { w: W; delay: number }) {
  const [limits, setLimits] = useState(w.limits);
  const [auto, setAuto] = useState(w.auto_approve);
  const [cap, setCap] = useState(w.per_claim_cap);
  const [age, setAge] = useState(w.max_age_days);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => setSaved(false), [limits, auto, cap, age]);

  async function save() {
    setBusy(true);
    setErr("");
    try {
      await api(`/admin/wallets/${w.id}`, { method: "PUT", json: { limits, auto_approve: auto, per_claim_cap: cap, max_age_days: age } });
      setSaved(true);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-6 animate-fade-up" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex items-center gap-3">
        <WalletBadge code={w.code} size={42} />
        <div className="flex-1">
          <p className="text-[15px] font-semibold">{w.name}</p>
          <p className="text-xs text-muted">
            {w.description} · {w.period === "monthly" ? "per month" : "per year"}
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-xs font-semibold">
          <span className={auto ? "text-brand" : "text-muted"}>Instant AI approval</span>
          <button type="button" role="switch" aria-checked={auto} onClick={() => setAuto(!auto)} className={cx("relative h-7 w-12 rounded-full transition", auto ? "bg-brand" : "bg-line")}>
            <span className={cx("absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-all", auto ? "left-6" : "left-1")} />
          </button>
        </label>
      </div>
      <div className="mt-5 grid grid-cols-3 gap-3">
        {Object.keys(limits).map((g) => (
          <label key={g} className="block">
            <span className="mb-1 block text-[11px] font-semibold text-muted">Grade {g} limit</span>
            <input className="field num" inputMode="numeric" value={limits[g]} onChange={(e) => setLimits({ ...limits, [g]: +e.target.value.replace(/\D/g, "") || 0 })} />
          </label>
        ))}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold text-muted">Instant-approval limit per claim (Rs)</span>
          <input className="field num" inputMode="numeric" value={cap} onChange={(e) => setCap(+e.target.value.replace(/\D/g, "") || 0)} />
        </label>
        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold text-muted">Oldest receipt accepted (days)</span>
          <input className="field num" inputMode="numeric" value={age} onChange={(e) => setAge(Math.min(365, Math.max(1, +e.target.value.replace(/\D/g, "") || 1)))} />
        </label>
      </div>
      {err && <p className="mt-3 rounded-2xl bg-bad-soft px-4 py-2 text-sm text-bad">{err}</p>}
      <div className="mt-4 flex justify-end">
        <Button size="sm" onClick={save} disabled={busy} variant={saved ? "soft" : "primary"}>
          {busy ? <LoaderCircle size={15} className="animate-spin" /> : saved ? <Check size={15} /> : null}
          {saved ? "Saved" : "Save changes"}
        </Button>
      </div>
    </Card>
  );
}
