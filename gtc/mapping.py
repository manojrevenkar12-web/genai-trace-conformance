"""Maps raw OpenTelemetry spans to the observations a trace backend shows: type, model, usage in exclusive buckets,
cost, input and output.

Usage is read per attribute family ("dialect") with that family's documented meaning: in the OpenTelemetry GenAI
conventions, OpenAI's raw usage and OpenInference, the input count already contains cached tokens; Langfuse's
usage_details keys are exclusive. Attributes that look like usage but belong to no known family are listed, never
guessed. This is a reference mapping written from those specifications, not Langfuse's server code.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gtc.harness.truth import PRICES, Usage

DIALECTS: dict[str, Any] = json.loads(Path(__file__).resolve().parents[1].joinpath("config/dialects.json").read_text())

GENERATION_OPS = {"chat", "text_completion", "generate_content", "completion", "responses"}
UNREADABLE = re.compile(r"\[object Object\]|<[\w.]+ object at 0x[0-9a-f]+>|^None$|^null$|^\{\}$|^\[\]$")
IO_IN = ("langfuse.observation.input", "gen_ai.input.messages", "gen_ai.prompt", "input.value", "gen_ai.system_instructions")
IO_OUT = ("langfuse.observation.output", "gen_ai.output.messages", "gen_ai.completion", "output.value")


@dataclass
class Observation:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    scope: str
    start_ns: int
    end_ns: int
    type: str
    model: str | None
    usage: Usage | None
    dialect: str | None
    usage_by_dialect: dict[str, Usage] = field(default_factory=dict)
    nonstandard: list[str] = field(default_factory=list)
    unknown_usage_attrs: list[str] = field(default_factory=list)
    input_text: str | None = None
    output_text: str | None = None

    @property
    def cost(self) -> float | None:
        if self.usage is None or self.model not in PRICES:
            return None
        return self.usage.cost(self.model)

    def as_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k not in ("usage", "usage_by_dialect")}
        d["usage"] = self.usage.__dict__ if self.usage else None
        d["usage_by_dialect"] = {k: u.__dict__ for k, u in self.usage_by_dialect.items()}
        d["cost"] = self.cost
        for k in ("input_text", "output_text"):
            if d[k] is not None:
                d[k] = d[k][:300]
        return d


def _int(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _json(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _from_usage_details(d: dict[str, Any]) -> Usage:
    rules = DIALECTS["langfuse_usage_details"]
    if "prompt_tokens" in d or "completion_tokens" in d:
        # OpenAI's raw usage object: prompt_tokens contains cached tokens
        details = d.get("prompt_tokens_details") or {}
        cached = _int(details.get("cached_tokens")) if isinstance(details, dict) else 0
        out_details = d.get("completion_tokens_details") or {}
        return Usage(input=_int(d.get("prompt_tokens")) - cached, cache_read=cached, cache_write=0, output=_int(d.get("completion_tokens")))
        _ = out_details
    cr = sum(_int(d.get(k)) for k in rules["cache_read_keys"])
    cw = sum(_int(d.get(k)) for k in rules["cache_write_keys"])
    cache_keys = set(rules["cache_read_keys"]) | set(rules["cache_write_keys"])
    inp = _int(d.get("input")) + sum(_int(v) for k, v in d.items() if k.startswith("input_") and k not in cache_keys and isinstance(v, int | float))
    out = _int(d.get("output")) + sum(_int(v) for k, v in d.items() if k.startswith("output_") and isinstance(v, int | float))
    return Usage(input=inp, cache_read=cr, cache_write=cw, output=out)


def _from_gen_ai(a: dict[str, Any], nonstandard: list[str]) -> Usage | None:
    g = DIALECTS["gen_ai"]
    if g["input"] not in a and g["output"] not in a:
        return None
    cr = sum(_int(a[k]) for k in g["cache_read"] if k in a)
    cw = sum(_int(a[k]) for k in g["cache_write"] if k in a)
    for alias, bucket in g["nonstandard_aliases"].items():
        if alias in a:
            nonstandard.append(alias)
            if bucket == "cache_read" and not any(k in a for k in g["cache_read"]):
                cr += _int(a[alias])
            if bucket == "cache_write" and not any(k in a for k in g["cache_write"]):
                cw += _int(a[alias])
    total_in = _int(a.get(g["input"]))
    return Usage(input=total_in - cr - cw, cache_read=cr, cache_write=cw, output=_int(a.get(g["output"])))


def _from_openinference(a: dict[str, Any]) -> Usage | None:
    o = DIALECTS["openinference"]
    if o["input"] not in a and o["output"] not in a:
        return None
    cr = sum(_int(a[k]) for k in o["cache_read"] if k in a)
    cw = sum(_int(a[k]) for k in o["cache_write"] if k in a)
    return Usage(input=_int(a.get(o["input"])) - cr - cw, cache_read=cr, cache_write=cw, output=_int(a.get(o["output"])))


def _kind(a: dict[str, Any], has_usage: bool) -> str:
    lf = a.get("langfuse.observation.type")
    if isinstance(lf, str) and lf:
        return lf
    op = a.get("gen_ai.operation.name")
    if op in GENERATION_OPS:
        return "generation"
    if op == "execute_tool":
        return "tool"
    if op in ("invoke_agent", "create_agent"):
        return "agent"
    oi = {"LLM": "generation", "TOOL": "tool", "AGENT": "agent", "CHAIN": "chain", "RETRIEVER": "retriever", "EMBEDDING": "embedding"}.get(
        str(a.get("openinference.span.kind", ""))
    )
    if oi:
        return oi
    return "generation" if has_usage else "span"


def _text(a: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        if k in a and a[k] not in (None, ""):
            v = a[k]
            return v if isinstance(v, str) else json.dumps(v)
    return None


def map_span(s: dict[str, Any]) -> Observation:
    a: dict[str, Any] = s["attributes"]
    by: dict[str, Usage] = {}
    nonstandard: list[str] = []
    if "langfuse.observation.usage_details" in a:
        d = _json(a["langfuse.observation.usage_details"])
        if isinstance(d, dict):
            by["langfuse"] = _from_usage_details(d)
    if (u := _from_gen_ai(a, nonstandard)) is not None:
        by["gen_ai"] = u
    if (u := _from_openinference(a)) is not None:
        by["openinference"] = u
    known = set(DIALECTS["semconv_gen_ai_usage_names"]) | set(DIALECTS["gen_ai"]["nonstandard_aliases"])
    known |= {DIALECTS["openinference"]["input"], DIALECTS["openinference"]["output"], *DIALECTS["openinference"]["cache_read"], *DIALECTS["openinference"]["cache_write"]}
    ignored = tuple(DIALECTS["gen_ai"]["ignored_prefixes"])
    unknown = sorted(
        k
        for k in a
        if ("usage" in k or "token_count" in k)
        and k.startswith(("gen_ai.", "llm."))
        and k not in known
        and not k.startswith(ignored)
        and not k.startswith("llm.token_count.total")
        and not k.startswith("llm.token_count.completion_details")
        and not k.startswith("llm.token_count.prompt_details")
    )
    for k in a:
        if (
            k.startswith("gen_ai.usage.")
            and not k.startswith(ignored)
            and k not in DIALECTS["semconv_gen_ai_usage_names"]
            and k not in nonstandard
            and k != "gen_ai.usage.total_tokens"
        ):
            nonstandard.append(k)
    dialect = next((d for d in ("langfuse", "gen_ai", "openinference") if d in by), None)
    kind = _kind(a, bool(by))
    model = a.get("langfuse.observation.model.name") or a.get("gen_ai.response.model") or a.get("gen_ai.request.model") or a.get("llm.model_name")
    return Observation(
        trace_id=s["trace_id"],
        span_id=s["span_id"],
        parent_span_id=s["parent_span_id"],
        name=s["name"],
        scope=s["scope"],
        start_ns=s["start_ns"],
        end_ns=s["end_ns"],
        type=kind,
        model=str(model) if model else None,
        usage=by[dialect] if dialect else None,
        dialect=dialect,
        usage_by_dialect=by,
        nonstandard=sorted(set(nonstandard)),
        unknown_usage_attrs=unknown,
        input_text=_text(a, IO_IN),
        output_text=_text(a, IO_OUT),
    )


def unreadable(text: str | None) -> bool:
    return text is None or text.strip() == "" or bool(UNREADABLE.search(text.strip()))
