"""Offline test for src/llm.py: the Ollama client is replaced by a fake stream (no Ollama needed).

Run:  python tests/test_llm.py
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src import llm  # noqa: E402


class FakeRun:
    def __init__(self):
        self.entries = []

    def log(self, kind, **fields):
        self.entries.append({"kind": kind, **fields})


class FakeStream:
    """Yields the given tokens; sleeps `stall` seconds before the first one (= Ollama hangs)."""
    def __init__(self, tokens, stall=0.0):
        self.tokens, self.stall, self.closed = tokens, stall, False

    def __iter__(self):
        time.sleep(self.stall)
        for i, tok in enumerate(self.tokens):
            if self.closed:
                raise ConnectionError("stream closed")
            last = i == len(self.tokens) - 1
            yield SimpleNamespace(usage=None, choices=[SimpleNamespace(
                delta=SimpleNamespace(content=tok), finish_reason="stop" if last else None)])
        yield SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=len(self.tokens)),
                              choices=[])

    def close(self):
        self.closed = True


def test_llm():
    msgs = [{"role": "user", "content": "hi"}]

    # normal answer: text joined, usage and seed logged
    run = FakeRun()
    with mock.patch.object(llm.client.chat.completions, "create", return_value=FakeStream(["a", "b"])) as c:
        assert llm.chat(run, msgs, label="generate", seed=101) == "ab"
    assert c.call_args.kwargs["seed"] == 101 and c.call_args.kwargs["max_tokens"] == config.MAX_TOKENS
    e = run.entries[-1]
    assert e["finish_reason"] == "stop" and e["prompt_tokens"] == 10 and e["seed"] == 101

    # Ollama stalls without sending anything: the wall-clock limit still fires
    run = FakeRun()
    with mock.patch.object(config, "LLM_MAX_SECONDS", 1), \
            mock.patch.object(llm.client.chat.completions, "create", return_value=FakeStream(["x"], stall=5)):
        t0 = time.time()
        try:
            llm.chat(run, msgs, label="critique")
            raise AssertionError("no timeout")
        except TimeoutError:
            pass
    assert time.time() - t0 < 4, "limit did not fire on time"
    assert run.entries[-1]["finish_reason"] == "wall_timeout"

    # connection error: logged, then raised
    run = FakeRun()
    with mock.patch.object(llm.client.chat.completions, "create", side_effect=ConnectionError("down")):
        try:
            llm.chat(run, msgs)
            raise AssertionError("error swallowed")
        except ConnectionError:
            pass
    assert run.entries[-1]["kind"] == "llm" and run.entries[-1]["response"] == ""


if __name__ == "__main__":
    test_llm()
    print("OK - llm checks passed")
