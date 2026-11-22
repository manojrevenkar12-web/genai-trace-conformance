"""Reading a scenario's traceback."""

from __future__ import annotations

import re


def error_line(err: str | None) -> str | None:
    """The line of a traceback that names the exception, not pydantic's 'further information' footer."""
    if not err:
        return None
    lines = [ln.strip() for ln in err.strip().splitlines() if ln.strip()]
    named = [ln for ln in lines if re.match(r"^[\w.]*(Error|Exception|Warning)\b", ln)]
    return (named[-1] if named else lines[-1])[:200]
