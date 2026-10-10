"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Check, LoaderCircle, PencilLine, X } from "lucide-react";
import { ClaimImage, ClaimSummary, Reasons, Timeline } from "@/components/claimDetail";
import { PageHeader, PageLoader } from "@/components/shell";
import { Avatar, Button, Card, CardHead, ErrorNote, LinkButton, cx } from "@/components/ui";
import type { ClaimFull, ClaimRow, WalletBal } from "@/lib/appTypes";
import { api } from "@/lib/client";
import { money, parseAmount } from "@/lib/format";
import { reviewHref } from "@/lib/routes";
import { useApi } from "@/lib/useApi";

type Detail = ClaimFull & { history: { count: number; median: number | null }; wallet_balance: WalletBal | null };

/** One claim in the finance review flow (pages: /finance/review/view?id=, legacy /finance/review/[id]). */
export function ReviewView({ id }: { id: string }) {
  const router = useRouter();
  const { data: c, error, reload, setData } = useApi<Detail>(`/admin/claims/${id}`);
  const [mode, setMode] = useState<"approve" | "reject" | null>(null);
  const [fix, setFix] = useState(false);
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function decide(action: "approve" | "reject") {
    setBusy(true);
    setErr("");
    try {
      const body: Record<string, unknown> = { action, note: note || null };
      if (action === "approve" && fix && parseAmount(amount) > 0) body.amount = parseAmount(amount);
      const r = await api<ClaimFull>(`/admin/claims/${id}/decide`, { json: body });
      setData({ ...(c as Detail), ...r });
      const q = await api<{ claims: ClaimRow[] }>("/admin/queue");
      const next = q.claims.find((x) => x.id !== +id);
      if (next) router.push(reviewHref(next.id));
      else router.push("/finance/review");
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title={c ? `${c.employee?.name}'s ${c.wallet?.name} claim` : "Review claim"}
        sub={c?.employee ? `${c.employee.title} · ${c.employee.department} · grade ${c.employee.grade}` : undefined}
        actions={
          <LinkButton href="/finance/review" variant="soft" size="sm">
            <ArrowLeft size={15} /> Queue
          </LinkButton>
        }
      />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!c && !error && <PageLoader label="Loading claim…" />}
      {c && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
          <div className="space-y-5 animate-fade-up">
            <ClaimImage c={c} />
            <Card className="p-6">
              <p className="mb-4 text-[15px] font-semibold">Timeline</p>
              <Timeline events={c.timeline ?? []} />
            </Card>
          </div>
          <div className="space-y-5 animate-fade-up [animation-delay:60ms]">
            {c.status === "in_review" ? (
              <Card className="p-6">
                <CardHead title="Your decision" sub="The employee sees your note" />
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <button onClick={() => setMode("approve")} className={cx("flex items-center justify-center gap-2 rounded-[20px] border-2 py-3.5 text-sm font-semibold transition", mode === "approve" ? "border-brand bg-brand-soft text-brand-deep" : "border-line hover:bg-surface-2")}>
                    <Check size={17} /> Approve
                  </button>
                  <button onClick={() => setMode("reject")} className={cx("flex items-center justify-center gap-2 rounded-[20px] border-2 py-3.5 text-sm font-semibold transition", mode === "reject" ? "border-bad bg-bad-soft text-bad" : "border-line hover:bg-surface-2")}>
                    <X size={17} /> Reject
                  </button>
                </div>
                {mode && (
                  <div className="mt-4 space-y-3 animate-fade-up">
                    {mode === "approve" && (
                      <>
                        <label className="flex items-center gap-2 text-[13px] font-medium">
                          <input type="checkbox" checked={fix} onChange={(e) => setFix(e.target.checked)} className="h-4 w-4 accent-[var(--color-brand)]" />
                          <PencilLine size={14} /> Correct the amount (saved as a training label)
                        </label>
                        {fix && (
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-muted">{c.currency}</span>
                            <input className="field num" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={String(c.amount ?? "")} />
                          </div>
                        )}
                      </>
                    )}
                    <textarea className="field min-h-[84px]" value={note} onChange={(e) => setNote(e.target.value)} placeholder={mode === "reject" ? "Reason (required), e.g. this receipt was already claimed" : "Note (optional)"} />
                    {err && <p className="rounded-2xl bg-bad-soft px-4 py-2.5 text-sm text-bad">{err}</p>}
                    <Button className="w-full" size="lg" variant={mode === "reject" ? "danger" : "primary"} disabled={busy || (mode === "reject" && !note.trim())} onClick={() => decide(mode)}>
                      {busy && <LoaderCircle size={17} className="animate-spin" />}
                      {mode === "approve" ? `Approve${fix && amount ? ` ${c.currency} ${amount}` : ""}` : "Reject claim"}
                    </Button>
                  </div>
                )}
              </Card>
            ) : (
              <Card className="p-5 text-sm">
                This claim was {c.status.replace("_", " ")}
                {c.decided_by ? ` by ${c.decided_by}` : ""}.
              </Card>
            )}
            <Reasons c={c} />
            <Card className="p-6">
              <div className="flex items-center gap-3">
                <Avatar name={c.employee?.name ?? "?"} size={44} />
                <div className="flex-1">
                  <p className="text-[14px] font-semibold">{c.employee?.name}</p>
                  <p className="text-xs text-muted">{c.employee?.title}</p>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2 text-[13px]">
                <div className="inset px-4 py-3">
                  <p className="text-[11px] text-muted">Usual {c.wallet?.name} claim</p>
                  <p className="num font-semibold">{c.history.median ? money(c.history.median) : "—"}</p>
                  <p className="text-[11px] text-muted">{c.history.count} earlier claims</p>
                </div>
                <div className="inset px-4 py-3">
                  <p className="text-[11px] text-muted">{c.wallet?.name} left</p>
                  <p className="num font-semibold">{money(c.wallet_balance?.left)}</p>
                  <p className="text-[11px] text-muted">of {money(c.wallet_balance?.limit)}</p>
                </div>
              </div>
            </Card>
            <ClaimSummary c={c} />
          </div>
        </div>
      )}
    </>
  );
}
