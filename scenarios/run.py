"""python -m scenarios.run <scenario>: runs one scenario against the harness named in GTC_BASE_URL."""

from __future__ import annotations

import importlib
import sys
import traceback

REGISTRY = {
    "openai.chat_cached": ("scenarios.openai_wrapper", "chat"),
    "openai.stream": ("scenarios.openai_wrapper", "stream"),
    "openai.tools": ("scenarios.openai_wrapper", "tools"),
    "langchain.openai_tools": ("scenarios.langchain_scenarios", "openai_tools"),
    "langchain.anthropic_cache": ("scenarios.langchain_scenarios", "anthropic_cache"),
    "langchain.anthropic_plus_otel": ("scenarios.langchain_scenarios", "anthropic_double_instrumented"),
    "pydantic_ai.openai_tools": ("scenarios.pydantic_ai_scenarios", "openai_tools"),
    "pydantic_ai.anthropic_cache": ("scenarios.pydantic_ai_scenarios", "anthropic_cache"),
    "agents_sdk.tools": ("scenarios.agents_sdk", "tools"),
    "concurrency.asyncio": ("scenarios.concurrency", "asyncio_gather"),
    "concurrency.threads": ("scenarios.concurrency", "threads"),
}

if __name__ == "__main__":
    mod, fn = REGISTRY[sys.argv[1]]
    try:
        getattr(importlib.import_module(mod), fn)()
    except Exception:
        traceback.print_exc()
        sys.exit(3)
