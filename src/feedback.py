"""What the critic sees in addition to its own code, per reflection level (escalating information):

    2a  nothing                          reflection alone
    2b  + artifacts of the execution     exit code, stdout, traceback, the saved plots
    2c  + external feedback              2b + an independent check of the RESULTS_JSON claims

The feedback is put in front of the critique prompt. It is built from the frozen v1 of the base experiment
(its stdout.txt, stderr.txt, outputs/ and result.json), so every level looks at exactly the same run.

Design decisions (keep in the report):
- Plots: qwen3 cannot read images, so 2b describes each PNG in text (size, blank or not, dominant colours).
- 2c says per claim only "supported / refuted / missing", never the correct value: the critic must find and
  fix the cause itself, otherwise 2c would measure copying the answer instead of reflection.
"""
import json
from pathlib import Path

from src.checker import check, extract_results

INTRO_2B = ("Your script was executed in a sandbox. These are the artifacts of that run "
            "(exit code, printed output, error, saved plots):")
INTRO_2C = ("In addition, an independent script computed the requested facts directly from the CSV and "
            "compared them with your RESULTS_JSON. It reports for each key only whether your value is "
            "supported, refuted or missing; it does not reveal the correct values.")
CLOSING = "Use this information in your review."

STDOUT_CHARS = 3000         # the report is at the start, RESULTS_JSON at the end: keep head and tail
STDERR_LINES = 25           # the end of a traceback is what matters


def prompt_texts(level):
    """The fixed texts a level adds to the prompt; they go into the manifest so a change is detected."""
    texts = {}
    if level in ("2b", "2c"):
        texts["feedback_2b"] = "\n".join((INTRO_2B, CLOSING))
    if level == "2c":
        texts["feedback_2c"] = INTRO_2C
    return texts


def build_feedback(level, v1_dir):
    """Feedback text for the critic of this level, built from the folder of the frozen v1 ('' for 2a)."""
    if level == "2a":
        return ""
    v1_dir = Path(v1_dir)
    parts = [INTRO_2B, artifacts(v1_dir)]
    if level == "2c":
        parts += [INTRO_2C, external_check(v1_dir)]
    parts.append(CLOSING)
    return "\n\n".join(parts)


# ---------------------------------------------------------------- 2b: artifacts
def _read(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _shorten(text, limit):
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n[... {len(text) - limit} characters omitted ...]\n" + text[-half:]


def artifacts(v1_dir):
    result = json.loads(_read(v1_dir / "result.json") or "{}")
    stdout = _read(v1_dir / "stdout.txt").strip()
    stderr = _read(v1_dir / "stderr.txt").strip()
    exit_code = result.get("exit_code")

    lines = [f"Exit code: {exit_code}" + (" (the script finished)" if exit_code == 0 else " (the script failed)")]
    lines.append("Printed output (stdout):\n" + (f"```\n{_shorten(stdout, STDOUT_CHARS)}\n```" if stdout
                                                  else "(nothing was printed)"))
    if stderr:
        tail = "\n".join(stderr.splitlines()[-STDERR_LINES:])
        lines.append(f"Error output (stderr, last {STDERR_LINES} lines):\n```\n{tail}\n```")
    lines.append("Saved plots in /outputs/:\n" + describe_plots(v1_dir / "outputs"))
    return "\n\n".join(lines)


def describe_plots(out_dir):
    """Text description of every PNG, since the model cannot see images."""
    pngs = sorted(Path(out_dir).glob("*.png")) if Path(out_dir).exists() else []
    if not pngs:
        return "- none (no PNG file was saved)"
    return "\n".join(describe_plot(p) for p in pngs)


def describe_plot(path):
    try:
        import matplotlib.image as mpimg
        import numpy as np
        img = mpimg.imread(path)
    except Exception as e:      # noqa: BLE001 - an unreadable file is itself a finding
        return f"- {path.name}: could not be read ({type(e).__name__})"
    h, w = img.shape[:2]
    rgb = img[..., :3] if img.ndim == 3 else np.stack([img] * 3, axis=-1)
    if rgb.std() < 0.01:
        return f"- {path.name}: {w}x{h} px, appears EMPTY (one uniform colour)"
    # share of non-white pixels = how much is actually drawn
    drawn = float((rgb.min(axis=-1) < 0.95).mean())
    return f"- {path.name}: {w}x{h} px, {drawn:.0%} of the area is drawn (not blank)"


# ---------------------------------------------------------------- 2c: external check
CLAIM_NAMES = {
    "n_months": "number of months",
    "busiest_month": "busiest month",
    "busiest_month_count": "flares in the busiest month",
    "flares_per_year": "flares per year",
    "n_strong": "number of strong flares",
    "pct_strong_per_year": "percentage of strong flares per year",
    "strong_share_increasing": "strong share increasing 2022-2025",
}


def external_check(v1_dir):
    stdout = _read(Path(v1_dir) / "stdout.txt")
    results = extract_results(stdout)
    if results is None:
        return ("Independent check: no RESULTS_JSON line was printed, so none of your claims could be checked. "
                "All 7 requested values are missing.")
    checks = check(results)
    lines = ["Independent check of your RESULTS_JSON:"]
    for key, ok in checks.items():
        if ok is None:
            continue
        if key not in results:
            verdict = "MISSING (key not in your JSON)"
        else:
            verdict = "supported" if ok else "REFUTED (the independent computation gives a different value)"
        lines.append(f"- {key} ({CLAIM_NAMES.get(key, key)}): {verdict}")
    return "\n".join(lines)
