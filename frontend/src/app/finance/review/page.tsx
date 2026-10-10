"use client";

import Link from "next/link";
import { ChevronRight, Copy, Sparkles, TriangleAlert } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Avatar, Card, Empty, ErrorNote, Skeleton, WalletBadge } from "@/components/ui";
import type { ClaimRow } from "@/lib/appTypes";
import { d, money } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function ReviewQueue() {
  const { data, error, reload } = useApi<{ claims: ClaimRow[] }>("/admin/queue");
  return (
    <>
      <PageHeader title="Review queue" sub="Claims the AI or the policy sent to a person, oldest first" />
      {error && <ErrorNote error={error} onRetry={reload} />}
      <Card className="p-3 sm:p-5">
        {!data && !error && (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-[76px]" />
            ))}
          </div>
        )}
        {data?.claims.length === 0 && <Empty title="All caught up" sub="New claims that need a person will appear here." />}
        <ul className="divide-y divide-line/70">
          {data?.claims.map((c) => {
            const dup = c.flags.some((f) => f.severity === "high");
            return (
              <li key={c.id}>
                <Link href={`/finance/review/${c.id}`} className="flex items-center gap-3.5 rounded-2xl px-2 py-3.5 transition hover:bg-surface-2/70">
                  <Avatar name={c.employee?.name ?? "?"} size={44} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[14px] font-semibold">
                      {c.employee?.name} <span className="font-normal text-muted">· {c.employee?.title}</span>
                    </p>
                    <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs text-muted">
                      {dup ? <Copy size={12} className="shrink-0 text-bad" /> : c.ai_fallback_used ? <Sparkles size={12} className="shrink-0 text-accent" /> : <TriangleAlert size={12} className="shrink-0 text-warn" />}
                      <span className="truncate">{c.reasons[0]}</span>
                      {c.reasons.length > 1 && <span className="shrink-0 rounded-full bg-surface-2 px-1.5 font-semibold">+{c.reasons.length - 1}</span>}
                    </p>
                  </div>
                  <div className="hidden items-center gap-2 md:flex">
                    <WalletBadge code={c.wallet?.code} size={30} />
                    <span className="text-xs text-muted">{d(c.receipt_date)}</span>
                  </div>
                  <div className="w-28 text-right">
                    <p className="num text-[14px] font-semibold">{money(c.amount_pkr)}</p>
                    <p className="text-[11px] text-muted">waiting {c.waiting_hours! < 24 ? `${Math.round(c.waiting_hours!)} h` : `${Math.round(c.waiting_hours! / 24)} d`}</p>
                  </div>
                  <ChevronRight size={16} className="text-muted" />
                </Link>
              </li>
            );
          })}
        </ul>
      </Card>
    </>
  );
}
