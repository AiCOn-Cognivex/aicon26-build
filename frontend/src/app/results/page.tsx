"use client";
import { useEffect, useState } from "react";
import CoverageChart, { type CurvePoint } from "@/components/CoverageChart";
import { getResults } from "@/lib/api";
import { RUNGS, evalFor, pct } from "@/lib/results";

const ROWS: { key: string; label: string; help: string }[] = [
  { key: "key_field_exact_match", label: "Key-field exact match", help: "share of the 5 header fields (total, subtotal, tax, service, discount) exactly right, absent counts as right if gold is absent" },
  { key: "posting_correct_rate", label: "Posting-correct receipts", help: "all 5 header fields right" },
  { key: "fully_correct_rate", label: "Fully-correct receipts", help: "header fields and every line item right" },
  { key: "line_item_f1", label: "Line-item F1", help: "name + qty + price must all match" },
  { key: "stp_rate", label: "STP rate", help: "share auto-posted by the decision layer" },
  { key: "auto_post_correctness", label: "Correct among auto-posted", help: "posting-correct share of auto-posted receipts" },
  { key: "token_entity_f1", label: "Token entity F1 (seqeval)", help: "word-tagging quality, only defined with gold OCR" },
];

function Table({ data, split, mode }: { data: Record<string, any>; split: string; mode: "A" | "B" }) {
  const cols = RUNGS.map((r) => ({ ...r, e: evalFor(data, r.key, split, mode) })).filter((c) => c.e);
  if (!cols.length) return <p className="text-sm text-muted">No results files yet for this mode.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase text-muted">
            <th className="py-2 pr-3 font-medium">Metric</th>
            {cols.map((c) => <th key={c.key} className="py-2 pr-3 text-right font-medium">{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {ROWS.filter((row) => cols.some((c) => c.e![row.key] !== undefined)).map((row) => (
            <tr key={row.key} className="border-b border-line/60">
              <td className="py-2 pr-3" title={row.help}>{row.label}</td>
              {cols.map((c) => <td key={c.key} className="py-2 pr-3 text-right font-mono">{pct(c.e![row.key])}</td>)}
            </tr>
          ))}
          <tr>
            <td className="py-2 pr-3 text-xs text-muted">Receipts (n)</td>
            {cols.map((c) => <td key={c.key} className="py-2 pr-3 text-right font-mono text-xs text-muted">{c.e!.n_receipts}</td>)}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export default function ResultsPage() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [source, setSource] = useState<"live" | "snapshot">("live");
  useEffect(() => {
    getResults().then(({ data, source }) => { setData(data); setSource(source); });
  }, []);
  if (!data) return <p className="text-sm text-muted">Loading results…</p>;
  const curve = data["threshold_curve"];
  const test = data["test_metrics"];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Results</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Every number here is read from the metric files the evaluation scripts write to <code>results/</code>; nothing is typed in by hand.
          Mode A feeds the model CORD&apos;s own (gold) OCR to isolate the extractor; Mode B runs real OCR on the image end to end.
          Source: {source === "live" ? "live API /results" : "bundled snapshot (API unreachable)"}.
        </p>
      </div>
      <section className="rounded-card border border-line bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold">Validation · Mode B (real OCR, end to end)</h2>
        <Table data={data} split="validation" mode="B" />
      </section>
      <section className="rounded-card border border-line bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold">Validation · Mode A (gold OCR)</h2>
        <Table data={data} split="validation" mode="A" />
      </section>
      {curve?.points && (
        <section className="rounded-card border border-line bg-surface p-4">
          <h2 className="mb-1 text-sm font-semibold">Decision layer: how many receipts can be auto-posted safely?</h2>
          <p className="mb-3 text-xs text-muted">{curve.model} · {curve.split} · {curve.mode === "B" ? "real OCR" : "gold OCR"} · n={curve.n}. {curve.note}</p>
          <CoverageChart points={curve.points as CurvePoint[]} target={curve.target ?? 0.98} chosen={curve.chosen_threshold} />
        </section>
      )}
      {test && (
        <section className="rounded-card border border-line bg-surface p-4">
          <h2 className="mb-3 text-sm font-semibold">Test set (evaluated once, after freezing model, preprocessing and threshold)</h2>
          <Table data={Object.fromEntries(Object.entries(test.evals ?? {}))} split="test" mode="B" />
          <div className="mt-4"><Table data={Object.fromEntries(Object.entries(test.evals ?? {}))} split="test" mode="A" /></div>
        </section>
      )}
      {data["ocr_benchmark"] && (
        <section className="rounded-card border border-line bg-surface p-4">
          <h2 className="mb-3 text-sm font-semibold">OCR engine benchmark (validation)</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-line text-left text-xs uppercase text-muted">
                <th className="py-2 pr-3 font-medium">Run</th><th className="py-2 pr-3 text-right font-medium">Word recall</th>
                <th className="py-2 pr-3 text-right font-medium">Key-amount recall</th><th className="py-2 pr-3 text-right font-medium">Median latency</th>
                <th className="py-2 text-right font-medium">Peak RAM</th></tr></thead>
              <tbody>
                {Object.entries<any>(data["ocr_benchmark"]).map(([k, v]) => (
                  <tr key={k} className="border-b border-line/60">
                    <td className="py-2 pr-3">{v.engine} (n={v.n})</td>
                    <td className="py-2 pr-3 text-right font-mono">{pct(v.word_recall)}</td>
                    <td className="py-2 pr-3 text-right font-mono">{pct(v.key_amount_recall)}</td>
                    <td className="py-2 pr-3 text-right font-mono">{v.latency_s_median}s</td>
                    <td className="py-2 text-right font-mono">{v.peak_rss_mb} MB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
