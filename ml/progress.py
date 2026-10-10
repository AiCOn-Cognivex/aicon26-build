"""One-line progress with ETA for long jobs: `[label] 120/800 (15%) elapsed 2m10s ETA 12m05s`.
Printed at most every `every` seconds (and at the end), flushed, so `Get-Content -Wait <log>` shows it live."""
from __future__ import annotations

import time


def _fmt(s: float) -> str:
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


class Progress:
    def __init__(self, total: int, label: str, every: float = 20.0, done: int = 0):
        self.total, self.label, self.every = total, label, every
        self.start_done = self.done = done
        self.t0 = self.last = time.time()

    def step(self, n: int = 1):
        self.done += n
        now = time.time()
        if now - self.last >= self.every or self.done >= self.total:
            self.last = now
            el = now - self.t0
            rate = (self.done - self.start_done) / el if el > 0 else 0
            eta = (self.total - self.done) / rate if rate > 0 else 0
            print(f"[{self.label}] {self.done}/{self.total} ({100 * self.done / max(1, self.total):.0f}%) "
                  f"elapsed {_fmt(el)} ETA {_fmt(eta)}", flush=True)
