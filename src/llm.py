"""Ollama-Call over the OpenAI-Client + Trace-Logging.

The call runs in a worker thread; the caller waits at most config.LLM_MAX_SECONDS in total. This is a real
wall-clock limit: it also fires when Ollama stalls and no token arrives at all (a check inside the stream
loop would only run when the next token comes).
"""
import threading

from openai import OpenAI

import config
from src.trace import timer

# timeout = max. wait for one network step; the total limit is LLM_MAX_SECONDS below
client = OpenAI(base_url=config.OLLAMA_URL, api_key="ollama", timeout=300, max_retries=0)  # key is ignored


def chat(run, messages, label="llm_call", max_tokens=None, **kw):
    """run: trace.Run or trace.Version (anything with .log). kw goes to the API, e.g. seed=101."""
    t = timer()
    parts = []
    state = {"stream": None, "usage": None, "finish": None, "error": None}

    def consume():
        try:
            state["stream"] = client.chat.completions.create(
                model=config.MODEL, messages=messages,
                temperature=config.TEMPERATURE, max_tokens=max_tokens or config.MAX_TOKENS,
                stream=True, stream_options={"include_usage": True}, **kw)
            for chunk in state["stream"]:
                if chunk.usage:
                    state["usage"] = chunk.usage
                if chunk.choices:
                    parts.append(chunk.choices[0].delta.content or "")
                    state["finish"] = chunk.choices[0].finish_reason or state["finish"]
        except Exception as e:          # noqa: BLE001 - also the error caused by closing the stream below
            state["error"] = e

    worker = threading.Thread(target=consume, daemon=True)
    worker.start()
    worker.join(timeout=config.LLM_MAX_SECONDS)
    if worker.is_alive():               # time is up: close the connection -> Ollama stops generating
        state["finish"] = "wall_timeout"
        if state["stream"] is not None:
            state["stream"].close()
        worker.join(timeout=2)            # do not wait for a thread that is still blocked

    text = "".join(parts)
    usage = state["usage"]
    run.log("llm", label=label, model=config.MODEL, seed=kw.get("seed"), seconds=t(),
            finish_reason=state["finish"],
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else len(parts),
            messages=messages, response=text)
    if state["finish"] == "wall_timeout":
        raise TimeoutError(f"LLM call exceeded {config.LLM_MAX_SECONDS}s ({len(parts)} chunks received)")
    if state["error"] is not None:
        raise state["error"]
    return text
