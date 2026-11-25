"""The Step-1 prompts of the series: step1_baseline_v2 (B4) differs from step1_baseline_v1 (B1-B3) only by the
definition of "strong" (docs/changes.md, row B4), and that definition gives the n_strong of ground_truth.json.

Run:  python tests/test_prompts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src.checker import GT, KEYS  # noqa: E402

PROMPTS = config.ROOT / "prompts"


def test_v2_differs_from_v1_only_by_the_definition_of_strong():
    old = (PROMPTS / "step1_baseline_v1.txt").read_text(encoding="utf-8").splitlines()
    new = (PROMPTS / "step1_baseline_v2.txt").read_text(encoding="utf-8").splitlines()
    assert [l for l in old if l not in new] == []
    added = [l for l in new if l not in old and l.strip()]
    assert len(added) == 1 and "goes_estimated_mean_class" in added[0] and "M or X" in added[0], added
    # the keys the checker reads are requested by both prompts
    assert all(k in "\n".join(new) for k in KEYS)


def test_definition_matches_ground_truth():
    """The definition in the prompt must give the n_strong of ground_truth.json."""
    csv = config.DATA_DIR / config.DATA_FILE
    if not csv.exists():
        print("skipped: data file not found (python tools/get_data.py)")
        return
    import pandas as pd
    df = pd.read_csv(csv, low_memory=False)
    strong = df["goes_estimated_mean_class"].astype("string").str[0].isin(["M", "X"])
    assert int(strong.sum()) == GT["n_strong_estimated_MX"]


if __name__ == "__main__":
    test_v2_differs_from_v1_only_by_the_definition_of_strong()
    test_definition_matches_ground_truth()
    print("OK - prompt checks passed")
