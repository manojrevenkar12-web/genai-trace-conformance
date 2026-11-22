"""The local server speaks the real APIs: driven here by the real OpenAI and Anthropic SDKs."""

import anthropic
import openai

from scenarios.common import POLICY

TOOLS = [{"type": "function", "function": {"name": "weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]


def test_openai_counts_cached_tokens_inside_prompt_tokens(harness):
    harness.reset()
    c = openai.OpenAI(base_url=f"{harness.base_url}/v1", api_key="x")
    msgs = [{"role": "system", "content": POLICY}, {"role": "user", "content": "hi [run:a]"}]
    first = c.chat.completions.create(model="gpt-test-mini", messages=msgs)
    second = c.chat.completions.create(model="gpt-test-mini", messages=msgs)
    assert first.usage.prompt_tokens_details.cached_tokens == 0
    cached = second.usage.prompt_tokens_details.cached_tokens
    assert cached > 0 and cached % 128 == 0 and second.usage.prompt_tokens == first.usage.prompt_tokens
    truth = harness.ledger.calls[1].usage
    assert truth.cache_read == cached and truth.input == second.usage.prompt_tokens - cached
    assert harness.ledger.calls[1].marker == "a"


def test_openai_stream_reports_usage_last(harness):
    harness.reset()
    c = openai.OpenAI(base_url=f"{harness.base_url}/v1", api_key="x")
    chunks = list(c.chat.completions.create(model="gpt-test-mini", messages=[{"role": "user", "content": "hi"}], stream=True, stream_options={"include_usage": True}))
    assert chunks[-1].usage is not None and chunks[-1].choices == []
    assert "".join(ch.choices[0].delta.content or "" for ch in chunks if ch.choices).startswith("Here is the answer")
    assert harness.ledger.calls[0].stream


def test_openai_tool_round_trip(harness):
    harness.reset()
    c = openai.OpenAI(base_url=f"{harness.base_url}/v1", api_key="x")
    r = c.chat.completions.create(model="gpt-test-mini", messages=[{"role": "user", "content": "weather?"}], tools=TOOLS)
    call = r.choices[0].message.tool_calls[0]
    assert call.function.name == "weather" and '"Berlin"' in call.function.arguments
    msgs = [{"role": "user", "content": "weather?"}, r.choices[0].message.model_dump(exclude_none=True), {"role": "tool", "tool_call_id": call.id, "content": "sunny"}]
    r2 = c.chat.completions.create(model="gpt-test-mini", messages=msgs, tools=TOOLS)
    assert r2.choices[0].finish_reason == "stop"
    assert harness.ledger.calls[0].tool_calls == ("weather",) and harness.ledger.calls[1].tool_calls == ()


def test_anthropic_writes_then_reads_the_cache_and_keeps_it_out_of_input(harness):
    harness.reset()
    c = anthropic.Anthropic(base_url=harness.base_url, api_key="x")
    system = [{"type": "text", "text": POLICY, "cache_control": {"type": "ephemeral"}}]
    a = c.messages.create(model="claude-test-sonnet", max_tokens=100, system=system, messages=[{"role": "user", "content": "hi"}])
    b = c.messages.create(model="claude-test-sonnet", max_tokens=100, system=system, messages=[{"role": "user", "content": "hi"}])
    assert a.usage.cache_creation_input_tokens > 0 and a.usage.cache_read_input_tokens == 0
    assert b.usage.cache_read_input_tokens == a.usage.cache_creation_input_tokens and b.usage.cache_creation_input_tokens == 0
    assert a.usage.input_tokens == b.usage.input_tokens < 100
    t = harness.ledger.calls[1].usage
    assert (t.input, t.cache_read, t.cache_write) == (b.usage.input_tokens, b.usage.cache_read_input_tokens, 0)


def test_anthropic_stream(harness):
    harness.reset()
    c = anthropic.Anthropic(base_url=harness.base_url, api_key="x")
    with c.messages.stream(model="claude-test-sonnet", max_tokens=100, messages=[{"role": "user", "content": "hi"}]) as s:
        text = "".join(s.text_stream)
        final = s.get_final_message()
    assert text.startswith("Here is the answer") and final.usage.output_tokens == harness.ledger.calls[0].usage.output
