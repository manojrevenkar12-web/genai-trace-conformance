# 1. Real SDKs against a local model server

**Status:** accepted

Integration bugs live in the interaction of real packages: an SDK release that starts emitting its own spans, a
framework that reports cache tokens under three names, an export filter that forwards more than it should. Mocking the
SDKs would remove exactly what breaks. So every scenario runs the real packages, pinned, in its own virtualenv, and
calls a local server that speaks the OpenAI and Anthropic APIs. The server answers deterministically, reports usage the
way each provider does (OpenAI counts cached tokens inside `prompt_tokens`; Anthropic reports cache reads and writes
beside `input_tokens`) and records the truth in exclusive buckets. The Langfuse client exports to the same process over
OTLP/HTTP at `/api/public/otel/v1/traces`, so the wire format is real too.

Consequence: no API keys, no network to model providers, deterministic usage, and a ground truth to compare with. What
is not covered: provider-side behaviour the server does not imitate (rate limits, partial streams, server-side errors).
