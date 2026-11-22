"""An OTLP/HTTP trace receiver at Langfuse's path (/api/public/otel/v1/traces).

It accepts what the Langfuse SDK and other OpenTelemetry exporters send (protobuf or JSON, optionally gzip) and keeps
the spans exactly as they arrived on the wire, with their instrumentation scope and resource.
"""

from __future__ import annotations

import base64
import gzip
import json
import threading
from dataclasses import dataclass, field
from typing import Any

from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest, ExportTraceServiceResponse
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from starlette.requests import Request
from starlette.responses import Response


def any_value(v: AnyValue) -> Any:
    kind = v.WhichOneof("value")
    if kind is None:
        return None
    if kind == "array_value":
        return [any_value(x) for x in v.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: any_value(kv.value) for kv in v.kvlist_value.values}
    if kind == "bytes_value":
        return base64.b64encode(v.bytes_value).decode()
    return getattr(v, kind)


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    scope: str
    scope_version: str
    start_ns: int
    end_ns: int
    attributes: dict[str, Any]
    resource: dict[str, Any]
    events: list[dict[str, Any]]
    status: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class SpanStore:
    spans: list[Span] = field(default_factory=list)
    requests: int = 0
    auth_headers: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def clear(self) -> None:
        with self.lock:
            self.spans.clear()
            self.requests = 0


def decode(body: bytes, content_type: str, encoding: str) -> ExportTraceServiceRequest:
    if encoding == "gzip" or body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    req = ExportTraceServiceRequest()
    if "json" in content_type:
        ParseDict(json.loads(body), req, ignore_unknown_fields=True)
    else:
        req.ParseFromString(body)
    return req


def spans_of(req: ExportTraceServiceRequest) -> list[Span]:
    out: list[Span] = []
    for rs in req.resource_spans:
        resource = {kv.key: any_value(kv.value) for kv in rs.resource.attributes}
        for ss in rs.scope_spans:
            for s in ss.spans:
                out.append(
                    Span(
                        trace_id=s.trace_id.hex(),
                        span_id=s.span_id.hex(),
                        parent_span_id=s.parent_span_id.hex() or None,
                        name=s.name,
                        scope=ss.scope.name,
                        scope_version=ss.scope.version,
                        start_ns=s.start_time_unix_nano,
                        end_ns=s.end_time_unix_nano,
                        attributes={kv.key: any_value(kv.value) for kv in s.attributes},
                        resource=resource,
                        events=[{"name": e.name, "time_ns": e.time_unix_nano, "attributes": {kv.key: any_value(kv.value) for kv in e.attributes}} for e in s.events],
                        status={0: "unset", 1: "ok", 2: "error"}.get(s.status.code, "unset"),
                    )
                )
    return out


class OtlpReceiver:
    def __init__(self, store: SpanStore) -> None:
        self.store = store

    async def traces(self, request: Request) -> Response:
        body = await request.body()
        try:
            req = decode(body, request.headers.get("content-type", ""), request.headers.get("content-encoding", ""))
        except Exception as e:
            return Response(f"cannot decode OTLP payload: {type(e).__name__}", status_code=400)
        new = spans_of(req)
        with self.store.lock:
            self.store.spans.extend(new)
            self.store.requests += 1
            if auth := request.headers.get("authorization"):
                self.store.auth_headers.add(auth)
        return Response(ExportTraceServiceResponse().SerializeToString(), media_type="application/x-protobuf")
