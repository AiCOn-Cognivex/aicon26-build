"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ArrowRight, CalendarClock, Eye, EyeOff, HandCoins, LoaderCircle, ScanLine, ShieldCheck, Sparkles } from "lucide-react";
import { Logo, PageLoader } from "@/components/shell";
import { Avatar, Button, cx } from "@/components/ui";
import { useAuth, type Me } from "@/lib/auth";
import { api, prefetch } from "@/lib/client";

type Demo = { password: string; accounts: { email: string; name: string; role: string; title: string }[] };

function SignIn() {
  const { user, ready, signIn } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [demo, setDemo] = useState<Demo | null>(null);
  const [waking, setWaking] = useState(false);

  const go = (u: Me) => {
    const dest = next && next.startsWith("/") ? next : u.role === "finance" ? "/finance" : "/app";
    // load the landing page's data while the page itself loads (one round trip saved)
    if (dest === "/app") prefetch("/me/dashboard");
    if (dest === "/finance") ["/admin/overview", "/admin/queue"].forEach(prefetch);
    router.replace(dest);
  };

  useEffect(() => {
    if (ready && user) go(user);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, user]);

  useEffect(() => {
    const slow = setTimeout(() => setWaking(true), 2500);
    api<Demo>("/auth/demo-accounts", { auth: false, timeoutMs: 90000 })
      .then(setDemo)
      .catch(() => {})
      .finally(() => {
        clearTimeout(slow);
        setWaking(false);
      });
    return () => clearTimeout(slow);
  }, []);

  async function submit(e: string, p: string, key: string) {
    setBusy(key);
    setError("");
    try {
      go(await signIn(e, p));
    } catch (err) {
      setError((err as Error).message);
      setBusy(null);
    }
  }

  if (!ready) return <PageLoader label="Opening…" />;

  return (
    <div className="min-h-screen p-3 sm:p-5">
      <div className="mx-auto grid min-h-[calc(100vh-2.5rem)] max-w-[1280px] gap-5 lg:grid-cols-[1.05fr_1fr]">
        {/* brand panel */}
        <section className="relative hidden overflow-hidden rounded-[32px] bg-brand-deep p-10 text-white lg:flex lg:flex-col">
          <Arcs />
          <Logo light />
          <div className="relative mt-auto max-w-md">
            <h1 className="text-[40px] font-bold leading-[1.1] tracking-tight">Your pay, allowances and claims. In one place.</h1>
            <p className="mt-4 text-[15px] leading-relaxed text-white/70">
              Know when you&apos;re paid and what you&apos;ll get. Snap a receipt and get reimbursed with your next salary, approved in seconds when our AI is sure, and checked by a person when it isn&apos;t.
            </p>
            <ul className="mt-8 space-y-3.5 text-[14px]">
              {[
                [CalendarClock, "Payday countdown and take-home forecast"],
                [ScanLine, "Receipt claims read by a calibrated AI model"],
                [HandCoins, "Interest-free advance on pay you've already earned"],
              ].map(([Icon, t], i) => {
                const I = Icon as typeof ScanLine;
                return (
                  <li key={i} className="flex items-center gap-3">
                    <span className="grid h-9 w-9 place-items-center rounded-full bg-white/10">
                      <I size={17} />
                    </span>
                    {t as string}
                  </li>
                );
              })}
            </ul>
          </div>
          <PreviewCard />
        </section>

        {/* form */}
        <section className="card flex flex-col justify-center px-6 py-10 sm:px-12 lg:px-16">
          <div className="lg:hidden">
            <Logo />
          </div>
          <div className="mx-auto w-full max-w-[420px] animate-fade-up">
            <h2 className="mt-8 text-[28px] font-bold tracking-tight lg:mt-0">Welcome back</h2>
            <p className="mt-1 text-sm text-muted">Sign in with your work email.</p>
            <form
              className="mt-7 space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                submit(email, password, "form");
              }}
            >
              <label className="block">
                <span className="mb-1.5 block text-[13px] font-semibold">Work email</span>
                <input className="field" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[13px] font-semibold">Password</span>
                <div className="relative">
                  <input className="field pr-12" type={show ? "text" : "password"} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
                  <button type="button" aria-label={show ? "Hide password" : "Show password"} onClick={() => setShow(!show)} className="absolute right-2 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full text-muted hover:bg-surface-2">
                    {show ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </label>
              {error && <p className="rounded-2xl bg-bad-soft px-4 py-2.5 text-sm text-bad">{error}</p>}
              <Button type="submit" size="lg" className="w-full" disabled={!!busy}>
                {busy === "form" ? <LoaderCircle size={18} className="animate-spin" /> : null}
                Sign in
              </Button>
            </form>

            <div className="my-7 flex items-center gap-3 text-xs font-semibold uppercase tracking-wider text-muted">
              <span className="h-px flex-1 bg-line" />
              Test accounts
              <span className="h-px flex-1 bg-line" />
            </div>
            <div className="space-y-2.5">
              {demo?.accounts.map((a) => (
                <button
                  key={a.email}
                  disabled={!!busy}
                  onClick={() => {
                    setEmail(a.email);
                    setPassword(demo.password);
                    submit(a.email, demo.password, a.email);
                  }}
                  className="group flex w-full items-center gap-3 rounded-[20px] border border-line bg-surface p-3 text-left transition hover:border-brand/40 hover:bg-brand-soft/40 disabled:opacity-60"
                >
                  <Avatar name={a.name} size={42} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold">{a.name}</span>
                    <span className="block truncate text-xs text-muted">
                      {a.role === "finance" ? "Finance · " : "Employee · "}
                      {a.title}
                    </span>
                  </span>
                  <span className={cx("grid h-9 w-9 place-items-center rounded-full transition", busy === a.email ? "bg-brand text-white" : "bg-surface-2 text-ink-2 group-hover:bg-brand group-hover:text-white")}>
                    {busy === a.email ? <LoaderCircle size={16} className="animate-spin" /> : <ArrowRight size={16} />}
                  </span>
                </button>
              ))}
              {!demo && (
                <div className="space-y-2.5">
                  <div className="skeleton h-[68px]" />
                  <div className="skeleton h-[68px]" />
                  {waking && <p className="text-center text-xs text-muted">Waking the server up, this can take a few seconds…</p>}
                </div>
              )}
            </div>
            {demo && (
              <p className="mt-4 flex items-start gap-2 text-xs leading-relaxed text-muted">
                <ShieldCheck size={15} className="mt-0.5 shrink-0" />
                <span>
                  Fictional demo company. Test password <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-ink-2">{demo.password}</code>. Real accounts sign in the same way with their own password.
                </span>
              </p>
            )}
            <Link href="/model" className="mt-8 inline-flex items-center gap-1.5 text-sm font-semibold text-brand hover:underline">
              <Sparkles size={15} /> How the AI works, and how we measured it
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}

function Arcs() {
  return (
    <svg className="pointer-events-none absolute -right-40 -top-40 h-[720px] w-[720px] opacity-60" viewBox="0 0 720 720" aria-hidden>
      {[340, 280, 220, 160].map((r, i) => (
        <circle key={r} cx="360" cy="360" r={r} fill="none" stroke="white" strokeOpacity={0.05 + i * 0.03} strokeWidth="40" />
      ))}
    </svg>
  );
}

function PreviewCard() {
  return (
    <div className="absolute right-10 top-24 w-64 rotate-[-4deg] rounded-[26px] bg-white/10 p-5 backdrop-blur-md">
      <p className="text-xs text-white/70">Next payday</p>
      <div className="mt-3 flex items-center gap-4">
        <svg width="64" height="64" className="-rotate-90" aria-hidden>
          <circle cx="32" cy="32" r="26" fill="none" stroke="white" strokeOpacity="0.15" strokeWidth="8" />
          <circle cx="32" cy="32" r="26" fill="none" stroke="#7ee2b8" strokeWidth="8" strokeLinecap="round" strokeDasharray="163" strokeDashoffset="55" />
        </svg>
        <div>
          <p className="text-2xl font-bold">20 days</p>
          <p className="text-xs text-white/70">Fri, 30 Oct</p>
        </div>
      </div>
      <div className="mt-4 h-2 rounded-full bg-white/15">
        <div className="h-2 w-2/3 rounded-full bg-[#7ee2b8]" />
      </div>
      <p className="mt-2 text-[11px] text-white/60">Meals allowance · 66% left</p>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<PageLoader label="Opening…" />}>
      <SignIn />
    </Suspense>
  );
}
