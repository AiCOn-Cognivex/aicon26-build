"""Ask Repay: an employee asks about their own pay; Gemini answers from that employee's records only (D29).

Optional and labelled: runs only when GEMINI_API_KEY is set, is read-only (it cannot submit,
approve or change anything) and never sees other employees' data. It does not touch the receipt model or any
reported model number.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections import deque

from .. import config

log = logging.getLogger("uvicorn.error")
MAX_QUESTIONS, WINDOW_S = 20, 600  # per employee, protects the API quota during public testing
_RECENT: dict[int, deque] = {}

SYSTEM = """You are Ask Repay, the pay assistant inside Repay, an employee finance app.
You are talking to {name} at {company}. Today is {today}.
Answer ONLY from the JSON data you are given about this employee. Rules:
- Money is in Pakistani rupees (write "Rs 12,500") unless the data names another currency.
- Be short and concrete: 1-4 sentences or up to 4 short bullets. No headings, no tables.
- Quote the exact numbers and dates from the data. Explain differences step by step when asked "why".
- If the data does not contain the answer, say so plainly and suggest asking the finance team. Never guess or invent
  policies, numbers, dates or tax rules.
- You cannot take actions. To do something, point to the right page: "Scan a receipt", "Claims", "Salary advance",
  "Payslips", "Provident fund".
- Reply in the language of the question (English, Urdu or Roman Urdu)."""


def allow(user_id: int) -> bool:
    q = _RECENT.setdefault(user_id, deque())
    now = time.time()
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= MAX_QUESTIONS:
        return False
    q.append(now)
    return True


def ask(question: str, data: dict, *, name: str, company: str, today: str, timeout: float = 25.0) -> dict:
    """Returns {"answer", "model"}; raises RuntimeError with a short reason on any failure."""
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM.format(name=name, company=company, today=today)}]},
        "contents": [{"role": "user", "parts": [{"text": "EMPLOYEE DATA (JSON):\n" + json.dumps(data, separators=(",", ":"))
                                                 + "\n\nQUESTION: " + question}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        log.warning("assistant: Gemini HTTP %s: %s", e.code, e.read()[:300])
        raise RuntimeError(f"Gemini returned {e.code}") from e
    except Exception as e:  # timeout, network
        log.warning("assistant: %r", e)
        raise RuntimeError(type(e).__name__) from e
    try:
        parts = resp["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    except (KeyError, IndexError, TypeError):
        text = ""
    if not text:
        raise RuntimeError("empty answer")
    return {"answer": text, "model": config.GEMINI_MODEL}
