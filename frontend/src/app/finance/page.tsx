"use client";

import Link from "next/link";
import { Banknote, BrainCircuit, ChevronRight, ClipboardCheck, Clock, Zap } from "lucide-react";
import { ArcGauge, HBars } from "@/components/charts";
import { PageHeader } from "@/components/shell";
import { Avatar, Card, CardHead, DemoTag, ErrorNote, LinkButton, Skeleton } from "@/components/ui";
import { ActivityList, SeeAll } from "@/components/widgets";
import type { ClaimRow, EventRow } from "@/lib/appTypes";
import { useAuth } from "@/lib/auth";
import { dLong, greeting, money, pctf } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Overview = {
  today: string;
  payday: string;
  cutoff: string;
  month: { submitted: number; auto_approved: number; decided: number; auto_rate: number | null; amount_approved: number; rejected: number };
  queue: { count: number; amount: number; oldest_hours: number };
  decision_hours_median: number | null;
  payroll: { pay_date: string; amount: number; claims: number; employees: number; advances: number };
  labels_collected: { reviewed: number; corrected: number };
  by_wallet: { wallet: string; approved: number; pending: number }[];
  advances_open: number;
  events: EventRow[];
  employees: number;
};

export default function FinanceOverview() {
  const { user } = useAuth();
  const { data, error, reload } = useApi<Overview>("/admin/overview");
  const queue = useApi<{ claims: ClaimRow[] }>("/admin/queue");
  return (
    <>
      <PageHeader
        avatar={user?.name}
        title={`${greeting()}, ${user?.name.split(" ")[0] ?? ""}`}
        sub={<span className="inline-flex flex-wrap items-center gap-2">Finance overview · {user?.company.name} <DemoTag /></span>}
        actions={
          <LinkButton href="/finance/review">
            <ClipboardCheck size={17} /> Review queue
          </LinkButton>
        }
      />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!data && !error && (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[200px] rounded-[28px]" />
          ))}
        </div>
      )}
      {data && (
        <div className="grid gap-5 xl:grid-cols-12">
          <Card className="p-6 md:col-span-1 xl:col-span-3 animate-fade-up">
            <CardHead title="Waiting for review" icon={<Clock size={18} />} />
            <p className="num mt-5 text-[38px] font-bold leading-none">{data.queue.count}</p>
            <p className="mt-2 text-sm text-muted">{money(data.queue.amount)} in claims</p>
            <p className="mt-4 text-xs text-muted">{data.queue.count ? `Oldest has waited ${data.queue.oldest_hours < 24 ? `${Math.round(data.queue.oldest_hours)} h` : `${Math.round(data.queue.oldest_hours / 24)} days`}` : "Queue is clear"}</p>
          </Card>
          <Card className="flex flex-col items-center p-6 text-center xl:col-span-3 animate-fade-up [animation-delay:50ms]">
            <CardHead title="Approved instantly by AI" sub="Claims submitted this month" />
            <div className="mt-4">
              <ArcGauge used={data.month.auto_approved} limit={Math.max(1, data.month.submitted)} size={170} stroke={14}>
                <p className="num text-[28px] font-bold leading-none">{pctf(data.month.auto_rate)}</p>
                <p className="mt-1 text-[11px] text-muted">
                  {data.month.auto_approved} of {data.month.submitted}
                </p>
              </ArcGauge>
            </div>
            <p className="mt-3 text-xs text-muted">Median time for a person to decide: {data.decision_hours_median !== null ? `${data.decision_hours_median} h` : "—"}</p>
          </Card>
          <Card className="p-6 xl:col-span-3 animate-fade-up [animation-delay:100ms]">
            <CardHead title="Next payroll" sub={dLong(data.payroll.pay_date)} icon={<Banknote size={18} />} />
            <p className="num mt-5 text-[30px] font-bold leading-none tracking-tight">{money(data.payroll.amount)}</p>
            <p className="mt-2 text-sm text-muted">
              {data.payroll.claims} claims · {data.payroll.employees} employees
            </p>
            <p className="mt-1 text-xs text-muted">Advances to deduct: {money(data.payroll.advances)}</p>
            <div className="mt-4">
              <SeeAll href="/finance/payroll" label="Open payroll" />
            </div>
          </Card>
          <Card className="relative overflow-hidden p-6 xl:col-span-3 animate-fade-up [animation-delay:150ms]">
            <div className="pointer-events-none absolute -bottom-16 -right-16 h-48 w-48 rounded-full border-[22px] border-accent-soft" />
            <CardHead title="Teaching the next model" icon={<BrainCircuit size={18} />} />
            <p className="num mt-5 text-[38px] font-bold leading-none">{data.labels_collected.reviewed}</p>
            <p className="mt-2 text-sm text-muted">claims checked by a person</p>
            <p className="relative mt-4 text-xs leading-relaxed text-muted">
              {data.labels_collected.corrected} amount corrections so far. Every decision is saved as a labelled example for retraining on your own receipts.
            </p>
          </Card>

          <Card className="p-6 xl:col-span-7">
            <CardHead title="Review queue" sub="Oldest first" right={<SeeAll href="/finance/review" />} />
            <ul className="mt-3 divide-y divide-line/70">
              {queue.data?.claims.length === 0 && <p className="py-8 text-center text-sm text-muted">Nothing waiting. Nice.</p>}
              {queue.data?.claims.slice(0, 5).map((c) => (
                <li key={c.id}>
                  <Link href={`/finance/review/${c.id}`} className="flex items-center gap-3 rounded-2xl px-2 py-3 transition hover:bg-surface-2/70">
                    <Avatar name={c.employee?.name ?? "?"} size={40} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13.5px] font-semibold">
                        {c.employee?.name} <span className="font-normal text-muted">· {c.wallet?.name}</span>
                      </p>
                      <p className="truncate text-xs text-muted">{c.reasons[0]}</p>
                    </div>
                    <span className="num text-[13.5px] font-semibold">{money(c.amount_pkr)}</span>
                    <ChevronRight size={16} className="text-muted" />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-6 xl:col-span-5">
            <CardHead title="Spend by allowance" sub="This month" />
            <div className="mt-5">
              <HBars rows={data.by_wallet.map((w) => ({ label: w.wallet, a: w.approved, b: w.pending }))} labels={["Approved", "In review"]} />
            </div>
          </Card>
          <Card className="p-6 xl:col-span-12">
            <CardHead title="Company activity" sub="Audit trail: every claim, decision, advance and policy change" icon={<Zap size={18} />} />
            <div className="mt-2 grid gap-x-8 md:grid-cols-2">
              <ActivityList events={data.events.slice(0, 6)} showEmployee />
              <ActivityList events={data.events.slice(6, 12)} showEmployee />
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
