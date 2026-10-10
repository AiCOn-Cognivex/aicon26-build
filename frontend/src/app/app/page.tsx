"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, CalendarClock, ChevronDown, HandCoins, Lightbulb, PiggyBank, ScanLine, TrendingUp } from "lucide-react";
import { AreaChart, ArcGauge, PayChart, Ring, SERIES } from "@/components/charts";
import { PageHeader } from "@/components/shell";
import { Card, CardHead, DemoTag, ErrorNote, LinkButton, Skeleton, cx } from "@/components/ui";
import { ActivityList, ClaimMini, MoneyCalendar, NotifBell, SeeAll, WalletCard } from "@/components/widgets";
import { AskRepay } from "@/components/AskRepay";
import type { Dashboard } from "@/lib/appTypes";
import { useAuth } from "@/lib/auth";
import { d, greeting, money, monthLabel } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function DashboardPage() {
  const { user } = useAuth();
  const { data, error, reload } = useApi<Dashboard>("/me/dashboard");
  const first = user?.name.split(" ")[0] ?? "";

  return (
    <>
      <PageHeader
        avatar={user?.name}
        title={`${greeting()}, ${first}`}
        sub={
          <span className="inline-flex flex-wrap items-center gap-2">
            Here&apos;s your money at a glance · {user?.company.name} <DemoTag />
          </span>
        }
        actions={
          <>
            <NotifBell nudges={data?.nudges ?? []} />
            <LinkButton href="/app/claims/new" className="hidden sm:inline-flex">
              <ScanLine size={17} /> Scan a receipt
            </LinkButton>
          </>
        }
      />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!data && !error && <DashSkeleton />}
      {data && <Body data={data} assistant={!!user?.assistant} />}
    </>
  );
}

function Body({ data, assistant }: { data: Dashboard; assistant: boolean }) {
  const p = data.payday;
  const chart = [
    ...data.paychecks.map((c) => ({ period: c.period, salary: c.salary, reimbursements: c.reimbursements, pay_date: c.pay_date })),
    { period: "next", salary: p.net - p.reimbursements, reimbursements: p.reimbursements, pay_date: p.pay_date, projected: true },
  ];
  const t = data.allowance_totals;
  return (
    <div className="grid gap-5 xl:grid-cols-12">
      <PaydayHero data={data} />

      <Card className="p-6 xl:col-span-3 animate-fade-up [animation-delay:60ms]">
        <CardHead title="Allowances left" sub="All wallets, this period" />
        <div className="mt-5 flex justify-center">
          <ArcGauge used={t.used} pending={t.pending} limit={t.limit} size={190} stroke={15}>
            <p className="num text-[26px] font-bold leading-none">{money(t.left)}</p>
            <p className="mt-1 text-xs text-muted">of {money(t.limit)}</p>
          </ArcGauge>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-2 text-center">
          {[
            ["Used", t.used, "bg-brand"],
            ["In review", t.pending, "bg-brand/35"],
            ["Left", t.left, "bg-line"],
          ].map(([l, v, c]) => (
            <div key={l as string} className="inset py-2.5">
              <p className="flex items-center justify-center gap-1.5 text-[11px] text-muted">
                <span className={cx("h-2 w-2 rounded-full", c as string)} />
                {l as string}
              </p>
              <p className="num mt-0.5 text-[13px] font-semibold">{money(v as number)}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card className="flex flex-col p-6 xl:col-span-3 animate-fade-up [animation-delay:120ms]">
        <CardHead title="Salary advance" sub="On pay you've already earned" icon={<HandCoins size={18} />} />
        <p className="mt-6 text-xs font-medium text-muted">Available right now</p>
        <p className="num mt-1 text-[32px] font-bold leading-none tracking-tight">{money(data.advance.available)}</p>
        <div className="mt-5">
          <div className="flex justify-between text-xs text-muted">
            <span>Earned so far this month</span>
            <span className="num font-semibold text-ink">{money(data.advance.earned_so_far)}</span>
          </div>
          <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full bg-gradient-to-r from-brand to-[#3fb68b]" style={{ width: `${Math.round(p.cycle_progress * 100)}%` }} />
          </div>
        </div>
        <p className="mt-4 text-xs text-muted">0% interest, no fees. Deducted on {d(p.pay_date, { weekday: "short", day: "numeric", month: "short" })}.</p>
        <LinkButton href="/app/advance" variant="dark" className="mt-6 w-full">
          Get an advance <ArrowUpRight size={16} />
        </LinkButton>
      </Card>

      {assistant && <AskRepay />}

      <section className="xl:col-span-12">
        <div className="mb-3 flex items-end justify-between px-1">
          <div>
            <h2 className="text-[17px] font-bold tracking-tight">Your allowances</h2>
            <p className="text-xs text-muted">Tap a wallet to claim against it</p>
          </div>
          <SeeAll href="/app/claims" label="All claims" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {data.wallets.map((w) => (
            <WalletCard key={w.id} w={w} />
          ))}
        </div>
      </section>

      <Card className="p-6 xl:col-span-8">
        <CardHead
          title="Pay history"
          sub="Take-home per month: salary plus reimbursements"
          right={
            <div className="hidden gap-4 text-xs text-muted sm:flex">
              <Legend color={SERIES.a} label="Salary" />
              <Legend color={SERIES.b} label="Reimbursements" />
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full border border-dashed border-brand bg-brand-soft" />
                Next payday
              </span>
            </div>
          }
        />
        <div className="mt-5">
          <PayChart data={chart} />
        </div>
      </Card>

      <Card className="flex flex-col p-6 xl:col-span-4">
        <CardHead title="Provident fund" sub="Your retirement savings" icon={<PiggyBank size={18} />} right={<SeeAll href="/app/pf" label="Details" />} />
        <p className="num mt-5 text-[30px] font-bold leading-none tracking-tight">{money(data.pf.balance)}</p>
        <p className="mt-2 inline-flex w-fit items-center gap-1 rounded-full bg-brand-soft px-2.5 py-1 text-xs font-semibold text-brand-strong">
          <TrendingUp size={13} /> +{money(data.pf.growth_12m)} in 12 months
        </p>
        <div className="mt-3 flex-1">
          <AreaChart axis={false} height={110} points={data.pf.series.map((s) => ({ label: monthLabel(s.period), sub: d(s.period + "-01", { month: "long", year: "numeric" }), value: s.balance }))} />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="inset px-3.5 py-2.5">
            <p className="text-[11px] text-muted">You add / month</p>
            <p className="num text-sm font-semibold">{money(data.pf.monthly_contribution - data.pf.employer_match_monthly)}</p>
          </div>
          <div className="inset px-3.5 py-2.5">
            <p className="text-[11px] text-muted">Employer adds</p>
            <p className="num text-sm font-semibold">{money(data.pf.employer_match_monthly)}</p>
          </div>
        </div>
      </Card>

      <Card className="p-6 xl:col-span-5">
        <CardHead title="Recent activity" sub="Claims, salary, advances and PF" right={<SeeAll href="/app/claims" />} />
        <div className="mt-2">
          <ActivityList events={data.activity} />
        </div>
      </Card>

      <Card className="p-6 xl:col-span-4">
        <CardHead title="Money calendar" sub="What's coming up" icon={<CalendarClock size={18} />} />
        <div className="mt-4">
          <MoneyCalendar items={data.calendar} />
        </div>
      </Card>

      <div className="space-y-5 xl:col-span-3">
        <Card className="p-6">
          <CardHead title="Claims in progress" right={<SeeAll href="/app/claims" />} />
          <div className="mt-3 space-y-1">
            {data.open_claims.length === 0 && <p className="py-4 text-center text-sm text-muted">Nothing in progress.</p>}
            {data.open_claims.map((c) => (
              <ClaimMini key={c.id} c={c} />
            ))}
          </div>
        </Card>
        {data.nudges.length > 0 && (
          <Card className="p-6">
            <CardHead title="Tips for you" icon={<Lightbulb size={18} />} />
            <ul className="mt-3 space-y-2.5 text-[13px] leading-snug text-ink-2">
              {data.nudges.slice(0, 3).map((n, i) => (
                <li key={i} className="rounded-2xl bg-surface-2/70 p-3">
                  {n.text}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}

function PaydayHero({ data }: { data: Dashboard }) {
  const p = data.payday;
  const [open, setOpen] = useState(false);
  const rows: [string, number][] = [
    ["Gross salary", p.gross],
    ["Income tax", -p.tax],
    ["Provident fund (your share)", -p.pf_employee],
    ...(p.advance_repayment ? ([["Salary advance", -p.advance_repayment]] as [string, number][]) : []),
    [`Approved claims (${p.reimbursement_count})`, p.reimbursements],
  ];
  return (
    <section className="relative overflow-hidden rounded-[var(--radius-card)] bg-gradient-to-br from-brand-deep via-[#0a5a3e] to-brand p-6 text-white shadow-[var(--shadow-lift)] sm:p-7 xl:col-span-6 animate-fade-up">
      <svg className="pointer-events-none absolute -right-24 -top-28 h-[420px] w-[420px]" viewBox="0 0 420 420" aria-hidden>
        {[190, 150, 110].map((r, i) => (
          <circle key={r} cx="210" cy="210" r={r} fill="none" stroke="white" strokeOpacity={0.05 + i * 0.025} strokeWidth="28" />
        ))}
      </svg>
      <div className="relative flex flex-wrap items-center gap-6">
        <Ring value={p.cycle_progress} size={150} stroke={14} color="#7ee2b8" track="rgb(255 255 255 / 0.14)">
          <div>
            <p className="num text-[34px] font-bold leading-none">{p.days_left}</p>
            <p className="mt-1 text-xs text-white/70">{p.days_left === 1 ? "day to go" : "days to go"}</p>
          </div>
        </Ring>
        <div className="min-w-0 flex-1">
          <p className="inline-flex items-center gap-1.5 rounded-full bg-white/12 px-3 py-1 text-xs font-semibold text-white/90">
            <CalendarClock size={13} /> Next payday · {d(p.pay_date, { weekday: "long", day: "numeric", month: "long" })}
          </p>
          <p className="mt-4 text-sm text-white/70">Expected take-home</p>
          <p className="num text-[38px] font-bold leading-tight tracking-tight sm:text-[44px]">{money(p.net)}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {p.reimbursements > 0 && <span className="rounded-full bg-[#7ee2b8]/20 px-2.5 py-1 font-semibold text-[#bdf3dc]">+ {money(p.reimbursements)} in claims</span>}
            {p.advance_repayment > 0 && <span className="rounded-full bg-white/12 px-2.5 py-1 font-semibold">− {money(p.advance_repayment)} advance</span>}
          </div>
        </div>
      </div>
      <div className="relative mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-white/12 pt-4">
        <p className="text-xs text-white/70">
          Claims approved by <span className="font-semibold text-white">{d(data.cutoff.date, { weekday: "short", day: "numeric", month: "short" })}</span> are paid this payday
        </p>
        <button onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 rounded-full bg-white/12 px-3.5 py-1.5 text-xs font-semibold transition hover:bg-white/20">
          Breakdown <ChevronDown size={14} className={cx("transition", open && "rotate-180")} />
        </button>
      </div>
      {open && (
        <div className="relative mt-4 space-y-1.5 rounded-[20px] bg-white/8 p-4 text-[13px] animate-fade-up">
          {rows.map(([l, v]) => (
            <div key={l} className="flex justify-between">
              <span className="text-white/75">{l}</span>
              <span className="num font-semibold">{v < 0 ? `− ${money(-v)}` : money(v)}</span>
            </div>
          ))}
          <div className="flex justify-between border-t border-white/15 pt-2 font-bold">
            <span>Take-home</span>
            <span className="num">{money(p.net)}</span>
          </div>
          <Link href="/app/payslips" className="block pt-1 text-xs font-semibold text-[#bdf3dc] hover:underline">
            See all payslips →
          </Link>
        </div>
      )}
    </section>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function DashSkeleton() {
  return (
    <div className="grid gap-5 xl:grid-cols-12">
      <Skeleton className="h-[290px] rounded-[28px] xl:col-span-6" />
      <Skeleton className="h-[290px] rounded-[28px] xl:col-span-3" />
      <Skeleton className="h-[290px] rounded-[28px] xl:col-span-3" />
      <Skeleton className="h-[250px] rounded-[28px] xl:col-span-12" />
      <Skeleton className="h-[320px] rounded-[28px] xl:col-span-8" />
      <Skeleton className="h-[320px] rounded-[28px] xl:col-span-4" />
    </div>
  );
}
