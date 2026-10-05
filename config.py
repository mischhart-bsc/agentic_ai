"""Central Configuration"""
from pathlib import Path

# --- LLM (Ollama) ---
OLLAMA_URL = "http://localhost:11434/v1"   # OpenAI-compatible Endpoint of Ollama
MODEL = "qwen3-4b-instruct-16k"
TEMPERATURE = 0.2
LLM_MAX_SECONDS = 600                       # hard wall-clock limit per LLM call

# --- Sandbox (Docker) ---
DOCKER_IMAGE = "agai-sandbox"
EXEC_TIMEOUT_S = 120                        # generated Code will get cancelled after

# --- Pfade ---
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RUNS_DIR = ROOT / "runs"
DATA_FILE = "stix_flarelist.csv"            # lies in data/, in Container under /data/
