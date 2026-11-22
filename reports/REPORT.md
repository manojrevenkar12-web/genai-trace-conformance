# Results

_Generated from `reports/`. Do not edit by hand._

## dev (config `56a35d7550d0`)

On 16 development environments (34 pinned SDK versions), 41 of 43 scenario runs completed and 2 crashed; the checks failed on 7 runs (cost_exact, one_generation_per_call). In the simulated ecosystem the lab cut project-days on broken traces by 52% (46% to 58%) against today.

| Environment | Runs | Crashed | Failing checks |
|---|---|---|---|
| openai · latest | 5 | 0 | none |
| openai · langfuse 5.0 / openai 3.0 | 5 | 0 | none |
| openai · langfuse 4.18 / openai 2.54 | 5 | 0 | none |
| openai · langfuse 3.15 / openai 1.109 | 5 | 0 | none |
| langchain · latest | 3 | 0 | langchain.anthropic_cache: one_generation_per_call (4 generations for 2 calls, from langfuse-sdk (2), com.anthropic.sdk.python (2))<br>langchain.anthropic_cache: cost_exact (traced $0.013865 vs charged $0.006933 (+100%))<br>langchain.anthropic_plus_otel: one_generation_per_call (6 generations for 2 calls, from langfuse-sdk (2), opentelemetry.instrumentation.anthropic )<br>langchain.anthropic_plus_otel: cost_exact (traced $0.020798 vs charged $0.006933 (+200%)) |
| langchain · anthropic 1.13 | 2 | 0 | langchain.anthropic_plus_otel: one_generation_per_call (4 generations for 2 calls, from langfuse-sdk (2), opentelemetry.instrumentation.anthropic )<br>langchain.anthropic_plus_otel: cost_exact (traced $0.013865 vs charged $0.006933 (+100%)) |
| langchain · langfuse 4.18 / langchain-openai 1.6 / anthropic 0.125 | 3 | 0 | langchain.anthropic_plus_otel: one_generation_per_call (4 generations for 2 calls, from langfuse-sdk (2), opentelemetry.instrumentation.anthropic )<br>langchain.anthropic_plus_otel: cost_exact (traced $0.013865 vs charged $0.006933 (+100%)) |
| langchain · langfuse 3 / langchain 0.3 | 3 | 0 | langchain.anthropic_plus_otel: one_generation_per_call (4 generations for 2 calls, from langfuse-sdk (2), opentelemetry.instrumentation.anthropic )<br>langchain.anthropic_plus_otel: cost_exact (traced $0.013865 vs charged $0.006933 (+100%)) |
| pydantic-ai · latest | 2 | 0 | pydantic_ai.anthropic_cache: one_generation_per_call (4 generations for 2 calls, from pydantic-ai (2), com.anthropic.sdk.python (2))<br>pydantic_ai.anthropic_cache: cost_exact (traced $0.013973 vs charged $0.006987 (+100%)) |
| pydantic-ai · 2.40 + newest anthropic the installer allows | 2 | 1 | pydantic_ai.anthropic_cache: runs (TypeError: Cannot instantiate typing.Union) |
| pydantic-ai · 2.40 / anthropic 1.17 | 2 | 0 | pydantic_ai.anthropic_cache: one_generation_per_call (4 generations for 2 calls, from pydantic-ai (2), com.anthropic.sdk.python (2))<br>pydantic_ai.anthropic_cache: cost_exact (traced $0.013973 vs charged $0.006987 (+100%)) |
| pydantic-ai · 1.107 | 2 | 0 | none |
| agents sdk · latest | 1 | 0 | none |
| agents sdk · 0.20 | 1 | 0 | none |
| agents sdk · 0.17 + newest openai the installer allows | 1 | 1 | agents_sdk.tools: runs (pydantic_core._pydantic_core.ValidationError: 1 validation error for InputTokensDetails) |
| agents sdk · 0.17 / openai 2.44 | 1 | 0 | none |

| First bad release | Package | Last good | First bad | Versions tested |
|---|---|---|---|---|
| Anthropic SDK starts exporting its own generation spans | anthropic | 1.13.0 | 1.14.0 | 4 |
| OpenAI SDK change crashes Agents SDK 0.17 | openai | 2.44.0 | 2.45.0 | 5 |
| Anthropic SDK change crashes Pydantic AI 2.40 | anthropic | 1.17.0 | 2.0.0 | 3 |

| Bug kind planted in real traces | Planted | Caught | Recall |
|---|---|---|---|
| attribute renamed | 30 | 30 | 100% |
| cache double count | 48 | 48 | 100% |
| cache dropped | 48 | 48 | 100% |
| context lost | 186 | 186 | 100% |
| duplicate generation | 204 | 204 | 100% |
| first token time missing | 24 | 0 | 0% |
| latency zero | 204 | 31 | 15% |
| model missing | 204 | 204 | 100% |
| object object output | 204 | 204 | 100% |
| parent never exported | 186 | 186 | 100% |
| runs mixed | 72 | 72 | 100% |
| tool span missing | 84 | 84 | 100% |
| usage missing | 204 | 204 | 100% |

Harmless changes (reordered exports, extra HTTP spans, extra attributes, renamed spans, 3 ms clock jitter): 510, false alarms: 0.

| Triage against maintainers' integration labels | Issues | Precision | Recall | F1 |
|---|---|---|---|---|
| Triage agent | 467 | 0.74 | 0.82 | 0.78 |
| Any mention of the framework | 467 | 0.55 | 0.91 | 0.69 |

| Design | Bugs reaching users | Caught by the lab | Project-days on broken traces cut | Wrong-cost project-days cut | Median days, release to fix | Maintainer hours / week |
|---|---|---|---|---|---|---|
| Today: users report it, a maintainer reproduces and bisects by hand | 100% | 0% | – | – | 10.6 | 5.6 |
| Triage agent on incoming issues, no conformance runs | 100% | 0% | 11% (11% to 12%) | 11% (10% to 13%) | 9.2 | 4.9 |
| Nightly conformance runs on each new release, with bisect | 100% | 43% | 35% (29% to 40%) | 35% (27% to 41%) | 6.4 | 5.9 |
| Nightly runs on releases and on each framework's main branch | 66% | 44% | 47% (40% to 54%) | 48% (38% to 57%) | 6.4 | 5.9 |
| The lab: nightly on releases and main, bisect, triage agent | 66% | 44% | 52% (46% to 58%) | 53% (44% to 61%) | 5.4 | 5.7 |

| Gate | Measured | Pass |
|---|---|---|
| recall on the bug kinds the checks cover at least 95% | 1.0 | yes |
| false alarms on harmless changes at most 1% | 0.0 | yes |
| triage F1 against maintainers' labels at least 0.65 | 0.78 | yes |
| lab cuts project-days on broken traces by at least 25% (low end of the interval) | 0.4557 | yes |
| lab maintainer hours at most 110% of today's | 1.011 | yes |

### Every failing or crashing run

- **langchain · latest**, `langchain.anthropic_cache`: one_generation_per_call fail: 4 generations for 2 calls, from langfuse-sdk (2), com.anthropic.sdk.python (2); cost_exact fail: traced $0.013865 vs charged $0.006933 (+100%); standard_attribute_names warn: non-standard: gen_ai.usage.cache_write.input_tokens
- **langchain · latest**, `langchain.anthropic_plus_otel`: one_generation_per_call fail: 6 generations for 2 calls, from langfuse-sdk (2), opentelemetry.instrumentation.anthropic (2), com.anthropic.sdk.python (2); cost_exact fail: traced $0.020798 vs charged $0.006933 (+200%); standard_attribute_names warn: non-standard: gen_ai.usage.cache_write.input_tokens
- **langchain · anthropic 1.13**, `langchain.anthropic_plus_otel`: one_generation_per_call fail: 4 generations for 2 calls, from langfuse-sdk (2), opentelemetry.instrumentation.anthropic (2); cost_exact fail: traced $0.013865 vs charged $0.006933 (+100%)
- **langchain · langfuse 4.18 / langchain-openai 1.6 / anthropic 0.125**, `langchain.anthropic_plus_otel`: one_generation_per_call fail: 4 generations for 2 calls, from langfuse-sdk (2), opentelemetry.instrumentation.anthropic (2); cost_exact fail: traced $0.013865 vs charged $0.006933 (+100%)
- **langchain · langfuse 3 / langchain 0.3**, `langchain.anthropic_plus_otel`: one_generation_per_call fail: 4 generations for 2 calls, from langfuse-sdk (2), opentelemetry.instrumentation.anthropic (2); cost_exact fail: traced $0.013865 vs charged $0.006933 (+100%)
- **pydantic-ai · latest**, `pydantic_ai.anthropic_cache`: one_generation_per_call fail: 4 generations for 2 calls, from pydantic-ai (2), com.anthropic.sdk.python (2); cost_exact fail: traced $0.013973 vs charged $0.006987 (+100%); standard_attribute_names warn: non-standard: gen_ai.usage.cache_write.input_tokens
- **pydantic-ai · 2.40 + newest anthropic the installer allows**, `pydantic_ai.anthropic_cache`: crashed: TypeError: Cannot instantiate typing.Union
- **pydantic-ai · 2.40 / anthropic 1.17**, `pydantic_ai.anthropic_cache`: one_generation_per_call fail: 4 generations for 2 calls, from pydantic-ai (2), com.anthropic.sdk.python (2); cost_exact fail: traced $0.013973 vs charged $0.006987 (+100%); standard_attribute_names warn: non-standard: gen_ai.usage.cache_write.input_tokens
- **agents sdk · 0.17 + newest openai the installer allows**, `agents_sdk.tools`: crashed: pydantic_core._pydantic_core.ValidationError: 1 validation error for InputTokensDetails
