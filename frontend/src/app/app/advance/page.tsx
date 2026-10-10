"use client";

import { useEffect, useState } from "react";
import { BadgePercent, CalendarCheck, HandCoins, LoaderCircle, ShieldCheck, Zap } from "lucide-react";
import { Ring } from "@/components/charts";
import { PageHeader, PageLoader } from "@/components/shell";
import { Button, Card, CardHead, Empty, ErrorNote, StatusPill, cx } from "@/components/ui";
import type { AdvanceSt } from "@/lib/appTypes";
import { api } from "@/lib/client";
import { ago, dLong, money } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function AdvancePage() {
  const { data, error, reload, setData } = useApi<AdvanceSt>("/advances");
  const [amount, setAmount] = useState(0);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (data) setAmount(Math.min(data.available, Math.max(1000, Math.round(data.available / 2 / 500) * 500)));
  }, [data]);

  async function request() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<AdvanceSt>("/advances", { json: { amount, reason } });
      setData(r);
      const last = r.history?.[0];
      setMsg({ ok: true, text: last?.status === "approved" ? `Approved. ${money(last.amount)} is on its way and will be deducted on ${dLong(r.repay_date)}.` : "Request sent. A finance manager will approve or decline it." });
      setReason("");
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Salary advance" sub="Take part of the pay you've already earned this month. Interest-free." />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!data && !error && <PageLoader />}
      {data && (
        <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
          <Card className="overflow-hidden p-0 animate-fade-up">
            <div className="flex flex-wrap items-center gap-7 bg-gradient-to-br from-brand-soft via-surface to-surface p-7">
              <Ring value={data.monthly_net ? data.earned_so_far / data.monthly_net : 0} size={168} stroke={15}>
                <div>
                  <p className="text-[11px] text-muted">Earned so far</p>
                  <p className="num text-[22px] font-bold leading-tight">{money(data.earned_so_far)}</p>
                  <p className="text-[11px] text-muted">of {money(data.monthly_net)}</p>
                </div>
              </Ring>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-muted">You can take up to</p>
                <p className="num text-[40px] font-bold leading-tight tracking-tight">{money(data.available)}</p>
                <p className="mt-1 text-xs text-muted">
                  {Math.round(data.share * 100)}% of what you&apos;ve earned{data.outstanding ? `, minus ${money(data.outstanding)} already advanced` : ""}.
                </p>
              </div>
            </div>
            <div className="space-y-5 p-7">
              {data.available >= 1000 ? (
                <>
                  <div>
                    <div className="mb-3 flex items-baseline justify-between">
                      <span className="text-[13px] font-semibold">How much do you need?</span>
                      <span className="num text-[22px] font-bold">{money(amount)}</span>
                    </div>
                    <input type="range" min={1000} max={data.available} step={500} value={amount} onChange={(e) => setAmount(+e.target.value)} className="w-full accent-[var(--color-brand)]" />
                    <div className="mt-3 flex flex-wrap gap-2">
                      {[0.25, 0.5, 1].map((f) => {
                        const v = Math.max(1000, Math.floor((data.available * f) / 500) * 500);
                        return (
                          <button key={f} onClick={() => setAmount(v)} className={cx("rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition", amount === v ? "bg-ink text-white" : "bg-surface-2 hover:bg-line")}>
                            {f === 1 ? "Max" : `${f * 100}%`} · {money(v)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <label className="block">
                    <span className="mb-1.5 block text-[13px] font-semibold">What is it for? (optional, private to finance)</span>
                    <input className="field" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="e.g. School fees, medical bill" />
                  </label>
                  <div className="inset grid grid-cols-3 divide-x divide-line text-center">
                    {[
                      ["Interest", "Rs 0"],
                      ["Fees", "Rs 0"],
                      ["Deducted on", dLong(data.repay_date)],
                    ].map(([k, v]) => (
                      <div key={k} className="px-2 py-3">
                        <p className="text-[11px] text-muted">{k}</p>
                        <p className="text-[13px] font-semibold">{v}</p>
                      </div>
                    ))}
                  </div>
                  <Button size="lg" className="w-full" onClick={request} disabled={busy}>
                    {busy ? <LoaderCircle size={18} className="animate-spin" /> : <HandCoins size={18} />}
                    Get {money(amount)} now
                  </Button>
                </>
              ) : (
                <p className="rounded-2xl bg-surface-2 p-4 text-sm text-muted">Nothing available right now. You can take an advance once you&apos;ve earned more of this month&apos;s pay.</p>
              )}
              {msg && <p className={cx("rounded-2xl px-4 py-3 text-sm animate-fade-up", msg.ok ? "bg-brand-soft text-brand-deep" : "bg-bad-soft text-bad")}>{msg.text}</p>}
            </div>
          </Card>

          <div className="space-y-5">
            <Card className="p-6 animate-fade-up [animation-delay:60ms]">
              <CardHead title="Why we built this" />
              <ul className="mt-4 space-y-3.5 text-[13px] text-ink-2">
                {[
                  [ShieldCheck, "An emergency before payday shouldn't mean borrowing at high interest from outside work."],
                  [BadgePercent, "No interest and no fees: you only get pay you have already earned."],
                  [Zap, "A finance manager approves each request. You see the decision here and in your activity."],
                  [CalendarCheck, "It comes back automatically from your next salary. Nothing to remember."],
                ].map(([I, t], i) => {
                  const Icon = I as typeof Zap;
                  return (
                    <li key={i} className="flex gap-3">
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-soft text-brand">
                        <Icon size={15} />
                      </span>
                      <span className="pt-1.5 leading-snug">{t as string}</span>
                    </li>
                  );
                })}
              </ul>
            </Card>
            <Card className="p-6 animate-fade-up [animation-delay:120ms]">
              <CardHead title="Your advances" />
              {!data.history?.length && <Empty title="No advances yet" />}
              <ul className="mt-2 divide-y divide-line/70">
                {data.history?.map((a) => (
                  <li key={a.id} className="flex items-center gap-3 py-3">
                    <span className="grid h-10 w-10 place-items-center rounded-full bg-surface-2">
                      <HandCoins size={17} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="num text-[14px] font-semibold">{money(a.amount)}</p>
                      <p className="truncate text-xs text-muted">
                        {a.reason || "Advance"} · {ago(a.requested_at)} · repay {dLong(a.repay_date)}
                      </p>
                    </div>
                    <StatusPill status={a.status} />
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
