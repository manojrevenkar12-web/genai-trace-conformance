"""Checks against hand-built traces, then the fault injectors against a trace captured from the real Langfuse SDK."""

import json
import random
from pathlib import Path

import pytest

from gtc.cell import run_cell
from gtc.checks import assign, run_checks
from gtc.faults import BENIGN, FAULTS
from gtc.mapping import map_span

SPECS = json.loads(Path("config/scenarios.json").read_text())


def call(seq, recv, fin, model="gpt-test-mini", marker="1", tools=()):
    from gtc.harness.truth import PRICES

    u = {"input": 10, "cache_read": 0, "cache_write": 0, "output": 5}
    p = PRICES[model]
    return {
        "seq": seq,
        "provider": "openai",
        "model": model,
        "stream": False,
        "usage": u,
        "marker": marker,
        "tool_calls": tools,
        "received_ns": recv,
        "finished_ns": fin,
        "cost": (10 * p["input"] + 5 * p["output"]) / 1e6,
    }


def gen(sid, start, end, parent="root", usage=None, text="[run:1]"):
    return {
        "trace_id": "t1",
        "span_id": sid,
        "parent_span_id": parent,
        "name": "g",
        "scope": "langfuse-sdk",
        "start_ns": start,
        "end_ns": end,
        "attributes": {
            "langfuse.observation.type": "generation",
            "langfuse.observation.model.name": "gpt-test-mini",
            "langfuse.observation.usage_details": json.dumps(usage or {"input": 10, "output": 5}),
            "langfuse.observation.input": f"hi {text}",
            "langfuse.observation.output": "answer",
        },
    }


ROOT = {
    "trace_id": "t1",
    "span_id": "root",
    "parent_span_id": None,
    "name": "run",
    "scope": "langfuse-sdk",
    "start_ns": 0,
    "end_ns": 10**9,
    "attributes": {"langfuse.observation.type": "span"},
}
SPEC = {"runs": 1, "tools": 0, "wrapped": True, "isolated": False}


def status(results):
    return {r.check: r.status for r in results}


def test_clean_trace_passes():
    calls = [call(0, 10_000_000, 20_000_000), call(1, 22_000_000, 30_000_000)]
    spans = [ROOT, gen("a", 9_000_000, 21_000_000), gen("b", 21_500_000, 31_000_000)]
    s = status(run_checks(SPEC, calls, spans)[0])
    assert all(v in ("pass", "n/a") for v in s.values()), s


def test_two_close_calls_do_not_swap():
    calls = [call(0, 10_000_000, 11_000_000), call(1, 11_500_000, 12_500_000)]
    a, b = gen("a", 9_900_000, 11_100_000), gen("b", 11_400_000, 12_600_000)
    by_call, phantom = assign(calls, [map_span(a), map_span(b)])
    assert [o.span_id for o in by_call[0]] == ["a"] and [o.span_id for o in by_call[1]] == ["b"] and not phantom


def test_duplicate_generation_and_doubled_cost():
    calls = [call(0, 10_000_000, 20_000_000)]
    dup = {**gen("c", 9_500_000, 20_500_000), "scope": "com.vendor.sdk"}
    s = status(run_checks(SPEC, calls, [ROOT, gen("a", 9_000_000, 21_000_000), dup])[0])
    assert s["one_generation_per_call"] == "fail" and s["cost_exact"] == "fail"


def test_usage_mismatch_names_the_cache_problem():
    c = call(0, 10_000_000, 20_000_000)
    c["usage"] = {"input": 10, "cache_read": 100, "cache_write": 0, "output": 5}
    r = {x.check: x for x in run_checks(SPEC, [c], [ROOT, gen("a", 9_000_000, 21_000_000, usage={"input": 110, "output": 5, "cache_read_input_tokens": 100})])[0]}
    assert r["usage_exact"].status == "fail" and "counted twice" in r["usage_exact"].detail


def test_unwrapped_generation_and_orphan():
    calls = [call(0, 10_000_000, 20_000_000)]
    s = status(run_checks(SPEC, calls, [gen("a", 9_000_000, 21_000_000, parent="missing")])[0])
    assert s["one_trace_per_run"] == "fail" and s["nested_under_run"] == "fail"


@pytest.fixture(scope="module")
def captured(harness):
    out = {}
    for scen in ("openai.chat_cached", "openai.tools", "concurrency.asyncio"):
        r = run_cell(harness, scen)
        assert r.exit_code == 0, r.stderr_tail
        out[scen] = r
    return out


def test_real_sdk_traces_pass(captured):
    for scen, r in captured.items():
        s = status(run_checks(SPECS[scen], r.calls, r.spans)[0])
        assert all(v in ("pass", "n/a") for v in s.values()), (scen, s)
        assert r.auth_ok  # the SDK authenticated with basic auth, as against Langfuse


def test_every_fault_that_applies_is_caught_by_its_check(captured):
    for scen, r in captured.items():
        for kind, (plant, expect) in FAULTS.items():
            spans = plant(r.spans, random.Random(1))
            if spans is None or not expect:
                continue
            s = status(run_checks(SPECS[scen], r.calls, spans)[0])
            flagged = {k for k, v in s.items() if v in ("fail", "warn")}
            assert flagged & expect, (scen, kind, s)


def test_harmless_changes_raise_no_alarm(captured):
    for scen, r in captured.items():
        for name, change in BENIGN.items():
            s = status(run_checks(SPECS[scen], r.calls, change(r.spans, random.Random(2)))[0])
            assert all(v in ("pass", "n/a") for v in s.values()), (scen, name, s)


def test_anthropic_sdk_duplicates_langchain_generations_today(harness):
    """The finding the matrix reports, reproduced with the pinned latest SDKs."""
    r = run_cell(harness, "langchain.anthropic_cache")
    res = {x.check: x for x in run_checks(SPECS["langchain.anthropic_cache"], r.calls, r.spans)[0]}
    assert res["one_generation_per_call"].status == "fail" and "com.anthropic.sdk.python" in res["one_generation_per_call"].detail
    assert res["usage_exact"].status == "pass"  # the integration's own generation is right; the extra one doubles cost
    assert res["cost_exact"].status == "fail"


def test_skewed_clock_still_matches_each_call_to_its_generation():
    """From a real capture shifted by -3 ms: the first generation now encloses both calls and the second encloses
    neither. Greedy matching swaps them; the whole-run assignment does not."""
    ms = 1_000_000
    calls = [call(0, 0 * ms, int(0.16 * ms)), call(1, int(6.31 * ms), int(6.5 * ms))]
    g1, g2 = gen("a", int(-3.66 * ms), int(6.68 * ms)), gen("b", int(6.9 * ms), int(9.61 * ms))
    by_call, phantom = assign(calls, [map_span(g1), map_span(g2)])
    assert [o.span_id for o in by_call[0]] == ["a"] and [o.span_id for o in by_call[1]] == ["b"] and not phantom
