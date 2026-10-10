"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowDownRight, ArrowUpRight, ChevronDown, FileBadge, FileText } from "lucide-react";
import { PageHeader, PageLoader } from "@/components/shell";
import { Card, DemoTag, ErrorNote, LinkButton, cx } from "@/components/ui";
import type { Pay } from "@/lib/appTypes";
import { d, dLong, money } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Slip = {
  period: string;
  pay_date: string;
  basic: number;
  house_rent: number;
  utilities: number;
  gross: number;
  tax: number;
  pf_employee: number;
  pf_employer: number;
  advance_repayment: number;
  reimbursements: number;
  net: number;
  changes?: { label: string; diff: number }[];
  net_diff?: number;
};

export default function PayslipsPage() {
  const { data, error, reload } = useApi<{ payslips: Slip[]; upcoming: Pay }>("/payslips");
  const [open, setOpen] = useState<string | null>(null);
  return (
    <>
      <PageHeader
        title="Payslips"
        sub={<span className="inline-flex items-center gap-2">Every salary, and what changed month to month <DemoTag /></span>}
        actions={
          <LinkButton href="/certificate" variant="soft" size="sm">
            <FileBadge size={15} /> Salary certificate
          </LinkButton>
        }
      />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!data && !error && <PageLoader />}
      {data && (
        <div className="space-y-5">
          <Card className="relative overflow-hidden p-6 sm:p-7 animate-fade-up">
            <div className="pointer-events-none absolute -right-16 -top-20 h-64 w-64 rounded-full border-[28px] border-brand-soft" />
            <p className="text-xs font-semibold uppercase tracking-wider text-brand">Coming up · {dLong(data.upcoming.pay_date)}</p>
            <div className="relative mt-3 flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-sm text-muted">Expected take-home</p>
                <p className="num text-[36px] font-bold leading-tight tracking-tight">{money(data.upcoming.net)}</p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <Chip label="Gross" v={money(data.upcoming.gross)} />
                <Chip label="Tax" v={`− ${money(data.upcoming.tax)}`} />
                <Chip label="PF" v={`− ${money(data.upcoming.pf_employee)}`} />
                {data.upcoming.advance_repayment > 0 && <Chip label="Advance" v={`− ${money(data.upcoming.advance_repayment)}`} />}
                <Chip label="Claims" v={`+ ${money(data.upcoming.reimbursements)}`} good />
              </div>
            </div>
          </Card>

          <Card className="p-3 sm:p-4">
            <ul className="divide-y divide-line/70">
              {data.payslips.map((s) => {
                const isOpen = open === s.period;
                return (
                  <li key={s.period}>
                    <button onClick={() => setOpen(isOpen ? null : s.period)} className="flex w-full items-center gap-3.5 rounded-2xl px-3 py-3.5 text-left transition hover:bg-surface-2/70">
                      <span className="grid h-11 w-11 place-items-center rounded-full bg-brand-soft text-brand">
                        <FileText size={18} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[14px] font-semibold">{d(s.period + "-01", { month: "long", year: "numeric" })}</p>
                        <p className="text-xs text-muted">Paid {dLong(s.pay_date)}</p>
                      </div>
                      {s.net_diff !== undefined && s.net_diff !== 0 && (
                        <span className={cx("hidden items-center gap-0.5 rounded-full px-2 py-0.5 text-[11.5px] font-semibold sm:inline-flex", s.net_diff > 0 ? "bg-brand-soft text-brand-strong" : "bg-surface-2 text-muted")}>
                          {s.net_diff > 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                          {money(Math.abs(s.net_diff))}
                        </span>
                      )}
                      <span className="num text-[15px] font-bold">{money(s.net)}</span>
                      <ChevronDown size={16} className={cx("text-muted transition", isOpen && "rotate-180")} />
                    </button>
                    {isOpen && <SlipDetail s={s} />}
                  </li>
                );
              })}
            </ul>
          </Card>
        </div>
      )}
    </>
  );
}

function Chip({ label, v, good }: { label: string; v: string; good?: boolean }) {
  return (
    <span className={cx("rounded-full px-3 py-1.5", good ? "bg-brand-soft text-brand-deep" : "bg-surface-2")}>
      <span className="text-muted">{label}</span> <span className="num font-semibold">{v}</span>
    </span>
  );
}

function SlipDetail({ s }: { s: Slip }) {
  const earn: [string, number][] = [
    ["Basic salary", s.basic],
    ["House rent allowance", s.house_rent],
    ["Utilities allowance", s.utilities],
  ];
  const ded: [string, number][] = [
    ["Income tax", s.tax],
    ["Provident fund (your share)", s.pf_employee],
    ...(s.advance_repayment ? ([["Salary advance repaid", s.advance_repayment]] as [string, number][]) : []),
  ];
  return (
    <div className="mx-3 mb-4 grid gap-4 rounded-[22px] bg-surface-2/70 p-5 text-[13px] animate-fade-up md:grid-cols-3">
      <Block title="Earnings" rows={earn} total={["Gross", s.gross]} />
      <Block title="Deductions" rows={ded} total={["Total deducted", s.tax + s.pf_employee + s.advance_repayment]} />
      <div>
        <Block title="Added" rows={[["Approved claims", s.reimbursements]]} total={["Take-home", s.net]} />
        <p className="mt-3 text-xs text-muted">Employer also added {money(s.pf_employer)} to your provident fund.</p>
        {!!s.changes?.length && (
          <div className="mt-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">vs last month</p>
            <ul className="mt-1.5 space-y-1">
              {s.changes.map((c) => (
                <li key={c.label} className="flex justify-between">
                  <span className="text-ink-2">{c.label}</span>
                  <span className={cx("num font-semibold", c.diff > 0 ? "text-ink" : "text-muted")}>
                    {c.diff > 0 ? "+" : "−"} {money(Math.abs(c.diff))}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <Link href="/app/pf" className="mt-3 inline-block text-xs font-semibold text-brand hover:underline">
          Provident fund →
        </Link>
      </div>
    </div>
  );
}

function Block({ title, rows, total }: { title: string; rows: [string, number][]; total: [string, number] }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</p>
      <ul className="mt-2 space-y-1.5">
        {rows.map(([k, v]) => (
          <li key={k} className="flex justify-between gap-3">
            <span className="text-ink-2">{k}</span>
            <span className="num font-medium">{money(v)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 flex justify-between border-t border-line pt-2 font-semibold">
        <span>{total[0]}</span>
        <span className="num">{money(total[1])}</span>
      </p>
    </div>
  );
}
