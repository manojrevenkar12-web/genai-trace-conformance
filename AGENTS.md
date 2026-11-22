# AGENTS.md

How to work in this repository, for people and coding agents alike.

## Fast feedback

```bash
uv venv -p 3.13 .venv && . .venv/bin/activate && uv pip install -r requirements.txt
ruff check . && ruff format --check . && mypy && pytest -q      # about 10 seconds, real SDKs included
python -m gtc.cli repro langchain.anthropic_cache                 # one scenario, every check
python -m gtc.eval.cli analyse dev                                # recompute the report from stored captures (seconds)
python -m gtc.eval.cli dev                                        # run the whole SDK matrix and bisections again (minutes)
cd web && npm ci && npm test && npm run build                     # dashboard
```

## Invariants

1. **The truth stays in the world.** The local model server (`gtc/harness/model_server.py`) decides usage and records
   it in the ledger; the release simulation (`gtc/world.py`) decides which releases break what. Checks read only the
   captured spans and the ledger. Scenarios never import `gtc`; they import only the SDKs under test.
2. **The world does not read the lab's settings.** `gtc/world.py` reads `config/world.json` and is handed detection
   ability as numbers; it never imports `gtc` and never reads `config/designs.json` itself. A test enforces it.
3. **Same luck for every design.** Every random draw in the simulation is keyed by what it is about (integration,
   release), never by order. Every design plays the same releases.
4. **The model reads and code decides.** The triage agent's optional Claude reader proposes labels; code keeps one only
   if it is an allowed label backed by a quote that appears in the issue word for word. Issue text is data.
5. **Real SDKs, real wire.** Integrations run unmodified in their own virtualenv with pinned versions; spans arrive over
   OTLP/HTTP at Langfuse's path with basic auth. Never mock an SDK to make a check pass.
6. **Settings in config.** Prices, dialects, scenarios, environments, gates, world rates and triage rules live in
   `config/*.json`.
7. **Reports are generated.** `reports/*.json`, `reports/REPORT.md` and the README block between the results markers come
   from `python -m gtc.eval.cli`. CI recomputes them from `reports/raw/` and fails on any difference.

## The held-out rule

Held-out environments (`config/heldout.json`), held-out simulation and fault seeds (`config/seeds.json`) and issues
created on or after the triage split date are not looked at while building. Gates (`config/gates.json`) are set on the
development run. `python -m gtc.eval.cli heldout` runs once and writes `heldout.lock` with the config hash; a second run
is refused, and CI fails if any config changes after the lock. CI enforces the development gates on every change; the
held-out gates are a one-time measurement and are reported as they came out (the triage gate failed, see the README).
