"""One local process that is both the model provider and the trace backend, on a free port."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route

from gtc.harness.model_server import ModelServer
from gtc.harness.otlp_receiver import OtlpReceiver, SpanStore
from gtc.harness.truth import Ledger


@dataclass
class Harness:
    base_url: str
    ledger: Ledger
    store: SpanStore
    models: ModelServer

    def reset(self) -> None:
        self.ledger.clear()
        self.store.clear()
        self.models.openai_prefixes.clear()
        self.models.anthropic_cache.clear()


def app(ledger: Ledger, store: SpanStore) -> tuple[Starlette, ModelServer]:
    models = ModelServer(ledger)
    otlp = OtlpReceiver(store)
    routes = [
        Route("/v1/chat/completions", models.openai_chat, methods=["POST"]),
        Route("/v1/messages", models.anthropic_messages, methods=["POST"]),
        Route("/api/public/otel/v1/traces", otlp.traces, methods=["POST"]),
    ]
    return Starlette(routes=routes), models


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def running() -> Iterator[Harness]:
    ledger, store = Ledger(), SpanStore()
    application, models = app(ledger, store)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("local server did not start")
        time.sleep(0.02)
    try:
        yield Harness(f"http://127.0.0.1:{port}", ledger, store, models)
    finally:
        server.should_exit = True
        t.join(timeout=5)
