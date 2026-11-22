"""The evaluation in two steps. collect() runs the real SDKs (the matrix, and on dev the bisections) and stores every
captured span; analyse() turns stored captures into the report: checks, fault study, triage scores and the release
simulation. analyse() is deterministic, so CI can recompute the report from the stored captures.
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import random
import re
import statistics
from pathlib import Path
from typing import Any

from gtc.bisect import bisect
from gtc.checks import CHECKS, FAIL, TITLES, WARN, run_checks
from gtc.eval.faultstudy import study
from gtc.faults import FAULTS
from gtc.harness.server import running
from gtc.cell import ROOT
from gtc.matrix import load, run_matrix
from gtc.triage import CFG as TRIAGE
from gtc.triage import score
from gtc.world import load_world, play

CONFIGS = ("world", "designs", "gates", "seeds", "scenarios", "matrix", "heldout", "triage", "dialects", "prices", "bisections")


def config_sha() -> str:
    h = hashlib.sha256()
    for n in CONFIGS:
        h.update((ROOT / "config" / f"{n}.json").read_bytes())
    return h.hexdigest()[:12]


def error_line(err: str | None) -> str | None:
    """The line of a traceback that names the exception, not pydantic's 'further information' footer."""
    if not err:
        return None
    lines = [ln.strip() for ln in err.strip().splitlines() if ln.strip()]
    named = [ln for ln in lines if re.match(r"^[\w.]*(Error|Exception|Warning)\b", ln)]
    return (named[-1] if named else lines[-1])[:200]


def raw_path(reports: Path, set_name: str) -> Path:
    return reports / "raw" / f"{set_name}.json.gz"


def collect(set_name: str, reports: Path) -> Path:
    envs = load("matrix")["environments"] if set_name == "dev" else load("heldout")["environments"]
    doc = run_matrix(environments=envs)
    doc["bisections"] = []
    if set_name == "dev":
        with running() as h:
            for b in load("bisections")["bisections"]:
                r = bisect(h, b["pins"], b["package"], b["good"], b["bad"], b["scenario"], b["check"])
                doc["bisections"].append({**b, "last_good": r.last_good, "first_bad": r.first_bad, "tested": r.tested})
    doc["collected_on"] = dt.date.today().isoformat()
    p = raw_path(reports, set_name)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt") as f:
        json.dump(doc, f)
    return p


def issues(set_name: str) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in (ROOT / "data" / "issues.jsonl").read_text().splitlines() if line.strip()]
    cut = TRIAGE["split_date"]
    return [x for x in rows if (x["created_at"] < cut) == (set_name == "dev")]


def _ci(xs: list[float], seed: int = 7, n: int = 2000) -> list[float]:
    r = random.Random(seed)
    means = sorted(statistics.fmean(r.choice(xs) for _ in xs) for _ in range(n))
    return [round(statistics.fmean(xs), 4), round(means[int(0.025 * n)], 4), round(means[int(0.975 * n) - 1], 4)]


def matrix_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    envs: dict[str, dict[str, Any]] = {}
    for c in cells:
        e = envs.setdefault(c["env"], {"scenarios": 0, "crashed": 0, "checks": {k: {"pass": 0, "fail": 0, "warn": 0, "n/a": 0} for k in CHECKS}, "failures": []})
        e["scenarios"] += 1
        if c.get("exit_code") != 0:
            e["crashed"] += 1
            e["failures"].append({"scenario": c["scenario"], "check": "runs", "detail": error_line(c.get("error")) or "did not run"})
            continue
        for r in c["results"]:
            e["checks"][r["check"]][r["status"]] += 1
            if r["status"] in (FAIL, WARN):
                e["failures"].append({"scenario": c["scenario"], "check": r["check"], "status": r["status"], "detail": r["detail"]})
    return envs


def analyse(set_name: str, reports: Path) -> dict[str, Any]:
    with gzip.open(raw_path(reports, set_name), "rt") as f:
        raw = json.load(f)
    seeds = load("seeds")[set_name]
    specs = {k: v for k, v in load("scenarios").items() if not k.startswith("_")}
    cells = raw["cells"]
    for c in cells:  # recompute from the captures, so a change to the checks shows up without rerunning SDKs
        if c.get("exit_code") == 0:
            res, _obs = run_checks(specs[c["scenario"]], c["truth"], c["raw_spans"])
            c["results"] = [x.as_dict() for x in res]
    ran = [c for c in cells if c.get("exit_code") == 0]
    faults = study(cells, specs, seeds["faults"])
    covered = [k for k, (_, expect) in FAULTS.items() if expect]
    covered_recall = sum(faults["kinds"][k]["caught"] for k in covered if k in faults["kinds"]) / max(
        sum(faults["kinds"][k]["planted"] for k in covered if k in faults["kinds"]), 1
    )
    iss = issues(set_name)
    triage = {"agent": score(iss), "naive": score(iss, threshold=1), "split_date": TRIAGE["split_date"]}

    world = load_world()
    designs = {k: v for k, v in load("designs").items() if not k.startswith("_")}
    recall = {k: (v["recall"] or 0.0) for k, v in faults["kinds"].items()}
    for k in world["fault_mix"]:
        recall.setdefault(k, 0.0)
    triage_recall = triage["agent"]["micro"]["recall"]
    alarms_per_run = (faults["false_alarm_rate"] or 0.0) * len(ran)
    per_seed: dict[str, list[dict[str, Any]]] = {n: [play(world, d, s, recall, triage_recall, alarms_per_run) for s in seeds["simulation"]] for n, d in designs.items()}
    sim: dict[str, Any] = {}
    base = per_seed["status_quo"]
    for n, runs in per_seed.items():
        cut = [1 - r["exposure_project_days"] / b["exposure_project_days"] if b["exposure_project_days"] else 0.0 for r, b in zip(runs, base, strict=True)]
        cost_cut = [1 - r["wrong_cost_project_days"] / b["wrong_cost_project_days"] if b["wrong_cost_project_days"] else 0.0 for r, b in zip(runs, base, strict=True)]
        fixes = [d for r in runs for d in r["days_release_to_fix"]]
        sim[n] = {
            "label": designs[n]["label"],
            "bugs_per_seed": round(statistics.fmean(r["bugs"] for r in runs), 2),
            "reached_users_share": _ci([r["reached_users"] / r["bugs"] if r["bugs"] else 0.0 for r in runs]),
            "caught_by_lab_share": _ci([r["caught_by_lab"] / r["bugs"] if r["bugs"] else 0.0 for r in runs]),
            "exposure_project_days": _ci([r["exposure_project_days"] for r in runs]),
            "exposure_cut_vs_status_quo": _ci(cut),
            "wrong_cost_cut_vs_status_quo": _ci(cost_cut),
            "median_days_release_to_fix": round(statistics.median(fixes), 2) if fixes else None,
            "issues_filed": _ci([r["issues_filed"] for r in runs]),
            "maintainer_hours_per_week": _ci([r["maintainer_hours"] / world["weeks"] for r in runs]),
        }
    gates = load("gates")
    lab = sim["lab"]
    verdict = [
        {
            "gate": f"recall on the bug kinds the checks cover at least {gates['coveredKindRecallMin']:.0%}",
            "measured": round(covered_recall, 3),
            "pass": covered_recall >= gates["coveredKindRecallMin"],
        },
        {
            "gate": f"false alarms on harmless changes at most {gates['falseAlarmRateMax']:.0%}",
            "measured": faults["false_alarm_rate"],
            "pass": (faults["false_alarm_rate"] or 0) <= gates["falseAlarmRateMax"],
        },
        {
            "gate": f"triage F1 against maintainers' labels at least {gates['triageF1Min']}",
            "measured": triage["agent"]["micro"]["f1"],
            "pass": triage["agent"]["micro"]["f1"] >= gates["triageF1Min"],
        },
        {
            "gate": f"lab cuts project-days on broken traces by at least {gates['labExposureCutLowMin']:.0%} (low end of the interval)",
            "measured": lab["exposure_cut_vs_status_quo"][1],
            "pass": lab["exposure_cut_vs_status_quo"][1] >= gates["labExposureCutLowMin"],
        },
        {
            "gate": f"lab maintainer hours at most {gates['labHoursMaxShareOfStatusQuo']:.0%} of today's",
            "measured": round(lab["maintainer_hours_per_week"][0] / sim["status_quo"]["maintainer_hours_per_week"][0], 3),
            "pass": lab["maintainer_hours_per_week"][0] <= gates["labHoursMaxShareOfStatusQuo"] * sim["status_quo"]["maintainer_hours_per_week"][0],
        },
    ]
    versions = sorted({f"{k}=={v}" for e in raw["environments"] for k, v in e["pins"].items()})
    return {
        "set": set_name,
        "config_sha": config_sha(),
        "collected_on": raw.get("collected_on"),
        "seeds": seeds,
        "facts": {
            "environments": len(raw["environments"]),
            "cells": len(cells),
            "cells_ran": len(ran),
            "cells_crashed": len(cells) - len(ran),
            "model_calls": sum(len(c["truth"]) for c in ran),
            "spans": sum(len(c["raw_spans"]) for c in ran),
            "pinned_versions": len(versions),
            "issues": len(iss),
        },
        "checks": [{"id": k, "title": TITLES[k]} for k in CHECKS],
        "environments": [{"name": e["name"], "family": e["family"], "pins": e["pins"]} for e in raw["environments"]],
        "matrix": matrix_summary(cells),
        "cells": [{"env": c["env"], "scenario": c["scenario"], "ran": c.get("exit_code") == 0, "error": error_line(c.get("error")), "results": c["results"]} for c in cells],
        "bisections": [{k: b[k] for k in ("name", "package", "scenario", "check", "last_good", "first_bad", "tested")} for b in raw.get("bisections", [])],
        "fault_study": {**faults, "covered_recall": round(covered_recall, 3)},
        "triage": triage,
        "simulation": sim,
        "gates": verdict,
    }
