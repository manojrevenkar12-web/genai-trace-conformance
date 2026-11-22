"""Many runs at once: each run must land in its own trace, with its own generation, under asyncio and under threads."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from scenarios.common import BASE, OPENAI_MODEL, flush_langfuse, marker

RUNS = 6


def asyncio_gather() -> None:
    from langfuse import observe
    from langfuse.openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=f"{BASE}/v1", api_key="sk-local")

    @observe(name="async-run")
    async def run(k: int) -> None:
        await asyncio.sleep(0.01 * (RUNS - k))  # finish out of order
        await client.chat.completions.create(model=OPENAI_MODEL, messages=[{"role": "user", "content": f"Weather in Berlin? {marker(k)}"}])

    async def all_runs() -> None:
        await asyncio.gather(*(run(k) for k in range(RUNS)))

    asyncio.run(all_runs())
    flush_langfuse()


def threads() -> None:
    from langfuse import observe
    from langfuse.openai import OpenAI

    client = OpenAI(base_url=f"{BASE}/v1", api_key="sk-local")

    @observe(name="thread-run")
    def run(k: int) -> None:
        client.chat.completions.create(model=OPENAI_MODEL, messages=[{"role": "user", "content": f"Weather in Berlin? {marker(k)}"}])

    with ThreadPoolExecutor(max_workers=RUNS) as pool:
        list(pool.map(run, range(RUNS)))
    flush_langfuse()
