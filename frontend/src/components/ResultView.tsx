"use client";
import { useState } from "react";
import type { Extraction, LineItem } from "@/lib/types";
import { FIELD_LABELS } from "@/lib/types";

const fmt = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : v.toLocaleString("en-US", { maximumFractionDigits: 2 });

const LABEL_COLOURS: Record<string, string> = {
  "total.total_price": "#b42318",
  "sub_total.subtotal_price": "#7a3fd1",
  "sub_total.tax_price": "#c2410c",
  "sub_total.service_price": "#0e7490",
  "sub_total.discount_price": "#a16207",
  "menu.nm": "#0f6e66",
  "menu.cnt": "#2563eb",
  "menu.price": "#15803d",
};
const colourFor = (label: string) => LABEL_COLOURS[label.replace(/^[BI]-/, "")] ?? "#94a3b8";

export function DecisionBanner({ r, threshold }: { r: Extraction; threshold?: number }) {
  const auto = r.decision === "AUTO_POST";
  return (
    <section
      aria-label="Decision"
      className={`rounded-card border p-4 ${auto ? "border-ok/30 bg-ok-soft" : "border-warn/30 bg-warn-soft"}`}
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded-md px-3 py-1 text-sm font-bold tracking-wide text-white ${auto ? "bg-ok" : "bg-warn"}`}>
          {auto ? "AUTO-POST" : "HUMAN REVIEW"}
        </span>
        <span className="text-sm text-ink">
          {auto ? "Safe to post to the ledger without a person checking it." : "Routed to a person before anything is posted."}
        </span>
      </div>
      <ul className="mt-2 list-disc pl-5 text-sm text-ink">
        {r.reasons.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted">
        Model: {r.model.name} · OCR: {r.ocr.engine ?? "gold"}
        {threshold !== undefined && <> · confidence threshold {threshold.toFixed(2)}</>}
        {r.timings_ms.total !== undefined && <> · server time {Math.round(r.timings_ms.total)} ms</>}
      </p>
    </section>
  );
}

function ConfBar({ c, threshold }: { c: number; threshold?: number }) {
  const low = threshold !== undefined && c < threshold;
  return (
    <div className="flex items-center gap-2" title={`confidence ${c.toFixed(3)}`}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-line" aria-hidden>
        <div className={`h-full ${low ? "bg-warn" : "bg-ok"}`} style={{ width: `${Math.round(c * 100)}%` }} />
      </div>
      <span className={`font-mono text-xs ${low ? "text-warn" : "text-muted"}`}>{c.toFixed(2)}</span>
    </div>
  );
}

export function FieldsTable({ r, threshold }: { r: Extraction; threshold?: number }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase text-muted">
            <th className="py-2 pr-2 font-medium">Field</th>
            <th className="py-2 pr-2 font-medium">Read as</th>
            <th className="py-2 pr-2 text-right font-medium">Amount</th>
            <th className="py-2 font-medium">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {Object.keys(FIELD_LABELS).map((k) => {
            const f = r.fields[k];
            return (
              <tr key={k} className="border-b border-line/60">
                <td className="py-2 pr-2 font-medium">{FIELD_LABELS[k]}</td>
                <td className="py-2 pr-2 font-mono text-xs text-muted">{f?.text ?? "not found"}</td>
                <td className="py-2 pr-2 text-right font-mono">{fmt(f?.value)}</td>
                <td className="py-2">{f ? <ConfBar c={f.confidence} threshold={threshold} /> : <span className="text-xs text-muted">—</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function LineItems({ items }: { items: LineItem[] }) {
  if (!items.length) return <p className="text-sm text-muted">No line items found.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase text-muted">
            <th className="py-2 pr-2 font-medium">Item</th>
            <th className="py-2 pr-2 text-right font-medium">Qty</th>
            <th className="py-2 pr-2 text-right font-medium">Price</th>
            <th className="py-2 text-right font-medium">Conf.</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it, i) => (
            <tr key={i} className="border-b border-line/60">
              <td className="py-1.5 pr-2">{it.name ?? <span className="text-muted">?</span>}</td>
              <td className="py-1.5 pr-2 text-right font-mono">{it.qty ?? "—"}</td>
              <td className="py-1.5 pr-2 text-right font-mono">{fmt(it.price_value)}</td>
              <td className="py-1.5 text-right font-mono text-xs text-muted">{it.confidence.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Reconciliation({ r }: { r: Extraction }) {
  const { status, checks } = r.reconciliation;
  const tone = status === "PASS" ? "text-ok" : status === "FAIL" ? "text-bad" : "text-muted";
  return (
    <div className="text-sm">
      <p className={`font-medium ${tone}`}>
        {status === "PASS" ? "Arithmetic reconciles" : status === "FAIL" ? "Arithmetic does not reconcile" : "Not checkable (no subtotal found)"}
      </p>
      <ul className="mt-1 space-y-1">
        {checks.map((c, i) => (
          <li key={i} className="flex flex-wrap gap-x-2">
            <span aria-hidden className={c.ok ? "text-ok" : "text-bad"}>{c.ok ? "✓" : "✗"}</span>
            <span className="text-ink">{c.rule}</span>
            <span className="font-mono text-xs text-muted">
              expected {fmt(c.expected)} · found {fmt(c.actual)}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs text-muted">Checks never change the extracted numbers. They can only send a receipt to review.</p>
    </div>
  );
}

export function LedgerEntry({ r }: { r: Extraction }) {
  const v = (k: string) => r.fields[k]?.value ?? 0;
  const total = r.fields.total?.value ?? null;
  const tax = v("tax");
  const expense = total === null ? null : total - tax;
  const posted = r.decision === "AUTO_POST";
  return (
    <div className="text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs uppercase text-muted">Mock journal entry</span>
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${posted ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn"}`}>
          {posted ? "Posted" : "Draft · awaiting review"}
        </span>
      </div>
      <table className="w-full font-mono text-xs">
        <thead>
          <tr className="text-left text-muted">
            <th className="py-1 font-normal">Account</th>
            <th className="py-1 text-right font-normal">Debit</th>
            <th className="py-1 text-right font-normal">Credit</th>
          </tr>
        </thead>
        <tbody>
          <tr><td className="py-1">Meals &amp; supplies expense</td><td className="text-right">{fmt(expense)}</td><td /></tr>
          <tr><td className="py-1">Input tax receivable</td><td className="text-right">{fmt(tax || null)}</td><td /></tr>
          <tr className="border-t border-line"><td className="py-1">Cash / accounts payable</td><td /><td className="text-right">{fmt(total)}</td></tr>
        </tbody>
      </table>
    </div>
  );
}

export function ReceiptOverlay({ src, r }: { src: string; r: Extraction }) {
  const [show, setShow] = useState(true);
  const [w, h] = r.ocr.image_size;
  return (
    <div>
      <label className="mb-2 flex items-center gap-2 text-xs text-muted">
        <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Show OCR boxes coloured by predicted label
      </label>
      <div className="relative w-full overflow-hidden rounded-md border border-line bg-white">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="Receipt" className="block w-full" />
        {show &&
          r.ocr.words.map((wd, i) => {
            const [x0, y0, x1, y1] = wd.box;
            const tagged = wd.label !== "O";
            return (
              <div
                key={i}
                title={`${wd.text} · ${wd.label} · ${wd.prob.toFixed(2)}`}
                className="absolute"
                style={{
                  left: `${(100 * x0) / w}%`, top: `${(100 * y0) / h}%`,
                  width: `${(100 * (x1 - x0)) / w}%`, height: `${(100 * (y1 - y0)) / h}%`,
                  border: `1.5px solid ${tagged ? colourFor(wd.label) : "rgba(148,163,184,.5)"}`,
                  background: tagged ? `${colourFor(wd.label)}22` : "transparent",
                }}
              />
            );
          })}
      </div>
    </div>
  );
}

export function OcrText({ r }: { r: Extraction }) {
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted">OCR text ({r.ocr.words.length} words)</summary>
      <p className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-canvas p-2 font-mono text-xs leading-relaxed">
        {r.ocr.words.map((w) => w.text).join(" ")}
      </p>
    </details>
  );
}

export function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-card border border-line bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink">{title}</h2>
      {children}
    </section>
  );
}

export default function ResultView({ r, imageSrc, threshold }: { r: Extraction; imageSrc?: string; threshold?: number }) {
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="space-y-4 lg:col-span-2">
        {imageSrc && (
          <Card title="Receipt">
            <ReceiptOverlay src={imageSrc} r={r} />
          </Card>
        )}
        <Card title="OCR">
          <OcrText r={r} />
        </Card>
      </div>
      <div className="space-y-4 lg:col-span-3">
        <DecisionBanner r={r} threshold={threshold} />
        <Card title="Key fields">
          <FieldsTable r={r} threshold={threshold} />
        </Card>
        <div className="grid gap-4 md:grid-cols-2">
          <Card title="Reconciliation">
            <Reconciliation r={r} />
          </Card>
          <Card title="Ledger">
            <LedgerEntry r={r} />
          </Card>
        </div>
        <Card title={`Line items (${r.line_items.length})`}>
          <LineItems items={r.line_items} />
        </Card>
      </div>
    </div>
  );
}
