"""Offline test for src/figures.py: every figure is written, with one run and with several runs per condition.

Run:  python tests/test_figures.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.figures import build_all  # noqa: E402
from src.metrics import condition_summary, run_summary  # noqa: E402

EXPECTED = {"chain_B1_t_score.png", "chain_B1_t_transitions.png", "chain_B1_t_funnel.png", "chain_B1_t_facts.png",
            "baselines.png", "score_breakdown.png", "cost_vs_score.png"}


def row(seed, exit_code, facts, category=None):
    return {"seed": seed, "exit_code": exit_code, "fact_score": facts, "fact_score_partial": facts, "funnel_depth": 6,
            "report_overall": 0.5, "error_category": category, "prompt_tokens": 1000, "completion_tokens": 500,
            "llm_seconds": 10, "answered": True, "code_found": True, "ran": exit_code == 0,
            "fact_n_months": facts > 0.5}


def build(n_runs):
    runs, conds = {}, {}
    for cond, level, base_cond in [("B1_t", "baseline", None), ("R1_t", "2a", "B1_t"), ("R2_t", "2b", "B1_t")]:
        conds[cond] = {"level": level, "base_condition": base_cond, "runs": []}
        for i in range(n_runs):
            run = f"p{i}_1"
            own = [row(101, i % 2, 0.3 + 0.1 * i), row(102, 0, 0.6, None)]
            base = None if base_cond is None else [row(101, 1, 0.0, "date_parse"), row(102, 0, 0.6)]
            runs[f"{cond}/{run}"] = {"condition": cond, "run": run, "person": f"p{i}", "level": level,
                                     "base": base_cond and f"{base_cond}/{run}", "sum": run_summary(own, base)}
            conds[cond]["runs"].append(f"{cond}/{run}")
        conds[cond]["sum"] = condition_summary([runs[u]["sum"] for u in conds[cond]["runs"]])
    return runs, conds, list(conds)


def test_figures():
    for n_runs in (1, 3):
        with tempfile.TemporaryDirectory() as tmp:
            runs, conds, order = build(n_runs)
            paths = build_all(Path(tmp) / "figures", conds, runs, order)
            assert {p.name for p in paths} == EXPECTED, {p.name for p in paths}
            assert all(p.stat().st_size > 10_000 for p in paths)          # a real image, not an empty file


if __name__ == "__main__":
    test_figures()
    print("OK - figure checks passed")
