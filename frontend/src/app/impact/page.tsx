"use client";
import { useEffect, useState } from "react";
import { getResults } from "@/lib/api";
import { pickHeadline } from "@/lib/results";

function Slider(props: { label: string; value: number; min: number; max: number; step: number; unit?: string; onChange: (v: number) => void }) {
  const id = props.label.replace(/\W+/g, "-");
  return (
    <div>
      <div className="flex justify-between text-sm">
        <label htmlFor={id}>{props.label}</label>
        <span className="font-mono">
          {props.value.toLocaleString()} {props.unit}
        </span>
      </div>
      <input id={id} type="range" className="w-full accent-[var(--color-brand)]" min={props.min} max={props.max} step={props.step}
        value={props.value} onChange={(e) => props.onChange(Number(e.target.value))} />
    </div>
  );
}

export default function ImpactPage() {
  const [measured, setMeasured] = useState<{ stp: number; correct: number; source: string } | null>(null);
  const [n, setN] = useState(2000);
  const [manualMin, setManualMin] = useState(3);
  const [reviewMin, setReviewMin] = useState(1.5);
  const [hourly, setHourly] = useState(1500);
  const [errCost, setErrCost] = useState(2000);
  const [stp, setStp] = useState(0.5);
  const [correct, setCorrect] = useState(0.98);

  useEffect(() => {
    getResults().then(({ data }) => {
      const h = pickHeadline(data);
      if (h && h.stp_rate !== undefined && h.auto_post_correctness !== null) {
        setMeasured({ stp: h.stp_rate, correct: h.auto_post_correctness, source: h._label });
        setStp(Number(h.stp_rate.toFixed(2)));
        setCorrect(Number(h.auto_post_correctness.toFixed(3)));
      }
    });
  }, []);

  const auto = n * stp;
  const reviewed = n - auto;
  const before = (n * manualMin) / 60;
  const after = (reviewed * reviewMin) / 60;
  const saved = before - after;
  const errors = auto * (1 - correct);
  const net = saved * hourly - errors * errCost;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Impact Simulator</h1>
        <p className="mt-2 inline-block rounded-md bg-warn-soft px-2 py-1 text-xs font-semibold text-warn">
          SIMULATED, not measured. Only the STP rate and auto-post correctness defaults come from our evaluation; everything else is an
          assumption you can change.
        </p>
        {measured && (
          <p className="mt-2 text-xs text-muted">
            Measured defaults from {measured.source}: STP {(100 * measured.stp).toFixed(1)}%, auto-post correctness{" "}
            {(100 * measured.correct).toFixed(1)}%.
          </p>
        )}
      </div>
      <div className="grid gap-5 md:grid-cols-2">
        <section className="space-y-4 rounded-card border border-line bg-surface p-4">
          <h2 className="text-sm font-semibold">Assumptions</h2>
          <Slider label="Receipts per month" value={n} min={100} max={20000} step={100} onChange={setN} />
          <Slider label="Manual entry time per receipt" value={manualMin} min={0.5} max={10} step={0.5} unit="min" onChange={setManualMin} />
          <Slider label="Review time per flagged receipt" value={reviewMin} min={0.5} max={10} step={0.5} unit="min" onChange={setReviewMin} />
          <Slider label="Staff cost per hour" value={hourly} min={200} max={10000} step={100} unit="PKR" onChange={setHourly} />
          <Slider label="Cost of one wrong posting" value={errCost} min={0} max={50000} step={500} unit="PKR" onChange={setErrCost} />
          <Slider label="STP rate (share auto-posted)" value={stp} min={0} max={1} step={0.01} onChange={setStp} />
          <Slider label="Correctness of auto-posted receipts" value={correct} min={0.8} max={1} step={0.001} onChange={setCorrect} />
        </section>
        <section className="space-y-3 rounded-card border border-line bg-surface p-4">
          <h2 className="text-sm font-semibold">Simulated monthly outcome</h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <dt className="text-muted">Auto-posted</dt><dd className="text-right font-mono">{Math.round(auto).toLocaleString()}</dd>
            <dt className="text-muted">Sent to review</dt><dd className="text-right font-mono">{Math.round(reviewed).toLocaleString()}</dd>
            <dt className="text-muted">Staff hours before</dt><dd className="text-right font-mono">{before.toFixed(0)} h</dd>
            <dt className="text-muted">Staff hours after</dt><dd className="text-right font-mono">{after.toFixed(0)} h</dd>
            <dt className="text-muted">Hours saved</dt><dd className="text-right font-mono text-ok">{saved.toFixed(0)} h</dd>
            <dt className="text-muted">Expected wrong auto-posts</dt><dd className="text-right font-mono text-bad">{errors.toFixed(1)}</dd>
            <dt className="border-t border-line pt-2 font-medium">Net value</dt>
            <dd className={`border-t border-line pt-2 text-right font-mono font-semibold ${net >= 0 ? "text-ok" : "text-bad"}`}>
              PKR {Math.round(net).toLocaleString()}
            </dd>
          </dl>
          <p className="text-xs text-muted">
            Net value = hours saved × staff cost − wrong auto-posts × cost per error. Review time applies to every receipt not auto-posted.
          </p>
        </section>
      </div>
    </div>
  );
}
