"use client";
import { useEffect, useState } from "react";
import ResultView from "@/components/ResultView";
import { getDemoExamples } from "@/lib/api";
import type { DemoExample } from "@/lib/types";

export default function BatchPage() {
  const [examples, setExamples] = useState<DemoExample[] | null>(null);
  const [sel, setSel] = useState<number>(0);

  useEffect(() => {
    getDemoExamples().then(setExamples);
  }, []);

  if (examples === null) return <p className="text-sm text-muted">Loading cached examples…</p>;
  if (!examples.length) return <p className="text-sm text-muted">No cached examples bundled yet.</p>;

  const auto = examples.filter((e) => e.result.decision === "AUTO_POST").length;
  const ex = examples[sel];
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Batch Demo</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          {examples.length} CORD v2 validation receipts processed ahead of time by the same pipeline (real OCR → model → decision).
          These are bundled with the website, so they work even if the API is down. {auto} of {examples.length} were auto-posted
          and {examples.length - auto} sent to human review.
        </p>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-2" role="tablist" aria-label="Examples">
        {examples.map((e, i) => {
          const isAuto = e.result.decision === "AUTO_POST";
          return (
            <button
              key={e.id}
              role="tab"
              aria-selected={i === sel}
              onClick={() => setSel(i)}
              className={`flex w-28 shrink-0 flex-col overflow-hidden rounded-md border text-left text-xs ${
                i === sel ? "border-brand ring-2 ring-brand/30" : "border-line"
              } bg-surface`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/demo/${e.image}`} alt="" className="h-24 w-full object-cover object-top" />
              <span className={`px-2 py-1 font-medium ${isAuto ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn"}`}>
                {isAuto ? "AUTO-POST" : "REVIEW"}
              </span>
            </button>
          );
        })}
      </div>
      {ex.note && <p className="rounded-md bg-brand-soft p-2 text-sm text-brand-strong">{ex.note}</p>}
      {ex.gold && (
        <p className="text-xs text-muted">
          Gold total for this receipt: <span className="font-mono">{ex.gold.total ?? "—"}</span> ({ex.id})
        </p>
      )}
      <ResultView r={ex.result} imageSrc={`/demo/${ex.image}`} />
    </div>
  );
}
