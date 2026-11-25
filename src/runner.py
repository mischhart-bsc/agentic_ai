"""Runs Code-Files in a Docker-Container (without network, read-only Files).

run is a trace.Version: the code lands in <condition>/<run>/s<seed>/<version>/code.py and the plots in that
version's own outputs/, so the plots of v1 and of a reflection level never mix.
"""
import subprocess
import config
from src.trace import timer


# Runner helpers ("shims"): this text runs INSIDE the container before the generated code (shims=True). It is a string,
# not a file, so it needs no extra file and no mount; its hash is stored in the manifest (condition.json: shim_hash).
SHIM = '''"""Runner helpers: imported INSIDE the sandbox before the generated code runs (see src/runner.py, shims=True).

They make the environment behave like a notebook, without touching the model's code (code.py stays exactly as written):
  - display(x)   exists, as in Jupyter (a plain script has no display -> NameError)
  - json.dumps   accepts numpy numbers/bools/arrays and pandas Timestamp/Period, also as dict KEYS
                 (before: "Object of type int64 is not JSON serializable", "keys must be str, int, ... not int64")
  - json.dump    the same, for writing /outputs/results.json (prompt step1_baseline_v3)

Every experiment records whether the shims were on and the hash of this file (manifest: runner_shims, shim_hash),
because they hide two kinds of model errors.
"""
import builtins
import json

import numpy as np
import pandas as pd

builtins.display = print


def _plain(o):
    """numpy/pandas scalars -> plain Python, recursively (dict keys included)."""
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return [_plain(v) for v in o.tolist()]
    if isinstance(o, (pd.Timestamp, pd.Period)):
        return str(o)
    if isinstance(o, dict):
        return {_plain(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    return o


_dumps = json.dumps


def _safe_dumps(obj, *args, **kwargs):
    return _dumps(_plain(obj), *args, **kwargs)


json.dumps = _safe_dumps

_dump = json.dump


def _safe_dump(obj, fp, *args, **kwargs):
    return _dump(_plain(obj), fp, *args, **kwargs)


json.dump = _safe_dump
'''


def run_code(run, code: str, shims=False):
    """shims=True: the SHIM text of src/runner.py is run before the code (display, numpy-safe json). The code itself is unchanged."""
    path = run.save_code(code)
    out_dir = run.dir / "outputs"
    cmd = ["docker", "run", "--rm", "--network", "none", "--memory", "2g", "--cpus", "2",
           "-v", f"{config.DATA_DIR.resolve()}:/data:ro",
           "-v", f"{path.parent.resolve()}:/code:ro",
           "-v", f"{out_dir.resolve()}:/outputs"]
    if shims:
        # one -c program: the helper text, then the generated file; runpy keeps the name /code/<file> in tracebacks,
        # so error lines are read the same way as without shims
        cmd += [config.DOCKER_IMAGE, "python", "-c",
                SHIM + f"\nimport runpy\nrunpy.run_path('/code/{path.name}', run_name='__main__')\n"]
    else:
        cmd += [config.DOCKER_IMAGE, "python", f"/code/{path.name}"]
    t = timer()
    try:
        # the container prints UTF-8; without encoding= Windows decodes it as cp1252 ("≥" -> "â‰¥")
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=config.EXEC_TIMEOUT_S)
        stdout, stderr, code_ = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        stdout, stderr, code_ = "", f"TIMEOUT after {config.EXEC_TIMEOUT_S}s", -1
    result = {"file": path.name, "shims": shims, "exit_code": code_, "seconds": t(),
              "stdout": stdout[-5000:], "stderr": stderr[-5000:]}
    run.log("exec", **result)
    return result
