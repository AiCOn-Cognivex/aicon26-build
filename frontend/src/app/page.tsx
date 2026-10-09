"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import ResultView from "@/components/ResultView";
import { ensureAwake, extract, health, API_URL, type ServerState } from "@/lib/api";
import type { Extraction } from "@/lib/types";

export default function ExtractPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [server, setServer] = useState<ServerState>("unknown");
  const [waitS, setWaitS] = useState(0);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Extraction | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [threshold, setThreshold] = useState<number | undefined>();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // wake the backend as soon as the page opens (free hosts sleep when idle)
    ensureAwake((s, t) => {
      setServer(s);
      setWaitS(t);
    }).then(async (ok) => {
      if (ok) {
        const h = await health();
        const p = h?.policy as { threshold?: number } | undefined;
        if (p?.threshold !== undefined) setThreshold(p.threshold);
      }
    });
  }, []);

  const pick = (f: File | null) => {
    setFile(f);
    setResult(null);
    setError("");
    if (preview) URL.revokeObjectURL(preview);
    setPreview(f ? URL.createObjectURL(f) : "");
  };

  const run = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      if (server !== "online") {
        const ok = await ensureAwake((s, t) => {
          setServer(s);
          setWaitS(t);
        });
        if (!ok) throw new Error("The API did not wake up. Use the Batch Demo tab (cached results) or the local fallback.");
      }
      const { result, latencyMs } = await extract(file);
      setResult(result);
      setLatency(latencyMs);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Extract &amp; Decide</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Upload or photograph a receipt. The system reads it (OCR), tags each word with a trained model, checks the arithmetic, and
          decides whether the entry is safe to post automatically or needs a person.
        </p>
      </div>

      <section className="rounded-card border border-line bg-surface p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <input
            ref={inputRef}
            id="receipt"
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
          <label
            htmlFor="receipt"
            className="cursor-pointer rounded-md border border-line px-4 py-2 text-center text-sm hover:bg-canvas"
          >
            {file ? "Change image" : "Choose or capture receipt"}
          </label>
          <span className="truncate text-sm text-muted">{file?.name ?? "No image selected"}</span>
          <button
            onClick={run}
            disabled={!file || busy}
            className="rounded-md bg-brand px-5 py-2 text-sm font-medium text-white hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-50 sm:ml-auto"
          >
            {busy ? "Processing…" : "Extract & decide"}
          </button>
        </div>
        <div className="mt-3 text-xs text-muted" role="status" aria-live="polite">
          {server === "waking" && <>Waking up the server… {waitS}s (free hosting sleeps when idle, first request can take up to a minute)</>}
          {server === "online" && <>API ready at {API_URL}{latency !== null && <> · last request {latency} ms round-trip</>}</>}
          {server === "offline" && (
            <span className="text-warn">
              API unreachable. Cached examples still work in <Link className="underline" href="/batch">Batch Demo</Link>.
            </span>
          )}
        </div>
        {error && <p className="mt-2 rounded-md bg-bad-soft p-2 text-sm text-bad">{error}</p>}
      </section>

      {result ? (
        <ResultView r={result} imageSrc={preview} threshold={threshold} />
      ) : (
        preview && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="Selected receipt" className="max-h-96 rounded-md border border-line" />
        )
      )}
    </div>
  );
}
