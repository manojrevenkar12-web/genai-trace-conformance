"""python -m gtc.eval.cli dev | heldout | analyse <set> | readme | gate | check

dev        run the SDK matrix and bisections, then analyse
heldout    the same on the held-out environments and seeds; runs once (heldout.lock)
analyse    recompute a report from stored captures
check      CI: the committed reports are what the code computes from the stored captures, and no config changed after
           the held-out run
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from gtc.eval.report import block, report_md, write_readme
from gtc.eval.run import analyse, collect, config_sha

REPORTS = Path(os.environ.get("GTC_REPORTS", "reports"))
LOCK = Path(os.environ.get("GTC_LOCK", "heldout.lock"))


def _read(name: str) -> dict[str, Any] | None:
    p = REPORTS / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _write(doc: dict[str, Any]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{doc['set']}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "dev"
    if cmd == "dev":
        collect("dev", REPORTS)
        _write(analyse("dev", REPORTS))
        return main(["readme"])
    if cmd == "heldout":
        if LOCK.exists():
            print(f"refused: the held-out run already happened ({LOCK.read_text().strip()}). It runs once.", file=sys.stderr)
            return 2
        collect("heldout", REPORTS)
        doc = analyse("heldout", REPORTS)
        _write(doc)
        LOCK.write_text(json.dumps({"config_sha": doc["config_sha"], "collected_on": doc["collected_on"]}) + "\n")
        return main(["readme"])
    if cmd == "analyse":
        _write(analyse(argv[1], REPORTS))
        return main(["readme"])
    if cmd == "readme":
        dev, held = _read("dev"), _read("heldout")
        if dev is None:
            print("no reports/dev.json yet; run `dev`", file=sys.stderr)
            return 1
        write_readme(Path("README.md"), block(dev, held))
        (REPORTS / "REPORT.md").write_text(report_md(dev, held))
        return 0
    if cmd == "gate":
        failed = False
        for name in ("dev", "heldout"):
            found = _read(name)
            for g in (found or {}).get("gates", []):
                print(f"{name:8} {'pass' if g['pass'] else 'FAIL'}  {g['gate']}: {g['measured']}")
                failed |= not g["pass"]
        return 1 if failed else 0
    if cmd == "check":
        for name in ("dev", "heldout"):
            committed = _read(name)
            if committed is None:
                continue
            again = json.loads(json.dumps(analyse(name, REPORTS)))
            if again != committed:
                diff = [k for k in committed if committed.get(k) != again.get(k)]
                print(f"reports/{name}.json differs from what the code computes from the stored captures: {diff}", file=sys.stderr)
                return 1
        if LOCK.exists():
            locked = json.loads(LOCK.read_text())["config_sha"]
            if locked != config_sha():
                print(f"config changed after the held-out run (locked {locked}, now {config_sha()})", file=sys.stderr)
                return 1
        print("reports match the stored captures; held-out lock holds")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
