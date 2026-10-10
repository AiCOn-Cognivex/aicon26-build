"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ChevronRight, ScanLine, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Button, Card, Empty, ErrorNote, LinkButton, Segmented, Skeleton, StatusPill, WalletBadge } from "@/components/ui";
import type { ClaimRow } from "@/lib/appTypes";
import { d, money } from "@/lib/format";
import { claimHref } from "@/lib/routes";
import { useApi } from "@/lib/useApi";

type Tab = "all" | "in_review" | "approved" | "paid" | "rejected";

export default function ClaimsPage() {
  const { data, error, reload } = useApi<{ claims: ClaimRow[] }>("/claims");
  const [tab, setTab] = useState<Tab>("all");
  const claims = useMemo(() => data?.claims ?? [], [data]);
  const groups = useMemo(() => {
    const f = (t: Tab) => (t === "all" ? claims : claims.filter((c) => (t === "approved" ? c.status === "approved" || c.status === "auto_approved" : c.status === t)));
    return { list: f(tab), count: (t: Tab) => f(t).length };
  }, [claims, tab]);
  const [shown, setShown] = useState(20);
  const months = useMemo(() => {
    const out: [string, ClaimRow[]][] = [];
    for (const c of groups.list.slice(0, shown)) {
      const m = d(c.receipt_date ?? c.submitted_at, { month: "long", year: "numeric" });
      if (!out.length || out[out.length - 1][0] !== m) out.push([m, []]);
      out[out.length - 1][1].push(c);
    }
    return out;
  }, [groups, shown]);
  const auto = claims.filter((c) => c.status === "auto_approved" || (c.status === "paid" && c.reasons.length === 0)).length;

  return (
    <>
      <PageHeader
        title="Claims"
        sub="Every receipt you've claimed, and where it is"
        actions={
          <LinkButton href="/app/claims/new">
            <ScanLine size={17} /> New claim
          </LinkButton>
        }
      />
      {error && <ErrorNote error={error} onRetry={reload} />}
      <Card className="p-4 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Segmented<Tab>
            value={tab}
            onChange={(t) => {
              setTab(t);
              setShown(20);
            }}
            options={[
              { value: "all", label: "All", count: groups.count("all") },
              { value: "in_review", label: "In review", count: groups.count("in_review") },
              { value: "approved", label: "Approved", count: groups.count("approved") },
              { value: "paid", label: "Paid", count: groups.count("paid") },
              { value: "rejected", label: "Rejected", count: groups.count("rejected") },
            ]}
          />
          {claims.length > 0 && (
            <p className="flex items-center gap-1.5 text-xs text-muted">
              <Sparkles size={13} className="text-brand" />
              {auto} of {claims.length} approved instantly by the AI
            </p>
          )}
        </div>
        <div className="mt-4">
          {!data && !error && (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-[68px]" />
              ))}
            </div>
          )}
          {data && groups.list.length === 0 && <Empty title="No claims here" sub="Scan a receipt to make your first claim." action={<LinkButton href="/app/claims/new" size="sm">New claim</LinkButton>} />}
          {months.map(([m, rows]) => (
            <section key={m} className="mt-3 first:mt-0">
              <div className="sticky top-0 z-10 flex items-center justify-between bg-surface/95 px-2 py-2 backdrop-blur">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">{m}</h3>
                <span className="num text-xs text-muted">{money(rows.reduce((t, c) => t + (c.amount_pkr ?? 0), 0))}</span>
              </div>
              <ul className="divide-y divide-line/70">
                {rows.map((c) => (
                  <li key={c.id}>
                    <Link href={claimHref(c.id)} className="flex items-center gap-3.5 rounded-2xl px-2 py-3 transition hover:bg-surface-2/70">
                      <WalletBadge code={c.wallet?.code} size={42} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[14px] font-semibold">{c.merchant || c.wallet?.name}</p>
                        <p className="truncate text-xs text-muted">
                          {c.wallet?.name} · {d(c.receipt_date, { day: "numeric", month: "short" })}
                          {c.pay_date && c.status !== "rejected" ? ` · ${c.status === "paid" ? "paid" : "pays"} ${d(c.pay_date)}` : ""}
                        </p>
                      </div>
                      <div className="hidden text-right sm:block">
                        <p className="num text-[14px] font-semibold">{money(c.amount_pkr)}</p>
                        {c.currency !== "PKR" && <p className="num text-[11px] text-muted">{c.currency} {c.amount?.toLocaleString()}</p>}
                      </div>
                      <StatusPill status={c.status} />
                      <ChevronRight size={16} className="text-muted" />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {groups.list.length > shown && (
            <div className="mt-4 flex justify-center">
              <Button variant="soft" onClick={() => setShown(shown + 20)}>
                Show more ({groups.list.length - shown} older)
              </Button>
            </div>
          )}
        </div>
      </Card>
    </>
  );
}
