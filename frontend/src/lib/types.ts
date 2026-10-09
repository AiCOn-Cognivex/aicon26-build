// Mirrors the predict() contract in ml/predict.py
export type Field = { text: string; value: number | null; confidence: number } | null;

export type LineItem = {
  name: string | null;
  qty: string | null;
  price: string | null;
  price_value: number | null;
  qty_value: number | null;
  confidence: number;
};

export type Check = { rule: string; expected: number; actual: number; ok: boolean };

export type OcrWord = { text: string; box: [number, number, number, number]; label: string; prob: number };

export type Extraction = {
  ocr: { engine?: string; image_size: [number, number]; words: OcrWord[] };
  fields: Record<string, Field>;
  line_items: LineItem[];
  reconciliation: { status: "PASS" | "FAIL" | "NOT_CHECKABLE"; checks: Check[] };
  decision: "AUTO_POST" | "HUMAN_REVIEW";
  reasons: string[];
  model: { name: string; rung: number };
  timings_ms: Record<string, number>;
};

export type DemoExample = {
  id: string;
  image: string; // file name under /demo/
  note?: string;
  result: Extraction;
  gold?: Record<string, string | null>;
};

export const FIELD_LABELS: Record<string, string> = {
  total: "Total",
  subtotal: "Subtotal",
  tax: "Tax",
  service_charge: "Service charge",
  discount: "Discount",
};
