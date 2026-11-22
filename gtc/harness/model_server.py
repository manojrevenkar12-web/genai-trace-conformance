"""A local model server that speaks the OpenAI Chat Completions and Anthropic Messages APIs.

Real SDKs call it unmodified through their base URL. Answers are deterministic: a request that offers tools and has
no tool result yet gets a tool call; otherwise it gets a short text answer. Usage is reported the way each provider
reports it (OpenAI counts cached tokens inside prompt_tokens; Anthropic reports cache reads and writes separately and
leaves them out of input_tokens), and the truth goes into the ledger in exclusive buckets.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from gtc.harness.truth import Ledger, Usage

MARKER = re.compile(r"\[run:([a-z0-9-]+)\]")
OPENAI_CACHE_MIN = 1024  # OpenAI caches prompts of 1,024 tokens or more, in 128-token steps
OPENAI_CACHE_STEP = 128


def tokens(text: str) -> int:
    return math.ceil(len(text) / 4) if text else 0


def _text_of(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                out.append(str(b.get("text") or b.get("content") or json.dumps(b.get("input", ""))))
            else:
                out.append(str(b))
        return " ".join(out)
    return json.dumps(content)


def _args_for(schema: dict[str, Any]) -> dict[str, Any]:
    """Deterministic arguments that satisfy a tool's JSON schema."""
    props = schema.get("properties", {}) or {}
    req = schema.get("required", list(props))
    out: dict[str, Any] = {}
    for name in req:
        t = (props.get(name) or {}).get("type", "string")
        out[name] = {"integer": 2, "number": 2.5, "boolean": True, "array": [], "object": {}}.get(t, "Berlin")
    return out


class ModelServer:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger
        self.openai_prefixes: set[str] = set()
        self.anthropic_cache: set[str] = set()

    # ---------- OpenAI ----------
    async def openai_chat(self, request: Request) -> Response:
        received = time.time_ns()
        body = await request.json()
        model = body.get("model", "gpt-test-mini")
        messages = body.get("messages", [])
        tools = body.get("tools") or []
        all_text = json.dumps(messages) + json.dumps(tools)
        marker = m.group(1) if (m := MARKER.search(all_text)) else None
        input_total = tokens(all_text)
        first = json.dumps(messages[:1])
        cached = 0
        if input_total >= OPENAI_CACHE_MIN and tokens(first) >= OPENAI_CACHE_MIN:
            key = hashlib.sha256(first.encode()).hexdigest()
            if key in self.openai_prefixes:
                cached = (tokens(first) // OPENAI_CACHE_STEP) * OPENAI_CACHE_STEP
            self.openai_prefixes.add(key)
        last = messages[-1] if messages else {}
        wants_tool = bool(tools) and last.get("role") not in ("tool", "function")
        if wants_tool:
            fn = tools[0].get("function", tools[0])
            calls: list[dict[str, Any]] = [{"id": f"call_{uuid.uuid4().hex[:12]}", "type": "function", "function": {"name": fn["name"], "arguments": json.dumps(_args_for(fn.get("parameters") or {}))}}]
            message: dict[str, Any] = {"role": "assistant", "content": None, "tool_calls": calls}
            out_text = json.dumps(calls)
            finish = "tool_calls"
        else:
            text = f"Here is the answer{f' for [run:{marker}]' if marker else ''}: Berlin is 18 degrees and sunny."
            message = {"role": "assistant", "content": text}
            out_text = text
            finish = "stop"
            calls = []
        output = tokens(out_text)
        usage = {
            "prompt_tokens": input_total,
            "completion_tokens": output,
            "total_tokens": input_total + output,
            "prompt_tokens_details": {"cached_tokens": cached, "audio_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 0, "audio_tokens": 0, "accepted_prediction_tokens": 0, "rejected_prediction_tokens": 0},
        }
        truth = Usage(input=input_total - cached, cache_read=cached, cache_write=0, output=output)
        cid = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        created = int(time.time())
        stream = bool(body.get("stream"))
        tool_names = tuple(c["function"]["name"] for c in calls)
        if not stream:
            self.ledger.add(provider="openai", model=model, stream=False, usage=truth, marker=marker, tool_calls=tool_names, received_ns=received, finished_ns=time.time_ns())
            return JSONResponse(
                {
                    "id": cid,
                    "object": "chat.completion",
                    "created": created,
                    "model": model,
                    "system_fingerprint": "fp_local",
                    "choices": [{"index": 0, "message": message, "finish_reason": finish, "logprobs": None}],
                    "usage": usage,
                }
            )
        include_usage = bool((body.get("stream_options") or {}).get("include_usage"))

        async def events() -> AsyncIterator[bytes]:
            def chunk(delta: dict[str, Any], finish_reason: str | None = None, u: dict[str, Any] | None = None, choices: bool = True) -> bytes:
                c: dict[str, Any] = {
                    "id": cid,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "system_fingerprint": "fp_local",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason, "logprobs": None}] if choices else [],
                }
                if u is not None:
                    c["usage"] = u
                return f"data: {json.dumps(c)}\n\n".encode()

            yield chunk({"role": "assistant", "content": ""})
            if calls:
                for i, call in enumerate(calls):
                    yield chunk({"tool_calls": [{"index": i, "id": call["id"], "type": "function", "function": {"name": call["function"]["name"], "arguments": ""}}]})
                    yield chunk({"tool_calls": [{"index": i, "function": {"arguments": call["function"]["arguments"]}}]})
            else:
                words = out_text.split(" ")
                for i, w in enumerate(words):
                    yield chunk({"content": w if i == 0 else " " + w})
            yield chunk({}, finish)
            if include_usage:
                yield chunk({}, None, usage, choices=False)
            yield b"data: [DONE]\n\n"
            self.ledger.add(provider="openai", model=model, stream=True, usage=truth, marker=marker, tool_calls=tool_names, received_ns=received, finished_ns=time.time_ns())

        return StreamingResponse(events(), media_type="text/event-stream")

    # ---------- Anthropic ----------
    async def anthropic_messages(self, request: Request) -> Response:
        received = time.time_ns()
        body = await request.json()
        model = body.get("model", "claude-test-sonnet")
        system = body.get("system")
        messages = body.get("messages", [])
        tools = body.get("tools") or []
        sys_blocks = [{"type": "text", "text": system}] if isinstance(system, str) else list(system or [])
        all_text = json.dumps(sys_blocks) + json.dumps(messages) + json.dumps(tools)
        marker = m.group(1) if (m := MARKER.search(all_text)) else None
        input_total = tokens(all_text)
        # prompt caching: everything up to and including the last block marked cache_control is the cached prefix
        prefix_parts: list[Any] = []
        cached_prefix = None
        for part in [*tools, *sys_blocks, *messages]:
            prefix_parts.append(part)
            blocks: list[Any] = part["content"] if isinstance(part, dict) and isinstance(part.get("content"), list) else [part]
            if any(isinstance(b, dict) and b.get("cache_control") for b in blocks):
                cached_prefix = json.dumps(prefix_parts)
        cache_read = cache_write = 0
        if cached_prefix is not None:
            n = min(tokens(cached_prefix), input_total)
            key = hashlib.sha256(cached_prefix.encode()).hexdigest()
            if key in self.anthropic_cache:
                cache_read = n
            else:
                cache_write = n
                self.anthropic_cache.add(key)
        uncached = input_total - cache_read - cache_write
        last = messages[-1] if messages else {}
        last_blocks: list[Any] = last["content"] if isinstance(last.get("content"), list) else []
        has_result = any(isinstance(b, dict) and b.get("type") == "tool_result" for b in last_blocks)
        if tools and not has_result:
            t = tools[0]
            content: list[dict[str, Any]] = [{"type": "tool_use", "id": f"toolu_{uuid.uuid4().hex[:12]}", "name": t["name"], "input": _args_for(t.get("input_schema") or {})}]
            stop = "tool_use"
            out_text = json.dumps(content)
            tool_names: tuple[str, ...] = (t["name"],)
        else:
            text = f"Here is the answer{f' for [run:{marker}]' if marker else ''}: Berlin is 18 degrees and sunny."
            content = [{"type": "text", "text": text}]
            stop = "end_turn"
            out_text = text
            tool_names = ()
        output = tokens(out_text)
        usage = {"input_tokens": uncached, "output_tokens": output, "cache_creation_input_tokens": cache_write, "cache_read_input_tokens": cache_read}
        truth = Usage(input=uncached, cache_read=cache_read, cache_write=cache_write, output=output)
        mid = f"msg_{uuid.uuid4().hex[:16]}"
        if not body.get("stream"):
            self.ledger.add(provider="anthropic", model=model, stream=False, usage=truth, marker=marker, tool_calls=tool_names, received_ns=received, finished_ns=time.time_ns())
            return JSONResponse({"id": mid, "type": "message", "role": "assistant", "model": model, "content": content, "stop_reason": stop, "stop_sequence": None, "usage": usage})

        async def events() -> AsyncIterator[bytes]:
            def ev(name: str, data: dict[str, Any]) -> bytes:
                return f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n".encode()

            start_usage = {**usage, "output_tokens": 1}
            yield ev(
                "message_start",
                {"message": {"id": mid, "type": "message", "role": "assistant", "model": model, "content": [], "stop_reason": None, "stop_sequence": None, "usage": start_usage}},
            )
            for i, block in enumerate(content):
                if block["type"] == "text":
                    yield ev("content_block_start", {"index": i, "content_block": {"type": "text", "text": ""}})
                    for w in block["text"].split(" "):
                        yield ev("content_block_delta", {"index": i, "delta": {"type": "text_delta", "text": w + " "}})
                else:
                    yield ev("content_block_start", {"index": i, "content_block": {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}})
                    yield ev("content_block_delta", {"index": i, "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}})
                yield ev("content_block_stop", {"index": i})
            yield ev("message_delta", {"delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": output}})
            yield ev("message_stop", {})
            self.ledger.add(provider="anthropic", model=model, stream=True, usage=truth, marker=marker, tool_calls=tool_names, received_ns=received, finished_ns=time.time_ns())

        return StreamingResponse(events(), media_type="text/event-stream")
