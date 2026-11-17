"""The two Step-1 prompts differ only by the changes the change register (docs/changes.md) lists.

prompts/legacy/step1_baseline_v3.txt   old baseline of the old series (experiment E10)
prompts/legacy/step1_baseline.txt      old-series candidate: defines "strong" and the model calls report(key, value)

Run:  python tests/test_prompts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src.checker import GT, KEYS  # noqa: E402

PROMPTS = config.ROOT / "prompts"


def test_current_differs_from_v3_only_by_c01_and_c02():
    old = (PROMPTS / "legacy" / "step1_baseline_v3.txt").read_text(encoding="utf-8").splitlines()
    new = (PROMPTS / "legacy" / "step1_baseline.txt").read_text(encoding="utf-8").splitlines()
    removed = [l for l in old if l not in new]
    added = [l for l in new if l not in old and l.strip()]
    # C02: the "save results with json.dump" line is replaced
    assert len(removed) == 1 and "json.dump" in removed[0], removed
    assert any("report(" in l for l in added) and not any("json.dump" in l for l in added), added
    # C01: the definition of "strong" is added
    assert any("goes_estimated_mean_class" in l and "M or X" in l for l in added), added
    # nothing else changed: 1 definition line + 3 report lines
    assert len(added) == 4, added
    # the keys the checker reads are still all requested
    assert all(f'"{k}"' in "\n".join(new) for k in KEYS)


def test_v2_differs_from_v1_only_by_the_definition_of_strong():
    old = (PROMPTS / "step1_baseline_v1.txt").read_text(encoding="utf-8").splitlines()
    new = (PROMPTS / "step1_baseline_v2.txt").read_text(encoding="utf-8").splitlines()
    assert [l for l in old if l not in new] == []
    added = [l for l in new if l not in old and l.strip()]
    assert len(added) == 1 and "goes_estimated_mean_class" in added[0] and "M or X" in added[0], added


def test_definition_matches_ground_truth():
    """The definition in the prompt must give the n_strong of ground_truth.json."""
    csv = config.DATA_DIR / config.DATA_FILE
    if not csv.exists():
        print("skipped: data file not found (python get_data.py)")
        return
    import pandas as pd
    df = pd.read_csv(csv, low_memory=False)
    strong = df["goes_estimated_mean_class"].astype("string").str[0].isin(["M", "X"])
    assert int(strong.sum()) == GT["n_strong_estimated_MX"]


if __name__ == "__main__":
    test_current_differs_from_v3_only_by_c01_and_c02()
    test_v2_differs_from_v1_only_by_the_definition_of_strong()
    test_definition_matches_ground_truth()
    print("OK - prompt checks passed")
