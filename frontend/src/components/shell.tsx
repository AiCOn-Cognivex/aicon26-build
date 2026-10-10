"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Banknote,
  ClipboardCheck,
  FileText,
  HandCoins,
  House,
  LayoutGrid,
  LogOut,
  Menu,
  PiggyBank,
  Receipt,
  ScanLine,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/client";
import { APP_NAME } from "@/lib/format";
import { Avatar, cx } from "./ui";

type Item = { href: string; label: string; icon: React.ComponentType<{ size?: number }>; badge?: number };

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <svg width="34" height="34" viewBox="0 0 34 34" aria-hidden>
        <rect width="34" height="34" rx="11" fill={light ? "#ffffff" : "var(--color-brand)"} />
        <path d="M9 22a8 8 0 0 1 16 0" fill="none" stroke={light ? "var(--color-brand)" : "#fff"} strokeWidth="3.2" strokeLinecap="round" />
        <path d="M13.5 22a3.5 3.5 0 0 1 7 0" fill="none" stroke={light ? "var(--color-brand)" : "#fff"} strokeOpacity="0.55" strokeWidth="3.2" strokeLinecap="round" />
      </svg>
      <span className={cx("text-[17px] font-bold tracking-tight", light ? "text-white" : "text-ink")}>{APP_NAME}</span>
    </span>
  );
}

export function PageLoader({ label = "Loading your money…" }: { label?: string }) {
  return (
    <div className="grid min-h-[60vh] place-items-center">
      <div className="flex flex-col items-center gap-4">
        <div className="relative h-16 w-16">
          <svg className="absolute inset-0 animate-[spin-slow_1.4s_linear_infinite]" viewBox="0 0 64 64" aria-hidden>
            <path d="M32 6a26 26 0 0 1 26 26" fill="none" stroke="var(--color-brand)" strokeWidth="6" strokeLinecap="round" />
          </svg>
          <svg className="absolute inset-0 animate-[spin-slow_2.2s_linear_infinite_reverse]" viewBox="0 0 64 64" aria-hidden>
            <path d="M32 16a16 16 0 0 1 16 16" fill="none" stroke="var(--color-accent)" strokeOpacity="0.7" strokeWidth="6" strokeLinecap="round" />
          </svg>
        </div>
        <p className="text-sm text-muted">{label}</p>
      </div>
    </div>
  );
}

function NavLink({ item, active, onClick }: { item: Item; active: boolean; onClick?: () => void }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onClick}
      className={cx(
        "group relative flex items-center gap-3 rounded-2xl px-3.5 py-2.5 text-[14px] font-medium transition",
        active ? "bg-brand-soft text-brand-deep" : "text-ink-2 hover:bg-surface-2",
      )}
    >
      {active && <span className="absolute -left-5 top-1/2 h-6 w-1.5 -translate-y-1/2 rounded-r-full bg-brand" />}
      <Icon size={18} />
      <span className="flex-1">{item.label}</span>
      {!!item.badge && <span className="rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-bold text-warn">{item.badge}</span>}
    </Link>
  );
}

function useNav(): { main: Item[]; finance: Item[]; more: Item[] } {
  const { user } = useAuth();
  const [queue, setQueue] = useState(0);
  const pathname = usePathname();
  useEffect(() => {
    if (user?.role !== "finance") return;
    api<{ claims: unknown[] }>("/admin/queue").then((r) => setQueue(r.claims.length)).catch(() => {});
  }, [user, pathname]);
  return {
    main: [
      { href: "/app", label: "Dashboard", icon: House },
      { href: "/app/claims", label: "Claims", icon: Receipt },
      { href: "/app/advance", label: "Salary advance", icon: HandCoins },
      { href: "/app/payslips", label: "Payslips", icon: FileText },
      { href: "/app/pf", label: "Provident fund", icon: PiggyBank },
    ],
    finance:
      user?.role === "finance"
        ? [
            { href: "/finance", label: "Overview", icon: LayoutGrid },
            { href: "/finance/review", label: "Review queue", icon: ClipboardCheck, badge: queue },
            { href: "/finance/payroll", label: "Payroll", icon: Banknote },
            { href: "/finance/policies", label: "Allowance policy", icon: SlidersHorizontal },
          ]
        : [],
    more: [{ href: "/model", label: "How the AI works", icon: Sparkles }],
  };
}

const isActive = (pathname: string, href: string) => (href === "/app" || href === "/finance" ? pathname === href : pathname.startsWith(href));

function Sidebar() {
  const { user, signOut } = useAuth();
  const pathname = usePathname();
  const nav = useNav();
  const router = useRouter();
  if (!user) return null;
  return (
    <aside className="card sticky top-5 hidden h-[calc(100vh-2.5rem)] w-[264px] shrink-0 flex-col p-5 lg:flex">
      <Link href="/app" className="px-1">
        <Logo />
      </Link>
      <div className="mt-4 rounded-2xl bg-surface-2 px-3.5 py-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Employer</p>
        <p className="truncate text-[13px] font-semibold">{user.company.name}</p>
      </div>
      <nav className="mt-5 flex-1 space-y-5 overflow-y-auto">
        <Section title="My money" items={nav.main} pathname={pathname} />
        {nav.finance.length > 0 && <Section title="Finance" items={nav.finance} pathname={pathname} />}
        <Section title="More" items={nav.more} pathname={pathname} />
      </nav>
      <div className="mt-4 flex items-center gap-3 border-t border-line pt-4">
        <Avatar name={user.name} size={40} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13.5px] font-semibold">{user.name}</p>
          <p className="truncate text-xs text-muted">{user.title}</p>
        </div>
        <button
          aria-label="Sign out"
          title="Sign out"
          onClick={() => {
            signOut();
            router.replace("/");
          }}
          className="grid h-9 w-9 place-items-center rounded-full text-muted transition hover:bg-bad-soft hover:text-bad"
        >
          <LogOut size={17} />
        </button>
      </div>
    </aside>
  );
}

function Section({ title, items, pathname, onClick }: { title: string; items: Item[]; pathname: string; onClick?: () => void }) {
  return (
    <div>
      <p className="mb-1.5 px-3.5 text-[11px] font-semibold uppercase tracking-wider text-muted">{title}</p>
      <div className="space-y-0.5">
        {items.map((i) => (
          <NavLink key={i.href} item={i} active={isActive(pathname, i.href)} onClick={onClick} />
        ))}
      </div>
    </div>
  );
}

function MobileNav() {
  const pathname = usePathname();
  const nav = useNav();
  const { user, signOut } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  if (!user) return null;
  const tab = (href: string, label: string, Icon: React.ComponentType<{ size?: number }>) => (
    <Link href={href} className={cx("flex flex-1 flex-col items-center gap-0.5 py-1 text-[10.5px] font-semibold", isActive(pathname, href) ? "text-brand" : "text-muted")}>
      <Icon size={20} />
      {label}
    </Link>
  );
  return (
    <>
      <div className="no-print fixed inset-x-3 bottom-3 z-40 flex items-end rounded-[26px] bg-surface/95 px-2 pb-2 pt-2 shadow-[var(--shadow-lift)] backdrop-blur lg:hidden">
        {tab("/app", "Home", House)}
        {tab("/app/claims", "Claims", Receipt)}
        <Link href="/app/claims/new" aria-label="Scan a receipt" className="-mt-7 mx-1 grid h-14 w-14 place-items-center rounded-full bg-brand text-white shadow-[0_10px_24px_-8px_rgb(15_122_85/0.8)] ring-4 ring-canvas">
          <ScanLine size={24} />
        </Link>
        {tab(user.role === "finance" ? "/finance/review" : "/app/advance", user.role === "finance" ? "Review" : "Advance", user.role === "finance" ? ClipboardCheck : HandCoins)}
        <button onClick={() => setOpen(true)} className="flex flex-1 flex-col items-center gap-0.5 py-1 text-[10.5px] font-semibold text-muted">
          <Menu size={20} />
          More
        </button>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm lg:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-x-3 bottom-3 max-h-[80vh] overflow-y-auto rounded-[28px] bg-surface p-5 animate-fade-up" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Avatar name={user.name} />
                <div>
                  <p className="text-sm font-semibold">{user.name}</p>
                  <p className="text-xs text-muted">{user.company.name}</p>
                </div>
              </div>
              <button aria-label="Close" onClick={() => setOpen(false)} className="grid h-9 w-9 place-items-center rounded-full bg-surface-2">
                <X size={18} />
              </button>
            </div>
            <div className="space-y-4">
              <Section title="My money" items={nav.main} pathname={pathname} onClick={() => setOpen(false)} />
              {nav.finance.length > 0 && <Section title="Finance" items={nav.finance} pathname={pathname} onClick={() => setOpen(false)} />}
              <Section title="More" items={nav.more} pathname={pathname} onClick={() => setOpen(false)} />
              <button
                onClick={() => {
                  signOut();
                  router.replace("/");
                }}
                className="flex w-full items-center gap-3 rounded-2xl px-3.5 py-2.5 text-[14px] font-medium text-bad hover:bg-bad-soft"
              >
                <LogOut size={18} /> Sign out
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/** Signed-in area: sidebar + content. Redirects to sign-in when there is no session. */
export function AppShell({ children, finance = false }: { children: React.ReactNode; finance?: boolean }) {
  const { user, ready } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    if (!ready) return;
    if (!user) router.replace(`/?next=${encodeURIComponent(pathname)}`);
    else if (finance && user.role !== "finance") router.replace("/app");
  }, [ready, user, finance, router, pathname]);
  if (!ready || !user || (finance && user.role !== "finance")) return <PageLoader label="Checking your session…" />;
  return (
    <div className="min-h-screen px-3 pb-28 pt-3 sm:px-4 lg:px-5 lg:pb-5 lg:pt-5">
      <div className="mx-auto flex max-w-[1480px] gap-5">
        <Sidebar />
        <main className="min-w-0 flex-1">{children}</main>
      </div>
      <MobileNav />
    </div>
  );
}

export function PageHeader({ title, sub, actions, avatar }: { title: React.ReactNode; sub?: React.ReactNode; actions?: React.ReactNode; avatar?: string }) {
  return (
    <header className="mb-5 flex flex-wrap items-center justify-between gap-4 px-1 pt-1 animate-fade-up">
      <div className="flex items-center gap-3.5">
        {avatar && <Avatar name={avatar} size={48} className="hidden sm:grid" />}
        <div>
          <h1 className="text-[22px] font-bold tracking-tight sm:text-[26px]">{title}</h1>
          {sub && <p className="mt-0.5 text-sm text-muted">{sub}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}
