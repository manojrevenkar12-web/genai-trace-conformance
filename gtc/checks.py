"""Conformance checks: what a developer would see in their trace backend, compared with what really happened.

The truth comes from the local model server's ledger; the observations come from the wire through the mapping. A
check never reads the scenario's code, only its declared expectations in config/scenarios.json.
"""

from __future__ import annotations

import functools
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from gtc.harness.truth import Usage
from gtc.mapping import Observation, map_span, unreadable

PASS, FAIL, WARN, NA = "pass", "fail", "warn", "n/a"
SLACK_NS = 20_000_000  # 20 ms of clock and scheduling slack between the client's span and the server's request
CHECKS = (
    "one_generation_per_call",
    "model_name",
    "usage_exact",
    "cost_exact",
    "readable_io",
    "one_trace_per_run",
    "nested_under_run",
    "tools_traced",
    "run_isolation",
    "standard_attribute_names",
)
TITLES = {
    "one_generation_per_call": "One generation per model call",
    "model_name": "Model name matches the call",
    "usage_exact": "Token usage matches, cache included once",
    "cost_exact": "Cost matches what the provider charged",
    "readable_io": "Input and output are readable text",
    "one_trace_per_run": "One trace per run, no broken parents",
    "nested_under_run": "Generations sit under their run",
    "tools_traced": "Every executed tool is traced",
    "run_isolation": "Concurrent runs stay in their own traces",
    "standard_attribute_names": "Usage attributes use standard GenAI names",
}


@dataclass(frozen=True)
class Result:
    check: str
    status: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"check": self.check, "status": self.status, "detail": self.detail}


def _usage(d: dict[str, Any]) -> Usage:
    return Usage(**d)


def assign(calls: list[dict[str, Any]], gens: list[Observation]) -> tuple[dict[int, list[Observation]], list[Observation]]:
    """Matches generations to the model calls whose request they enclose in time.

    First one generation per call, closest pairs first, so two calls a few milliseconds apart cannot swap; only then
    are leftover generations attached to their nearest call as duplicates. A run marker in the prompt, when present,
    restricts the candidates.
    """

    def candidates(g: Observation) -> list[dict[str, Any]]:
        fits = [c for c in calls if g.start_ns <= c["received_ns"] + SLACK_NS and g.end_ns + SLACK_NS >= c["finished_ns"]]
        text = (g.input_text or "") + (g.output_text or "")
        marked = [c for c in fits if c["marker"] and f"[run:{c['marker']}]" in text]
        return marked if len({c["marker"] for c in marked}) == 1 else fits

    def gap(g: Observation, c: dict[str, Any]) -> tuple[int, int]:
        # first: how far the call falls outside the generation (0 when the generation encloses it); then: edge distance
        outside = max(0, g.start_ns - c["received_ns"]) + max(0, c["finished_ns"] - g.end_ns)
        return int(outside), int(abs(c["received_ns"] - g.start_ns) + abs(g.end_ns - c["finished_ns"]))

    cands = {id(g): candidates(g) for g in gens}
    by_call: dict[int, list[Observation]] = defaultdict(list)
    used_g: set[int] = set()
    for seq, gi in _optimal(calls, gens, cands, gap):
        by_call[seq].append(gens[gi])
        used_g.add(gi)
    phantom: list[Observation] = []
    for gi, g in enumerate(gens):
        if gi in used_g:
            continue
        if not cands[id(g)]:
            phantom.append(g)
            continue
        best = min(cands[id(g)], key=lambda c: gap(g, c))
        by_call[best["seq"]].append(g)
    for seq in by_call:
        by_call[seq].sort(key=lambda o: o.start_ns)
    return by_call, phantom


def _optimal(calls: list[dict[str, Any]], gens: list[Observation], cands: dict[int, list[dict[str, Any]]], gap: Any) -> list[tuple[int, int]]:
    """One generation per call, minimising the total cost over the whole run (exact for small runs, greedy beyond).

    Greedy closest-pair matching can take a pair that forces a much worse one later; with at most a few dozen
    generations per scenario the exact assignment is cheap."""
    order = sorted(calls, key=lambda c: c["received_ns"])
    allowed = {c["seq"]: [gi for gi, g in enumerate(gens) if any(x["seq"] == c["seq"] for x in cands[id(g)])] for c in order}
    if len(gens) > 16:
        pairs = sorted(((gap(gens[gi], c), gi, c["seq"]) for c in order for gi in allowed[c["seq"]]), key=lambda p: (p[0], p[1], p[2]))
        out: list[tuple[int, int]] = []
        ug: set[int] = set()
        uc: set[int] = set()
        for _, gi, seq in pairs:
            if gi not in ug and seq not in uc:
                out.append((seq, gi))
                ug.add(gi)
                uc.add(seq)
        return out

    cost = {(c["seq"], gi): gap(gens[gi], c) for c in order for gi in allowed[c["seq"]]}
    miss = (10**15, 10**15)  # a call left without a generation costs more than any real pairing

    @functools.cache
    def best(i: int, mask: int) -> tuple[tuple[int, int], tuple[tuple[int, int], ...]]:
        if i == len(order):
            return (0, 0), ()
        seq = order[i]["seq"]
        sub, rest = best(i + 1, mask)
        top = ((sub[0] + miss[0], sub[1] + miss[1]), rest)
        for gi in allowed[seq]:
            if mask & (1 << gi):
                continue
            sub, rest = best(i + 1, mask | (1 << gi))
            c = cost[(seq, gi)]
            cand = ((sub[0] + c[0], sub[1] + c[1]), ((seq, gi), *rest))
            if cand[0] < top[0]:
                top = cand
        return top

    return list(best(0, 0)[1])


def _describe(seen: Usage, truth: Usage) -> str:
    parts = []
    for b in ("input", "cache_read", "cache_write", "output"):
        sv, tv = getattr(seen, b), getattr(truth, b)
        if sv != tv:
            parts.append(f"{b} {sv} vs {tv}")
    hint = ""
    if seen.input_side > truth.input_side and (seen.input_side - truth.input_side) in (truth.cache_read, truth.cache_write, truth.cache_read + truth.cache_write):
        hint = " (cached tokens counted twice)"
    elif seen.input_side == truth.input_side and seen.input > truth.input:
        hint = " (cached tokens billed as uncached input)"
    elif seen.input_side < truth.input_side:
        hint = " (cached tokens dropped)"
    return ", ".join(parts) + hint


def run_checks(spec: dict[str, Any], calls: list[dict[str, Any]], spans: list[dict[str, Any]]) -> tuple[list[Result], list[Observation]]:
    obs = [map_span(s) for s in spans]
    gens = sorted((o for o in obs if o.type == "generation"), key=lambda o: o.start_ns)
    by_call, phantom = assign(calls, gens)
    out: list[Result] = []

    # 1. exactly one generation per model call
    dup = {seq: g for seq, g in by_call.items() if len(g) > 1}
    missing = [c["seq"] for c in calls if c["seq"] not in by_call]
    if not calls:
        out.append(Result("one_generation_per_call", FAIL, "the scenario made no model calls"))
    elif dup or missing or phantom:
        bits = []
        if dup:
            scopes = Counter(o.scope for g in dup.values() for o in g)
            bits.append(f"{sum(len(g) for g in dup.values())} generations for {len(dup)} calls, from {', '.join(f'{s} ({n})' for s, n in scopes.items())}")
        if missing:
            bits.append(f"{len(missing)} of {len(calls)} calls have no generation")
        if phantom:
            bits.append(f"{len(phantom)} generations match no call")
        out.append(Result("one_generation_per_call", FAIL, "; ".join(bits)))
    else:
        out.append(Result("one_generation_per_call", PASS, f"{len(calls)} calls, {len(gens)} generations"))

    # 2. model name
    wrong = [(g.model, c["model"]) for c in calls for g in by_call.get(c["seq"], []) if g.model != c["model"]]
    out.append(
        Result(
            "model_name",
            FAIL if wrong else (PASS if gens else NA),
            f"{len(wrong)} wrong, e.g. {wrong[0][0]!r} for {wrong[0][1]!r}" if wrong else "all generations name the model that answered",
        )
    )

    # 3. usage, per call, from the first generation the integration wrote
    bad: list[str] = []
    no_usage = 0
    for c in calls:
        for g in by_call.get(c["seq"], [])[:1]:
            if g.usage is None:
                no_usage += 1
            elif g.usage != _usage(c["usage"]):
                bad.append(f"call {c['seq']}: {_describe(g.usage, _usage(c['usage']))}")
    if bad or no_usage:
        out.append(Result("usage_exact", FAIL, "; ".join(bad[:3] + ([f"{no_usage} generations carry no usage"] if no_usage else []))))
    else:
        out.append(Result("usage_exact", PASS if by_call else NA, "input, cache reads, cache writes and output match every call"))

    # 4. cost as the trace backend would total it: every generation counts
    truth_cost = sum(c["cost"] for c in calls)
    seen_cost = sum(g.cost or 0.0 for g in gens)
    if truth_cost == 0:
        out.append(Result("cost_exact", NA, "no cost"))
    else:
        err = (seen_cost - truth_cost) / truth_cost
        out.append(Result("cost_exact", PASS if abs(err) <= 0.005 else FAIL, f"traced ${seen_cost:.6f} vs charged ${truth_cost:.6f} ({err:+.0%})"))

    # 5. readable input and output on the generations that represent each call
    unread = [g for c in calls for g in by_call.get(c["seq"], [])[:1] if unreadable(g.input_text) or unreadable(g.output_text)]
    objobj = [g for g in obs if (g.input_text and "[object Object]" in g.input_text) or (g.output_text and "[object Object]" in g.output_text)]
    if unread or objobj:
        ex = (objobj or unread)[0]
        out.append(Result("readable_io", FAIL, f"{len(unread) + len(objobj)} observations without readable input or output, e.g. {ex.scope} '{ex.name}'"))
    else:
        out.append(Result("readable_io", PASS if gens else NA, "every generation shows its prompt and answer"))

    # 6. one trace per run and no broken parent links
    ids = {(o.trace_id, o.span_id) for o in obs}
    orphans = [o for o in obs if o.parent_span_id and (o.trace_id, o.parent_span_id) not in ids]
    traces_with_calls = {g.trace_id for g in gens}
    ok = len(traces_with_calls) == spec["runs"] and not orphans
    out.append(
        Result(
            "one_trace_per_run",
            PASS if ok else FAIL,
            f"{len(traces_with_calls)} traces for {spec['runs']} runs" + (f", {len(orphans)} spans point to a parent that never arrived" if orphans else ""),
        )
    )

    # 7. generations under their run
    if spec["wrapped"]:
        parent = {(o.trace_id, o.span_id): o for o in obs}
        loose = [g for g in gens if g.parent_span_id is None or (g.trace_id, g.parent_span_id) not in parent]
        out.append(
            Result("nested_under_run", FAIL if loose else PASS, f"{len(loose)} generations are trace roots or detached" if loose else "every generation has its run as an ancestor")
        )
    else:
        out.append(Result("nested_under_run", NA, "scenario has no wrapping run"))

    # 8. tools
    executed = sum(len(c["tool_calls"]) for c in calls)
    tools = [o for o in obs if o.type == "tool"]
    if spec["tools"] == 0:
        out.append(Result("tools_traced", NA, "no tools"))
    else:
        out.append(Result("tools_traced", PASS if len(tools) == executed else FAIL, f"{len(tools)} tool observations for {executed} tool calls"))

    # 9. isolation of concurrent runs
    if spec["isolated"]:
        markers_by_trace: dict[str, set[str]] = defaultdict(set)
        for c in calls:
            for g in by_call.get(c["seq"], []):
                markers_by_trace[g.trace_id].add(c["marker"])
        mixed = [t for t, m in markers_by_trace.items() if len(m) > 1]
        distinct = len({m for ms in markers_by_trace.values() for m in ms})
        ok = not mixed and len(markers_by_trace) == spec["runs"] and distinct == spec["runs"]
        out.append(Result("run_isolation", PASS if ok else FAIL, f"{len(markers_by_trace)} traces for {spec['runs']} runs, {len(mixed)} traces mix runs"))
    else:
        out.append(Result("run_isolation", NA, "single run"))

    # 10. attribute names
    nonstd = sorted({n for o in obs for n in o.nonstandard})
    unknown = sorted({n for o in obs for n in o.unknown_usage_attrs})
    if nonstd or unknown:
        out.append(Result("standard_attribute_names", WARN, "non-standard: " + ", ".join(nonstd + unknown)))
    else:
        out.append(Result("standard_attribute_names", PASS, "only standard usage attributes"))
    return out, obs
