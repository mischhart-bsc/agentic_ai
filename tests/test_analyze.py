"""Offline test for analyze.py with hand-made result.json files (no Ollama, no Docker needed).

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
            assert csv_path.read_text(encoding="utf-8").splitlines()[0].startswith("experiment,base,level")

            levels, seeds, table = analyze.comparison("E01", manifests, rows)
            assert levels == ["baseline", "2a"] and seeds == [101, 102, 103, 104, 105]

            st = analyze.level_stats("2a", seeds, table)
            assert st["transitions"] == {"fixed": 1, "broken": 1, "swapped": 1, "same_error": 1, "infra": 1}
            base = analyze.level_stats("baseline", seeds, table)
            assert base["infra"] == 1 and base["ran"] == 1               # docker failure excluded

            analyze.print_comparison("E01", levels, seeds, table)
            page = analyze.write_html("E01", manifests, levels, seeds, table).read_text(encoding="utf-8")
            assert "json_serialize" in page and "fixed: 1" in page


if __name__ == "__main__":
    test_analyze()
    print("OK - analyze checks passed")
