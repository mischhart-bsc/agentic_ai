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


def test_judges_use_llm_chat():
    """Both judges go through src/llm.chat (time limit), at temperature 0; a failed call is an error, not a crash."""
    from unittest import mock
    from src import judge
    from src.judge_code import judge_code
    answer = json.dumps({**{c: 4 for c in CRITERIA}, "justification": "ok"})

    def fake_chat(log, messages, label="", **kw):
        log.log("llm", label=label, response=answer)
        return answer

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "code.py").write_text("print(1)", encoding="utf-8")
        with mock.patch.object(judge, "chat", side_effect=fake_chat) as chat:
            r = judge_code(tmp)
        assert chat.call_args.kwargs["temperature"] == 0.0 and chat.call_args.kwargs["model"] == judge.JUDGE_MODEL
        assert r["mean"] == 4.0 and json.loads((Path(tmp) / "judge_code.json").read_text(encoding="utf-8"))["mean"] == 4.0
        kinds = [json.loads(l)["kind"] for l in (Path(tmp) / "judge_code.jsonl").read_text(encoding="utf-8").splitlines()]
        assert kinds == ["llm", "scores"]

        with mock.patch.object(judge, "chat", side_effect=TimeoutError("LLM call exceeded 600s")):
            r = judge.judge_report(tmp, "Some report text.")
        assert r["scores"] is None and r["error"].startswith("TimeoutError")
        assert not (Path(tmp) / "judge.json").exists()


if __name__ == "__main__":
    test_judge_code()
    test_judges_use_llm_chat()
    print("OK - code judge offline checks passed")
