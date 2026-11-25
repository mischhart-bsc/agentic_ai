"""Offline test for src/metrics.py: success score, two-stage means, paired deltas, transitions.

Run:  python tests/test_metrics.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.metrics import (COMPONENTS, SCORE_WEIGHTS, components, condition_summary, run_summary, score,  # noqa: E402
                         transition)


def row(seed, exit_code=0, facts=0.0, partial=None, depth=0, report=0.0, category=None, tokens=1000):
    return {"seed": seed, "exit_code": exit_code, "fact_score": facts, "fact_score_partial": partial,
            "funnel_depth": depth, "report_overall": report, "error_category": category,
            "prompt_tokens": tokens, "completion_tokens": 0, "llm_seconds": 10}


def test_score():
    assert abs(sum(SCORE_WEIGHTS.values()) - 1) < 1e-9 and list(SCORE_WEIGHTS) == COMPONENTS
    # everything right = 100, nothing = 0
    assert score(row(1, 0, facts=1, partial=1, depth=8, report=1)) == 100.0
    assert score(row(1, 1, facts=0, depth=0, report=0)) == 0.0
    # the formula: 100 x sum(weight x component)
    r = row(1, 0, facts=0.5, partial=0.75, depth=4, report=0.6)
    expected = 100 * (0.35 * 0.5 + 0.15 * 0.75 + 0.15 * 1 + 0.10 * 0.5 + 0.25 * 0.6)
    assert score(r) == round(expected, 2), (score(r), expected)
    # without a partial value the strict facts count for both
    assert components(row(1, facts=0.4))["facts_partial"] == 0.4
    # an infrastructure failure is not the model's fault: no score
    assert score(row(1, 1, category="llm_timeout")) is None and components(row(1, 1, category="infra_docker")) is None


def test_two_stages_and_pairing():
    base_a = [row(101, facts=0.2), row(102, facts=0.4)]                    # facts 20 and 40 -> run mean 30
    base_b = [row(101, facts=0.6), row(102, facts=0.6)]                    # run mean 60
    sa, sb = run_summary(base_a), run_summary(base_b)
    assert (sa["facts"], sa["facts_sd"], sb["facts"], sb["facts_sd"]) == (30.0, 10.0, 60.0, 0.0)
    c = condition_summary([sa, sb])
    assert (c["facts"], c["facts_sd_runs"], c["facts_sd_seeds"]) == (45.0, 15.0, 5.0)

    # a reflection run is compared with ITS base run, seed by seed
    level = [row(101, facts=0.5), row(102, 1, facts=0.0, category="date_parse")]
    base = [row(101, 1, facts=0.0, category="json_serialize"), row(102, 0, facts=0.4)]
    s = run_summary(level, base)
    assert s["transitions"] == {"fixed": 1, "broken": 1}
    assert s["delta"]["facts"] == 25.0 - 20.0
    # infra seeds are counted, not averaged
    s = run_summary([row(101, facts=1), row(102, 1, category="infra_docker")])
    assert s["n"] == 2 and s["infra"] == 1 and s["facts"] == 100.0

    # Δ score per 1k extra tokens
    dear = run_summary([row(101, facts=1, partial=1, tokens=3000)], [row(101, facts=0, tokens=1000)])
    c = condition_summary([dear])
    assert c["tokens_delta"] == 2000 and c["score_per_1k_tokens"] == round(c["score_delta"] / 2, 2)


def test_transitions():
    ok, crash_a, crash_b = row(1, 0), row(1, 1, category="a"), row(1, 1, category="b")
    assert transition(crash_a, ok) == "fixed" and transition(ok, crash_a) == "broken"
    assert transition(ok, ok) == "still_ok" and transition(crash_a, crash_a) == "same_error"
    assert transition(crash_a, crash_b) == "swapped" and transition(row(1, 1, category="llm_timeout"), ok) == "infra"
    assert transition(None, ok) is None


if __name__ == "__main__":
    test_score()
    test_two_stages_and_pairing()
    test_transitions()
    print("OK - metrics checks passed")
