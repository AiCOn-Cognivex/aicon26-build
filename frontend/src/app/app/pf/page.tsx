"use client";

import { Landmark, PiggyBank, TrendingUp } from "lucide-react";
import { AreaChart, Ring } from "@/components/charts";
import { PageHeader, PageLoader } from "@/components/shell";
import { Card, CardHead, DemoTag, ErrorNote } from "@/components/ui";
import type { PF } from "@/lib/appTypes";
import { d, money, monthLabel } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type PFDetail = PF & { rate: number; series_full: { period: string; employee: number; employer: number }[] };

export default function PFPage() {
  const { data, error, reload } = useApi<PFDetail>("/me/pf");
  return (
    <>
      <PageHeader title="Provident fund" sub={<span className="inline-flex items-center gap-2">Savings you and your employer build together <DemoTag /></span>} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!data && !error && <PageLoader />}
      {data && (
        <div className="grid gap-5 xl:grid-cols-3">
          <Card className="p-6 sm:p-7 xl:col-span-2 animate-fade-up">
            <CardHead title="Balance" sub="Last 12 months" icon={<PiggyBank size={18} />} />
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <p className="num text-[38px] font-bold leading-none tracking-tight">{money(data.balance)}</p>
              <span className="mb-1 inline-flex items-center gap-1 rounded-full bg-brand-soft px-2.5 py-1 text-xs font-semibold text-brand-strong">
                <TrendingUp size={13} /> +{money(data.growth_12m)} this year
              </span>
            </div>
            <div className="mt-6">
              <AreaChart height={240} points={data.series.map((s) => ({ label: monthLabel(s.period), sub: d(s.period + "-01", { month: "long", year: "numeric" }), value: s.balance }))} />
            </div>
          </Card>
          <Card className="flex flex-col items-center p-6 text-center animate-fade-up [animation-delay:60ms]">
            <CardHead title="Who put it in" sub="Contributions since you joined" />
            <div className="my-6">
              <Ring value={data.employee_total / (data.employee_total + data.employer_total)} size={180} stroke={18} color="var(--color-brand)" track="var(--color-accent)">
                <div>
                  <p className="text-[11px] text-muted">Employer match</p>
                  <p className="num text-xl font-bold">{money(data.employer_total)}</p>
                </div>
              </Ring>
            </div>
            <div className="grid w-full grid-cols-2 gap-2 text-left">
              <div className="inset px-4 py-3">
                <p className="flex items-center gap-1.5 text-[11px] text-muted">
                  <span className="h-2 w-2 rounded-full bg-brand" /> You
                </p>
                <p className="num text-sm font-semibold">{money(data.employee_total)}</p>
              </div>
              <div className="inset px-4 py-3">
                <p className="flex items-center gap-1.5 text-[11px] text-muted">
                  <span className="h-2 w-2 rounded-full bg-accent" /> Employer
                </p>
                <p className="num text-sm font-semibold">{money(data.employer_total)}</p>
              </div>
            </div>
            <p className="mt-4 text-xs text-muted">Each month you and your employer each put in {(data.rate * 100).toFixed(2)}% of your basic salary.</p>
          </Card>
          <Card className="p-6 animate-fade-up [animation-delay:100ms]">
            <CardHead title="In 5 years" sub="If contributions continue" icon={<TrendingUp size={18} />} />
            <p className="num mt-5 text-[30px] font-bold tracking-tight">{money(data.projection_5y)}</p>
            <p className="mt-2 text-xs leading-relaxed text-muted">
              Estimate: today&apos;s balance plus {money(data.monthly_contribution)} a month, growing at an assumed {(data.assumed_profit_rate * 100).toFixed(0)}% a year. Real profit rates are declared by the fund each year.
            </p>
          </Card>
          <Card className="p-6 animate-fade-up [animation-delay:140ms]">
            <CardHead title="Borrow from your fund" sub="Company policy (demo)" icon={<Landmark size={18} />} />
            <p className="num mt-5 text-[30px] font-bold tracking-tight">{money(data.loan_eligible)}</p>
            <p className="mt-2 text-xs leading-relaxed text-muted">Up to 80% of your own contributions can be taken as a provident fund loan, repaid from salary.</p>
          </Card>
          <Card className="p-6 animate-fade-up [animation-delay:180ms]">
            <CardHead title="Monthly contribution" />
            <ul className="mt-4 space-y-2 text-[13px]">
              <li className="flex justify-between">
                <span className="text-muted">You</span>
                <span className="num font-semibold">{money(data.monthly_contribution - data.employer_match_monthly)}</span>
              </li>
              <li className="flex justify-between">
                <span className="text-muted">Employer</span>
                <span className="num font-semibold">{money(data.employer_match_monthly)}</span>
              </li>
              <li className="flex justify-between border-t border-line pt-2 font-semibold">
                <span>Total each month</span>
                <span className="num">{money(data.monthly_contribution)}</span>
              </li>
            </ul>
          </Card>
        </div>
      )}
    </>
  );
}
