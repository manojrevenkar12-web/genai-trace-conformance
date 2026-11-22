"""OpenAI Agents SDK traced with the OpenInference instrumentor into Langfuse."""

from __future__ import annotations

from scenarios.common import BASE, OPENAI_MODEL, flush_langfuse, marker


def tools() -> None:
    from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool, set_tracing_disabled
    from langfuse import get_client
    from openai import AsyncOpenAI
    from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

    get_client()
    OpenAIAgentsInstrumentor().instrument()
    set_tracing_disabled(False)

    @function_tool
    def weather(city: str) -> str:
        """Current weather for a city."""
        return f"{city}: 18 degrees, sunny"

    model = OpenAIChatCompletionsModel(model=OPENAI_MODEL, openai_client=AsyncOpenAI(base_url=f"{BASE}/v1", api_key="sk-local"))
    agent = Agent(name="weather-agent", instructions="Answer weather questions.", tools=[weather], model=model)
    Runner.run_sync(agent, f"Weather in Berlin? {marker(1)}")
    flush_langfuse()
