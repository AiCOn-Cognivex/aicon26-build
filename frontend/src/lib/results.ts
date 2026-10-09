// Helpers to read the metric files served by /results (keys = file names in results/ without .json).
export const RUNGS: { key: string; label: string }[] = [
  { key: "rules", label: "Rung 0 · Rules (before)" },
  { key: "crf", label: "Rung 1 · CRF" },
  { key: "lilt", label: "Rung 2 · LiLT transformer" },
];

export type Summary = Record<string, any> & { _label: string };

export function evalFor(data: Record<string, any>, model: string, split: string, mode: "A" | "B"): Record<string, any> | null {
  return data[`eval_${model}_${split}_mode${mode}`] ?? null;
}

/** Headline = final model on TEST in real-OCR mode if available, else best model on validation (real OCR). */
export function pickHeadline(data: Record<string, any>): Summary | null {
  const test = data["test_metrics"];
  if (test?.headline) return { ...test.headline, _label: `test set (n=${test.headline.n_receipts}), ${test.headline.model}, real OCR` };
  for (const m of ["lilt", "crf", "rules"]) {
    const e = evalFor(data, m, "validation", "B");
    if (e) return { ...e, _label: `validation set (n=${e.n_receipts}), ${e.model}, real OCR` };
  }
  return null;
}

export const pct = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${(100 * v).toFixed(d)}%`;
