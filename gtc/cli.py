"""python -m gtc.cli repro <scenario> [--pins pkg==version ...] | triage <issue number> | bisect <name>

repro   run one scenario with the family's latest pins, optionally overriding some, and print every check
triage  triage one issue from data/issues.jsonl and print the reply a maintainer can edit
bisect  run one bisection from config/bisections.json
"""

from __future__ import annotations

import json
import sys
from typing import Any

from gtc.bisect import bisect
from gtc.cell import ROOT, run_cell
from gtc.checks import run_checks
from gtc.harness.server import running
from gtc.matrix import ensure_env, load
from gtc.triage import comment, triage


def _latest_pins(family: str) -> dict[str, str]:
    env = next(e for e in load("matrix")["environments"] if e["family"] == family and e["name"].endswith("latest"))
    pins: dict[str, str] = env["pins"]
    return dict(pins)


def repro(scenario: str, overrides: list[str]) -> int:
    spec = load("scenarios")[scenario]
    pins = _latest_pins(spec["family"])
    for o in overrides:
        k, v = o.split("==", 1)
        pins[k] = v
    py, err = ensure_env(pins)
    if py is None:
        print(f"these pins do not resolve: {err}", file=sys.stderr)
        return 2
    with running() as h:
        r = run_cell(h, scenario, python=py)
    print("pins: " + ", ".join(f"{k}=={v}" for k, v in sorted(pins.items())))
    if r.exit_code != 0:
        print("crashed:\n" + r.stderr_tail)
        return 1
    results, _ = run_checks(spec, r.calls, r.spans)
    for x in results:
        print(f"{x.check:26} {x.status:5} {x.detail}")
    return 1 if any(x.status == "fail" for x in results) else 0


def _status() -> dict[tuple[str, str], str]:
    p = ROOT / "reports" / "dev.json"
    if not p.exists():
        return {}
    doc = json.loads(p.read_text())
    fam = {e["name"]: e["family"] for e in doc["environments"]}
    out: dict[tuple[str, str], str] = {}
    for c in doc["cells"]:
        if not c["env"].endswith("latest"):
            continue
        for r in c["results"]:
            k = (fam[c["env"]], r["check"])
            if out.get(k) != "fail":
                out[k] = r["status"]
    return out


def triage_issue(number: int) -> int:
    rows: list[dict[str, Any]] = [json.loads(line) for line in (ROOT / "data" / "issues.jsonl").read_text().splitlines() if line.strip()]
    issue = next((x for x in rows if x["number"] == number), None)
    if issue is None:
        print(f"issue #{number} is not in data/issues.jsonl", file=sys.stderr)
        return 2
    t = triage(issue)
    print(f"#{number} {issue['title']}\n")
    print(comment(t, _status()))
    print(f"\nmaintainers' labels: {', '.join(x for x in issue['labels'] if x.startswith('integration')) or 'none'}")
    return 0


def run_bisect(name: str) -> int:
    b = next(x for x in load("bisections")["bisections"] if x["name"] == name)
    with running() as h:
        r = bisect(h, b["pins"], b["package"], b["good"], b["bad"], b["scenario"], b["check"])
    for t in r.tested:
        print(f"{b['package']} {t['version']:10} {'good' if t['good'] else 'bad' if t['good'] is False else 'n/a'}  {t['detail']}")
    print(f"last good {r.last_good}, first bad {r.first_bad}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "repro":
        pins = argv[argv.index("--pins") + 1 :] if "--pins" in argv else []
        return repro(argv[1], pins)
    if len(argv) == 2 and argv[0] == "triage":
        return triage_issue(int(argv[1].lstrip("#")))
    if len(argv) >= 2 and argv[0] == "bisect":
        return run_bisect(" ".join(argv[1:]))
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
