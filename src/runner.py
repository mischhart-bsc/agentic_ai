"""Runs Code-Files in a Docker-Container (without network, read-only Files)."""
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
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=config.EXEC_TIMEOUT_S)
        stdout, stderr, code_ = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        stdout, stderr, code_ = "", f"TIMEOUT nach {config.EXEC_TIMEOUT_S}s", -1
    result = {"file": path.name, "exit_code": code_, "seconds": t(),
              "stdout": stdout[-5000:], "stderr": stderr[-5000:]}
    run.log("exec", **result)
    return result
