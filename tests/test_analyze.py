"""Offline test for analyze.py with hand-made result.json files (no Ollama, no Docker needed).

test_analyze:          flat experiments (legacy layout): comparison, transitions, html
test_two_stage_means:  run layout <condition>/<person>_<n>/s<seed>: mean over seeds, then over runs; paired delta

Run:  python tests/test_analyze.py
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analyze  # noqa: E402
import config  # noqa: E402


def write(root, exp, level, base, seed, version, exit_code, category=None, facts=0.0):
    d = root / exp
    d.mkdir(exist_ok=True)
    (d / "experiment.json").write_text(json.dumps({"id": exp, "level": level, "base": base,
                                                   "data_context": "schema", "seeds": [101, 102, 103, 104, 105],
                                                   "status": "complete"}), encoding="utf-8")
    v = d / "cases" / f"s{seed}" / version
    v.mkdir(parents=True)
    (v / "result.json").write_text(json.dumps({
        "seed": seed, "version": version, "parent": None if version == "v1" else f"E01/s{seed}/v1",
        "exit_code": exit_code, "error_category": category, "fact_score": facts, "n_plots": 1,
        "cost": {"llm_calls": 1, "prompt_tokens": 1000, "completion_tokens": 500, "llm_seconds": 10.0}}),
        encoding="utf-8")


def test_analyze():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "experiments"
        root.mkdir()
        # baseline v1:         101 crash A, 102 ok, 103 crash A, 104 crash A, 105 docker down
        # 2a on the same v1:   101 ok,      102 crash, 103 crash B, 104 crash A, 105 ok
        for seed, ex, cat in [(101, 1, "json_serialize"), (102, 0, None), (103, 1, "date_parse"),
                              (104, 1, "date_parse"), (105, 1, "infra_docker")]:
            write(root, "E01", "baseline", None, seed, "v1", ex, cat, 0.3 if ex == 0 else 0.0)
        for seed, ex, cat in [(101, 0, None), (102, 1, "period_type"), (103, 1, "api_misuse"),
                              (104, 1, "date_parse"), (105, 0, None)]:
            write(root, "E02", "2a", "E01", seed, "2a", ex, cat, 0.6 if ex == 0 else 0.0)

        with mock.patch.object(config, "EXPERIMENTS_DIR", root), \
                mock.patch.object(config, "ROOT", Path(tmp)), \
                mock.patch.object(analyze, "RESULTS_DIR", Path(tmp) / "results"):
            manifests, rows = analyze.collect()
            assert len(rows) == 10
            csv_path = analyze.write_csv(rows)
            assert csv_path.read_text(encoding="utf-8").splitlines()[0].startswith("experiment,condition,run,person,base,level")

            levels, seeds, table = analyze.comparison("E01", manifests, rows)
            assert levels == ["baseline", "2a"] and seeds == [101, 102, 103, 104, 105]

            st = analyze.level_stats("2a", seeds, table)
            assert st["transitions"] == {"fixed": 1, "broken": 1, "swapped": 1, "same_error": 1, "infra": 1}
            base = analyze.level_stats("baseline", seeds, table)
            assert base["infra"] == 1 and base["ran"] == 1               # docker failure excluded

            analyze.print_comparison("E01", levels, seeds, table)
            page = analyze.write_html("E01", manifests, levels, seeds, table).read_text(encoding="utf-8")
            assert "json_serialize" in page and "fixed: 1" in page


def write_run(root, cond, run, level, base_run, seed, facts):
    """One result in the run layout; condition.json and run.json are (re)written as needed."""
    (root / cond / run / f"s{seed}" / ("v1" if level == "baseline" else level)).mkdir(parents=True, exist_ok=True)
    (root / cond / "condition.json").write_text(json.dumps({"id": cond, "level": level, "base": base_run and
                                                            base_run.split("/")[0]}), encoding="utf-8")
    (root / cond / run / "run.json").write_text(json.dumps({
        "person": run.split("_")[0], "base_run": base_run, "seeds": [101, 102], "status": "complete",
        "started": f"2026-11-2{len(run)}T10:00:00"}), encoding="utf-8")
    v = root / cond / run / f"s{seed}" / ("v1" if level == "baseline" else level)
    (v / "result.json").write_text(json.dumps({
        "seed": seed, "version": v.name, "exit_code": 0, "error_category": None, "fact_score": facts, "n_plots": 1,
        "cost": {"llm_calls": 1, "prompt_tokens": 1000, "completion_tokens": 500, "llm_seconds": 10.0}}), encoding="utf-8")


def test_two_stage_means():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "experiments"
        # B1: vanessa_1 seeds 20 % and 40 % (run mean 30), jan_1 60 % and 60 % (run mean 60)
        #     -> condition mean 45, sd between runs 15, mean sd inside a run (10 + 0) / 2 = 5
        for run, f1, f2 in [("vanessa_1", 0.2, 0.4), ("jan_1", 0.6, 0.6)]:
            write_run(root, "B1_t", run, "baseline", None, 101, f1)
            write_run(root, "B1_t", run, "baseline", None, 102, f2)
        # R1 only on vanessa's run: 50 % -> paired delta +20 against ITS base run (not +5 against the B1 mean of 45)
        for seed in (101, 102):
            write_run(root, "R1_t", "vanessa_1", "2a", "B1_t/vanessa_1", seed, 0.5)

        log = Path(tmp) / "PERFORMANCE_LOG.md"
        with mock.patch.object(config, "EXPERIMENTS_DIR", root), mock.patch.object(config, "ROOT", Path(tmp)),                 mock.patch.object(analyze, "RESULTS_DIR", Path(tmp) / "results"), mock.patch.object(analyze, "LOG_FILE", log),                 mock.patch.object(analyze, "facts_for_dir", lambda d: {}):   # keep the hand-made fact_score
            manifests, rows = analyze.collect()
            assert set(manifests) == {"B1_t/vanessa_1", "B1_t/jan_1", "R1_t/vanessa_1"} and len(rows) == 6
            assert {r["person"] for r in rows} == {"vanessa", "jan"}
            text = analyze.write_performance_log(manifests, rows).read_text(encoding="utf-8")
            b1 = next(l for l in text.splitlines() if l.startswith("| B1_t |"))
            r1 = next(l for l in text.splitlines() if l.startswith("| R1_t |"))
            assert "| 45.0 | 15.0 | 5.0 | – |" in b1, b1
            assert "| 50.0 | – (1 run) | 0.0 | +20.0 |" in r1, r1

            # a comparison table per base run; the file name has no slash
            levels, seeds, table = analyze.comparison("B1_t/vanessa_1", manifests, rows)
            assert levels == ["baseline", "2a"]
            assert analyze.write_html("B1_t/vanessa_1", manifests, levels, seeds, table).name == "comparison_B1_t__vanessa_1.html"


if __name__ == "__main__":
    test_analyze()
    test_two_stage_means()
    print("OK - analyze checks passed")
