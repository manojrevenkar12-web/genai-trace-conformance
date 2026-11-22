import gzip
import json

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from gtc.harness.otlp_receiver import decode, spans_of
from gtc.mapping import map_span, unreadable


def request(attrs: dict) -> ExportTraceServiceRequest:
    def val(v):
        if isinstance(v, bool):
            return {"boolValue": v}
        if isinstance(v, int):
            return {"intValue": str(v)}
        return {"stringValue": str(v)}

    d = {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "t"}}]},
                "scopeSpans": [
                    {
                        "scope": {"name": "pydantic-ai", "version": "2"},
                        "spans": [
                            {
                                "traceId": "AAAAAAAAAAAAAAAAAAAAAQ==",
                                "spanId": "AAAAAAAAAAE=",
                                "name": "chat m",
                                "startTimeUnixNano": "1",
                                "endTimeUnixNano": "2",
                                "attributes": [{"key": k, "value": val(v)} for k, v in attrs.items()],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    from google.protobuf.json_format import ParseDict

    return ParseDict(d, ExportTraceServiceRequest())


def test_protobuf_json_and_gzip_decode_to_the_same_spans():
    req = request({"gen_ai.operation.name": "chat", "gen_ai.usage.input_tokens": 10})
    pb = req.SerializeToString()
    js = json.dumps(MessageToDict(req)).encode()
    a = spans_of(decode(pb, "application/x-protobuf", ""))
    b = spans_of(decode(gzip.compress(pb), "application/x-protobuf", "gzip"))
    c = spans_of(decode(js, "application/json", ""))
    assert [s.as_dict() for s in a] == [s.as_dict() for s in b] == [s.as_dict() for s in c]
    assert a[0].attributes["gen_ai.usage.input_tokens"] == 10 and a[0].scope == "pydantic-ai" and a[0].parent_span_id is None


def span(attrs: dict, scope: str = "x") -> dict:
    return {"trace_id": "t", "span_id": "s", "parent_span_id": None, "name": "n", "scope": scope, "start_ns": 0, "end_ns": 1, "attributes": attrs}


def test_gen_ai_input_includes_cache_reads_and_writes():
    o = map_span(
        span(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.usage.input_tokens": 1596,
                "gen_ai.usage.output_tokens": 16,
                "gen_ai.usage.cache_read.input_tokens": 1574,
                "gen_ai.response.model": "claude-test-sonnet",
            }
        )
    )
    assert o.type == "generation" and (o.usage.input, o.usage.cache_read, o.usage.cache_write, o.usage.output) == (22, 1574, 0, 16)
    assert o.nonstandard == []


def test_nonstandard_cache_write_name_is_read_and_flagged():
    o = map_span(span({"gen_ai.operation.name": "chat", "gen_ai.usage.input_tokens": 1586, "gen_ai.usage.output_tokens": 16, "gen_ai.usage.cache_write.input_tokens": 1571}))
    assert o.usage.cache_write == 1571 and o.usage.input == 15
    assert o.nonstandard == ["gen_ai.usage.cache_write.input_tokens"]


def test_langfuse_usage_details_exclusive_and_openai_raw():
    lc = map_span(
        span(
            {
                "langfuse.observation.type": "generation",
                "langfuse.observation.usage_details": json.dumps({"input": 15, "output": 16, "total": 1602, "cache_read_input_tokens": 1571, "cache_creation_input_tokens": 0}),
            }
        )
    )
    assert (lc.usage.input, lc.usage.cache_read, lc.usage.output) == (15, 1571, 16)
    raw = map_span(
        span(
            {
                "langfuse.observation.type": "generation",
                "langfuse.observation.usage_details": json.dumps(
                    {"prompt_tokens": 1577, "completion_tokens": 16, "total_tokens": 1593, "prompt_tokens_details": {"cached_tokens": 1536}}
                ),
            }
        )
    )
    assert (raw.usage.input, raw.usage.cache_read, raw.usage.output) == (41, 1536, 16)


def test_openinference_and_aggregated_usage():
    oi = map_span(span({"openinference.span.kind": "LLM", "llm.token_count.prompt": 103, "llm.token_count.completion": 31, "llm.token_count.prompt_details.cache_read": 3}))
    assert oi.type == "generation" and (oi.usage.input, oi.usage.cache_read) == (100, 3)
    agent = map_span(span({"gen_ai.operation.name": "invoke_agent", "gen_ai.aggregated_usage.input_tokens": 254}))
    assert agent.type == "agent" and agent.usage is None


def test_unreadable():
    assert unreadable("[object Object]") and unreadable("<foo.Bar object at 0x7f00aa>") and unreadable("") and unreadable(None)
    assert not unreadable('[{"role": "user", "content": "hi"}]')
