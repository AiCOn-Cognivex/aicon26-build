"use client";

import Link from "next/link";
import {
  BookOpen,
  CircleCheck,
  CircleDashed,
  CircleX,
  Clock,
  Fuel,
  Sparkles,
  Stethoscope,
  UtensilsCrossed,
  Wallet as WalletIcon,
  Wifi,
  Zap,
} from "lucide-react";
import { initials } from "@/lib/format";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cx("card", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardHead({ title, sub, icon, right }: { title: string; sub?: React.ReactNode; icon?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-center gap-3">
        {icon && <span className="grid h-10 w-10 place-items-center rounded-full bg-surface-2 text-ink-2">{icon}</span>}
        <div>
          <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          {sub && <p className="text-xs text-muted">{sub}</p>}
        </div>
      </div>
      {right}
    </div>
  );
}

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "soft" | "ghost" | "danger" | "dark"; size?: "sm" | "md" | "lg" };

const btnBase = "inline-flex items-center justify-center gap-2 rounded-full font-semibold transition active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none";
const btnVariant = {
  primary: "bg-brand text-white shadow-[0_8px_20px_-10px_rgb(15_122_85/0.8)] hover:bg-brand-strong",
  dark: "bg-ink text-white hover:bg-ink-2",
  soft: "bg-surface-2 text-ink hover:bg-line/70",
  ghost: "text-ink-2 hover:bg-surface-2",
  danger: "bg-bad-soft text-bad hover:bg-bad hover:text-white",
};
const btnSize = { sm: "h-9 px-4 text-[13px]", md: "h-11 px-5 text-sm", lg: "h-13 px-7 text-[15px]" };

export function Button({ variant = "primary", size = "md", className, ...rest }: BtnProps) {
  return <button className={cx(btnBase, btnVariant[variant], btnSize[size], className)} {...rest} />;
}

export function LinkButton({ href, variant = "primary", size = "md", className, children }: { href: string; variant?: BtnProps["variant"]; size?: BtnProps["size"]; className?: string; children: React.ReactNode }) {
  return (
    <Link href={href} className={cx(btnBase, btnVariant[variant], btnSize[size], className)}>
      {children}
    </Link>
  );
}

const STATUS: Record<string, { label: string; cls: string; icon: React.ReactNode }> = {
  draft: { label: "Draft", cls: "bg-surface-2 text-muted", icon: <CircleDashed size={13} /> },
  auto_approved: { label: "Auto-approved", cls: "bg-brand-soft text-brand-strong", icon: <Zap size={13} /> },
  approved: { label: "Approved", cls: "bg-ok-soft text-ok", icon: <CircleCheck size={13} /> },
  in_review: { label: "In review", cls: "bg-warn-soft text-warn", icon: <Clock size={13} /> },
  rejected: { label: "Rejected", cls: "bg-bad-soft text-bad", icon: <CircleX size={13} /> },
  paid: { label: "Paid", cls: "bg-accent-soft text-accent", icon: <CircleCheck size={13} /> },
  requested: { label: "Requested", cls: "bg-warn-soft text-warn", icon: <Clock size={13} /> },
  repaid: { label: "Repaid", cls: "bg-accent-soft text-accent", icon: <CircleCheck size={13} /> },
};

export function StatusPill({ status }: { status: string }) {
  const s = STATUS[status] ?? STATUS.draft;
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-1 text-[11.5px] font-semibold", s.cls)}>
      {s.icon}
      {s.label}
    </span>
  );
}

const WALLET_STYLE: Record<string, { icon: React.ComponentType<{ size?: number }>; cls: string }> = {
  meals: { icon: UtensilsCrossed, cls: "bg-[#fff1e6] text-[#b4530a]" },
  fuel: { icon: Fuel, cls: "bg-[#e8f0ff] text-[#2f55c7]" },
  medical: { icon: Stethoscope, cls: "bg-[#fde9ef] text-[#b42356]" },
  mobile: { icon: Wifi, cls: "bg-[#ecebff] text-[#5546d6]" },
  learning: { icon: BookOpen, cls: "bg-[#e5f6ef] text-[#0f7a55]" },
};

export function WalletBadge({ code, size = 40 }: { code?: string | null; size?: number }) {
  const s = (code && WALLET_STYLE[code]) || { icon: WalletIcon, cls: "bg-surface-2 text-ink-2" };
  const Icon = s.icon;
  return (
    <span className={cx("grid shrink-0 place-items-center rounded-full", s.cls)} style={{ width: size, height: size }}>
      <Icon size={Math.round(size * 0.45)} />
    </span>
  );
}

const AVATAR_TINTS = ["bg-[#e2f3eb] text-[#0a5c40]", "bg-[#e9ebfd] text-[#3a46b8]", "bg-[#fff1e6] text-[#9a4a0b]", "bg-[#fde9ef] text-[#9c1d4b]", "bg-[#e8f0ff] text-[#24479f]"];

export function Avatar({ name, size = 40, className }: { name: string; size?: number; className?: string }) {
  const tint = AVATAR_TINTS[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_TINTS.length];
  return (
    <span className={cx("grid shrink-0 place-items-center rounded-full font-bold", tint, className)} style={{ width: size, height: size, fontSize: size * 0.36 }}>
      {initials(name)}
    </span>
  );
}

export function SourceTag({ source }: { source?: string | null }) {
  if (!source) return null;
  const map: Record<string, [string, string]> = {
    model: ["AI model", "bg-brand-soft text-brand-strong"],
    rules: ["Rules", "bg-surface-2 text-ink-2"],
    gemini: ["Gemini fallback", "bg-accent-soft text-accent"],
    today: ["Default", "bg-surface-2 text-muted"],
    sample: ["Sample: rupiah", "bg-surface-2 text-ink-2"],
  };
  const [label, cls] = map[source] ?? [source, "bg-surface-2 text-muted"];
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-semibold", cls)}>
      {source === "model" || source === "gemini" ? <Sparkles size={10} /> : null}
      {label}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} />;
}

export function Empty({ title, sub, action }: { title: string; sub?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      <svg width="88" height="52" viewBox="0 0 88 52" aria-hidden>
        <path d="M6 48a38 38 0 0 1 76 0" fill="none" stroke="var(--color-line)" strokeWidth="8" strokeLinecap="round" />
        <path d="M22 48a22 22 0 0 1 44 0" fill="none" stroke="var(--color-brand-soft)" strokeWidth="8" strokeLinecap="round" />
      </svg>
      <p className="font-semibold">{title}</p>
      {sub && <p className="max-w-sm text-sm text-muted">{sub}</p>}
      {action}
    </div>
  );
}

export function ErrorNote({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="card flex flex-wrap items-center justify-between gap-3 p-5 text-sm">
      <span className="text-bad">{error}</span>
      {onRetry && (
        <Button variant="soft" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function DemoTag() {
  return <span className="rounded-full bg-warn-soft px-2 py-0.5 text-[10.5px] font-semibold text-warn">Demo data</span>;
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: string; count?: number }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-full bg-surface-2 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition",
            value === o.value ? "bg-surface text-ink shadow-[0_2px_8px_-4px_rgb(13_26_21/0.25)]" : "text-muted hover:text-ink",
          )}
        >
          {o.label}
          {o.count !== undefined && <span className="ml-1.5 text-muted">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}
