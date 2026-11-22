"""Finds the first release of one package that breaks a scenario, holding every other pin fixed.

A cell is good when the scenario runs and the named check passes (or, with check=None, when it just runs). Versions
come from the package index in release order; the search tests about log2(n) of them.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

from gtc.cell import run_cell
from gtc.checks import FAIL, run_checks
from gtc.harness.server import Harness
from gtc.matrix import ensure_env, load


def versions(package: str) -> list[str]:
    """Release versions, oldest first, without pre-releases."""
    out = subprocess.run(["pip", "index", "versions", package.split("[")[0]], capture_output=True, text=True).stdout
    line = next((ln for ln in out.splitlines() if ln.startswith("Available versions:")), "")
    vs = [v.strip() for v in line.split(":", 1)[-1].split(",") if v.strip()]
    return [v for v in reversed(vs) if re.fullmatch(r"\d+(\.\d+)*", v)]


@dataclass
class Bisection:
    package: str
    scenario: str
    check: str | None
    last_good: str | None = None
    first_bad: str | None = None
    tested: list[dict[str, Any]] = field(default_factory=list)


def good(h: Harness, pins: dict[str, str], scenario: str, check: str | None) -> tuple[bool | None, str]:
    py, _err = ensure_env(pins)
    if py is None:
        return None, "does not resolve"
    r = run_cell(h, scenario, python=py)
    if r.exit_code != 0:
        from gtc.eval.run import error_line

        return False, "crashes: " + (error_line(r.stderr_tail) or "?")
    if check is None:
        return True, "runs"
    spec = load("scenarios")[scenario]
    res = {x.check: x for x in run_checks(spec, r.calls, r.spans)[0]}
    x = res[check]
    return x.status != FAIL, x.detail


def bisect(h: Harness, base: dict[str, str], package: str, lo: str, hi: str, scenario: str, check: str | None) -> Bisection:
    """[lo] must be good and [hi] bad. Versions that do not resolve with the other pins are skipped."""
    vs = versions(package)
    cand = vs[vs.index(lo) : vs.index(hi) + 1]
    b = Bisection(package, scenario, check)
    i, j = 0, len(cand) - 1
    while j - i > 1:
        m = (i + j) // 2
        ok, why = good(h, {**base, package: cand[m]}, scenario, check)
        b.tested.append({"version": cand[m], "good": ok, "detail": why})
        if ok is None:  # unresolvable: drop it and keep searching the same range
            cand.pop(m)
            j -= 1
            continue
        if ok:
            i = m
        else:
            j = m
    b.last_good, b.first_bad = cand[i], cand[j]
    return b
