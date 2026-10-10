"use client";

import { useState } from "react";
import { Check, HandCoins, LoaderCircle, ShieldCheck, X } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Avatar, Button, Card, CardHead, Empty, ErrorNote, Skeleton, StatusPill, cx } from "@/components/ui";
import { api } from "@/lib/client";
import { ago, dLong, money } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Adv = {
  id: number;
  employee: string;
  title: string;
  grade: string;
  amount: number;
  status: string;
  reason: string;
  requested_at: string;
  decided_at: string | null;
  decided_by: string | null;
  note: string | null;
  repay_date: string | null;
  can_decide: boolean;
  cap?: number;
  monthly_net?: number;
};
type List = { advances: Adv[]; can_approve: boolean; approvers: string[] };

export default function AdvancesPage() {
  const { data, error, reload } = useApi<List>("/admin/advances");
  const pending = data?.advances.filter((a) => a.status === "requested") ?? [];
  const done = data?.advances.filter((a) => a.status !== "requested") ?? [];
  return (
    <>
      <PageHeader title="Salary advances" sub="Interest-free advances on pay already earned. A finance manager or higher approves each request." />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {data && !data.can_approve && (
        <p className="mb-5 flex items-center gap-2.5 rounded-[22px] bg-accent-soft px-5 py-3.5 text-[13px] text-ink-2 animate-fade-up">
          <ShieldCheck size={17} className="shrink-0 text-accent" />
          You can see requests. Approving them needs a finance manager or higher{data.approvers.length ? ` (${data.approvers.join(", ")})` : ""}.
        </p>
      )}
      <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
        <Card className="p-5 sm:p-6 animate-fade-up">
          <CardHead title="Waiting for a decision" sub={pending.length ? `${pending.length} request${pending.length > 1 ? "s" : ""} · ${money(pending.reduce((s, a) => s + a.amount, 0))}` : undefined} />
          {!data && !error && <Skeleton className="mt-4 h-[120px]" />}
          {data && !pending.length && <Empty title="No requests waiting" sub="New advance requests from employees appear here." />}
          <div className="mt-4 space-y-3">
            {pending.map((a) => (
              <Pending key={a.id} a={a} onDone={reload} />
            ))}
          </div>
        </Card>
        <Card className="p-5 sm:p-6 animate-fade-up [animation-delay:60ms]">
          <CardHead title="Decided" />
          {data && !done.length && <Empty title="Nothing decided yet" />}
          <ul className="mt-2 divide-y divide-line/70">
            {done.map((a) => (
              <li key={a.id} className="flex items-center gap-3 py-3">
                <Avatar name={a.employee} size={38} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13.5px] font-semibold">{a.employee}</p>
                  <p className="truncate text-xs text-muted">
                    {a.reason || "Advance"}
                    {a.decided_by ? ` · by ${a.decided_by}` : ""}
                    {a.repay_date && a.status !== "rejected" ? ` · repay ${dLong(a.repay_date)}` : ""}
                  </p>
                </div>
                <div className="text-right">
                  <p className="num text-[13.5px] font-semibold">{money(a.amount)}</p>
                  <StatusPill status={a.status} />
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}

function Pending({ a, onDone }: { a: Adv; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [err, setErr] = useState("");
  async function decide(action: "approve" | "reject") {
    setBusy(action);
    setErr("");
    try {
      await api(`/admin/advances/${a.id}/decide`, { json: { action, note: note || null } });
      onDone();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(null);
    }
  }
  const share = a.monthly_net ? a.amount / a.monthly_net : null;
  return (
    <div className="rounded-[22px] border border-line p-4">
      <div className="flex items-center gap-3">
        <Avatar name={a.employee} size={44} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-semibold">
            {a.employee} <span className="font-normal text-muted">· {a.title}</span>
          </p>
          <p className="truncate text-xs text-muted">
            {a.reason || "No reason given"} · {ago(a.requested_at)}
          </p>
        </div>
        <div className="text-right">
          <p className="num text-[18px] font-bold">{money(a.amount)}</p>
          <p className="text-[11px] text-muted">{share !== null ? `${Math.round(share * 100)}% of monthly take-home` : ""}</p>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center text-[12px]">
        {[
          ["Earned-pay cap", a.cap !== undefined ? money(a.cap) : "—"],
          ["Interest", "Rs 0"],
          ["Deducted on", "Next payday"],
        ].map(([k, v]) => (
          <div key={k} className="inset py-2">
            <p className="text-[11px] text-muted">{k}</p>
            <p className="font-semibold">{v}</p>
          </div>
        ))}
      </div>
      {a.can_decide ? (
        <div className="mt-3 space-y-2.5">
          <input className="field" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="Note to the employee (required to decline)" />
          {err && <p className="rounded-2xl bg-bad-soft px-4 py-2 text-sm text-bad">{err}</p>}
          <div className="flex gap-2.5">
            <Button className="flex-1" onClick={() => decide("approve")} disabled={!!busy}>
              {busy === "approve" ? <LoaderCircle size={16} className="animate-spin" /> : <Check size={16} />} Approve
            </Button>
            <Button className="flex-1" variant="soft" onClick={() => decide("reject")} disabled={!!busy || !note.trim()}>
              {busy === "reject" ? <LoaderCircle size={16} className="animate-spin" /> : <X size={16} />} Decline
            </Button>
          </div>
        </div>
      ) : (
        <p className={cx("mt-3 flex items-center gap-2 rounded-2xl bg-surface-2 px-3.5 py-2.5 text-xs text-muted")}>
          <HandCoins size={14} /> Waiting for a finance manager
        </p>
      )}
    </div>
  );
}
