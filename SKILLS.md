# SKILLS.md

Repeatable tasks, each with the commands that finish it.

## Add a framework integration to the lab
1. Write the scenario in `scenarios/<framework>.py` the way the framework's docs and Langfuse's integration guide show
   it. Import only the SDKs. Point clients at `BASE` and give prompts a `[run:k]` marker.
2. Register it in `scenarios/run.py` and declare what it must produce in `config/scenarios.json` (runs, tools, wrapped,
   isolated).
3. If the local server lacks an API the framework calls, add it to `gtc/harness/model_server.py` with the provider's
   real usage semantics, and record truth in exclusive buckets.
4. Add environments to `config/matrix.json`: the newest pins, and one or two older sets your users still run.
5. `python -m gtc.cli repro <scenario>`, then `python -m gtc.eval.cli dev`.

## A framework shipped a release and a check fails
1. `python -m gtc.cli repro <scenario> --pins <package>==<version>` to see it.
2. Add a bisection to `config/bisections.json` and `python -m gtc.cli bisect <name>` for the first bad release.
3. Write the report under `docs/upstream/` and add the failure to `config/known_findings.json` so the nightly run
   names it instead of paging.

## Triage an issue
`python -m gtc.cli triage <number>` prints the labels, the symptom, the versions it mentions and the scenario and check
to run, with the check's current status. Edit and post.

## Add a usage dialect
A new attribute family goes in `config/dialects.json` with its meaning (does input include cache?). Add a mapping test
in `tests/test_receiver_mapping.py` with a real span from that instrumentation.

## Run the held-out evaluation (once)
`python -m gtc.eval.cli heldout`, then `python scripts/screenshots.py`; commit `reports/`, `heldout.lock`, the README
and the screenshots together.
