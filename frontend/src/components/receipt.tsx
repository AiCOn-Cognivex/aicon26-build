"use client";

import { useEffect, useState } from "react";
import { Check, Eye, EyeOff, ImageOff, LoaderCircle } from "lucide-react";
import { blobUrl } from "@/lib/client";
import type { OcrWord } from "@/lib/types";
import { cx } from "./ui";

/** Load a protected image (receipt) with the session token and return an object URL. */
export function useAuthedImage(path: string | null) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!path) return;
    let url: string | null = null;
    blobUrl(path)
      .then((u) => {
        url = u;
        setSrc(u);
      })
      .catch(() => setFailed(true));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [path]);
  return { src, failed };
}

export const FIELD_COLORS: Record<string, { label: string; color: string }> = {
  "total.total_price": { label: "Total", color: "#0f7a55" },
  "sub_total.subtotal_price": { label: "Subtotal", color: "#5b6cf0" },
  "sub_total.tax_price": { label: "Tax", color: "#c26a00" },
  "sub_total.service_price": { label: "Service", color: "#c23a6b" },
  "sub_total.discount_price": { label: "Discount", color: "#2a8fa8" },
};

/** Receipt photo with the boxes of the words the model tagged as money fields. */
export function ReceiptViewer({ src, words, size, className }: { src: string | null; words?: OcrWord[]; size?: [number, number]; className?: string }) {
  const [show, setShow] = useState(true);
  const tagged = (words ?? []).filter((w) => w.label !== "O");
  return (
    <div className={cx("relative overflow-hidden rounded-[24px] bg-surface-2", className)}>
      {src ? (
        <div className="relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={src} alt="Receipt" className="block h-auto w-full" />
          {show && size &&
            tagged.map((w, i) => {
              const cat = w.label.slice(2);
              const f = FIELD_COLORS[cat];
              const [x0, y0, x1, y1] = w.box;
              return (
                <span
                  key={i}
                  title={`${f?.label ?? cat.replace("menu.", "item ")} · ${(w.prob * 100).toFixed(0)}% sure`}
                  className="absolute rounded-[5px]"
                  style={{
                    left: `${(x0 / size[0]) * 100}%`, top: `${(y0 / size[1]) * 100}%`,
                    width: `${((x1 - x0) / size[0]) * 100}%`, height: `${((y1 - y0) / size[1]) * 100}%`,
                    border: `2px solid ${f?.color ?? "rgb(13 26 21 / 0.25)"}`,
                    background: f ? `${f.color}22` : "rgb(13 26 21 / 0.04)",
                  }}
                />
              );
            })}
        </div>
      ) : (
        <div className="grid aspect-[3/4] place-items-center text-muted">
          <LoaderCircle className="animate-spin" />
        </div>
      )}
      {words && words.length > 0 && (
        <button onClick={() => setShow(!show)} className="absolute right-3 top-3 inline-flex items-center gap-1.5 rounded-full bg-ink/80 px-3 py-1.5 text-xs font-semibold text-white backdrop-blur hover:bg-ink">
          {show ? <EyeOff size={13} /> : <Eye size={13} />}
          {show ? "Hide AI reading" : "Show AI reading"}
        </button>
      )}
    </div>
  );
}

export function NoImage() {
  return (
    <div className="grid aspect-[4/3] place-items-center rounded-[24px] bg-surface-2 text-center text-sm text-muted">
      <div>
        <ImageOff className="mx-auto mb-2" />
        Receipt image archived
      </div>
    </div>
  );
}

const STEPS = ["Uploading securely", "Reading the text (OCR)", "Finding the amounts (AI model)", "Checking the arithmetic and your allowance"];

/** Shown while the receipt is being read: a scanning beam over the photo and step-by-step progress. */
export function ScanLoader({ src }: { src: string }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const ts = [450, 1100, 1900].map((ms, i) => setTimeout(() => setStep(i + 1), ms));
    return () => ts.forEach(clearTimeout);
  }, []);
  return (
    <div className="card mx-auto grid max-w-3xl gap-8 p-6 sm:grid-cols-[minmax(0,260px)_1fr] sm:p-8 animate-fade-up">
      <div className="relative mx-auto w-full max-w-[260px] overflow-hidden rounded-[24px] bg-ink">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="Receipt being read" className="block h-auto w-full opacity-80" />
        <div className="absolute inset-0 bg-gradient-to-b from-brand/10 via-transparent to-brand/10" />
        <div className="absolute inset-x-0 h-16 -translate-y-1/2 animate-scan">
          <div className="h-full bg-gradient-to-b from-transparent via-[#7ee2b8]/45 to-transparent" />
          <div className="absolute inset-x-3 top-1/2 h-[2px] rounded-full bg-[#7ee2b8] shadow-[0_0_18px_4px_rgb(126_226_184/0.8)]" />
        </div>
        {["left-3 top-3 border-l-[3px] border-t-[3px] rounded-tl-xl", "right-3 top-3 border-r-[3px] border-t-[3px] rounded-tr-xl", "left-3 bottom-3 border-l-[3px] border-b-[3px] rounded-bl-xl", "right-3 bottom-3 border-r-[3px] border-b-[3px] rounded-br-xl"].map((c) => (
          <span key={c} className={cx("absolute h-7 w-7 border-[#7ee2b8]", c)} />
        ))}
      </div>
      <div className="flex flex-col justify-center">
        <p className="text-xs font-semibold uppercase tracking-wider text-brand">Reading your receipt</p>
        <h2 className="mt-1 text-[22px] font-bold tracking-tight">Hold on, this takes a moment</h2>
        <ol className="mt-6 space-y-4">
          {STEPS.map((s, i) => (
            <li key={s} className={cx("flex items-center gap-3.5 text-[14px] transition", i > step && "text-muted")}>
              <span className={cx("grid h-8 w-8 shrink-0 place-items-center rounded-full transition", i < step ? "bg-brand text-white" : i === step ? "bg-brand-soft text-brand" : "bg-surface-2")}>
                {i < step ? <Check size={16} className="animate-pop" /> : i === step ? <LoaderCircle size={16} className="animate-spin" /> : <span className="h-1.5 w-1.5 rounded-full bg-muted/50" />}
              </span>
              <span className={cx(i === step && "font-semibold")}>{s}</span>
            </li>
          ))}
        </ol>
        <p className="mt-6 text-xs text-muted">Only amounts the model is sure about can be approved automatically. Everything else goes to a person.</p>
      </div>
    </div>
  );
}
