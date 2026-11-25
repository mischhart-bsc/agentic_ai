"""Setup check: Ollama -> Docker -> data. The model writes a few lines of code, the sandbox runs them, the trace is printed.

It uses the same Case/Version tracing as the experiments, but in a temporary folder: nothing is kept and the machine
does not have to be in config.RUNNERS yet (this is the first thing to run on a new machine).

Run:  python tools/smoke_test.py      expected: exit 0, (33076, 40) and the column names
"""
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # project folder: config.py, src/

import config  # noqa: E402
from src.experiment import Experiment  # noqa: E402
from src.llm import chat  # noqa: E402
from src.runner import run_code  # noqa: E402
from src.trace import Case  # noqa: E402

prompt = (f"Write Python code that loads /data/{config.DATA_FILE} with pandas "
          "and prints df.shape and df.columns.tolist(). "
          "Return only one ```python code block.")

with tempfile.TemporaryDirectory() as tmp:
    exp = Experiment("S0_smoke", "smoke", {"smoke": prompt}, [1], person="smoke", root=tmp)
    print(f"model {config.MODEL}, digest {exp.manifest['model_digest'] or 'NOT FOUND (is Ollama running?)'}")
    version = Case(exp, 1).version("v1")
    answer = chat(version, [{"role": "user", "content": prompt}], label="smoke")
    m = re.search(r"```python\n(.*?)```", answer, re.S)
    res = run_code(version, m.group(1) if m else answer)
    print("exit:", res["exit_code"])
    print(res["stdout"] or res["stderr"])
    print("trace:")
    for line in (exp.case_dir(1) / "trace.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        print(f"  {e['kind']:<13} {e.get('stage') or '':<6} " + ", ".join(
            f"{k}={e[k]}" for k in ("seconds", "prompt_tokens", "completion_tokens", "exit_code") if e.get(k) is not None))
