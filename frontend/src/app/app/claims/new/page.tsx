"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Camera, Check, CircleAlert, Clock, ImageUp, LoaderCircle, ScanLine, Sparkles, X, Zap } from "lucide-react";
import { ReceiptViewer, ScanLoader } from "@/components/receipt";
import { PageHeader } from "@/components/shell";
import { Button, Card, LinkButton, SourceTag, WalletBadge, cx } from "@/components/ui";
import type { ClaimFull, WalletBal } from "@/lib/appTypes";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/client";
import { dLong, money } from "@/lib/format";

const SAMPLES = ["validation_0", "validation_3", "validation_1", "validation_21", "validation_23", "validation_5"];
type Scan = ClaimFull & { wallets: WalletBal[] };

export default function Page() {
  return (
    <Suspense>
      <NewClaim />
    </Suspense>
  );
}

function NewClaim() {
  const wanted = useSearchParams().get("wallet");
  const [stage, setStage] = useState<"pick" | "scanning" | "review" | "done">("pick");
  const [preview, setPreview] = useState("");
  const [sample, setSample] = useState(false);
  const [scan, setScan] = useState<Scan | null>(null);
  const [result, setResult] = useState<ClaimFull | null>(null);
  const [error, setError] = useState("");

  async function start(file: File, isSample = false) {
    setError("");
    setSample(isSample);
    setPreview(URL.createObjectURL(file));
    setStage("scanning");
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api<Scan>("/claims/scan", { form: fd, timeoutMs: 120000 });
      setScan(r);
      setStage("review");
    } catch (e) {
      setError((e as Error).message);
      setStage("pick");
    }
  }

  return (
    <>
      <PageHeader
        title={stage === "done" ? "Claim submitted" : "New claim"}
        sub={stage === "review" ? "Check what we read, then submit" : stage === "done" ? "Here's what happens next" : "Snap or upload a receipt. Our AI reads it for you."}
        actions={
          <LinkButton href="/app/claims" variant="soft" size="sm">
            <ArrowLeft size={15} /> Claims
          </LinkButton>
        }
      />
      {stage === "pick" && <Picker onFile={start} error={error} />}
      {stage === "scanning" && <ScanLoader src={preview} />}
      {stage === "review" && scan && (
        <Review
          scan={scan}
          preview={preview}
          sample={sample}
          wanted={wanted}
          onDone={(c) => {
            setResult(c);
            setStage("done");
          }}
          onDiscard={async () => {
            await api(`/claims/${scan.id}`, { method: "DELETE" }).catch(() => {});
            setScan(null);
            setStage("pick");
          }}
        />
      )}
      {stage === "done" && result && <Done c={result} onAgain={() => { setResult(null); setScan(null); setStage("pick"); }} />}
    </>
  );
}

function Picker({ onFile, error }: { onFile: (f: File, sample?: boolean) => void; error: string }) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [loadingSample, setLoadingSample] = useState<string | null>(null);
  async function sample(name: string) {
    setLoadingSample(name);
    const r = await fetch(`/demo/${name}.jpg`);
    onFile(new File([await r.blob()], `${name}.jpg`, { type: "image/jpeg" }), true);
  }
  return (
    <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
      <Card className="p-3 animate-fade-up">
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            const f = e.dataTransfer.files?.[0];
            if (f) onFile(f);
          }}
          className={cx(
            "flex min-h-[340px] cursor-pointer flex-col items-center justify-center gap-4 rounded-[24px] border-2 border-dashed p-8 text-center transition",
            drag ? "border-brand bg-brand-soft/60" : "border-line bg-surface-2/60 hover:border-brand/50 hover:bg-brand-soft/30",
          )}
        >
          <span className="relative grid h-24 w-24 place-items-center">
            <svg className="absolute inset-0" viewBox="0 0 96 96" aria-hidden>
              <circle cx="48" cy="48" r="44" fill="none" stroke="var(--color-brand-soft)" strokeWidth="8" />
              <path d="M48 4a44 44 0 0 1 44 44" fill="none" stroke="var(--color-brand)" strokeWidth="8" strokeLinecap="round" />
            </svg>
            <ScanLine size={34} className="text-brand" />
          </span>
          <div>
            <p className="text-lg font-bold">Snap or drop a receipt</p>
            <p className="mt-1 text-sm text-muted">JPG or PNG up to 8 MB. On a phone this opens the camera.</p>
          </div>
          <span className="inline-flex gap-2">
            <span className="inline-flex h-11 items-center gap-2 rounded-full bg-brand px-5 text-sm font-semibold text-white">
              <Camera size={17} /> Take photo
            </span>
            <span className="inline-flex h-11 items-center gap-2 rounded-full bg-surface px-5 text-sm font-semibold shadow-[var(--shadow-soft)]">
              <ImageUp size={17} /> Upload
            </span>
          </span>
          <input ref={input} type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
        </label>
        {error && <p className="m-3 rounded-2xl bg-bad-soft px-4 py-2.5 text-sm text-bad">{error}</p>}
      </Card>
      <Card className="p-6 animate-fade-up [animation-delay:80ms]">
        <h2 className="text-[15px] font-semibold">No receipt handy?</h2>
        <p className="mt-1 text-xs text-muted">Try a sample: restaurant receipts from the public CORD v2 dataset (Jakarta, in rupiah), never used to train the model.</p>
        <div className="mt-4 grid grid-cols-3 gap-3">
          {SAMPLES.map((s) => (
            <button key={s} onClick={() => sample(s)} disabled={!!loadingSample} className="group relative aspect-[3/4] overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line transition hover:ring-2 hover:ring-brand">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/demo/${s}.jpg`} alt="Sample receipt" className="h-full w-full object-cover object-top transition group-hover:scale-105" />
              {loadingSample === s && (
                <span className="absolute inset-0 grid place-items-center bg-ink/40 text-white">
                  <LoaderCircle className="animate-spin" />
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="mt-5 space-y-2.5 text-[13px] text-ink-2">
          {[
            [Sparkles, "An AI model reads the total, tax and service charge"],
            [Zap, "Sure and within policy: approved instantly"],
            [Clock, "Not sure: a person in finance checks it"],
          ].map(([I, t], i) => {
            const Icon = I as typeof Zap;
            return (
              <p key={i} className="flex items-center gap-2.5">
                <span className="grid h-7 w-7 place-items-center rounded-full bg-brand-soft text-brand">
                  <Icon size={14} />
                </span>
                {t as string}
              </p>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

function Review({ scan, preview, sample, wanted, onDone, onDiscard }: { scan: Scan; preview: string; sample: boolean; wanted: string | null; onDone: (c: ClaimFull) => void; onDiscard: () => void }) {
  const { user } = useAuth();
  const s = scan.suggestions;
  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const [wallet, setWallet] = useState(wanted || s.wallet || "meals");
  const [amount, setAmount] = useState(s.amount !== null ? String(s.amount) : "");
  // sample receipts are CORD v2 (Jakarta): always rupiah, whatever the text rules guessed
  const [currency, setCurrency] = useState(sample ? "IDR" : s.currency || "PKR");
  const [date, setDate] = useState(s.date || today);
  const [merchant, setMerchant] = useState(s.merchant || "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const rates = { PKR: 1, ...(user?.company.fx_rates ?? {}) } as Record<string, number>;
  const amt = parseFloat(amount) || 0;
  const pkr = amt * (rates[currency] ?? 1);
  const w = scan.wallets.find((x) => x.code === wallet);
  const ex = scan.extraction;
  const conf = s.amount_confidence;
  const edited = scan.model_total !== null && Math.abs(amt - scan.model_total) > 0.5;
  const checks = useMemo(
    () => [
      { ok: scan.model_decision === "AUTO_POST", label: scan.model_decision === "AUTO_POST" ? "AI is confident about every amount" : `AI isn't sure: ${ex.reasons[0] ?? "low confidence"}` },
      { ok: !edited && s.amount_source === "model", label: s.amount_source !== "model" ? "Amount not read by our model" : edited ? "You changed the amount the AI read" : "Amount matches what the AI read" },
      { ok: !!w?.auto_approve, label: w?.auto_approve ? `${w?.name} allows instant approval` : `${w?.name ?? "This"} claims are always checked by a person` },
      { ok: !!w && pkr <= w.left && pkr <= (w.per_claim_cap || Infinity), label: w && pkr > w.left ? `More than the ${money(w.left)} left` : w && w.per_claim_cap && pkr > w.per_claim_cap ? `Above the ${money(w.per_claim_cap)} instant-approval limit` : "Within your balance and limit" },
      { ok: scan.flags.length === 0, label: scan.flags.length ? scan.flags[0].message : "No duplicate found" },
    ],
    [scan, ex, edited, s, w, pkr],
  );
  const allOk = checks.every((c) => c.ok);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const c = await api<ClaimFull>(`/claims/${scan.id}/submit`, { json: { wallet, amount: amt, currency, receipt_date: date, merchant: merchant || null, note: note || null } });
      onDone(c);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <div className="space-y-4 animate-fade-up">
        <ReceiptViewer src={preview} words={ex.words} size={ex.image_size} className="shadow-[var(--shadow-soft)]" />
        <Card className="p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">What the AI read</p>
          <div className="mt-3 space-y-2.5">
            {Object.entries(ex.fields).map(([k, f]) =>
              f ? (
                <div key={k} className="flex items-center gap-3 text-[13px]">
                  <span className="w-24 capitalize text-muted">{k.replace("_", " ")}</span>
                  <span className="num w-24 font-semibold">{f.text}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                    <div className={cx("h-full rounded-full", f.confidence >= 0.7 ? "bg-brand" : "bg-warn")} style={{ width: `${f.confidence * 100}%` }} />
                  </div>
                  <span className="num w-10 text-right text-xs text-muted">{Math.round(f.confidence * 100)}%</span>
                </div>
              ) : null,
            )}
            <p className="pt-1 text-xs text-muted">
              Arithmetic check:{" "}
              <span className={cx("font-semibold", ex.reconciliation.status === "PASS" ? "text-ok" : ex.reconciliation.status === "FAIL" ? "text-bad" : "text-muted")}>
                {ex.reconciliation.status === "PASS" ? "adds up" : ex.reconciliation.status === "FAIL" ? "doesn't add up" : "not enough fields to check"}
              </span>
              {" · "}
              {scan.model_name} · read in {Math.round((ex.timings_ms?.total ?? 0) / 100) / 10} s
            </p>
          </div>
        </Card>
      </div>

      <Card className="p-6 sm:p-7 animate-fade-up [animation-delay:80ms]">
        <div className="space-y-5">
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[13px] font-semibold">Allowance</span>
              {s.wallet && <span className="text-[11px] text-muted">Suggested from the receipt {s.wallet_keywords?.length ? `(“${s.wallet_keywords.slice(0, 2).join("”, “")}”)` : ""}</span>}
            </div>
            <div className="flex flex-wrap gap-2">
              {scan.wallets.map((x) => (
                <button key={x.code} onClick={() => setWallet(x.code)} className={cx("flex items-center gap-2 rounded-full border py-1.5 pl-1.5 pr-3.5 text-[13px] font-semibold transition", wallet === x.code ? "border-brand bg-brand-soft text-brand-deep" : "border-line hover:bg-surface-2")}>
                  <WalletBadge code={x.code} size={26} />
                  {x.name}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
            <label className="block">
              <span className="mb-1.5 flex items-center gap-2 text-[13px] font-semibold">
                Amount on receipt <SourceTag source={s.amount_source} />
                {conf !== null && conf !== undefined && <span className="text-[11px] font-normal text-muted">{Math.round(conf * 100)}% sure</span>}
              </span>
              <input className="field num text-lg font-semibold" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0" />
            </label>
            <label className="block">
              <span className="mb-1.5 flex items-center gap-2 text-[13px] font-semibold">
                Currency <SourceTag source={sample ? "sample" : s.currency_source} />
              </span>
              <select className="field" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                {Object.keys(rates).map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
          </div>
          {currency !== "PKR" && amt > 0 && (
            <p className="-mt-2 text-xs text-muted">
              ≈ <span className="num font-semibold text-ink">{money(pkr)}</span> at the company&apos;s demo rate (1 {currency} = Rs {rates[currency]})
            </p>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 flex items-center gap-2 text-[13px] font-semibold">
                Receipt date <SourceTag source={s.date ? s.date_source : "today"} />
              </span>
              <input className="field" type="date" max={today} value={date} onChange={(e) => setDate(e.target.value)} />
            </label>
            <label className="block">
              <span className="mb-1.5 flex items-center gap-2 text-[13px] font-semibold">
                Merchant <SourceTag source={s.merchant ? s.merchant_source : null} />
              </span>
              <input className="field" value={merchant} onChange={(e) => setMerchant(e.target.value)} placeholder="Optional" />
            </label>
          </div>
          <label className="block">
            <span className="mb-1.5 block text-[13px] font-semibold">Note for finance</span>
            <input className="field" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Lunch with client at Lahore office" />
          </label>

          {w && (
            <div className="inset flex items-center justify-between px-4 py-3 text-[13px]">
              <span className="text-muted">{w.name} after this claim</span>
              <span className="num font-semibold">
                {money(w.left)} → <span className={pkr > w.left ? "text-bad" : "text-brand"}>{money(Math.max(0, w.left - pkr))}</span>
              </span>
            </div>
          )}

          <div className="rounded-[22px] border border-line p-4">
            <p className="flex items-center justify-between text-[13px] font-semibold">
              Instant approval checks
              <span className={cx("rounded-full px-2.5 py-0.5 text-[11px]", allOk ? "bg-brand-soft text-brand-strong" : "bg-warn-soft text-warn")}>{allOk ? "Likely instant" : "Will go to finance"}</span>
            </p>
            <ul className="mt-3 space-y-2">
              {checks.map((c, i) => (
                <li key={i} className="flex items-start gap-2.5 text-[13px]">
                  <span className={cx("mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full", c.ok ? "bg-brand text-white" : "bg-warn-soft text-warn")}>{c.ok ? <Check size={12} /> : <CircleAlert size={12} />}</span>
                  <span className={c.ok ? "text-ink-2" : "text-ink"}>{c.label}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[11px] text-muted">Preview only. The server makes the final decision with the same rules.</p>
          </div>

          {error && <p className="rounded-2xl bg-bad-soft px-4 py-2.5 text-sm text-bad">{error}</p>}
          <div className="flex flex-wrap gap-3">
            <Button size="lg" className="flex-1" onClick={submit} disabled={busy || amt <= 0}>
              {busy ? <LoaderCircle size={18} className="animate-spin" /> : <Check size={18} />}
              Submit claim
            </Button>
            <Button size="lg" variant="soft" onClick={onDiscard} disabled={busy}>
              <X size={17} /> Discard
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

function Done({ c, onAgain }: { c: ClaimFull; onAgain: () => void }) {
  const router = useRouter();
  const auto = c.status === "auto_approved";
  useEffect(() => {
    router.prefetch(`/app/claims/${c.id}`);
  }, [router, c.id]);
  return (
    <Card className="mx-auto max-w-xl overflow-hidden p-0 text-center animate-fade-up">
      <div className={cx("relative px-8 pb-8 pt-10", auto ? "bg-gradient-to-b from-brand-soft to-surface" : "bg-gradient-to-b from-warn-soft to-surface")}>
        <span className={cx("mx-auto grid h-20 w-20 place-items-center rounded-full text-white animate-pop", auto ? "bg-brand" : "bg-warn")}>{auto ? <Zap size={36} /> : <Clock size={36} />}</span>
        <h2 className="mt-5 text-[26px] font-bold tracking-tight">{auto ? "Approved instantly" : "Sent to finance"}</h2>
        <p className="mx-auto mt-2 max-w-sm text-[15px] text-ink-2">
          {auto ? (
            <>
              <span className="num font-semibold">{money(c.amount_pkr)}</span> will be paid with your salary on <span className="font-semibold">{dLong(c.pay_date)}</span>.
            </>
          ) : (
            <>A person in finance will check this claim. You&apos;ll see the decision in your claims.</>
          )}
        </p>
      </div>
      {!auto && c.reasons.length > 0 && (
        <div className="px-8 pb-2 text-left">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Why it needs a person</p>
          <ul className="space-y-2">
            {c.reasons.map((r, i) => (
              <li key={i} className="flex gap-2.5 rounded-2xl bg-surface-2/70 p-3 text-[13px]">
                <CircleAlert size={16} className="mt-0.5 shrink-0 text-warn" />
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap justify-center gap-3 p-8 pt-6">
        <Button variant="soft" onClick={onAgain}>
          <ScanLine size={17} /> Scan another
        </Button>
        <Link href={`/app/claims/${c.id}`} className="inline-flex h-11 items-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-white hover:bg-ink-2">
          View claim
        </Link>
      </div>
    </Card>
  );
}
