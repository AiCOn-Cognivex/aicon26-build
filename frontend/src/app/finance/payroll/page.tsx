"use client";

import { useState } from "react";
import { BadgeCheck, ChevronLeft, ChevronRight, Download, LoaderCircle } from "lucide-react";
import { PageHeader, PageLoader } from "@/components/shell";
import { Avatar, Button, Card, Empty, ErrorNote } from "@/components/ui";
import { api, download } from "@/lib/client";
import { d, dLong, money } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Payroll = {
  pay_date: string;
  previous: string;
  next: string;
  cutoff: string;
  rows: { employee_id: number; name: string; email: string; department: string; reimbursements: number; claims: number; advance_deduction: number; net_adjustment: number; paid: boolean }[];
  totals: { reimbursements: number; claims: number; advance_deduction: number; net_adjustment: number };
  closed: boolean;
};

export default function PayrollPage() {
  const [date, setDate] = useState<string | null>(null);
  const { data, error, reload } = useApi<Payroll>(`/admin/payroll${date ? `?pay_date=${date}` : ""}`);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);

  async function close() {
    if (!data) return;
    setBusy(true);
    try {
      await api("/admin/payroll/close", { json: { pay_date: data.pay_date } });
      setConfirm(false);
      await reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Payroll" sub="What to add to (or deduct from) each salary. Export it to your payroll system." />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!data && !error && <PageLoader />}
      {data && (
        <div className="space-y-5">
          <Card className="flex flex-wrap items-center justify-between gap-4 p-5 animate-fade-up">
            <div className="flex items-center gap-2">
              <button aria-label="Previous pay run" onClick={() => setDate(data.previous)} className="grid h-10 w-10 place-items-center rounded-full bg-surface-2 hover:bg-line">
                <ChevronLeft size={18} />
              </button>
              <div className="px-2 text-center">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Pay run</p>
                <p className="text-[15px] font-bold">{dLong(data.pay_date)}</p>
              </div>
              <button aria-label="Next pay run" onClick={() => setDate(data.next)} className="grid h-10 w-10 place-items-center rounded-full bg-surface-2 hover:bg-line">
                <ChevronRight size={18} />
              </button>
            </div>
            <p className="text-xs text-muted">Claims approved by {d(data.cutoff, { day: "numeric", month: "short" })} are in this run</p>
            <div className="flex gap-2">
              <Button variant="soft" disabled={!data.rows.length} onClick={() => download(`/admin/payroll.csv?pay_date=${data.pay_date}`, `payroll-adjustments-${data.pay_date}.csv`)}>
                <Download size={16} /> CSV
              </Button>
              {data.closed ? (
                <span className="inline-flex h-11 items-center gap-2 rounded-full bg-brand-soft px-5 text-sm font-semibold text-brand-strong">
                  <BadgeCheck size={17} /> Paid
                </span>
              ) : (
                <Button disabled={!data.rows.length} onClick={() => setConfirm(true)}>
                  Mark as paid
                </Button>
              )}
            </div>
          </Card>
          {confirm && (
            <Card className="flex flex-wrap items-center justify-between gap-3 border-brand/30 p-5 animate-fade-up">
              <p className="text-sm">
                Mark {data.totals.claims} claims as paid and {money(data.totals.advance_deduction)} of advances as repaid on {dLong(data.pay_date)}? Employees see it at once.
              </p>
              <div className="flex gap-2">
                <Button variant="soft" onClick={() => setConfirm(false)}>
                  Cancel
                </Button>
                <Button onClick={close} disabled={busy}>
                  {busy && <LoaderCircle size={16} className="animate-spin" />} Confirm
                </Button>
              </div>
            </Card>
          )}
          <div className="grid gap-5 md:grid-cols-3">
            {[
              ["Reimbursements to add", data.totals.reimbursements, `${data.totals.claims} approved claims`],
              ["Advances to deduct", data.totals.advance_deduction, "Interest-free salary advances"],
              ["Net change to payroll", data.totals.net_adjustment, `${data.rows.length} employees`],
            ].map(([k, v, s], i) => (
              <Card key={k as string} className="p-6 animate-fade-up" style={{ animationDelay: `${i * 50}ms` }}>
                <p className="text-sm text-muted">{k as string}</p>
                <p className="num mt-2 text-[28px] font-bold tracking-tight">{money(v as number)}</p>
                <p className="mt-1 text-xs text-muted">{s as string}</p>
              </Card>
            ))}
          </div>
          <Card className="overflow-hidden p-0">
            {!data.rows.length ? (
              <Empty title="Nothing in this pay run" sub="Approved claims and advances will show here." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-[13.5px]">
                  <thead>
                    <tr className="bg-surface-2/70 text-left text-xs text-muted">
                      <th className="px-6 py-3 font-semibold">Employee</th>
                      <th className="px-4 py-3 text-right font-semibold">Claims</th>
                      <th className="px-4 py-3 text-right font-semibold">Reimburse</th>
                      <th className="px-4 py-3 text-right font-semibold">Advance</th>
                      <th className="px-6 py-3 text-right font-semibold">Net change</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line/70">
                    {data.rows.map((r) => (
                      <tr key={r.employee_id}>
                        <td className="px-6 py-3">
                          <div className="flex items-center gap-3">
                            <Avatar name={r.name} size={34} />
                            <div>
                              <p className="font-semibold">{r.name}</p>
                              <p className="text-xs text-muted">{r.department}</p>
                            </div>
                          </div>
                        </td>
                        <td className="num px-4 py-3 text-right">{r.claims}</td>
                        <td className="num px-4 py-3 text-right">{money(r.reimbursements)}</td>
                        <td className="num px-4 py-3 text-right">{r.advance_deduction ? `− ${money(r.advance_deduction)}` : "—"}</td>
                        <td className="num px-6 py-3 text-right font-semibold">{money(r.net_adjustment)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
