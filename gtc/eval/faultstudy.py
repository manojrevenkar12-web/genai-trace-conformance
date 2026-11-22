"""How well the checks catch each kind of real integration bug, and whether harmless changes raise alarms.

Faults are planted into clean traces captured from real SDK runs; a fault counts as caught when a check that passed
on the clean trace now fails (or, for attribute names, warns). Attribution is right when one of the checks the fault
is meant to trip is among those that flagged it.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from gtc.checks import FAIL, WARN, run_checks
from gtc.faults import BENIGN, FAULTS


def _flags(spec: dict[str, Any], calls: list[dict[str, Any]], spans: list[dict[str, Any]]) -> dict[str, str]:
    return {r.check: r.status for r in run_checks(spec, calls, spans)[0]}


def clean(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in cells if c.get("exit_code") == 0 and c["results"] and not any(r["status"] == FAIL for r in c["results"])]


def study(cells: list[dict[str, Any]], specs: dict[str, Any], seeds: list[int], plants_per_cell: int = 2) -> dict[str, Any]:
    base = clean(cells)
    caught: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # planted, caught, attributed
    false_alarm = [0, 0]
    examples: dict[str, str] = {}
    for seed in seeds:
        for ci, c in enumerate(base):
            spec = specs[c["scenario"]]
            before = _flags(spec, c["truth"], c["raw_spans"])
            for kind, (plant, expect) in FAULTS.items():
                for j in range(plants_per_cell):
                    r = random.Random(f"{seed}:{ci}:{kind}:{j}")
                    spans = plant(c["raw_spans"], r)
                    if spans is None:
                        continue
                    after = _flags(spec, c["truth"], spans)
                    new = {k for k, v in after.items() if v == FAIL and before[k] != FAIL} | {k for k, v in after.items() if v == WARN and before[k] not in (FAIL, WARN)}
                    caught[kind][0] += 1
                    caught[kind][1] += bool(new)
                    caught[kind][2] += bool(new & expect)
                    if new and kind not in examples:
                        examples[kind] = f"{c['scenario']} ({c['env']}): {', '.join(sorted(new))}"
            for bname, change in BENIGN.items():
                r = random.Random(f"{seed}:{ci}:{bname}")
                after = _flags(spec, c["truth"], change(c["raw_spans"], r))
                false_alarm[0] += 1
                false_alarm[1] += any(after[k] in (FAIL, WARN) and before[k] not in (FAIL, WARN) for k in after)
    kinds = {
        k: {"planted": v[0], "caught": v[1], "attributed": v[2], "recall": round(v[1] / v[0], 3) if v[0] else None, "example": examples.get(k)} for k, v in sorted(caught.items())
    }
    planted = sum(v[0] for v in caught.values())
    return {
        "clean_cells": len(base),
        "kinds": kinds,
        "overall_recall": round(sum(v[1] for v in caught.values()) / planted, 3) if planted else None,
        "attribution": round(sum(v[2] for v in caught.values()) / max(sum(v[1] for v in caught.values()), 1), 3),
        "benign_changes": false_alarm[0],
        "false_alarms": false_alarm[1],
        "false_alarm_rate": round(false_alarm[1] / false_alarm[0], 4) if false_alarm[0] else None,
    }
