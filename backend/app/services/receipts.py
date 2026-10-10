"""Receipt helpers around the extraction model: image fingerprints, QR codes, and the fields our model
was not trained on (date, merchant, receipt type, currency).

Every value here carries its source so the UI can label it honestly:
  "model"  - the CRF extraction model (amounts only: total, subtotal, tax, service, discount)
  "rules"  - regular expressions / keyword lists in this file
  "gemini" - optional LLM fallback (only when GEMINI_API_KEY is set; never auto-approves)
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import urllib.request
from datetime import date

import numpy as np
from PIL import Image

from .. import config

# ---------- image ----------


def prepare_image(data: bytes) -> tuple[bytes, Image.Image]:
    """Upright, max 1600 px, re-encoded JPEG (what we store and show)."""
    from ml.ocr import load_image
    img = load_image(data)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue(), img


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dhash(img: Image.Image) -> str:
    """64-bit difference hash: near-identical photos (re-saved, resized, recompressed) differ in few bits."""
    g = img.convert("L").resize((9, 8), Image.LANCZOS)
    px = [int(v) for v in np.asarray(g, dtype=np.int16).ravel()]  # Python ints: no fixed-width overflow
    bits = 0
    for r in range(8):
        for c in range(8):
            bits = (bits << 1) | (px[r * 9 + c] > px[r * 9 + c + 1])
    return f"{bits & 0xFFFFFFFFFFFFFFFF:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def decode_qr(img: Image.Image) -> str | None:
    """QR payload (e.g. FBR / PRA tax-invoice QR on Pakistani receipts). OpenCV ships with RapidOCR."""
    try:
        import cv2
        arr = np.asarray(img.convert("RGB"))[:, :, ::-1]
        text, _, _ = cv2.QRCodeDetector().detectAndDecode(arr)
        return text.strip()[:400] or None
    except Exception:
        return None


# ---------- text heuristics ----------

def lines_from_words(words: list[dict]) -> list[str]:
    from ml.layout import group_lines
    return [" ".join(words[i]["text"] for i in line) for line in group_lines(words)]


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_D_NUM = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b")
_D_ISO = re.compile(r"\b(20\d{2})[/.\-](\d{1,2})[/.\-](\d{1,2})\b")
# D25: OCR glues the time onto the year: "13/7/202510:04pm"
_D_GLUED = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})(?=\d{1,2}[:.]\d{2})")
_D_TXT = re.compile(r"\b(\d{1,2})[\s\-]*([A-Za-z]{3})[a-z]*[\s\-,]*(\d{2,4})\b")


def find_date(lines: list[str], today: date) -> str | None:
    """First plausible date printed on the receipt (day-first, as in Pakistan and Indonesia)."""
    def ok(y, m, d):
        try:
            y = y + 2000 if y < 100 else y
            v = date(y, m, d)
            return v if date(2015, 1, 1) <= v <= today else None
        except ValueError:
            return None
    for line in lines:
        for m in _D_ISO.finditer(line):
            v = ok(int(m[1]), int(m[2]), int(m[3]))
            if v:
                return v.isoformat()
        for m in [*_D_NUM.finditer(line), *_D_GLUED.finditer(line)]:
            # day-first (Pakistan, Indonesia); month-first only if day-first is impossible ("11/20/2019")
            v = ok(int(m[3]), int(m[2]), int(m[1])) or ok(int(m[3]), int(m[1]), int(m[2]))
            if v:
                return v.isoformat()
        for m in _D_TXT.finditer(line):
            mon = _MONTHS.get(m[2].lower())
            if mon:
                v = ok(int(m[3]), mon, int(m[1]))
                if v:
                    return v.isoformat()
    return None


_NOT_MERCHANT = re.compile(r"receipt|invoice|bill|table|order|cashier|date|time|tel|phone|ntn|strn|welcome|no\.|#", re.I)


def guess_merchant(lines: list[str]) -> str | None:
    """Top-of-receipt line that looks like a name (mostly letters)."""
    for line in lines[:4]:
        letters = sum(ch.isalpha() for ch in line)
        if letters >= 4 and letters / max(len(line), 1) > 0.6 and not _NOT_MERCHANT.search(line):
            return line.strip().title()[:80]
    return None


WALLET_KEYWORDS = {
    "fuel": r"petrol|diesel|\bfuel\b|octane|\bltrs?\b|litre|liter|\bpso\b|shell|total ?parco|attock|byco|hascol|nozzle|pump|pertamina|\bhsd\b|\bms\b",
    "medical": r"pharma|pharmacy|chemist|medical|clinic|hospital|\blab\b|diagnostic|\btab\b|tablet|syrup|capsule|\bmg\b|\bdr\.?\b",
    "mobile": r"\bjazz\b|telenor|\bzong\b|ufone|ptcl|nayatel|storm ?fiber|broadband|internet|recharge|\bpostpaid\b",
    "learning": r"course|tuition|academy|udemy|coursera|book ?store|books|exam fee|certification|training",
    "meals": r"restaurant|cafe|coffee|\btea\b|burger|pizza|chicken|rice|biryani|karahi|naan|roti|bbq|\bnasi\b|\bmie\b|\bayam\b|\bes\b|latte|dine|take ?away|service charge",
}


def suggest_wallet(text: str, has_items: bool) -> tuple[str | None, list[str]]:
    scores = {}
    for code, rx in WALLET_KEYWORDS.items():
        hits = sorted({m.group(0).lower() for m in re.finditer(rx, text, re.I)})
        if hits:
            scores[code] = hits
    if not scores:
        return ("meals", []) if has_items else (None, [])
    code = max(scores, key=lambda k: len(scores[k]))
    return code, scores[code][:5]


def detect_currency(text: str) -> str:
    t = text.lower()
    if re.search(r"\brp\.?\b|rp\d|\bpb1\b|\bppn\b|jumlah|tunai|kembali|\bidr\b", t):
        return "IDR"
    if re.search(r"\$|\busd\b", t):
        return "USD"
    return "PKR"


# ---------- optional Gemini fallback ----------

GEMINI_PROMPT = (
    "You read ONE photo of a purchase receipt for an employee expense claim. Reply with JSON only, keys: "
    "is_receipt (boolean), total (number: the final amount paid, digits only, no separators or symbols), "
    "currency (ISO code such as PKR, IDR, USD), date (YYYY-MM-DD), merchant (string), "
    "category (one of: meals, fuel, medical, mobile, learning, other), litres (number, fuel receipts only). "
    "Use null for anything you cannot read clearly. Never guess."
)


def gemini_available() -> bool:
    return bool(config.GEMINI_API_KEY)


def gemini_read(jpeg: bytes, timeout: float = 20.0) -> dict | None:
    """Ask Gemini to read the receipt. Returns a validated dict or None (any failure -> None)."""
    if not config.GEMINI_API_KEY:
        return None
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}},
                                    {"text": GEMINI_PROMPT}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read())
        raw = json.loads(resp["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as e:  # network, quota, bad JSON: the claim simply goes to a person
        return {"error": type(e).__name__}
    out = {"model": config.GEMINI_MODEL}
    try:
        out["total"] = float(raw["total"]) if raw.get("total") is not None else None
    except (TypeError, ValueError):
        out["total"] = None
    cur = str(raw.get("currency") or "").upper()[:3]
    out["currency"] = cur if re.fullmatch(r"[A-Z]{3}", cur) else None
    try:
        out["date"] = date.fromisoformat(str(raw.get("date"))).isoformat() if raw.get("date") else None
    except ValueError:
        out["date"] = None
    out["merchant"] = (str(raw["merchant"]).strip()[:80] or None) if raw.get("merchant") else None
    cat = str(raw.get("category") or "").lower()
    out["category"] = cat if cat in ("meals", "fuel", "medical", "mobile", "learning", "other") else None
    out["is_receipt"] = bool(raw.get("is_receipt", True))
    return out
