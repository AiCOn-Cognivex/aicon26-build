"use client";

import { useRef, useState } from "react";
import { ArrowUp, LoaderCircle, Sparkles } from "lucide-react";
import { api } from "@/lib/client";
import { Card, cx } from "./ui";

const SUGGESTIONS = [
  "Why is my take-home different this month?",
  "How much allowance do I have left?",
  "When will my last claim be paid?",
  "How much salary advance can I take?",
  "Mera agla payday kab hai?",
];

type Turn = { q: string; a?: string; error?: string };

/** Light formatting for model text: "- " / "* " lines become bullets, **bold** markers are dropped. */
function Answer({ text }: { text: string }) {
  const lines = text.replace(/\*\*/g, "").split("\n").map((l) => l.trim()).filter(Boolean);
  const bullets = lines.filter((l) => /^[-*•]\s/.test(l));
  return (
    <div className="space-y-1.5">
      {lines.filter((l) => !/^[-*•]\s/.test(l)).map((l, i) => (
        <p key={i}>{l}</p>
      ))}
      {bullets.length > 0 && (
        <ul className="ml-4 list-disc space-y-1">
          {bullets.map((l, i) => (
            <li key={i}>{l.replace(/^[-*•]\s/, "")}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Ask Repay: questions about your own pay, answered by Gemini from your records only (D29). */
export function AskRepay() {
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setQ("");
    setTurns((t) => [...t.slice(-2), { q: text }]);
    try {
      const r = await api<{ answer: string }>("/me/ask", { json: { question: text }, timeoutMs: 40000 });
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a: r.answer } : x)));
    } catch (e) {
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, error: (e as Error).message } : x)));
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  }

  return (
    <Card className="relative overflow-hidden p-6 xl:col-span-12 animate-fade-up [animation-delay:150ms]">
      <svg className="pointer-events-none absolute -right-16 -top-20 h-64 w-64 opacity-[0.07]" viewBox="0 0 200 200" aria-hidden>
        <circle cx="100" cy="100" r="80" fill="none" stroke="var(--color-accent)" strokeWidth="26" />
      </svg>
      <div className="flex flex-wrap items-center gap-3">
        <span className="grid h-11 w-11 place-items-center rounded-full bg-accent-soft text-accent">
          <Sparkles size={20} />
        </span>
        <div className="flex-1">
          <h2 className="text-[17px] font-bold tracking-tight">Ask Repay</h2>
          <p className="text-xs text-muted">Questions about your pay, allowances, claims and advance. Answers come only from your own records.</p>
        </div>
        <span className="rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-semibold text-accent">AI · Google Gemini</span>
      </div>

      {turns.length > 0 && (
        <div className="mt-5 space-y-4">
          {turns.map((t, i) => (
            <div key={i} className="space-y-2.5">
              <p className="ml-auto w-fit max-w-[85%] rounded-[20px] rounded-br-md bg-ink px-4 py-2.5 text-[13.5px] text-white">{t.q}</p>
              <div className={cx("w-fit max-w-[92%] rounded-[20px] rounded-bl-md px-4 py-3 text-[13.5px] leading-relaxed", t.error ? "bg-bad-soft text-bad" : "bg-surface-2 text-ink")}>
                {t.a ? (
                  <Answer text={t.a} />
                ) : t.error ? (
                  t.error
                ) : (
                  <span className="flex items-center gap-2 text-muted">
                    <LoaderCircle size={15} className="animate-spin" /> Looking at your pay data…
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <form
        className="mt-5 flex items-center gap-2 rounded-full border border-line bg-surface p-1.5 pl-5 focus-within:border-accent/60"
        onSubmit={(e) => {
          e.preventDefault();
          ask(q);
        }}
      >
        <input
          ref={input}
          className="min-w-0 flex-1 bg-transparent text-[14px] outline-none placeholder:text-muted"
          value={q}
          maxLength={400}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask anything about your money, in English or Urdu…"
        />
        <button type="submit" aria-label="Ask" disabled={busy || q.trim().length < 2} className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent text-white transition disabled:opacity-40">
          {busy ? <LoaderCircle size={17} className="animate-spin" /> : <ArrowUp size={18} />}
        </button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" disabled={busy} onClick={() => ask(s)} className="rounded-full bg-surface-2 px-3 py-1.5 text-[12px] font-medium text-ink-2 transition hover:bg-accent-soft hover:text-accent disabled:opacity-50">
            {s}
          </button>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-muted">Optional AI feature: your pay data for this question is sent to Google Gemini. It can make mistakes; your payslip is the official record. It never approves or changes anything.</p>
    </Card>
  );
}
