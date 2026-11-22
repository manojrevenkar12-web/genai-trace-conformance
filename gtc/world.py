"""The simulated framework ecosystem: releases, the tracing bugs some of them ship, the projects that upgrade into
them, and when somebody notices. Every design plays the same releases with the same luck; only what the design can
see differs. Detection ability enters as numbers measured elsewhere (check recall from the fault study, triage
recall from real issues); the world does not import the lab.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_world() -> dict[str, Any]:
    out: dict[str, Any] = json.loads((ROOT / "config" / "world.json").read_text())
    return out


class Keyed:
    """Random draws keyed by what they are about, so every design sees the same draw for the same event."""

    def __init__(self, seed: int) -> None:
        self.seed = seed

    def rng(self, *key: object) -> random.Random:
        h = hashlib.blake2b(repr((self.seed, *key)).encode(), digest_size=8).digest()
        return random.Random(int.from_bytes(h, "big"))

    def u(self, *key: object) -> float:
        return self.rng(*key).random()


@dataclass(frozen=True)
class Bug:
    integration: str
    release_day: float
    kind: str
    users: int
    visible_on_main_days: float | None  # days before release the change was on main, if it was


@dataclass
class Outcome:
    bug: Bug
    detected_by: str  # lab | users | nobody
    detect_day: float | None
    fix_day: float | None
    exposure_project_days: float
    maintainer_hours: float
    issues_filed: int


def bugs(world: dict[str, Any], k: Keyed) -> list[Bug]:
    out: list[Bug] = []
    days = world["weeks"] * 7
    kinds, weights = zip(*world["fault_mix"].items(), strict=True)
    for name, it in world["integrations"].items():
        r = k.rng("releases", name)
        t = 0.0
        i = 0
        while True:
            t += r.expovariate(it["releases_per_week"] / 7)
            if t >= days:
                break
            i += 1
            if k.u("breaks", name, i) < world["break_probability"]:
                kind = k.rng("kind", name, i).choices(kinds, weights)[0]
                on_main = k.u("main", name, i) < it["on_main_first"]
                out.append(Bug(name, t, kind, it["users"], it["lead_days"] if on_main else None))
    return out


def exposure(users: int, release: float, fix: float | None, horizon: float, tau: float) -> float:
    """Project-days on the broken release: upgrades start at the release and reverse once the fix ships."""
    if fix is not None and fix <= release:
        return 0.0
    end = horizon if fix is None else min(fix, horizon)
    a = end - release
    on_broken = a - tau * (1 - math.exp(-a / tau))  # integral of 1 - exp(-t/tau) from 0 to a
    tail = 0.0
    if fix is not None and fix < horizon:
        f_at_fix = 1 - math.exp(-a / tau)
        b = horizon - fix
        tail = f_at_fix * tau * (1 - math.exp(-b / tau))
    return users * (on_broken + tail)


def first_report(users: int, release: float, horizon: float, tau: float, rate: float, e: float) -> float | None:
    """When cumulative affected project-days times the report rate first reaches the drawn Exp(1) value e."""
    lo, hi = release, horizon
    if exposure(users, release, None, horizon, tau) * rate < e:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if exposure(users, release, None, mid, tau) * rate >= e:
            hi = mid
        else:
            lo = mid
    return hi


def play(world: dict[str, Any], design: dict[str, Any], seed: int, recall: dict[str, float], triage_recall: float, false_alarms_per_run: float) -> dict[str, Any]:
    k = Keyed(seed)
    horizon = world["weeks"] * 7
    tau = world["upgrade_days"]
    H = world["hours"]
    outcomes: list[Outcome] = []
    for i, b in enumerate(bugs(world, k)):
        covered = world["integrations"][b.integration]["covered"]
        caught = design["nightly"] and covered and k.u("lab-catches", b.integration, i) < recall.get(b.kind, 0.0)
        report = first_report(b.users, b.release_day, horizon, tau, world["report_per_affected_project_day"], k.rng("report", b.integration, i).expovariate(1.0))
        if caught:
            det = b.release_day - b.visible_on_main_days if design["main_branch"] and b.visible_on_main_days else b.release_day + 1.0
            hours = H["review_lab_finding"] + (0.0 if design["bisect"] else H["bisect_manual"]) + H["fix"]
            fix = det + world["fix_days"]
            if report is not None and report < det:  # a user still got there first
                caught = False
        if not caught:
            if report is None:
                outcomes.append(Outcome(b, "nobody", None, None, exposure(b.users, b.release_day, None, horizon, tau), 0.0, 0))
                continue
            agent_right = design["agent"] and k.u("agent-right", b.integration, i) < triage_recall
            triage = 0.5 if agent_right else world["triage_days_manual"]
            repro = 0.5 if (agent_right and covered) else H["repro_manual"]
            det = report
            fix = report + triage + world["fix_days"]
            hours = H["triage"] * (0.5 if agent_right else 1.0) + repro + H["bisect_manual"] + H["fix"]
        e = exposure(b.users, b.release_day, fix, horizon, tau)
        filed = 0 if fix <= b.release_day else 1 + int(e * world["report_per_affected_project_day"])
        outcomes.append(Outcome(b, "lab" if caught else "users", det, fix, e, hours, filed))
    weeks = world["weeks"]
    lab_hours = (H["lab_upkeep_per_week"] * weeks + false_alarms_per_run * 7 * weeks * H["false_alarm"]) if design["nightly"] else 0.0
    cost_kinds = set(world["cost_faults"])
    return {
        "bugs": len(outcomes),
        "reached_users": sum(1 for o in outcomes if o.exposure_project_days > 0),
        "caught_before_release": sum(1 for o in outcomes if o.detected_by == "lab" and o.fix_day is not None and o.fix_day <= o.bug.release_day),
        "caught_by_lab": sum(1 for o in outcomes if o.detected_by == "lab"),
        "never_noticed": sum(1 for o in outcomes if o.detected_by == "nobody"),
        "exposure_project_days": sum(o.exposure_project_days for o in outcomes),
        "wrong_cost_project_days": sum(o.exposure_project_days for o in outcomes if o.bug.kind in cost_kinds),
        "days_release_to_fix": [o.fix_day - o.bug.release_day for o in outcomes if o.fix_day is not None],
        "issues_filed": sum(o.issues_filed for o in outcomes),
        "maintainer_hours": sum(o.maintainer_hours for o in outcomes) + lab_hours,
        "per_bug": [
            {
                "integration": o.bug.integration,
                "kind": o.bug.kind,
                "release_day": round(o.bug.release_day, 1),
                "detected_by": o.detected_by,
                "fix_day": None if o.fix_day is None else round(o.fix_day, 1),
                "exposure": round(o.exposure_project_days),
            }
            for o in outcomes
        ],
    }
