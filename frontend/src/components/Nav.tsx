"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import ServerBadge from "./ServerBadge";

const TABS = [
  { href: "/", label: "Extract & Decide" },
  { href: "/batch", label: "Batch Demo" },
  { href: "/results", label: "Results" },
  { href: "/impact", label: "Impact Simulator" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold text-ink">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-brand text-sm text-white" aria-hidden>
            C
          </span>
          Cognivex <span className="hidden font-normal text-muted sm:inline">Receipt Auto-Post</span>
        </Link>
        <nav aria-label="Main" className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto">
          {TABS.map((t) => {
            const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
            return (
              <Link
                key={t.href}
                href={t.href}
                aria-current={active ? "page" : undefined}
                className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm ${
                  active ? "bg-brand-soft font-medium text-brand-strong" : "text-muted hover:bg-canvas hover:text-ink"
                }`}
              >
                {t.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto">
          <ServerBadge />
        </div>
      </div>
    </header>
  );
}
