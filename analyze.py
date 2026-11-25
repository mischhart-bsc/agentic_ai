"""Analyse all experiments: one CSV row per version, per condition the mean over its runs, and per baseline run a
comparison seed x level.

Structure: experiments/<condition>/<person>_<n>/s<seed>/ (see src/experiment.py). Inside this script a run is called
by its unit id "<condition>/<run>", e.g. B4_strong/vanessa_1. Where a command takes an id, a condition with a single
run is enough (B4_strong). Old flat experiments (experiments/_legacy, --legacy) count as a condition with one run.

Two-stage mean (PERFORMANCE_LOG.md, section 0): first the mean over the seeds of each run, then the mean of these
run means, so every run has the same weight. A reflection condition is compared with its base run by run
(paired): each run minus the base run it reflected on, then averaged.

Run:  python analyze.py                          all experiments; comparison for every baseline
      python analyze.py --trace B4_strong 101   one trace as a story (--version v1, --full)
      python analyze.py --run B4_strong 101     all details of one version; --details: one line per version
      python analyze.py --exp <exp> --judge           LLM judge on the reports (--judge-code: on the code; needs Ollama)
      python analyze.py --exp <exp> --human-template  human_scores.csv to fill in; then --agreement compares it with the judge
      python analyze.py --base B4_strong/vanessa_1   only this baseline run and the levels built on it
      python analyze.py --legacy                 also include experiments/_legacy (migrated old runs)

Success score (0-100): one comparable number per seed, run and condition, a weighted sum of facts (strict and
partial), finished runs, funnel depth and report quality (src/metrics.py: SCORE_WEIGHTS). Cost is reported next to it.

Writes:
  results/versions.csv                  one row per version (experiment, seed, version, exit, error, facts, score, cost)
  results/runs.csv                      one row per run: mean and sd over its seeds of every metric, delta vs. its base run
  results/conditions.csv                one row per condition: mean of the run means, sd between runs, paired delta
  results/figures/*.png                 the figures of src/figures.py (score per level, transitions, funnel, facts, cost)
  PERFORMANCE_LOG.md                    one row per experiment: what changed, funnel, facts, cost, conditions
  results/comparison_<base run>.html    table seed x level, transitions vs. v1, means and cost per level

Transitions of a level compared with v1 of the same seed:
  fixed       v1 crashed, the level runs
  broken      v1 ran, the level crashes
  swapped     both crash, but with a different error category
  same_error  both crash with the same error category
  still_ok    both run
"""
import argparse
import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime
from statistics import mean, median, pstdev

import config
from src.checker import KEYS, report_precision
from src.evaluate import FUNNEL, WEIGHTS, facts_for_dir, funnel_for_dir, report_quality_for_dir
from src.experiment import case_path, load, resolve, runs_of, unit_dir
from src.metrics import COMPONENTS, RUN_METRICS, SCORE_WEIGHTS, condition_summary, infra, ran, run_summary, \
    seed_metrics, transition

RESULTS_DIR = config.ROOT / "results"
TEXT_KEYS = ["n_months", "busiest_month", "busiest_month_count", "n_strong", "strong_share_increasing"]   # readable from prose
COLUMNS = ["experiment", "condition", "run", "person", "base", "level", "data_context", "case", "seed", "version", "parent", "llm_error",
           "exit_code", "error_category", "error_line", "results_json_found", "fact_score", "fact_score_partial", "n_plots",
           "llm_calls", "prompt_tokens", "completion_tokens", "llm_seconds", "exec_seconds", "truncated",
           "funnel_depth", "crash_pos", "report_precision", "report_overall", *[f"rep_{d}" for d in WEIGHTS], "report_flags", "text_fact_score", *[f"text_{k}" for k in TEXT_KEYS],
           *[f"fact_{k}" for k in KEYS], *FUNNEL, "score", *[f"score_{c}" for c in COMPONENTS]]


# ---------------------------------------------------------------- collect
def unit_ids(legacy=False):
    """Unit ids of all runs: '<condition>/<run>' for the run structure, the folder name for a flat experiment."""
    root = config.EXPERIMENTS_DIR
    ids = []
    for d in sorted(root.glob("*")):
        if (d / "condition.json").exists():
            ids += [f"{d.name}/{r}" for r in runs_of(d.name)]
        elif (d / "experiment.json").exists():          # flat experiment (layout before 25 Nov 2026)
            ids.append(d.name)
    if legacy:
        ids += [d.name for d in sorted((root / "_legacy").glob("*")) if (d / "experiment.json").exists()]
    return ids


def version_files(unit_id):
    """All result.json of a run: <run>/s*/<version>/ or, flat, <experiment>/cases/s*/<version>/."""
    d = unit_dir(unit_id)
    return sorted(d.glob("cases/*/*/result.json") if (d / "cases").is_dir() else d.glob("s*/*/result.json"))


def collect(legacy=False):
    """(manifests by unit id, rows): one row per result.json of every run."""
    manifests, rows = {}, []
    for uid in unit_ids(legacy):
        m = load(uid)
        manifests[uid] = m
        for res_file in version_files(uid):
            r = json.loads(res_file.read_text(encoding="utf-8"))
            r.update(facts_for_dir(res_file.parent))        # fresh, so a parser change applies to old runs too
            cost = r.get("cost") or {}
            fn = funnel_for_dir(res_file.parent)
            rq = report_quality_for_dir(res_file.parent)
            stdout_file = res_file.parent / "stdout.txt"
            code_file = res_file.parent / "code.py"
            n_lines = len(code_file.read_text(encoding="utf-8").splitlines()) if code_file.exists() else 0
            crash_pos = round(r["error_line"] / n_lines, 2) if r.get("error_line") and n_lines else None
            rows.append({
                "experiment": uid, "condition": m.get("condition"), "run": m.get("run"), "person": m.get("person"),
                "base": m.get("base"), "level": m.get("level"),
                "data_context": m.get("data_context"), "case": res_file.parent.parent.name,
                "seed": r.get("seed"), "version": res_file.parent.name, "parent": r.get("parent"),
                **{k: r.get(k) for k in ("llm_error", "exit_code", "error_category", "error_line",
                                         "results_json_found", "fact_score", "fact_score_partial", "n_plots")},
                **{k: cost.get(k) for k in ("llm_calls", "prompt_tokens", "completion_tokens",
                                            "llm_seconds", "exec_seconds", "truncated")},
                "funnel_depth": fn["depth"], "crash_pos": crash_pos, "report_precision": report_precision(stdout_file.read_text(encoding="utf-8")) if stdout_file.exists() else None,
                "report_overall": rq["overall"], **{f"rep_{d}": v for d, v in rq["dimensions"].items()},
                "report_flags": " | ".join(rq["flags"]),
                "text_fact_score": rq["details"]["correctness"]["text_fact_score"],
                **{f"text_{k}": rq["details"]["correctness"]["text_facts"].get(k) for k in TEXT_KEYS},
                **{f"fact_{k}": (r.get("checks") or {}).get(k) for k in KEYS}, **fn["stages"],
                "path": str(res_file.parent),
            })
            sm = seed_metrics(rows[-1])
            rows[-1].update({"score": sm["score"], **{f"score_{c}": sm[c] for c in COMPONENTS}})
    return manifests, rows


def summaries(manifests, rows):
    """(runs, conds, order): run_summary per run (stage 1), condition_summary per condition (stage 2).
    runs[unit id]  = {condition, run, person, level, base, sum}
    conds[cond]    = {level, base_condition, runs: [unit ids], sum}
    order          = conditions in the order their first run started"""
    own = {}
    for r in rows:
        lv = manifests[r["experiment"]].get("level")
        if r["version"] == ("v1" if lv == "baseline" else lv):
            own.setdefault(r["experiment"], []).append(r)
    runs, conds = {}, {}
    for uid in sorted(manifests, key=lambda u: manifests[u].get("started") or ""):
        m = manifests[uid]
        if not own.get(uid):
            continue
        base = m.get("base")
        runs[uid] = {"condition": m.get("condition") or uid, "run": m.get("run"), "person": m.get("person"),
                     "level": m.get("level"), "base": base,
                     "sum": run_summary(own[uid], own.get(base) if base else None)}
        c = conds.setdefault(runs[uid]["condition"], {"level": m.get("level"), "runs": [],
                                                      "base_condition": m.get("base_condition") or
                                                      (base.split("/")[0] if base else None)})
        c["runs"].append(uid)
    for c in conds.values():
        c["sum"] = condition_summary([runs[u]["sum"] for u in c["runs"]])
    return runs, conds, list(conds)


def write_summary_csvs(runs, conds):
    """results/runs.csv (stage 1) and results/conditions.csv (stage 2): every metric, nothing summarised away."""
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / "runs.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["run", "condition", "person", "level", "base_run", "n", "infra", *[x for k in RUN_METRICS for x in (k, f"{k}_sd")],
                *[f"delta_{k}" for k in RUN_METRICS], *[f"trans_{t}" for t in ("fixed", "still_ok", "swapped", "same_error", "broken", "infra")]]
        w = csv.writer(f)
        w.writerow(cols)
        for uid, x in runs.items():
            s, t = x["sum"], x["sum"]["transitions"] or {}
            w.writerow([uid, x["condition"], x["person"], x["level"], x["base"], s["n"], s["infra"],
                        *[v for k in RUN_METRICS for v in (s[k], s[f"{k}_sd"])],
                        *[(s.get("delta") or {}).get(k) for k in RUN_METRICS],
                        *[t.get(k, 0) if x["sum"]["transitions"] is not None else "" for k in
                          ("fixed", "still_ok", "swapped", "same_error", "broken", "infra")]])
    with open(RESULTS_DIR / "conditions.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["condition", "level", "base_condition", "runs", "n", "infra",
                *[x for k in RUN_METRICS for x in (k, f"{k}_sd_runs", f"{k}_sd_seeds", f"{k}_delta", f"{k}_delta_sd")],
                "score_per_1k_tokens"]
        w = csv.writer(f)
        w.writerow(cols)
        for cond, c in conds.items():
            s = c["sum"]
            w.writerow([cond, c["level"], c["base_condition"], " ".join(x.split("/")[-1] for x in c["runs"]), s["n"], s["infra"],
                        *[s[x] for k in RUN_METRICS for x in (k, f"{k}_sd_runs", f"{k}_sd_seeds", f"{k}_delta", f"{k}_delta_sd")],
                        s["score_per_1k_tokens"]])
    return RESULTS_DIR / "runs.csv", RESULTS_DIR / "conditions.csv"


def write_csv(rows):
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / "versions.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


# ---------------------------------------------------------------- compare
# ran(), infra(), transition(): src/metrics.py


def comparison(base_id, manifests, rows):
    """{level: {seed: row}} for the baseline (level 'baseline' = v1) and every level built on it."""
    table = defaultdict(dict)
    for r in rows:
        if r["experiment"] == base_id and r["version"] == "v1":
            table["baseline"][r["seed"]] = r
        elif r["base"] == base_id and r["version"] == r["level"]:
            table[r["level"]][r["seed"]] = r
    levels = ["baseline"] + sorted(l for l in table if l != "baseline")
    seeds = sorted({s for l in table.values() for s in l})
    return levels, seeds, table


def level_stats(level, seeds, table):
    cells = [table[level].get(s) for s in seeds]
    done = [c for c in cells if c is not None]
    real = [c for c in done if not infra(c)]
    trans = Counter(transition(table["baseline"].get(s), table[level].get(s)) for s in seeds)
    trans.pop(None, None)
    return {
        "n": len(done),
        "infra": len(done) - len(real),
        "ran": sum(ran(c) for c in real),
        "facts": mean(c["fact_score"] or 0 for c in real) if real else None,
        "depth": mean(c["funnel_depth"] for c in real) if real else None,
        "tokens": mean((c["prompt_tokens"] or 0) + (c["completion_tokens"] or 0) for c in done) if done else None,
        "seconds": mean(c["llm_seconds"] or 0 for c in done) if done else None,
        "transitions": dict(trans),
        "errors": Counter(c["error_category"] for c in real if not ran(c)),
    }


def print_comparison(base_id, levels, seeds, table):
    print(f"\n=== {base_id}   ({len(seeds)} seeds, levels: {', '.join(levels)})")
    print(f"  {'seed':<6}" + "".join(f"{l:<26}" for l in levels))
    for s in seeds:
        cells = []
        for l in levels:
            c = table[l].get(s)
            cells.append("-" if c is None else ("ok" if ran(c) else c["error_category"] or "?")
                         + ("" if c is None else f" {c['fact_score'] or 0:.0%}"))
        print(f"  s{s:<5}" + "".join(f"{x:<26}" for x in cells))
    print()
    for l in levels:
        st = level_stats(l, seeds, table)
        facts = "-" if st["facts"] is None else f"{st['facts']:.0%}"
        depth = "-" if st["depth"] is None else f"{st['depth']:.1f}/{len(FUNNEL)}"
        line = (f"  {l:<9} ran {st['ran']}/{st['n'] - st['infra']}  depth {depth:>5}  facts {facts:>4}  "
                f"tokens {st['tokens'] or 0:>7,.0f}  llm {st['seconds'] or 0:>5.0f}s")
        if st["infra"]:
            line += f"  (+{st['infra']} infra failures excluded)"
        if l != "baseline":
            line += "  | " + ", ".join(f"{k} {v}" for k, v in sorted(st["transitions"].items()))
        print(line)


# ---------------------------------------------------------------- html
def _colour(c):
    if c is None:
        return "#f3f3f3"
    if infra(c):
        return "#dddddd"
    if not ran(c):
        return "#f4c7c3"
    f = c["fact_score"] or 0
    return "#fce8b2" if f < 0.5 else ("#d9ead3" if f < 1 else "#b7e1cd")


def write_html(base_id, manifests, levels, seeds, table):
    def cell(c):
        if c is None:
            return '<td style="background:#f3f3f3">–</td>'
        label = "ok" if ran(c) else html.escape(c["error_category"] or "?")
        link = Path(c["path"]).relative_to(config.ROOT).as_posix()
        return (f'<td style="background:{_colour(c)}"><a href="../{link}/code.py">{label}</a><br>'
                f'<b>{c["fact_score"] or 0:.0%}</b> facts · {c["n_plots"] or 0} plots<br>'
                f'<small>{(c["prompt_tokens"] or 0) + (c["completion_tokens"] or 0):,} tok</small></td>')

    exp_of = {"baseline": base_id}
    exp_of.update({r["level"]: r["experiment"] for l in levels for r in table[l].values() if l != "baseline"})
    head = "".join(f"<th>{l}<br><small>{html.escape(exp_of.get(l, ''))}</small></th>" for l in levels)
    body = "".join(f"<tr><th>s{s}</th>{''.join(cell(table[l].get(s)) for l in levels)}</tr>" for s in seeds)

    stats = {l: level_stats(l, seeds, table) for l in levels}
    def row(name, fn):
        return f"<tr><th>{name}</th>{''.join(f'<td>{fn(stats[l], l)}</td>' for l in levels)}</tr>"
    summary = "".join([
        row("ran", lambda s, l: f"{s['ran']}/{s['n'] - s['infra']}"),
        row("funnel depth", lambda s, l: "–" if s["depth"] is None else f"{s['depth']:.1f}/{len(FUNNEL)}"),
        row("mean facts", lambda s, l: "–" if s["facts"] is None else f"{s['facts']:.0%}"),
        row("tokens / seed", lambda s, l: f"{s['tokens'] or 0:,.0f}"),
        row("LLM s / seed", lambda s, l: f"{s['seconds'] or 0:,.0f}"),
        row("vs. v1", lambda s, l: "" if l == "baseline" else
            "<br>".join(f"{k}: {v}" for k, v in sorted(s["transitions"].items()))),
        row("errors", lambda s, l: "<br>".join(f"{k}: {v}" for k, v in s["errors"].most_common())),
    ])
    m = manifests[base_id]
    info = (f"model {m.get('model')} · T={m.get('temperature')} · data context {m.get('data_context')} · "
            f"commit {m.get('git_commit')}{' (dirty)' if m.get('git_dirty') else ''} · {m.get('machine')}")
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>{base_id}</title>
<style>body{{font-family:sans-serif;margin:24px}} table{{border-collapse:collapse;margin:12px 0}}
td,th{{border:1px solid #ccc;padding:6px 10px;text-align:center;vertical-align:top}}
a{{color:#222}} .legend span{{padding:2px 8px;margin-right:6px}}</style></head><body>
<h2>Reflection levels on {html.escape(base_id)}</h2><p>{html.escape(info)}</p>
<p class="legend"><span style="background:#b7e1cd">all facts right</span><span style="background:#d9ead3">≥50 % facts</span>
<span style="background:#fce8b2">ran, &lt;50 % facts</span><span style="background:#f4c7c3">crashed</span>
<span style="background:#dddddd">infrastructure failure</span></p>
<table><tr><th>seed</th>{head}</tr>{body}</table>
<h3>Per level</h3><table><tr><th></th>{''.join(f'<th>{l}</th>' for l in levels)}</tr>{summary}</table>
<p><small>Every level starts from the same frozen v1 of the baseline. Transitions compare a level with v1 of the
same seed; infrastructure failures are excluded. Click a cell to open its code.</small></p></body></html>"""
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"comparison_{base_id.replace('/', '__')}.html"
    path.write_text(page, encoding="utf-8")
    return path


# ---------------------------------------------------------------- PERFORMANCE_LOG.md
LOG_FILE = config.ROOT / "PERFORMANCE_LOG.md"


def _ms(values, fmt):
    """'mean ± sd' of a list (sd of the n seeds, not an estimate); '–' if empty."""
    return "–" if not values else f"{fmt(mean(values))} ± {fmt(pstdev(values))}"


def _own_rows(exp_id, manifest, rows):
    """The rows an experiment is about: v1 of a baseline, the level's version of a reflection experiment."""
    own = "v1" if manifest.get("level") == "baseline" else manifest.get("level")
    return [r for r in rows if r["experiment"] == exp_id and r["version"] == own]


def crash_text(x):
    """Mean position of the crash line in the script, e.g. '84 % of script' (late = it almost finished)."""
    return "–" if not x["crash_pos"] else f"{mean(x['crash_pos']):.0f} % of script"


def experiment_summary(exp_id, manifest, rows):
    mine = _own_rows(exp_id, manifest, rows)
    real = [r for r in mine if not infra(r)]
    return {
        "n": len(mine), "infra": len(mine) - len(real),
        "ran": sum(ran(r) for r in real),
        "depth": [r["funnel_depth"] for r in real],
        "facts": [(r["fact_score"] or 0) * 100 for r in real],
        "tokens": [(r["prompt_tokens"] or 0) + (r["completion_tokens"] or 0) for r in mine],
        "seconds": [r["llm_seconds"] or 0 for r in mine],
        "stages": {k: sum(bool(r[k]) for r in real) for k in FUNNEL},
        "errors": Counter(r["error_category"] for r in real if not ran(r)),
        "crash_pos": [r["crash_pos"] * 100 for r in real if r["crash_pos"] is not None],
        "per_fact": {k: sum(r[f"fact_{k}"] is True for r in real) for k in KEYS},
        "text_fact": {k: (sum(r[f"text_{k}"] is True for r in real), sum(r[f"text_{k}"] is not None for r in real))
                      for k in TEXT_KEYS},
        "truncated": sum(bool(r["truncated"]) for r in real),
        "plots": [r["n_plots"] or 0 for r in real],
        "precision": [r["report_precision"] for r in real if r["report_precision"] is not None],
        "exec_seconds": [r["exec_seconds"] or 0 for r in real],
        "llm_calls": [r["llm_calls"] or 0 for r in mine],
        "quality": {"overall": [r["report_overall"] * 100 for r in real if r["report_overall"] is not None],
                    **{d: [r[f"rep_{d}"] * 100 for r in real if r[f"rep_{d}"] is not None] for d in WEIGHTS}},
        "flags": Counter(f for r in real for f in (r["report_flags"] or "").split(" | ") if f),
    }


def reference_of(exp_id, manifests):
    """What a run is compared with: its base run, or for a baseline the previous baseline run of ANOTHER condition
    (by start time), preferably from the same person."""
    m = manifests[exp_id]
    if m.get("base"):
        return m["base"]
    earlier = [i for i, o in manifests.items() if o.get("level") == "baseline" and o.get("condition") != m.get("condition")
               and (o.get("started") or "") < (m.get("started") or "")]
    same_person = [i for i in earlier if manifests[i].get("person") == m.get("person")]
    return max(same_person or earlier, key=lambda i: manifests[i].get("started") or "", default=None)


def quality_vs_cost(ids, manifests, sums):
    """Section 1b: one table per baseline that has reflection levels: what each level gains and what it costs.
    'per 1k extra tokens' = Δ facts (percentage points) / (Δ tokens per seed / 1000) against the baseline."""
    L = ["", "## 1b. Quality vs cost per reflection level", "",
         "One table per baseline. Quality: runs that finished, funnel depth, facts, report quality (0-100). Cost: LLM calls, "
         "tokens and LLM seconds per seed (seconds depend on the machine and its power mode; compare tokens). "
         "**Δ facts per 1k extra tokens** = how many percentage points of facts a level gains for every 1,000 tokens it costs "
         "more than the baseline."]
    for b in ids:
        levels = sorted((i for i in ids if manifests[i].get("base") == b),
                        key=lambda i: (manifests[i].get("level") or "", manifests[i].get("started") or ""))
        if manifests[b].get("level") != "baseline" or not levels or not sums[b]["n"]:
            continue
        L += ["", f"### Base {b}", "",
              "| Level | Exp | Ran | Depth | Facts % | Report | LLM calls | Tokens / seed | LLM s / seed | Δ facts | Δ tokens | Δ facts per 1k extra tokens |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        base_facts, base_tok = mean(sums[b]["facts"] or [0]), mean(sums[b]["tokens"])
        for i in [b] + levels:
            x = sums[i]
            if not x["n"]:
                L.append(f"| {manifests[i].get('level')} | {i} | no results yet | | | | | | | | | |")
                continue
            facts, tok = mean(x["facts"] or [0]), mean(x["tokens"])
            report = f"{mean(x['quality']['overall']):.0f}" if x["quality"]["overall"] else "–"
            if i == b:
                d_facts = d_tok = per_k = "–"
            else:
                d_facts, d_tok = f"{facts - base_facts:+.1f}", f"{tok - base_tok:+,.0f}"
                per_k = f"{(facts - base_facts) / ((tok - base_tok) / 1000):+.2f}" if tok - base_tok > 0 else "–"
            L.append(f"| {manifests[i].get('level')} | {i} | {x['ran']}/{x['n'] - x['infra']} | "
                     f"{mean(x['depth'] or [0]):.1f} | {facts:.0f} | {report} | {mean(x['llm_calls']):.1f} | "
                     f"{tok:,.0f} | {mean(x['seconds']):,.0f} | {d_facts} | {d_tok} | {per_k} |")
    return L


def short(unit_id):
    """'B4_strong/vanessa_1' -> 'B4/vanessa_1', 'E10_baseline_v3' -> 'E10' (for table cells)."""
    cond, _, run = (unit_id or "").partition("/")
    return f"{cond.split('_')[0]}/{run}" if run else cond.split("_")[0]


def _v(x, fmt="{:.1f}"):
    return "–" if x is None else fmt.format(x)


def condition_overview(conds, runs):
    """Section 0: one row per condition, the success score first, then every component (two-stage means)."""
    w = ", ".join(f"{k} {v:.2f}" for k, v in SCORE_WEIGHTS.items())
    L = ["## 0. Per condition: success score and its parts (two-stage mean over runs)", "",
         f"**Score** (0-100) = 100 x ({' + '.join(f'{v:.2f} x {k}' for k, v in SCORE_WEIGHTS.items())}); every part is 0-1 "
         "per seed (facts = share of the 7 facts right, strict or with partial credit for the years; ran = code finished; "
         "depth = funnel stages passed / 8; report = report quality). Weights in `src/metrics.py`. Cost is not part of the score.",
         "Stage 1: mean over the seeds of a run. Stage 2: mean of the run means (every run weighs the same). "
         "**sd runs** = spread between the run means (needs 2+ runs); **sd seeds** = mean spread inside a run. "
         "**Δ (paired)** = every reflection run minus the base run it reflected on, averaged over the runs. "
         "Infrastructure failures (Docker down, LLM timeout) are left out and counted.", "",
         "| Condition | Level | Runs | Score | sd runs | sd seeds | Δ score (paired) | Facts % | Facts partial % | Ran % | Depth % | Report | Tokens / seed | Δ score per 1k extra tokens |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for cond, c in conds.items():
        s = c["sum"]
        names = ", ".join(runs[u]["run"] or "–" for u in c["runs"]) + (f" (+{s['infra']} infra)" if s["infra"] else "")
        L.append(f"| {cond} | {c['level']} | {names} | **{_v(s['score'])}** | "
                 f"{_v(s['score_sd_runs']) if len(c['runs']) > 1 else '– (1 run)'} | {_v(s['score_sd_seeds'])} | "
                 f"{_v(s['score_delta'], '{:+.1f}')} | {_v(s['facts'])} | {_v(s['facts_partial'])} | {_v(s['ran'])} | "
                 f"{_v(s['depth'])} | {_v(s['report'])} | {_v(s['tokens'], '{:,.0f}')} | {_v(s['score_per_1k_tokens'], '{:+.2f}')} |")
    L += ["", "### 0b. Score of every run (stage 1)", "",
          "| Run | Level | Base run | Score ± sd seeds | Δ score vs. base run | " + " | ".join(COMPONENTS) + " | Transitions vs. v1 |",
          "|---|---|---|---|---|" + "---|" * len(COMPONENTS) + "---|"]
    for uid, x in runs.items():
        s = x["sum"]
        trans = ", ".join(f"{k} {v}" for k, v in sorted((s["transitions"] or {}).items())) or "–"
        L.append(f"| {uid} | {x['level']} | {x['base'] or '–'} | {_v(s['score'])} ± {_v(s['score_sd'])} | "
                 f"{_v((s.get('delta') or {}).get('score'), '{:+.1f}')} | " + " | ".join(_v(s[k]) for k in COMPONENTS)
                 + f" | {trans} |")
    return L


def figures_section(paths):
    if not paths:
        return []
    L = ["", "## Figures", "", "Built by `python analyze.py` into `results/figures/` (bar = mean of the runs, dot = one run).", ""]
    for p in paths:
        rel = Path(p).relative_to(config.ROOT).as_posix()
        L += [f"![{Path(p).stem}]({rel})", ""]
    return L


def write_performance_log(manifests, rows, figure_paths=()):
    ids = sorted((i for i, m in manifests.items() if m.get("status") != "legacy" and not i.startswith("L")),
                 key=lambda i: manifests[i].get("started") or "")
    sums = {i: experiment_summary(i, manifests[i], rows) for i in ids}
    n_stage = len(FUNNEL)

    def delta(i, key):
        ref = reference_of(i, manifests)
        if ref not in sums or not sums[i][key] or not sums[ref][key]:
            return "–"
        d = mean(sums[i][key]) - mean(sums[ref][key])
        return f"{d:+.1f} vs {short(ref)}"

    L = ["# Performance log", "",
         f"Generated by `python analyze.py` on {datetime.now():%Y-%m-%d %H:%M}. **Do not edit by hand** "
         "(it is rebuilt from `experiments/*/`). One row per experiment; every experiment runs the same seeds.", "",
         f"How to read: **depth** = how many funnel stages in a row a run passed (0-{n_stage}); a crash early gives a low depth, "
         "a wrong number at the end still gives a high one. **facts** = share of the 7 requested values that match "
         "`ground_truth.json`. **Δ** = difference of the mean against the reference experiment named in the cell.", "",
         "Shims = runner helpers (`SHIM` in `src/runner.py`: `display`, numpy-safe JSON).", "",
         "Funnel stages: " + " → ".join(f"`{k}`" for k in FUNNEL), ""]
    runs, conds, _ = summaries({i: manifests[i] for i in ids}, [r for r in rows if r["experiment"] in ids])
    L += condition_overview(conds, runs)
    L += figures_section(figure_paths)
    L += ["", "## 1. Overview (one row per run)", "",
         f"| Run | Level | What changed | Ran | Depth (0-{n_stage}) | Δ depth | Crash at | Facts % | Δ facts | Tokens / seed | LLM s / seed |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i in ids:
        m, x = manifests[i], sums[i]
        change = m.get("change") or m.get("note") or "⚠ not described"
        L.append(f"| {i} | {m.get('level')} | {change} | {x['ran']}/{x['n'] - x['infra']} | "
                 f"{_ms(x['depth'], lambda v: f'{v:.1f}')} | {delta(i, 'depth')} | "
                 f"{crash_text(x)} | "
                 f"{_ms(x['facts'], lambda v: f'{v:.0f}')} | {delta(i, 'facts')} | "
                 f"{mean(x['tokens']):,.0f} | {mean(x['seconds']):,.0f} |" if x["n"] else f"| {i} | {m.get('level')} | {change} | no results yet | | | | | | |")

    L += quality_vs_cost(ids, manifests, sums)

    L += ["", "## 2. Funnel (runs that reached each stage)", "",
          "| Exp | " + " | ".join(FUNNEL) + " |", "|---|" + "---|" * len(FUNNEL)]
    for i in ids:
        x = sums[i]
        L.append(f"| {i} | " + " | ".join(f"{x['stages'][k]}/{x['n'] - x['infra']}" for k in FUNNEL) + " |")

    L += ["", "## 3. Where the runs fail (error category of the runs that crashed)", "",
          "| Exp | Errors |", "|---|---|"]
    for i in ids:
        errs = ", ".join(f"{k} ×{v}" for k, v in sums[i]["errors"].most_common()) or "–"
        L.append(f"| {i} | {errs} |")

    L += ["", "## 4. Accuracy per fact (runs with the correct value)", "",
          "| Exp | " + " | ".join(KEYS) + " |", "|---|" + "---|" * len(KEYS)]
    for i in ids:
        x = sums[i]
        L.append(f"| {i} | " + " | ".join(f"{x['per_fact'][k]}/{x['n'] - x['infra']}" for k in KEYS) + " |")

    L += ["", "### 4b. Facts read from the report text (right / readable)", "",
          "Used when the model prints no RESULTS_JSON: the same facts, read from the prose. `readable` = the text names the "
          "fact at all. flares_per_year and pct_strong_per_year cannot be read from prose.", "",
          "| Exp | " + " | ".join(TEXT_KEYS) + " |", "|---|" + "---|" * len(TEXT_KEYS)]
    for i in ids:
        x = sums[i]
        L.append(f"| {i} | " + " | ".join(f"{x['text_fact'][k][0]}/{x['text_fact'][k][1]}" for k in TEXT_KEYS) + " |")

    L += ["", "## 5. Other measures", "",
          "| Exp | Facts % median (min-max) | Truncated | Plots (mean) | Report precision (mean) | Exec s / run | LLM calls / run |",
          "|---|---|---|---|---|---|---|"]
    for i in ids:
        x = sums[i]
        if not x["facts"]:
            continue
        prec = "–" if not x["precision"] else f"{mean(x['precision']):.0%} (n={len(x['precision'])})"
        L.append(f"| {i} | {median(x['facts']):.0f} ({min(x['facts']):.0f}-{max(x['facts']):.0f}) | "
                 f"{x['truncated']}/{x['n'] - x['infra']} | {mean(x['plots']):.1f} | {prec} | "
                 f"{mean(x['exec_seconds']):.1f} | {mean(x['llm_calls']):.1f} |")

    L += ["", "## 6. Report quality (0-100, mean ± sd over the seeds; weights " +
          ", ".join(f"{d} {w:.2f}" for d, w in WEIGHTS.items()) + ")", "",
          "| Exp | Overall | " + " | ".join(WEIGHTS) + " | Most frequent flags |", "|---|---|" + "---|" * len(WEIGHTS) + "---|"]
    for i in ids:
        x = sums[i]
        if not x["quality"]["overall"]:
            continue
        top = "; ".join(f"{f} ×{n}" for f, n in x["flags"].most_common(3)) or "–"
        L.append(f"| {i} | " + " | ".join(_ms(x["quality"][d], lambda v: f"{v:.0f}") for d in ("overall", *WEIGHTS))
                 + f" | {top} |")

    L += ["", "## 7. Conditions (who requested what, where)", "",
          "| Exp | Model (digest) | Temp | Shims | Ollama URL | Docker image | Machine | Commit | Prompts (hash) | Started | Status |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i in ids:
        m = manifests[i]
        prompts = ", ".join(f"{k} `{str(v)[7:15]}`" for k, v in (m.get("prompts") or {}).items())
        commit = f"{m.get('git_commit')}{' (dirty)' if m.get('git_dirty') else ''}"
        L.append(f"| {i} | {m.get('model')} ({m.get('model_digest')}) | {m.get('temperature')} | "
                 f"{'on' if m.get('runner_shims') else 'off'} | {m.get('ollama_url') or '–'} | {m.get('docker_image') or '–'} | {m.get('machine')} | {commit} | "
                 f"{prompts} | {m.get('started')} | {m.get('status')} |")
    L.append("")
    LOG_FILE.write_text("\n".join(L), encoding="utf-8")
    return LOG_FILE


# ---------------------------------------------------------------- judges and human scores (from evaluate_reports.py)
HUMAN_CSV = config.ROOT / "human_scores.csv"


def version_dirs(exp_id, manifests):
    """Folders of the versions a run is about (v1 of a baseline, the level's version otherwise)."""
    own = "v1" if manifests[exp_id].get("level") == "baseline" else manifests[exp_id].get("level")
    return sorted(d for d in (case_path(exp_id, s) / own for s in manifests[exp_id].get("seeds") or []) if d.is_dir())


def case_id(d):
    """The id used in human_scores.csv: the folder relative to experiments/, e.g. B4_strong/vanessa_1/s101/v1."""
    return d.relative_to(config.EXPERIMENTS_DIR).as_posix()


def run_judges(exp_id, manifests, report=False, code=False):
    """LLM judge (needs Ollama) on the report text and/or the generated code of every version of an experiment.
    Writes judge.json / judge_code.json into the version folder."""
    for d in version_dirs(exp_id, manifests):
        if not (d / "result.json").exists():
            continue
        if report:
            from src.judge import judge_report
            text = report_quality_for_dir(d)["report_text"]
            if text:
                print(f"Judge: {case_id(d)} ...")
                judge_report(d, text)
        if code:
            from src.judge_code import judge_code
            print(f"Code judge: {case_id(d)} ...")
            judge_code(d)


def human_template(exp_id, manifests):
    """Empty human_scores.csv (scale 1-5, criteria in src/judge.py) for the versions that have a report text."""
    from src.judge import CRITERIA
    if HUMAN_CSV.exists():
        print(f"{HUMAN_CSV.name} exists - not overwritten.")
        return
    with open(HUMAN_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run_id", "rater", *CRITERIA, "comment"])
        for d in version_dirs(exp_id, manifests):
            if (d / "result.json").exists() and report_quality_for_dir(d)["report_text"]:
                w.writerow([case_id(d), "", *[""] * len(CRITERIA), ""])
    print(f"Template written: {HUMAN_CSV.name} (versions with a report text only). Scale 1-5, see src/judge.py")


def print_run(exp_id, seed, manifests):
    """All details of one version (was evaluate_reports.py --run): dimensions, flags, details, report text, judge scores."""
    dirs = [d for d in version_dirs(exp_id, manifests) if d.parent.name == f"s{seed}" and (d / "result.json").exists()]
    if not dirs:
        raise SystemExit(f"No evaluated version for {exp_id} s{seed}")
    d = dirs[0]
    rq = report_quality_for_dir(d)
    print(f"\n=== {case_id(d)}   overall {rq['overall']}")
    for dim, w in WEIGHTS.items():
        print(f"  {dim:<13} {rq['dimensions'][dim]}   (weight {w:.2f})")
    if (d / "judge.json").exists():
        print(f"  judge         {json.loads((d / 'judge.json').read_text(encoding='utf-8')).get('scores')}")
    print("  Flags:")
    for f in rq["flags"] or ["-"]:
        print(f"    - {f}")
    print("  Details:")
    for dim, det in rq["details"].items():
        print(f"    [{dim}] " + json.dumps(det, ensure_ascii=False, default=str))
    if rq["report_text"]:
        print("  Report text:\n    " + rq["report_text"][:1500].replace("\n", "\n    "))


def print_details(rows):
    """One line per version: report quality overall and the five dimensions (was evaluate_reports.py --details)."""
    f = lambda v: "  -  " if v is None else f"{v:5.2f}"      # noqa: E731
    for r in rows:
        print(f"  {r['experiment']}/{r['case']}/{r['version']:<8} overall={f(r['report_overall'])} "
              + " ".join(f"{d[:4]}={f(r[f'rep_{d}'])}" for d in WEIGHTS))


# ---------------------------------------------------------------- one trace as a story
def _short(text, n=110):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + " …"


def _describe(e, full):
    """One trace line (an event of trace.jsonl) as text. kind: version_start, llm, exec, result, error."""
    kind = e["kind"]
    if kind == "version_start":
        return f"start (parent: {e.get('parent') or '-'})", []
    if kind == "llm":
        head = (f"{e.get('label')}: {e.get('prompt_tokens')} tokens in, {e.get('completion_tokens')} out, "
                f"{e.get('seconds')}s, finish={e.get('finish_reason')}")
        return head, (["    --- last prompt message ---", e["messages"][-1]["content"],
                       "    --- answer ---", e.get("response", "")] if full else [])
    if kind == "exec":
        err = [l for l in (e.get("stderr") or "").splitlines() if l.strip()]
        return f"code {e.get('file')}: exit={e.get('exit_code')}, {e.get('seconds')}s" + (f"  | {_short(err[-1])}" if err else ""), []
    if kind == "result":
        return (f"result: exit={e.get('exit_code')} error={e.get('error_category') or '-'} "
                f"depth={e.get('funnel_depth', 'n/a (older result)')}/{len(FUNNEL)} facts={e.get('fact_score')} plots={e.get('n_plots')}"), []
    if kind == "error":
        return f"ERROR in {e.get('stage')}: {e.get('error_type')} {_short(e.get('error'))}", []
    return _short(json.dumps(e, ensure_ascii=False)), []


def print_trace(exp_id, seed, version=None, full=False):
    """Print the trace of one case, one line per event (full: with prompts and answers)."""
    path = case_path(resolve(exp_id), seed) / "trace.jsonl"
    if not path.exists():
        raise SystemExit(f"No trace at {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if version and e.get("version") != version:
            continue
        head, extra = _describe(e, full)
        print(f"{e['step']:>3}  {e['time'][11:]}  {e.get('version') or '-':<6} {e['kind']:<13} {head}")
        for l in extra:
            print(l)


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="only this baseline run and its levels, e.g. B4_strong/vanessa_1")
    ap.add_argument("--legacy", action="store_true", help="include migrated old runs in versions.csv")
    ap.add_argument("--trace", nargs=2, metavar=("EXP", "SEED"), help="print one trace as a story, e.g. --trace B4_strong 101")
    ap.add_argument("--version", help="with --trace: only this version, e.g. v1 or 2a")
    ap.add_argument("--full", action="store_true", help="with --trace: also print prompts and answers")
    ap.add_argument("--run", nargs=2, metavar=("EXP", "SEED"), help="all details of one version, e.g. --run B4_strong 101")
    ap.add_argument("--details", action="store_true", help="one line per version with the report quality")
    ap.add_argument("--exp", help="for --judge, --judge-code, --human-template: the experiment to work on")
    ap.add_argument("--judge", action="store_true", help="LLM judge on the report text (needs Ollama)")
    ap.add_argument("--judge-code", action="store_true", help="LLM judge on the generated code (needs Ollama)")
    ap.add_argument("--human-template", action="store_true", help="write human_scores.csv to fill in yourself")
    ap.add_argument("--agreement", action="store_true", help="compare human_scores.csv with the judge")
    args = ap.parse_args()

    if args.trace:
        print_trace(args.trace[0], int(args.trace[1]), args.version, args.full)
        raise SystemExit(0)

    if args.agreement:
        from src.judge import agreement
        if not HUMAN_CSV.exists():
            raise SystemExit("human_scores.csv is missing - run --human-template first and fill it in.")
        res = agreement(HUMAN_CSV, config.EXPERIMENTS_DIR)
        print(json.dumps(res, indent=2) if res else "No common scores found (judge.json missing? run --judge first).")
        raise SystemExit(0)

    manifests, rows = collect(args.legacy)
    if args.run:
        print_run(resolve(args.run[0]), int(args.run[1]), manifests)
        raise SystemExit(0)
    if args.judge or args.judge_code or args.human_template:
        args.exp = resolve(args.exp) if args.exp else None
        if not args.exp or args.exp not in manifests:
            raise SystemExit("--exp <experiment id> is required (and must exist) for --judge, --judge-code, --human-template")
        if args.human_template:
            human_template(args.exp, manifests)
        else:
            run_judges(args.exp, manifests, report=args.judge, code=args.judge_code)
        raise SystemExit(0)
    if not rows:
        raise SystemExit(f"No results found in {config.EXPERIMENTS_DIR}")
    print(f"{len(rows)} versions from {len(manifests)} experiments -> {write_csv(rows)}")

    from src.figures import build_all
    ids = {i for i, m in manifests.items() if m.get("status") != "legacy" and not i.startswith("L")}
    runs, conds, order = summaries({i: manifests[i] for i in ids}, [r for r in rows if r["experiment"] in ids])
    print(f"run and condition tables -> {', '.join(str(p) for p in write_summary_csvs(runs, conds))}")
    figure_paths = build_all(RESULTS_DIR / "figures", conds, runs, order)
    print(f"{len(figure_paths)} figures -> {RESULTS_DIR / 'figures'}")
    print(f"performance log -> {write_performance_log(manifests, rows, figure_paths)}")
    if args.details:
        print_details(rows)

    bases = [resolve(args.base)] if args.base else sorted(i for i, m in manifests.items()
                                                 if m.get("level") == "baseline" and m.get("status") != "legacy")
    for b in bases:
        if b not in manifests:
            raise SystemExit(f"Experiment '{b}' not found")
        levels, seeds, table = comparison(b, manifests, rows)
        print_comparison(b, levels, seeds, table)
        print(f"  -> {write_html(b, manifests, levels, seeds, table)}")
