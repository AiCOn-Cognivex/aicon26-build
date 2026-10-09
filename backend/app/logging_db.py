"""Optional prediction log (SQLite). Disabled unless PREDICTIONS_DB is set; never breaks a request."""
from __future__ import annotations

import json
import os
import sqlite3
import time

_DB = os.getenv("PREDICTIONS_DB")


def _conn():
    c = sqlite3.connect(_DB)
    c.execute("""CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, filename TEXT, model TEXT,
        decision TEXT, total REAL, reasons TEXT, latency_ms REAL)""")
    return c


def log_prediction(filename: str | None, res: dict) -> None:
    if not _DB:
        return
    try:
        total = (res["fields"].get("total") or {}).get("value")
        with _conn() as c:
            c.execute("INSERT INTO predictions (ts, filename, model, decision, total, reasons, latency_ms) "
                      "VALUES (?,?,?,?,?,?,?)",
                      (time.time(), filename, res["model"]["name"], res["decision"], total,
                       json.dumps(res["reasons"]), res["timings_ms"].get("total")))
    except Exception:
        pass
