"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  Banknote,
  Bell,
  CalendarClock,
  ChevronRight,
  CircleCheck,
  CircleX,
  Clock,
  HandCoins,
  Lightbulb,
  PencilLine,
  PiggyBank,
  Receipt,
  RotateCcw,
  SlidersHorizontal,
  TriangleAlert,
  Zap,
} from "lucide-react";
import type { CalItem, ClaimRow, EventRow, WalletBal } from "@/lib/appTypes";
import { ago, d, money } from "@/lib/format";
import { claimHref } from "@/lib/routes";
import { ArcGauge } from "./charts";
import { StatusPill, WalletBadge, cx } from "./ui";

const EVENT_ICON: Record<string, [React.ComponentType<{ size?: number }>, string]> = {
  claim_submitted: [Receipt, "bg-surface-2 text-ink-2"],
  claim_auto_approved: [Zap, "bg-brand-soft text-brand-strong"],
  claim_approved: [CircleCheck, "bg-ok-soft text-ok"],
  claim_in_review: [Clock, "bg-warn-soft text-warn"],
  claim_rejected: [CircleX, "bg-bad-soft text-bad"],
  claim_corrected: [PencilLine, "bg-accent-soft text-accent"],
  claim_paid: [Banknote, "bg-accent-soft text-accent"],
  salary_credited: [Banknote, "bg-brand-soft text-brand-strong"],
  pf_contribution: [PiggyBank, "bg-[#fff1e6] text-[#b4530a]"],
  advance_requested: [HandCoins, "bg-surface-2 text-ink-2"],
  advance_approved: [HandCoins, "bg-brand-soft text-brand-strong"],
  advance_repaid: [RotateCcw, "bg-accent-soft text-accent"],
  policy_changed: [SlidersHorizontal, "bg-surface-2 text-ink-2"],
};

export function EventIcon({ kind, size = 38 }: { kind: string; size?: number }) {
  const [Icon, cls] = EVENT_ICON[kind] ?? [Receipt, "bg-surface-2 text-ink-2"];
  return (
    <span className={cx("grid shrink-0 place-items-center rounded-full", cls)} style={{ width: size, height: size }}>
      <Icon size={Math.round(size * 0.45)} />
    </span>
  );
}

export function ActivityList({ events, showEmployee = false }: { events: EventRow[]; showEmployee?: boolean }) {
  return (
    <ul className="divide-y divide-line/70">
      {events.map((e) => {
        const href = e.ref_type === "claim" && e.ref_id ? claimHref(e.ref_id) : undefined;
        const body = (
          <div className="flex items-center gap-3 py-3">
            <EventIcon kind={e.kind} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13.5px] font-semibold">{e.title}</p>
              <p className="truncate text-xs text-muted">
                {showEmployee && e.employee ? `${e.employee} · ` : ""}
                {ago(e.ts)}
                {e.actor && e.kind !== "claim_submitted" ? ` · by ${e.actor}` : ""}
              </p>
            </div>
            {e.amount !== null && (
              <span className={cx("num shrink-0 text-[13.5px] font-semibold", e.kind === "salary_credited" || e.kind === "claim_paid" ? "text-brand" : "text-ink")}>
                {e.kind === "salary_credited" || e.kind === "claim_paid" ? "+" : ""}
                {money(e.amount)}
              </span>
            )}
          </div>
        );
        return <li key={e.id}>{href && !showEmployee ? <Link href={href} className="block rounded-2xl transition hover:bg-surface-2/60">{body}</Link> : body}</li>;
      })}
    </ul>
  );
}

const CAL_STYLE: Record<string, string> = {
  payday: "bg-brand text-white",
  cutoff: "bg-warn-soft text-warn",
  reset: "bg-accent-soft text-accent",
  advance: "bg-surface-2 text-ink-2",
};

export function MoneyCalendar({ items }: { items: CalItem[] }) {
  return (
    <ul className="space-y-2.5">
      {items.map((i, k) => (
        <li key={k} className="flex items-center gap-3.5 rounded-[20px] bg-surface-2/70 p-2.5 pr-4">
          <span className={cx("flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-2xl leading-none", CAL_STYLE[i.kind] ?? CAL_STYLE.advance)}>
            <span className="text-[17px] font-bold">{d(i.date, { day: "numeric" })}</span>
            <span className="mt-0.5 text-[10px] font-semibold uppercase">{d(i.date, { month: "short" })}</span>
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[13.5px] font-semibold">{i.title}</p>
            {i.detail && <p className="truncate text-xs text-muted">{i.detail}</p>}
          </div>
          {i.amount !== undefined && <span className="num text-[13.5px] font-semibold">{money(i.amount)}</span>}
        </li>
      ))}
    </ul>
  );
}

export function WalletCard({ w }: { w: WalletBal }) {
  return (
    <Link href={`/app/claims/new?wallet=${w.code}`} className="card group flex flex-col p-5 transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)]">
      <div className="flex items-center gap-2.5">
        <WalletBadge code={w.code} size={36} />
        <div className="min-w-0">
          <p className="truncate text-[13.5px] font-semibold">{w.name}</p>
          <p className="text-[11px] text-muted">{w.period === "monthly" ? "Monthly" : "Yearly"} · resets {d(w.resets_on)}</p>
        </div>
      </div>
      <div className="mt-4 flex justify-center">
        <ArcGauge used={w.used} pending={w.pending} limit={w.limit} size={150} stroke={13}>
          <p className="num text-[19px] font-bold leading-tight">{money(w.left)}</p>
          <p className="text-[11px] text-muted">left of {money(w.limit)}</p>
        </ArcGauge>
      </div>
      <div className="mt-3 space-y-1 text-[11.5px]">
        {w.pending > 0 && <p className="text-muted">{money(w.pending)} waiting for review</p>}
        {w.runs_out_on && (
          <p className="flex items-center gap-1 font-medium text-warn">
            <TriangleAlert size={12} /> At this pace, runs out {d(w.runs_out_on)}
          </p>
        )}
        <p className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold", w.auto_approve ? "bg-brand-soft text-brand-strong" : "bg-surface-2 text-muted")}>
          {w.auto_approve ? <Zap size={11} /> : <Clock size={11} />}
          {w.auto_approve ? "Instant AI approval" : "Checked by finance"}
        </p>
      </div>
    </Link>
  );
}

export function ClaimMini({ c }: { c: ClaimRow }) {
  return (
    <Link href={claimHref(c.id)} className="flex items-center gap-3 rounded-2xl p-2 transition hover:bg-surface-2">
      <WalletBadge code={c.wallet?.code} size={36} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-semibold">{c.merchant || c.wallet?.name}</p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="num text-xs font-semibold text-ink-2">{money(c.amount_pkr)}</span>
          <StatusPill status={c.status} />
        </div>
      </div>
    </Link>
  );
}

export function NotifBell({ nudges }: { nudges: { kind: string; text: string }[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <div ref={ref} className="relative">
      <button aria-label="Notifications" onClick={() => setOpen(!open)} className="relative grid h-11 w-11 place-items-center rounded-full bg-surface shadow-[var(--shadow-soft)] transition hover:bg-surface-2">
        <Bell size={18} />
        {nudges.length > 0 && <span className="absolute right-2.5 top-2.5 h-2.5 w-2.5 rounded-full bg-bad ring-2 ring-surface" />}
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-[min(340px,85vw)] rounded-[24px] bg-surface p-3 shadow-[var(--shadow-lift)] animate-fade-up">
          <p className="px-2 pb-2 pt-1 text-xs font-semibold uppercase tracking-wider text-muted">For you</p>
          {nudges.length === 0 && <p className="px-2 pb-2 text-sm text-muted">You&apos;re all caught up.</p>}
          {nudges.map((n, i) => (
            <div key={i} className="flex gap-3 rounded-2xl p-2.5 text-[13px] hover:bg-surface-2">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-warn-soft text-warn">
                {n.kind === "cutoff" ? <CalendarClock size={15} /> : <Lightbulb size={15} />}
              </span>
              <span className="leading-snug">{n.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function SeeAll({ href, label = "See all" }: { href: string; label?: string }) {
  return (
    <Link href={href} className="inline-flex items-center gap-0.5 rounded-full px-3 py-1.5 text-[13px] font-semibold text-brand hover:bg-brand-soft">
      {label} <ChevronRight size={15} />
    </Link>
  );
}
