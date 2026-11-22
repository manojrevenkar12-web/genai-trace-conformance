"""Runs one scenario in one environment against a fresh harness and returns what the wire saw."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gtc.harness.server import Harness

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class CellRun:
    scenario: str
    exit_code: int
    stderr_tail: str
    seconds: float
    calls: list[dict[str, Any]]
    spans: list[dict[str, Any]]
    auth_ok: bool


def run_cell(h: Harness, scenario: str, python: str = sys.executable, timeout: float = 120) -> CellRun:
    h.reset()
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith(("OPENAI", "ANTHROPIC", "LANGFUSE", "OTEL"))},
        "GTC_BASE_URL": h.base_url,
        "LANGFUSE_BASE_URL": h.base_url,
        "LANGFUSE_HOST": h.base_url,
        "LANGFUSE_PUBLIC_KEY": "pk-lf-local",
        "LANGFUSE_SECRET_KEY": "sk-lf-local",
        "OPENAI_API_KEY": "sk-local",
        "OPENAI_BASE_URL": f"{h.base_url}/v1",
        "ANTHROPIC_API_KEY": "local",
        "ANTHROPIC_BASE_URL": h.base_url,
        "OPENAI_AGENTS_DISABLE_TRACING": "1",  # the Agents SDK's own exporter would call api.openai.com
        "PYTHONPATH": str(ROOT),
        "PYTHONHASHSEED": "0",
    }
    t0 = time.time()
    p = subprocess.run([python, "-m", "scenarios.run", scenario], env=env, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    time.sleep(0.2)  # the receiver may still be writing the last export
    with h.store.lock:
        spans = [s.as_dict() for s in h.store.spans]
        auth = any(a.startswith("Basic ") for a in h.store.auth_headers)
    with h.ledger.lock:
        calls = [c.as_dict() for c in h.ledger.calls]
    return CellRun(scenario, p.returncode, (p.stderr or "")[-2000:], round(time.time() - t0, 2), calls, spans, auth)
