"""LangChain with Langfuse's CallbackHandler: a tool-calling loop on OpenAI, prompt caching on Anthropic, and the
same Anthropic call with an OpenTelemetry Anthropic instrumentor also switched on (two instrumentations at once)."""

from __future__ import annotations

from scenarios.common import ANTHROPIC_MODEL, BASE, OPENAI_MODEL, POLICY, flush_langfuse, marker


def _weather_tool():  # type: ignore[no-untyped-def]
    from langchain_core.tools import tool

    @tool
    def weather(city: str) -> str:
        """Current weather for a city."""
        return f"{city}: 18 degrees, sunny"

    return weather


def openai_tools() -> None:
    """A hand-written tool loop, wrapped in one @observe agent as Langfuse's docs suggest, so it is one trace."""
    from langchain_core.messages import HumanMessage, ToolMessage
    from langchain_openai import ChatOpenAI
    from langfuse import observe
    from langfuse.langchain import CallbackHandler

    @observe(name="lc-tool-agent", as_type="agent")
    def run() -> None:
        handler = CallbackHandler()
        w = _weather_tool()
        llm = ChatOpenAI(model=OPENAI_MODEL, base_url=f"{BASE}/v1", api_key="sk-local").bind_tools([w])
        msgs = [HumanMessage(f"Weather in Berlin? {marker(1)}")]
        cfg = {"callbacks": [handler]}
        ai = llm.invoke(msgs, config=cfg)
        msgs.append(ai)
        for call in ai.tool_calls:
            msgs.append(ToolMessage(w.invoke(call["args"], config=cfg), tool_call_id=call["id"]))
        llm.invoke(msgs, config=cfg)

    run()
    flush_langfuse()


def _anthropic_cached(handler) -> None:  # type: ignore[no-untyped-def]
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = ChatAnthropic(model=ANTHROPIC_MODEL, base_url=BASE, api_key="local", max_tokens=256)
    system = SystemMessage(content=[{"type": "text", "text": POLICY, "cache_control": {"type": "ephemeral"}}])
    for _ in range(2):
        llm.invoke([system, HumanMessage(f"Weather in Berlin? {marker(1)}")], config={"callbacks": [handler], "run_name": "lc-cached"})


def anthropic_cache() -> None:
    from langfuse.langchain import CallbackHandler

    _anthropic_cached(CallbackHandler())
    flush_langfuse()


def anthropic_double_instrumented() -> None:
    from langfuse import get_client
    from langfuse.langchain import CallbackHandler
    from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

    get_client()  # Langfuse sets up the global tracer provider first, as its docs show
    AnthropicInstrumentor().instrument()
    _anthropic_cached(CallbackHandler())
    flush_langfuse()
