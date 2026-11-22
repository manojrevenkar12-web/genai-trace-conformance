# Cookbook: from zero to a checked trace in five minutes

## 1. Run one integration against the local server

```bash
uv venv -p 3.13 .venv && . .venv/bin/activate && uv pip install -r requirements.txt
python -m gtc.cli repro openai.chat_cached
```

The harness starts one local process that is both the model provider (`/v1/chat/completions`, `/v1/messages`) and the
trace backend (`/api/public/otel/v1/traces`), runs the scenario in a subprocess with `LANGFUSE_BASE_URL`,
`OPENAI_BASE_URL` and `ANTHROPIC_BASE_URL` pointing at it, and prints every check.

## 2. Try an older SDK

```bash
python -m gtc.cli repro langchain.anthropic_cache --pins anthropic==1.13.0   # passes
python -m gtc.cli repro langchain.anthropic_cache --pins anthropic==1.14.0   # two generations per call
```

Each pin set gets its own virtualenv under `.matrix/`, built by uv and reused.

## 3. Write a new scenario

```python
# scenarios/my_framework.py
from scenarios.common import BASE, OPENAI_MODEL, flush_langfuse, marker


def tools() -> None:
    from langfuse import observe
    from my_framework import Agent  # the SDK under test, unmodified

    @observe(name="my-run", as_type="agent")
    def run() -> None:
        Agent(model=OPENAI_MODEL, base_url=f"{BASE}/v1").run(f"Weather in Berlin? {marker(1)}")

    run()
    flush_langfuse()
```

Register it in `scenarios/run.py`, declare `{"runs": 1, "tools": 1, "wrapped": true, "isolated": false}` in
`config/scenarios.json`, and run `python -m gtc.cli repro my_framework.tools`.

## 4. Read a failure

```
one_generation_per_call  fail  4 generations for 2 calls, from langfuse-sdk (2), com.anthropic.sdk.python (2)
cost_exact               fail  traced $0.013865 vs charged $0.006933 (+100%)
```

The scopes name who emitted each generation. The cost line is what the user's dashboard would show against what the
provider charged. Next: `python -m gtc.cli bisect "Anthropic SDK starts exporting its own generation spans"`.
