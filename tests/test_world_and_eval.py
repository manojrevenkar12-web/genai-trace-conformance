import ast
import json
import math
from pathlib import Path

import pytest

from gtc.errors import error_line
from gtc.eval import cli
from gtc.world import Keyed, bugs, exposure, load_world, play

DESIGNS = {k: v for k, v in json.loads(Path("config/designs.json").read_text()).items() if not k.startswith("_")}
RECALL = {k: 1.0 for k in load_world()["fault_mix"]}


def test_same_bugs_for_every_design():
    w = load_world()
    a, b = bugs(w, Keyed(5)), bugs(w, Keyed(5))
    assert a == b and len(a) > 0
    runs = {n: play(w, d, 5, RECALL, 0.8, 0.0) for n, d in DESIGNS.items()}
    keys = {n: [(x["integration"], x["kind"], x["release_day"]) for x in r["per_bug"]] for n, r in runs.items()}
    assert len({json.dumps(v) for v in keys.values()}) == 1


def test_exposure_math():
    assert exposure(100, 10, 5, 100, 14) == 0.0
    a = 30.0
    expected = 100 * (a - 14 * (1 - math.exp(-a / 14)))
    assert exposure(100, 0, None, a, 14) == pytest.approx(expected)
    assert exposure(100, 0, 10, 100, 14) < exposure(100, 0, None, 100, 14)


def test_lab_never_worse_than_status_quo_on_exposure():
    w = load_world()
    for s in range(1, 6):
        sq = play(w, DESIGNS["status_quo"], s, RECALL, 0.8, 0.0)["exposure_project_days"]
        lab = play(w, DESIGNS["lab"], s, RECALL, 0.8, 0.0)["exposure_project_days"]
        assert lab <= sq + 1e-6


def test_the_world_does_not_import_the_lab():
    tree = ast.parse(Path("gtc/world.py").read_text())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not {m for m in mods if m.startswith("gtc")}
    assert "designs.json" not in Path("gtc/world.py").read_text()


def test_scenarios_import_only_sdks():
    for p in Path("scenarios").glob("*.py"):
        tree = ast.parse(p.read_text())
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not {m for m in mods if m.startswith("gtc")}, p


def test_error_line_finds_the_exception():
    tb = "Traceback\n  File x\npydantic_core._pydantic_core.ValidationError: 1 validation error for InputTokensDetails\ncache_write_tokens\n  Field required\n    For further information visit https://errors.pydantic.dev"
    assert error_line(tb).startswith("pydantic_core._pydantic_core.ValidationError")


def test_heldout_runs_once(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "LOCK", tmp_path / "heldout.lock")
    monkeypatch.setattr(cli, "REPORTS", tmp_path)
    monkeypatch.setattr(cli, "collect", lambda s, r: None)
    dev = json.loads(Path("reports/dev.json").read_text())
    monkeypatch.setattr(cli, "analyse", lambda s, r: {**dev, "set": s})
    monkeypatch.setattr(cli, "main", cli.main)
    monkeypatch.setattr("gtc.eval.cli.write_readme", lambda *a: None)
    (tmp_path / "dev.json").write_text(json.dumps(json.loads(Path("reports/dev.json").read_text())))
    assert cli.main(["heldout"]) == 0
    assert cli.main(["heldout"]) == 2
