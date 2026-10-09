"""Runs Code-Files in a Docker-Container (without network, read-only Files).

run is a trace.Run (old) or a trace.Version (experiments). With a Version the code lands in
cases/s<seed>/<version>/code.py and the plots in that version's own outputs/, so the plots of v1 and of a
reflection level never mix.
"""
import subprocess
import config
from src.trace import timer


def run_code(run, code: str):
    path = run.save_code(code)
    out_dir = run.dir / "outputs"
    cmd = ["docker", "run", "--rm", "--network", "none",
           "--memory", "2g", "--cpus", "2",
           "-v", f"{config.DATA_DIR.resolve()}:/data:ro",
           "-v", f"{path.parent.resolve()}:/code:ro",
           "-v", f"{out_dir.resolve()}:/outputs",
           config.DOCKER_IMAGE, "python", f"/code/{path.name}"]
    t = timer()
    try:
        # the container prints UTF-8; without encoding= Windows decodes it as cp1252 ("≥" -> "â‰¥")
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=config.EXEC_TIMEOUT_S)
        stdout, stderr, code_ = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        stdout, stderr, code_ = "", f"TIMEOUT nach {config.EXEC_TIMEOUT_S}s", -1
    result = {"file": path.name, "exit_code": code_, "seconds": t(),
              "stdout": stdout[-5000:], "stderr": stderr[-5000:]}
    run.log("exec", **result)
    return result
