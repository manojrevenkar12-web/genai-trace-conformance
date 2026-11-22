"""Langfuse's drop-in OpenAI wrapper: plain, streaming, cached prompt, and a tool round trip under @observe."""

from __future__ import annotations

import json

from scenarios.common import BASE, OPENAI_MODEL, POLICY, flush_langfuse, marker

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Current weather for a city.",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        },
    }
]


def chat() -> None:
    from langfuse import observe
    from langfuse.openai import OpenAI

    client = OpenAI(base_url=f"{BASE}/v1", api_key="sk-local")

    @observe(name="cached-chat")
    def run() -> None:
        for _ in range(2):  # the second call hits the prompt cache
            client.chat.completions.create(model=OPENAI_MODEL, messages=[{"role": "system", "content": POLICY}, {"role": "user", "content": f"Weather in Berlin? {marker(1)}"}])

    run()
    flush_langfuse()


def stream() -> None:
    from langfuse import observe
    from langfuse.openai import OpenAI

    client = OpenAI(base_url=f"{BASE}/v1", api_key="sk-local")

    @observe(name="streamed-chat")
    def run() -> None:
        s = client.chat.completions.create(
            model=OPENAI_MODEL,
            stream=True,
            stream_options={"include_usage": True},
            messages=[{"role": "user", "content": f"Weather in Berlin? {marker(1)}"}],
        )
        for _ in s:
            pass

    run()
    flush_langfuse()


def tools() -> None:
    from langfuse import observe
    from langfuse.openai import OpenAI

    client = OpenAI(base_url=f"{BASE}/v1", api_key="sk-local")

    @observe(name="weather", as_type="tool")
    def weather(city: str) -> str:
        return f"{city}: 18 degrees, sunny"

    @observe(name="tool-agent", as_type="agent")
    def run() -> None:
        msgs: list[dict] = [{"role": "user", "content": f"Weather in Berlin? {marker(1)}"}]
        r = client.chat.completions.create(model=OPENAI_MODEL, messages=msgs, tools=TOOLS)
        call = r.choices[0].message.tool_calls[0]
        msgs.append(r.choices[0].message.model_dump(exclude_none=True))
        msgs.append({"role": "tool", "tool_call_id": call.id, "content": weather(**json.loads(call.function.arguments))})
        client.chat.completions.create(model=OPENAI_MODEL, messages=msgs, tools=TOOLS)

    run()
    flush_langfuse()
