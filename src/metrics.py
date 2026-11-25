"""Metrics of a run: per seed, per run (mean over its seeds), per condition (mean of the run means).

One number for comparison: the SUCCESS SCORE (0-100), a weighted sum of five components that are all 0..1 per seed:

    facts          share of the 7 facts with the correct value (strict: a {year: value} fact is all or nothing)
    facts_partial  the same with partial credit for {year: value} facts (share of correct years)
    ran            the code finished (exit code 0)
    depth          how far the run got in the funnel (stages passed / 8)
    report         report quality (src/evaluate.py: execution, completeness, correctness, method, plots)

The weights are in SCORE_WEIGHTS (one place; they sum to 1). Cost is NOT part of the score on purpose: a level that
is better but costs 4x more must show as a trade-off, not hide inside one number. It is reported next to the score
(tokens, LLM seconds) and as "score points per 1,000 extra tokens". Every component stays available on its own
(results/runs.csv, PERFORMANCE_LOG.md, the breakdown figure), so the score loses no information.

Infrastructure failures (Docker down, LLM timeout) are not the model's fault: such seeds get no score and are left
out of the means (they are counted separately as 'infra').

Two-stage mean: first the mean over the seeds of a run, then the mean of the run means, so every run weighs the same.
A reflection run is compared with ITS base run (paired), because it reflected on exactly those frozen v1s.
"""
from collections import Counter
from statistics import mean, pstdev

from src.checker import KEYS
from src.evaluate import FUNNEL

SCORE_WEIGHTS = {"facts": 0.35, "facts_partial": 0.15, "ran": 0.15, "depth": 0.10, "report": 0.25}
COMPONENTS = list(SCORE_WEIGHTS)
INFRA = ("infra_docker", "llm_timeout", "llm_error")
TRANSITIONS = ("fixed", "still_ok", "swapped", "same_error", "broken")

# per-run metrics that are averaged (all per seed); score first, then the components, then cost
RUN_METRICS = ["score", *COMPONENTS, "tokens", "llm_seconds"]


# ---------------------------------------------------------------- one seed
def ran(r):
    return r is not None and r.get("exit_code") == 0


def infra(r):
    """Failures that are not the model's fault (Docker down, LLM timeout): excluded from scores and transitions."""
    return r is not None and r.get("error_category") in INFRA


def components(r):
    """The five score components of one seed, each 0..1 (None for an infrastructure failure)."""
    if infra(r):
        return None
    return {
        "facts": float(r.get("fact_score") or 0),
        "facts_partial": float(r.get("fact_score_partial") if r.get("fact_score_partial") is not None
                               else r.get("fact_score") or 0),
        "ran": 1.0 if ran(r) else 0.0,
        "depth": (r.get("funnel_depth") or 0) / len(FUNNEL),
        "report": float(r.get("report_overall") or 0),
    }


def score(r):
    """Success score 0-100 of one seed (None for an infrastructure failure)."""
    c = components(r)
    return None if c is None else round(100 * sum(SCORE_WEIGHTS[k] * c[k] for k in COMPONENTS), 2)


def seed_metrics(r):
    """All averaged metrics of one seed; scores and components in 0-100, cost as is. None values for infra seeds."""
    c = components(r)
    cost = {"tokens": (r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0),
            "llm_seconds": r.get("llm_seconds") or 0}
    if c is None:
        return {"score": None, **{k: None for k in COMPONENTS}, **cost}
    return {"score": score(r), **{k: round(100 * v, 2) for k, v in c.items()}, **cost}


def transition(v1, lv):
    """What a reflection level did to the v1 of the same seed."""
    if v1 is None or lv is None:
        return None
    if infra(v1) or infra(lv):
        return "infra"
    if ran(v1) and ran(lv):
        return "still_ok"
    if ran(lv):
        return "fixed"
    if ran(v1):
        return "broken"
    return "same_error" if v1.get("error_category") == lv.get("error_category") else "swapped"


# ---------------------------------------------------------------- one run
def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(mean(xs), 2) if xs else None


def _sd(xs):
    xs = [x for x in xs if x is not None]
    return round(pstdev(xs), 2) if len(xs) > 1 else None


def run_summary(own_rows, base_rows=None):
    """Stage 1: one run (its own versions: v1 of a baseline, the level's version of a reflection run).
    base_rows: the v1 rows of its base run (for a reflection run) -> transitions and paired deltas."""
    real = [r for r in own_rows if not infra(r)]
    per_seed = [seed_metrics(r) for r in own_rows]
    out = {"n": len(own_rows), "infra": len(own_rows) - len(real), "seeds": sorted(r["seed"] for r in own_rows)}
    for k in RUN_METRICS:
        vals = [m[k] for m in per_seed]
        out[k], out[f"{k}_sd"] = _mean(vals), _sd(vals)
    out["stages"] = {s: sum(bool(r.get(s)) for r in real) for s in FUNNEL}
    out["per_fact"] = {k: sum(r.get(f"fact_{k}") is True for r in real) for k in KEYS}
    out["errors"] = Counter(r.get("error_category") for r in real if not ran(r))
    out["transitions"] = None
    if base_rows is not None:
        by_seed = {r["seed"]: r for r in base_rows}
        out["transitions"] = Counter(t for t in (transition(by_seed.get(r["seed"]), r) for r in own_rows) if t)
        base = run_summary(base_rows)
        out["delta"] = {k: (round(out[k] - base[k], 2) if out[k] is not None and base[k] is not None else None)
                        for k in RUN_METRICS}
    return out


# ---------------------------------------------------------------- one condition
def condition_summary(run_sums):
    """Stage 2: mean of the run means. sd_runs = spread between runs (2+ runs); sd_seeds = mean spread inside a run."""
    out = {"runs": len(run_sums), "n": sum(s["n"] for s in run_sums), "infra": sum(s["infra"] for s in run_sums)}
    for k in RUN_METRICS:
        means = [s[k] for s in run_sums if s[k] is not None]
        out[k] = _mean(means)
        out[f"{k}_sd_runs"] = _sd(means)
        out[f"{k}_sd_seeds"] = _mean([s[f"{k}_sd"] for s in run_sums])
        deltas = [s["delta"][k] for s in run_sums if s.get("delta") and s["delta"][k] is not None]
        out[f"{k}_delta"] = _mean(deltas)
        out[f"{k}_delta_sd"] = _sd(deltas)
    real = out["n"] - out["infra"]
    out["stages"] = {s: sum(r["stages"][s] for r in run_sums) for s in FUNNEL}
    out["per_fact"] = {k: sum(r["per_fact"][k] for r in run_sums) for k in KEYS}
    out["real"] = real
    out["errors"] = sum((r["errors"] for r in run_sums), Counter())
    trans = [r["transitions"] for r in run_sums if r["transitions"] is not None]
    out["transitions"] = sum(trans, Counter()) if trans else None
    tok = out["tokens_delta"]
    out["score_per_1k_tokens"] = (round(out["score_delta"] / (tok / 1000), 2)
                                  if out["score_delta"] is not None and tok and tok > 0 else None)
    return out
