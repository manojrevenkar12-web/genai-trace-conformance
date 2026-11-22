# Draft report: Anthropic SDK ≥ 1.14 spans double every Claude generation behind LangChain and Pydantic AI

_Draft for the Langfuse issue tracker and, for the attribute name, the Anthropic SDK. Not filed; written from the lab's
reproduction so a maintainer can check it and post it._

## What happens

With `anthropic>=1.14.0` installed, the Anthropic Python SDK emits its own OpenTelemetry span for every
`messages.create` call (instrumentation scope `com.anthropic.sdk.python`, `gen_ai.operation.name = chat`, full
`gen_ai.usage.*`). The Langfuse client's default export filter forwards spans that carry `gen_ai.*` attributes, so a
user who traces Claude through the LangChain `CallbackHandler` or Pydantic AI's instrumentation gets **two generations
per call**, and the trace's cost is **doubled**. With the OpenLLMetry Anthropic instrumentor also on, it is three.

## Reproduce

```bash
python -m gtc.cli repro langchain.anthropic_cache --pins anthropic==1.14.0
python -m gtc.cli repro langchain.anthropic_cache --pins anthropic==1.13.0   # one generation per call
```

Matrix result (latest pins: langfuse 5.2.0, langchain-core 1.8.4, langchain-anthropic 1.7.12, anthropic 2.12.0):

```
one_generation_per_call  fail  4 generations for 2 calls, from langfuse-sdk (2), com.anthropic.sdk.python (2)
cost_exact               fail  traced $0.013865 vs charged $0.006933 (+100%)
```

Bisect over the Anthropic SDK's releases, everything else fixed: last good **1.13.0**, first bad **1.14.0**.

## Second, smaller point: attribute name

The SDK reports cache writes as `gen_ai.usage.cache_write.input_tokens`. The GenAI semantic conventions name it
`gen_ai.usage.cache_creation.input_tokens`, which the OpenLLMetry instrumentor and Pydantic AI use. A backend that reads
only the standard name prices cache writes as plain input.

## Possible fixes

- In Langfuse: when a span from a framework integration (LangChain, Pydantic AI) already represents the call, do not
  export the provider SDK's child generation span by default; or document `should_export_span` for this case.
- In the Anthropic SDK: use the standard attribute name, and consider an opt-out for its spans when a framework above it
  is already instrumented.
