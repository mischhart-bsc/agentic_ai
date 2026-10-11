"""Offline test for src/judge_code.py (no Ollama needed): prompt content, answer parsing, code lookup.

Run:  python tests/test_judge_code.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.checker import GT  # noqa: E402
from src.judge import parse_scores  # noqa: E402
from src.judge_code import CRITERIA, build_messages, last_code  # noqa: E402


def test_judge_code():
    # the prompt carries the code, every criterion and every scale level, but no ground-truth numbers
    user = build_messages("df = pd.read_csv('x')")[1]["content"]
    assert "df = pd.read_csv('x')" in user
    assert all(c in user for c in CRITERIA)
    assert str(GT["busiest_month_count"]) not in user and GT["busiest_month"] not in user

    # a well-formed answer is parsed, out-of-range or incomplete answers are rejected
    good = json.dumps({**{c: 4 for c in CRITERIA}, "justification": "ok"})
    assert parse_scores("noise " + good, CRITERIA)["column_choice"] == 4
    assert parse_scores(json.dumps({**{c: 6 for c in CRITERIA}}), CRITERIA) is None
    assert parse_scores(json.dumps({"column_choice": 3}), CRITERIA) is None
    assert parse_scores("no json", CRITERIA) is None

    # the newest generated script is judged; a run without code gives None
    with tempfile.TemporaryDirectory() as tmp:
        assert last_code(tmp) is None
        (Path(tmp) / "code").mkdir()
        (Path(tmp) / "code" / "step_002.py").write_text("old", encoding="utf-8")
        (Path(tmp) / "code" / "step_005.py").write_text("new", encoding="utf-8")
        assert last_code(tmp) == "new"


if __name__ == "__main__":
    test_judge_code()
    print("OK - code judge offline checks passed")
