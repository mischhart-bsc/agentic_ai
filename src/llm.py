"""Ollama-Call over the OpenAI-Client + Trace-Logging."""
from openai import OpenAI
import config
from src.trace import timer

client = OpenAI(base_url=config.OLLAMA_URL, api_key="ollama", timeout=900, max_retries=0)  # Key wird ignoriert


def chat(run, messages, label="llm_call", **kw):
    t = timer()
    resp = client.chat.completions.create(
        model=config.MODEL, messages=messages,
        temperature=config.TEMPERATURE, **kw)
    text = resp.choices[0].message.content or ""
    run.log("llm", label=label, model=config.MODEL, seconds=t(),
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
            messages=messages, response=text)
    return text
