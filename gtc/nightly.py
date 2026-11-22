"""python -m gtc.nightly: the lab as it runs every night.

Builds one environment per framework family from the newest releases on the package index (nothing pinned), runs
the family's scenarios, and compares the failing checks with the known findings. A new failure is the signal; a known
one is listed with its upstream reference. Writes reports/nightly/<date>.json.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any

from gtc.bisect import versions
from gtc.cell import ROOT
from gtc.matrix import load, run_matrix

FAMILY_PACKAGES = {
    "openai": ["langfuse", "openai"],
    "langchain": ["langfuse", "langchain-core", "langchain-openai", "langchain-anthropic", "anthropic", "openai", "opentelemetry-instrumentation-anthropic"],
    "pydantic_ai": ["langfuse", "pydantic-ai-slim[openai,anthropic]", "anthropic"],
    "agents_sdk": ["langfuse", "openai-agents", "openinference-instrumentation-openai-agents"],
}


def latest_environments() -> list[dict[str, Any]]:
    scen = {k: v for k, v in load("scenarios").items() if not k.startswith("_")}
    out = []
    for fam, pkgs in FAMILY_PACKAGES.items():
        pins = {p: versions(p)[-1] for p in pkgs}
        out.append({"name": f"{fam} · newest", "family": fam, "pins": pins, "scenarios": [k for k, v in scen.items() if v["family"] == fam]})
    return out


def main() -> int:
    known = {(k["scenario"], k["check"]) for k in load("known_findings")["findings"]}
    doc = run_matrix(environments=latest_environments())
    new: list[dict[str, Any]] = []
    still: list[dict[str, Any]] = []
    for c in doc["cells"]:
        if c.get("exit_code") != 0:
            new.append({"env": c["env"], "scenario": c["scenario"], "check": "runs", "detail": (c.get("error") or "")[-300:]})
            continue
        for r in c["results"]:
            if r["status"] == "fail":
                row = {"env": c["env"], "scenario": c["scenario"], "check": r["check"], "detail": r["detail"]}
                (still if (c["scenario"], r["check"]) in known else new).append(row)
    out = ROOT / "reports" / "nightly"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{dt.date.today().isoformat()}.json").write_text(json.dumps({"environments": doc["environments"], "new": new, "known": still}, indent=1) + "\n")
    for row in still:
        print(f"known  {row['scenario']} {row['check']}: {row['detail']}")
    for row in new:
        print(f"NEW    {row['scenario']} {row['check']}: {row['detail']}")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
