"""Ollama-Call over the OpenAI-Client + Trace-Logging."""
from openai import OpenAI
import config
from src.trace import timer

client = OpenAI(base_url=config.OLLAMA_URL, api_key="ollama", timeout=300, max_retries=0)  # Key wird ignoriert


def chat(run, messages, label="llm_call", max_tokens=4000, **kw):
    t = timer()
    stream = client.chat.completions.create(
        model=config.MODEL, messages=messages,
        temperature=config.TEMPERATURE, max_tokens=max_tokens,
        stream=True, stream_options={"include_usage": True}, **kw)

    parts, usage, finish = [], None, None
    try:
        for chunk in stream:
            if chunk.usage:
                usage = chunk.usage
            if chunk.choices:
                parts.append(chunk.choices[0].delta.content or "")
                finish = chunk.choices[0].finish_reason or finish
            if t() > config.LLM_MAX_SECONDS:
                finish = "wall_timeout"
                break
    finally:
        stream.close()          # closing the connection makes Ollama stop generating

    text = "".join(parts)
    run.log("llm", label=label, model=config.MODEL, seconds=t(), finish_reason=finish,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else len(parts),
            messages=messages, response=text)
    if finish == "wall_timeout":
        raise TimeoutError(f"LLM call exceeded {config.LLM_MAX_SECONDS}s "
                           f"({len(parts)} chunks received)")
    return text
