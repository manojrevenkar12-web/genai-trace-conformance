"""Shared bits for scenarios. Scenarios run inside a matrix environment with pinned SDK versions, so they import only
the SDKs under test and the standard library."""

from __future__ import annotations

import os

BASE = os.environ.get("GTC_BASE_URL", "http://127.0.0.1:9")  # set by the harness for every run
OPENAI_MODEL = "gpt-test-mini"
ANTHROPIC_MODEL = "claude-test-sonnet"

# A long, stable policy so providers cache it: about 1,500 tokens.
POLICY = "\n".join(f"Rule {i}: answer travel questions about European cities precisely, cite the city, never invent prices, and keep answers short." for i in range(1, 50))


def marker(k: int | str) -> str:
    return f"[run:{k}]"


def flush_langfuse() -> None:
    try:
        from langfuse import get_client

        c = get_client()
        c.flush()
        c.shutdown()
    except Exception as e:
        print(f"flush failed: {type(e).__name__}: {e}")


def weather(city: str) -> str:
    """Current weather for a city."""
    return f"{city}: 18 degrees, sunny"
