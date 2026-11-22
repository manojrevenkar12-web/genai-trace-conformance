"""Plants the bugs integrations really ship into clean captured traces, and benign changes that must not raise an alarm.

Each fault kind comes from a class of real Langfuse integration issues (duplicate generations from a second
instrumentation, cached tokens counted twice or dropped, '[object Object]' output, lost context, renamed attributes).
The fault knows which check should catch it; the checks never see the fault.
"""

from __future__ import annotations

import copy
import json
import random
from collections.abc import Callable
from typing import Any

from gtc.mapping import map_span

Spans = list[dict[str, Any]]
USAGE_KEYS = ("langfuse.observation.usage_details", "gen_ai.usage.input_tokens", "llm.token_count.prompt")


def _gens(spans: Spans) -> list[int]:
    return [i for i, s in enumerate(spans) if map_span(s).type == "generation"]


def _new_id(r: random.Random) -> str:
    return f"{r.getrandbits(64):016x}"


def duplicate_generation(spans: Spans, r: random.Random) -> Spans | None:
    g = _gens(spans)
    if not g:
        return None
    s = copy.deepcopy(spans[r.choice(g)])
    s["span_id"] = _new_id(r)
    s["scope"] = "com.vendor.sdk"
    return [*spans, s]


def _cached(spans: Spans) -> list[int]:
    out = []
    for i in _gens(spans):
        u = map_span(spans[i]).usage
        if u and (u.cache_read or u.cache_write):
            out.append(i)
    return out


def cache_double_count(spans: Spans, r: random.Random) -> Spans | None:
    c = _cached(spans)
    if not c:
        return None
    spans = copy.deepcopy(spans)
    s = spans[r.choice(c)]
    a = s["attributes"]
    u = map_span(s).usage
    assert u is not None
    extra = u.cache_read + u.cache_write
    if "langfuse.observation.usage_details" in a:
        d = json.loads(a["langfuse.observation.usage_details"]) if isinstance(a["langfuse.observation.usage_details"], str) else dict(a["langfuse.observation.usage_details"])
        if "prompt_tokens" in d:
            d["prompt_tokens"] = int(d["prompt_tokens"]) + extra
        else:
            d["input"] = int(d.get("input", 0)) + extra
        a["langfuse.observation.usage_details"] = json.dumps(d)
    elif "gen_ai.usage.input_tokens" in a:
        a["gen_ai.usage.input_tokens"] = int(a["gen_ai.usage.input_tokens"]) + extra
    else:
        a["llm.token_count.prompt"] = int(a["llm.token_count.prompt"]) + extra
    return spans


def cache_dropped(spans: Spans, r: random.Random) -> Spans | None:
    c = _cached(spans)
    if not c:
        return None
    spans = copy.deepcopy(spans)
    a = spans[r.choice(c)]["attributes"]
    for k in list(a):
        if "cache" in k and ("usage" in k or "token_count" in k):
            del a[k]
    if "langfuse.observation.usage_details" in a:
        d = json.loads(a["langfuse.observation.usage_details"]) if isinstance(a["langfuse.observation.usage_details"], str) else dict(a["langfuse.observation.usage_details"])
        for k in list(d):
            if "cache" in k:
                d.pop(k)
        if isinstance(d.get("prompt_tokens_details"), dict):
            d["prompt_tokens_details"].pop("cached_tokens", None)
        a["langfuse.observation.usage_details"] = json.dumps(d)
    return spans


def object_object_output(spans: Spans, r: random.Random) -> Spans | None:
    g = _gens(spans)
    if not g:
        return None
    spans = copy.deepcopy(spans)
    a = spans[r.choice(g)]["attributes"]
    for k in ("langfuse.observation.output", "gen_ai.output.messages", "output.value", "gen_ai.completion"):
        if k in a:
            a[k] = "[object Object]"
            return spans
    a["gen_ai.output.messages"] = "[object Object]"
    return spans


def context_lost(spans: Spans, r: random.Random) -> Spans | None:
    """A generation created on a thread or task that lost the run's context starts its own trace."""
    g = [i for i in _gens(spans) if spans[i]["parent_span_id"]]
    if not g:
        return None
    spans = copy.deepcopy(spans)
    s = spans[r.choice(g)]
    s["parent_span_id"] = None
    s["trace_id"] = f"{r.getrandbits(128):032x}"
    return spans


def parent_never_exported(spans: Spans, r: random.Random) -> Spans | None:
    roots = [i for i, s in enumerate(spans) if s["parent_span_id"] is None and any(x["parent_span_id"] == s["span_id"] for x in spans)]
    if not roots:
        return None
    drop = r.choice(roots)
    return [s for i, s in enumerate(spans) if i != drop]


def model_missing(spans: Spans, r: random.Random) -> Spans | None:
    g = _gens(spans)
    if not g:
        return None
    spans = copy.deepcopy(spans)
    a = spans[r.choice(g)]["attributes"]
    for k in ("langfuse.observation.model.name", "gen_ai.response.model", "gen_ai.request.model", "llm.model_name"):
        a.pop(k, None)
    return spans


def usage_missing(spans: Spans, r: random.Random) -> Spans | None:
    g = _gens(spans)
    if not g:
        return None
    spans = copy.deepcopy(spans)
    a = spans[r.choice(g)]["attributes"]
    for k in list(a):
        if k == "langfuse.observation.usage_details" or k.startswith(("gen_ai.usage.", "llm.token_count.")):
            del a[k]
    return spans


def tool_span_missing(spans: Spans, r: random.Random) -> Spans | None:
    tools = [i for i, s in enumerate(spans) if map_span(s).type == "tool"]
    if not tools:
        return None
    drop = r.choice(tools)
    kids = {spans[drop]["span_id"]}
    return [s for i, s in enumerate(spans) if i != drop and s["parent_span_id"] not in kids]


def attribute_renamed(spans: Spans, r: random.Random) -> Spans | None:
    """An instrumentation ships the pre-standard name for input tokens."""
    g = [i for i in _gens(spans) if "gen_ai.usage.input_tokens" in spans[i]["attributes"]]
    if not g:
        return None
    spans = copy.deepcopy(spans)
    a = spans[r.choice(g)]["attributes"]
    a["gen_ai.usage.prompt_tokens"] = a.pop("gen_ai.usage.input_tokens")
    return spans


def runs_mixed(spans: Spans, r: random.Random) -> Spans | None:
    """A concurrent run's generation lands in another run's trace."""
    g = _gens(spans)
    traces = sorted({spans[i]["trace_id"] for i in g})
    if len(traces) < 2:
        return None
    spans = copy.deepcopy(spans)
    i = r.choice(g)
    other = r.choice([t for t in traces if t != spans[i]["trace_id"]])
    root = next(s for s in spans if s["trace_id"] == other and s["parent_span_id"] is None)
    spans[i]["trace_id"], spans[i]["parent_span_id"] = other, root["span_id"]
    return spans


def latency_zero(spans: Spans, r: random.Random) -> Spans | None:
    """The generation is closed the moment it opens, so latency reads 0 ms. No check looks at durations."""
    g = _gens(spans)
    if not g:
        return None
    spans = copy.deepcopy(spans)
    s = spans[r.choice(g)]
    s["end_ns"] = s["start_ns"]
    return spans


def first_token_time_missing(spans: Spans, r: random.Random) -> Spans | None:
    """A streamed generation loses its completion start time, so time to first token cannot be shown."""
    g = [i for i in _gens(spans) if "langfuse.observation.completion_start_time" in spans[i]["attributes"]]
    if not g:
        return None
    spans = copy.deepcopy(spans)
    spans[r.choice(g)]["attributes"].pop("langfuse.observation.completion_start_time")
    return spans


# fault -> the checks that should flag it
FAULTS: dict[str, tuple[Callable[[Spans, random.Random], Spans | None], set[str]]] = {
    "duplicate_generation": (duplicate_generation, {"one_generation_per_call", "cost_exact"}),
    "cache_double_count": (cache_double_count, {"usage_exact", "cost_exact"}),
    "cache_dropped": (cache_dropped, {"usage_exact", "cost_exact"}),
    "object_object_output": (object_object_output, {"readable_io"}),
    "context_lost": (context_lost, {"one_trace_per_run", "nested_under_run", "run_isolation"}),
    "parent_never_exported": (parent_never_exported, {"one_trace_per_run", "nested_under_run"}),
    "model_missing": (model_missing, {"model_name", "cost_exact"}),
    "usage_missing": (usage_missing, {"usage_exact", "cost_exact"}),
    "tool_span_missing": (tool_span_missing, {"tools_traced"}),
    "attribute_renamed": (attribute_renamed, {"standard_attribute_names", "usage_exact"}),
    "runs_mixed": (runs_mixed, {"run_isolation"}),
    # real bug classes no check covers yet: they show where the lab stops
    "latency_zero": (latency_zero, set()),
    "first_token_time_missing": (first_token_time_missing, set()),
}


# benign changes a correct backend must not care about
def reorder(spans: Spans, r: random.Random) -> Spans:
    s = list(spans)
    r.shuffle(s)
    return s


def extra_http_spans(spans: Spans, r: random.Random) -> Spans:
    out = list(spans)
    for s in spans:
        if map_span(s).type == "generation":
            out.append(
                {
                    **copy.deepcopy(s),
                    "span_id": _new_id(r),
                    "parent_span_id": s["span_id"],
                    "name": "POST",
                    "scope": "opentelemetry.instrumentation.httpx",
                    "attributes": {"http.request.method": "POST", "url.full": "http://127.0.0.1/v1/chat/completions", "http.response.status_code": 200},
                }
            )
    return out


def extra_attributes(spans: Spans, r: random.Random) -> Spans:
    out = copy.deepcopy(spans)
    for s in out:
        s["attributes"]["deployment.environment"] = "staging"
        s["attributes"]["user.id"] = f"u{r.randrange(1000)}"
    return out


def renamed_spans(spans: Spans, r: random.Random) -> Spans:
    out = copy.deepcopy(spans)
    for s in out:
        s["name"] = s["name"].upper()
    return out


def clock_jitter(spans: Spans, r: random.Random) -> Spans:
    out = copy.deepcopy(spans)
    for s in out:
        d = r.randint(-3_000_000, 3_000_000)
        s["start_ns"] += d
        s["end_ns"] += d
    return out


BENIGN: dict[str, Callable[[Spans, random.Random], Spans]] = {
    "reordered_export": reorder,
    "http_client_spans": extra_http_spans,
    "extra_attributes": extra_attributes,
    "renamed_spans": renamed_spans,
    "clock_jitter_3ms": clock_jitter,
}
