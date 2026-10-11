"""End-to-end-test: LLM writes Code -> Docker runs it -> Trace."""
import re
from src.trace import Run
from src.llm import chat
from src.runner import run_code
import config

run = Run("smoke")
prompt = (f"Write Python code that loads /data/{config.DATA_FILE} with pandas "
          "and prints df.shape and df.columns.tolist(). "
          "Return only one ```python code block.")
answer = chat(run, [{"role": "user", "content": prompt}], label="smoke")
m = re.search(r"```python\n(.*?)```", answer, re.S)
code = m.group(1) if m else answer
res = run_code(run, code)
print("exit:", res["exit_code"]); print(res["stdout"] or res["stderr"])
print("Trace:", run.trace_file)
