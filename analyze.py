"""Analyse all experiments: one CSV row per version, and per baseline a comparison seed x level.

Run:  python analyze.py                          all experiments; comparison for every baseline
      python analyze.py --base E01_baseline_schema   only this baseline and the levels built on it
      python analyze.py --legacy                 also include experiments/_legacy (migrated old runs)

Writes:
  results/versions.csv                  one row per version (experiment, seed, version, exit, error, facts, cost)
  results/comparison_<base>.html        table seed x level, transitions vs. v1, means and cost per level

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
from statistics import mean

import config

RESULTS_DIR = config.ROOT / "results"
COLUMNS = ["experiment", "base", "level", "data_context", "case", "seed", "version", "parent", "llm_error",
           "exit_code", "error_category", "error_line", "results_json_found", "fact_score", "n_plots",
           "llm_calls", "prompt_tokens", "completion_tokens", "llm_seconds", "exec_seconds", "truncated"]


# ---------------------------------------------------------------- collect
def experiment_dirs(legacy=False):
    root = config.EXPERIMENTS_DIR
    dirs = [d for d in sorted(root.glob("*")) if (d / "experiment.json").exists()]
    if legacy:
        dirs += [d for d in sorted((root / "_legacy").glob("*")) if (d / "experiment.json").exists()]
    return dirs


def collect(legacy=False):
    """(manifests by id, rows): one row per result.json of every experiment."""
    manifests, rows = {}, []
    for d in experiment_dirs(legacy):
        m = json.loads((d / "experiment.json").read_text(encoding="utf-8"))
        manifests[m["id"]] = m
        for res_file in sorted(d.glob("cases/*/*/result.json")):
            r = json.loads(res_file.read_text(encoding="utf-8"))
            cost = r.get("cost") or {}
            rows.append({
                "experiment": m["id"], "base": m.get("base"), "level": m.get("level"),
                "data_context": m.get("data_context"), "case": res_file.parent.parent.name,
                "seed": r.get("seed"), "version": res_file.parent.name, "parent": r.get("parent"),
                **{k: r.get(k) for k in ("llm_error", "exit_code", "error_category", "error_line",
                                         "results_json_found", "fact_score", "n_plots")},
                **{k: cost.get(k) for k in ("llm_calls", "prompt_tokens", "completion_tokens",
                                            "llm_seconds", "exec_seconds", "truncated")},
                "path": str(res_file.parent),
            })
    return manifests, rows


def write_csv(rows):
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / "versions.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


# ---------------------------------------------------------------- compare
def ran(r):
    return r is not None and r["exit_code"] == 0


def infra(r):
    """Failures that are not the model's fault (Docker down, LLM timeout): excluded from transitions."""
    return r is not None and (r["error_category"] in ("infra_docker", "llm_timeout", "llm_error"))


def transition(v1, lv):
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
    return "same_error" if v1["error_category"] == lv["error_category"] else "swapped"


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
        line = (f"  {l:<9} ran {st['ran']}/{st['n'] - st['infra']}  facts {facts:>4}  "
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
    path = RESULTS_DIR / f"comparison_{base_id}.html"
    path.write_text(page, encoding="utf-8")
    return path


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="only this baseline experiment and its levels")
    ap.add_argument("--legacy", action="store_true", help="include migrated old runs in versions.csv")
    args = ap.parse_args()

    manifests, rows = collect(args.legacy)
    if not rows:
        raise SystemExit(f"No results found in {config.EXPERIMENTS_DIR}")
    print(f"{len(rows)} versions from {len(manifests)} experiments -> {write_csv(rows)}")

    bases = [args.base] if args.base else sorted(i for i, m in manifests.items()
                                                 if m.get("level") == "baseline" and m.get("status") != "legacy")
    for b in bases:
        if b not in manifests:
            raise SystemExit(f"Experiment '{b}' not found")
        levels, seeds, table = comparison(b, manifests, rows)
        print_comparison(b, levels, seeds, table)
        print(f"  -> {write_html(b, manifests, levels, seeds, table)}")
