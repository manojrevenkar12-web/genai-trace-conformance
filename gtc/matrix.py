"""The version matrix: one isolated environment per pinned set of SDK versions, every scenario of the family run in
it against a fresh harness, every check recorded."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from typing import Any

from gtc.cell import ROOT, run_cell
from gtc.checks import run_checks
from gtc.harness.server import running

ENVS = ROOT / ".matrix"


def load(name: str) -> Any:
    return json.loads((ROOT / "config" / f"{name}.json").read_text())


def env_id(pins: dict[str, str]) -> str:
    return hashlib.sha1(json.dumps(pins, sort_keys=True).encode()).hexdigest()[:10]


def ensure_env(pins: dict[str, str]) -> tuple[str | None, str]:
    """Creates (or reuses) a venv with exactly these pins. Returns the interpreter, or None and the resolver's error."""
    d = ENVS / env_id(pins)
    py = d / "bin" / "python"
    if (d / ".ok").exists():
        return str(py), ""
    subprocess.run(["uv", "venv", "-q", "-p", f"{sys.version_info.major}.{sys.version_info.minor}", str(d)], check=True)
    reqs = [f"{k}=={v}" for k, v in sorted(pins.items())]
    p = subprocess.run(["uv", "pip", "install", "-q", "--python", str(py), *reqs], capture_output=True, text=True)
    if p.returncode != 0:
        return None, (p.stderr or p.stdout)[-600:]
    (d / ".ok").write_text(json.dumps(pins))
    return str(py), ""


def run_matrix(only_env: str | None = None, environments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    envs = environments if environments is not None else load("matrix")["environments"]
    specs = {k: v for k, v in load("scenarios").items() if not k.startswith("_")}
    cells: list[dict[str, Any]] = []
    with running() as h:
        for env in envs:
            if only_env and env["name"] != only_env:
                continue
            py, err = ensure_env(env["pins"])
            for scen in env["scenarios"]:
                spec = specs[scen]
                if py is None:
                    cells.append({"env": env["name"], "scenario": scen, "error": "dependencies do not resolve: " + err, "results": []})
                    continue
                r = run_cell(h, scen, python=py)
                results, obs = run_checks(spec, r.calls, r.spans) if r.exit_code == 0 else ([], [])
                cells.append(
                    {
                        "env": env["name"],
                        "scenario": scen,
                        "exit_code": r.exit_code,
                        "seconds": r.seconds,
                        "error": None if r.exit_code == 0 else r.stderr_tail[-800:],
                        "calls": len(r.calls),
                        "spans": len(r.spans),
                        "results": [x.as_dict() for x in results],
                        "observations": [o.as_dict() for o in obs],
                        "truth": r.calls,
                        "raw_spans": r.spans,
                    }
                )
    return {"environments": envs, "cells": cells}
