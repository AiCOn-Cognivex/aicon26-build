"use client";

import { CircleAlert, MessageSquareText, Sparkles } from "lucide-react";
import type { ClaimFull, EventRow } from "@/lib/appTypes";
import { ago, d, dLong, money } from "@/lib/format";
import { NoImage, ReceiptViewer, useAuthedImage } from "./receipt";
import { Card, StatusPill, WalletBadge, cx } from "./ui";
import { EventIcon } from "./widgets";

export function ClaimImage({ c }: { c: ClaimFull }) {
  const { src } = useAuthedImage(c.has_image ? `/claims/${c.id}/image` : null);
  if (!c.has_image) return <NoImage />;
  return <ReceiptViewer src={src} words={c.extraction?.words} size={c.extraction?.image_size} className="shadow-[var(--shadow-soft)]" />;
}

export function ClaimSummary({ c }: { c: ClaimFull }) {
  const rows: [string, React.ReactNode][] = [
    ["Allowance", c.wallet?.name ?? "—"],
    ["Receipt date", d(c.receipt_date, { day: "numeric", month: "long", year: "numeric" })],
    ["Merchant", c.merchant || "—"],
    ["On the receipt", `${c.currency} ${c.amount?.toLocaleString() ?? "—"}`],
    ...(c.currency !== "PKR" ? ([["Exchange rate", `1 ${c.currency} = Rs ${c.fx_rate} (demo rate)`]] as [string, React.ReactNode][]) : []),
    ["AI read the total as", c.model_total !== null ? `${c.currency} ${c.model_total.toLocaleString()}` : "not found"],
    ...(c.note ? ([["Note", c.note]] as [string, React.ReactNode][]) : []),
  ];
  return (
    <Card className="p-6">
      <div className="flex items-center gap-3">
        <WalletBadge code={c.wallet?.code} size={44} />
        <div className="min-w-0 flex-1">
          <p className="num text-[26px] font-bold leading-tight tracking-tight">{money(c.amount_pkr)}</p>
          <p className="text-xs text-muted">Claim #{c.id} · submitted {ago(c.submitted_at)}</p>
        </div>
        <StatusPill status={c.status} />
      </div>
      {c.pay_date && c.status !== "rejected" && (
        <p className="mt-4 rounded-2xl bg-brand-soft px-4 py-2.5 text-[13px] text-brand-deep">
          {c.status === "paid" ? "Paid" : c.status === "in_review" ? "If approved, paid" : "Will be paid"} with salary on{" "}
          <span className="font-semibold">{dLong(c.pay_date)}</span>
        </p>
      )}
      <dl className="mt-4 divide-y divide-line/70 text-[13px]">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 py-2.5">
            <dt className="text-muted">{k}</dt>
            <dd className="num text-right font-medium">{v}</dd>
          </div>
        ))}
      </dl>
      {c.reviewer_note && (
        <div className="mt-3 flex gap-2.5 rounded-2xl bg-surface-2 p-3.5 text-[13px]">
          <MessageSquareText size={16} className="mt-0.5 shrink-0 text-muted" />
          <span>
            <span className="font-semibold">{c.decided_by ?? "Finance"}:</span> {c.reviewer_note}
          </span>
        </div>
      )}
    </Card>
  );
}

export function Reasons({ c }: { c: ClaimFull }) {
  if (!c.reasons.length)
    return (
      <Card className="flex items-center gap-3 p-5 text-[13px]">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-brand-soft text-brand">
          <Sparkles size={16} />
        </span>
        Every check passed, so the claim was approved automatically.
      </Card>
    );
  return (
    <Card className="p-6">
      <p className="text-[15px] font-semibold">Why a person checks it</p>
      <ul className="mt-3 space-y-2">
        {c.reasons.map((r, i) => (
          <li key={i} className="flex gap-2.5 rounded-2xl bg-surface-2/70 p-3 text-[13px]">
            <CircleAlert size={16} className={cx("mt-0.5 shrink-0", r.startsWith("Possible duplicate") ? "text-bad" : "text-warn")} />
            {r}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function Timeline({ events }: { events: EventRow[] }) {
  return (
    <ol className="relative space-y-5 pl-1">
      <span className="absolute bottom-3 left-[19px] top-3 w-[2px] rounded-full bg-line" aria-hidden />
      {events.map((e) => (
        <li key={e.id} className="relative flex gap-3.5">
          <span className="relative z-10 rounded-full ring-4 ring-surface">
            <EventIcon kind={e.kind} />
          </span>
          <div className="pt-1">
            <p className="text-[13.5px] font-semibold">{e.title}</p>
            <p className="text-xs text-muted">
              {new Date(e.ts).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
              {e.actor && e.kind !== "claim_submitted" ? ` · ${e.actor}` : e.kind === "claim_auto_approved" || e.kind === "claim_in_review" ? " · automatic" : ""}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
