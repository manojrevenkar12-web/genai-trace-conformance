"""What really happened on the wire: every model call the local server answered, with its exact usage.

The server is the world. It decides usage the way the real providers report it and records the truth in exclusive
buckets (uncached input, cache read, cache write, output), so a check can tell a double count from a real cost.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PRICES: dict[str, dict[str, float]] = {k: v for k, v in json.loads(Path(__file__).resolve().parents[2].joinpath("config/prices.json").read_text()).items() if not k.startswith("_")}


@dataclass(frozen=True)
class Usage:
    input: int  # uncached input tokens
    cache_read: int
    cache_write: int
    output: int

    @property
    def input_side(self) -> int:
        return self.input + self.cache_read + self.cache_write

    def cost(self, model: str) -> float:
        p = PRICES[model]
        return (self.input * p["input"] + self.cache_read * p["cache_read"] + self.cache_write * p["cache_write"] + self.output * p["output"]) / 1e6


@dataclass(frozen=True)
class Call:
    seq: int
    provider: str  # openai | anthropic
    model: str
    stream: bool
    usage: Usage
    marker: str | None  # the run marker found in the prompt, for concurrency scenarios
    tool_calls: tuple[str, ...]  # tools the model asked for in this response
    received_ns: int
    finished_ns: int

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cost"] = self.usage.cost(self.model)
        return d


@dataclass
class Ledger:
    calls: list[Call] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, **kw: Any) -> Call:
        with self.lock:
            c = Call(seq=len(self.calls), **kw)
            self.calls.append(c)
            return c

    def clear(self) -> None:
        with self.lock:
            self.calls.clear()
