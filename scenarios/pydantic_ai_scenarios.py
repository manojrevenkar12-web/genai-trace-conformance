"""Pydantic AI agents instrumented with OpenTelemetry, exported through the Langfuse client."""

from __future__ import annotations

import asyncio

from scenarios.common import ANTHROPIC_MODEL, BASE, OPENAI_MODEL, POLICY, flush_langfuse, marker, weather


def openai_tools() -> None:
    from langfuse import get_client
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    get_client()
    Agent.instrument_all()
    agent = Agent(
        OpenAIChatModel(OPENAI_MODEL, provider=OpenAIProvider(base_url=f"{BASE}/v1", api_key="sk-local")),
        instructions="You answer weather questions.",
        tools=[weather],
        name="pai-weather",
    )
    asyncio.run(agent.run(f"Weather in Berlin? {marker(1)}"))
    flush_langfuse()


def anthropic_cache() -> None:
    from langfuse import get_client
    from pydantic_ai import Agent
    from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
    from pydantic_ai.providers.anthropic import AnthropicProvider

    get_client()
    Agent.instrument_all()
    model = AnthropicModel(ANTHROPIC_MODEL, provider=AnthropicProvider(base_url=BASE, api_key="local"))
    agent = Agent(model, instructions=POLICY, name="pai-cached", model_settings=AnthropicModelSettings(anthropic_cache_instructions=True, max_tokens=256))  # type: ignore[typeddict-unknown-key]

    async def go() -> None:
        for _ in range(2):
            await agent.run(f"Weather in Berlin? {marker(1)}")

    asyncio.run(go())
    flush_langfuse()
