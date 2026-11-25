"""Central Configuration"""
from pathlib import Path

# --- LLM (Ollama) ---
OLLAMA_URL = "http://localhost:11434/v1"   # OpenAI-compatible Endpoint of Ollama
MODEL = "qwen3-4b-instruct-16k"
TEMPERATURE = 0.7
LLM_MAX_SECONDS = 600                       # hard wall-clock limit per LLM call
MAX_TOKENS=4000                             # max answer length per LLM call

# --- Sandbox (Docker) ---
DOCKER_IMAGE = "agai-sandbox"
EXEC_TIMEOUT_S = 120                        # generated Code will get cancelled after

# --- Pfade ---
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RUNS_DIR = ROOT / "runs"
EXPERIMENTS_DIR = ROOT / "experiments"      # one folder per experiment
DATA_FILE = "stix_flarelist.csv"            # lies in data/, in Container under /data/

# --- Who runs an experiment (run folders are named <person>_<n>, e.g. vanessa_1) ---
# The person is found from the machine name (platform.node()). On another machine: add it here,
# or set the environment variable AGAI_PERSON for one session.
RUNNERS = {
    "MacBook-Pro-von-Vanessa.local": "vanessa",
    "MacBook-Air-von-Jan.local": "jan",
    "Surface-Mischa": "mischa",
}
