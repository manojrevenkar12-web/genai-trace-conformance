import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


@pytest.fixture(scope="session")
def harness():
    from gtc.harness.server import running

    with running() as h:
        yield h
