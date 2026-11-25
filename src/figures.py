"""Figures of the analysis (PNG, for the report). Built by analyze.py into results/figures/.

Every figure shows the mean of the run means AND each run as a dot, so a second or third run of a condition
(jan_1, mischa_1, ...) shows up without any change here.

Per chain (a baseline condition and the reflection conditions built on it, e.g. B4_strong -> R1_2a, R2_2b, R3_2c):
    chain_<base>_score.png        score, facts and finished runs per level (bar = mean of runs, dot = one run)
    chain_<base>_transitions.png  what each level did to v1 of the same seed: fixed / still ok / swapped / same error / broken
    chain_<base>_funnel.png       share of the seeds that reached each funnel stage, per level
    chain_<base>_facts.png        which of the 7 facts are right how often, per level
Overall:
    baselines.png                 the baseline series (B1 -> B4): score and facts per condition
    score_breakdown.png           what each component contributes to the score of each condition
    cost_vs_score.png             tokens per seed vs. score: mean per condition, range and dots of its runs

Colours: the validated reference palette of the dataviz guide (categorical slots in fixed order; status colours only
for the transitions, always with a label). One y-axis per chart; small multiples instead of two scales.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.checker import KEYS  # noqa: E402
from src.evaluate import FUNNEL  # noqa: E402
from src.metrics import COMPONENTS, SCORE_WEIGHTS  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
LEVEL_ORDER = ["baseline", "2a", "2b", "2c"]
LEVEL_COLOR = dict(zip(LEVEL_ORDER, SERIES))
LEVEL_MARKER = dict(zip(LEVEL_ORDER, ["o", "s", "D", "^"]))
STATUS = {"fixed": ("#0ca30c", "fixed"), "still_ok": (AXIS, "still ok"), "swapped": ("#fab219", "swapped error"),
          "same_error": ("#ec835a", "same error"), "broken": ("#d03b3b", "broken"), "infra": (MUTED, "infra failure")}
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def _style():
    plt.rcParams.update({
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 9,
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK, "axes.titlesize": 10,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.grid.axis": "y",
        "grid.color": GRID, "grid.linewidth": 0.8, "xtick.color": INK2, "ytick.color": INK2,
        "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False, "legend.fontsize": 8,
    })


def _short(cond):
    return cond.split("_")[0]


def _save(fig, out_dir, name):
    path = out_dir / name
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def _bars_with_runs(ax, labels, means, runs, colors, fmt="{:.0f}", ymax=100):
    """Bar = mean of the run means; one dot per run (slight jitter so several runs stay visible)."""
    x = range(len(labels))
    ax.bar(x, [m or 0 for m in means], width=0.55, color=colors, edgecolor=SURFACE, linewidth=2, zorder=2)
    for i, vals in enumerate(runs):
        n = len(vals)
        for j, v in enumerate(vals):
            if v is None:
                continue
            ax.scatter(i + (j - (n - 1) / 2) * 0.09, v, s=26, color=INK, edgecolor=SURFACE, linewidth=1.2, zorder=3)
    for i, m in enumerate(means):
        if m is not None:                       # above the bar and above every dot, so the label never covers a run
            top = max([m] + [v for v in runs[i] if v is not None])
            ax.text(i, min(top, ymax) + ymax * 0.03, fmt.format(m), ha="center", va="bottom", color=INK, fontsize=9)
    ax.set_xticks(list(x), labels)
    ax.set_ylim(0, ymax * 1.12)


# ---------------------------------------------------------------- per chain
def chain_score(out_dir, base, chain, conds, runs):
    """Score, facts and finished runs per level: three small multiples, one scale each (0-100)."""
    levels = [conds[c]["level"] for c in chain]
    labels = [f"{_short(c)}\n{conds[c]['level']}" for c in chain]
    colors = [LEVEL_COLOR.get(lv, SERIES[4]) for lv in levels]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=True)
    for ax, (key, title) in zip(axes, [("score", "Success score (0-100)"), ("facts", "Facts correct (strict, %)"),
                                       ("ran", "Code finished (%)")]):
        means = [conds[c]["sum"][key] for c in chain]
        dots = [[runs[u]["sum"][key] for u in conds[c]["runs"]] for c in chain]
        _bars_with_runs(ax, labels, means, dots, colors)
        ax.set_title(title, loc="left")
    n_runs = ", ".join(f"{_short(c)}: {len(conds[c]['runs'])}" for c in chain)
    fig.suptitle(f"Reflection levels on {base}   (bar = mean of the runs, dot = one run; runs per level: {n_runs})",
                 x=0.01, ha="left", color=INK2, fontsize=9)
    fig.tight_layout()
    return _save(fig, out_dir, f"chain_{base}_score.png")


def chain_transitions(out_dir, base, chain, conds):
    """Stacked bars: what each level did to v1 of the same seed, summed over all runs of the level."""
    levels = [c for c in chain if conds[c]["sum"]["transitions"] is not None]
    if not levels:
        return None
    fig, ax = plt.subplots(figsize=(8, 0.7 + 0.55 * len(levels)))
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    for i, c in enumerate(levels):
        t = conds[c]["sum"]["transitions"]
        left = 0
        for key in (*STATUS,):
            n = t.get(key, 0)
            if not n:
                continue
            colour, label = STATUS[key]
            ax.barh(i, n, left=left, height=0.5, color=colour, edgecolor=SURFACE, linewidth=2, zorder=2,
                    label=label if label not in ax.get_legend_handles_labels()[1] else None)
            ink = INK if key in ("swapped", "still_ok") else "#ffffff"
            ax.text(left + n / 2, i, str(n), ha="center", va="center", color=ink, fontsize=8, zorder=3)
            left += n
    ax.set_yticks(range(len(levels)), [f"{_short(c)} {conds[c]['level']}" for c in levels])
    ax.invert_yaxis()
    ax.set_xlabel("seeds (all runs of the level)")
    ax.set_title(f"What each level did to v1 of the same seed (base {base})", loc="left")
    ax.legend(ncol=6, loc="upper left", bbox_to_anchor=(0, -0.35 if len(levels) < 3 else -0.22))
    fig.tight_layout()
    return _save(fig, out_dir, f"chain_{base}_transitions.png")


def chain_funnel(out_dir, base, chain, conds):
    """Share of the seeds (without infra failures) that reached each funnel stage: grouped bars, one per level, so
    levels with the same values stay visible (lines would hide each other)."""
    levels = [c for c in chain if conds[c]["sum"]["real"]]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    width = min(0.8 / max(len(levels), 1), 0.2)
    for i, c in enumerate(levels):
        s = conds[c]["sum"]
        lv = conds[c]["level"]
        xs = [j + (i - (len(levels) - 1) / 2) * width for j in range(len(FUNNEL))]
        ax.bar(xs, [100 * s["stages"][k] / s["real"] for k in FUNNEL], width=width, color=LEVEL_COLOR.get(lv, SERIES[4]),
               edgecolor=SURFACE, linewidth=1.5, zorder=2, label=f"{_short(c)} {lv}")
    ax.set_xticks(range(len(FUNNEL)), FUNNEL, rotation=20, ha="right")
    ax.set_ylim(0, 105)
    ax.set_ylabel("% of seeds that reached the stage")
    ax.set_title(f"Funnel per level (base {base})", loc="left")
    ax.legend(ncol=len(levels), loc="upper right")
    fig.tight_layout()
    return _save(fig, out_dir, f"chain_{base}_funnel.png")


def chain_facts(out_dir, base, chain, conds):
    """Heatmap level x fact: % of the seeds with the correct value (sequential blue, value written in every cell)."""
    rows = [c for c in chain if conds[c]["sum"]["real"]]
    data = [[100 * conds[c]["sum"]["per_fact"][k] / conds[c]["sum"]["real"] for k in KEYS] for c in rows]
    fig, ax = plt.subplots(figsize=(10, 0.8 + 0.5 * len(rows)))
    ax.grid(False)
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            colour = SEQ[min(int(v / 100 * (len(SEQ) - 1) + 0.5), len(SEQ) - 1)]
            ax.add_patch(plt.Rectangle((j, i), 0.96, 0.9, color=colour))
            ax.text(j + 0.48, i + 0.45, f"{v:.0f}%", ha="center", va="center",
                    color="#ffffff" if v >= 50 else INK, fontsize=8)
    ax.set_xlim(0, len(KEYS))
    ax.set_ylim(len(rows), 0)
    ax.set_xticks([j + 0.48 for j in range(len(KEYS))], KEYS, rotation=20, ha="right")
    ax.set_yticks([i + 0.45 for i in range(len(rows))], [f"{_short(c)} {conds[c]['level']}" for c in rows])
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.set_title(f"Facts correct per level, % of seeds (base {base})", loc="left")
    fig.tight_layout()
    return _save(fig, out_dir, f"chain_{base}_facts.png")


# ---------------------------------------------------------------- overall
def baselines(out_dir, base_conds, conds, runs):
    """The baseline series in start order: score and facts per condition (small multiples, same 0-100 scale)."""
    if not base_conds:
        return None
    labels = [_short(c) for c in base_conds]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
    for ax, (key, title) in zip(axes, [("score", "Success score (0-100)"), ("facts", "Facts correct (strict, %)")]):
        _bars_with_runs(ax, labels, [conds[c]["sum"][key] for c in base_conds],
                        [[runs[u]["sum"][key] for u in conds[c]["runs"]] for c in base_conds],
                        [SERIES[0]] * len(base_conds))
        ax.set_title(title, loc="left")
    fig.suptitle("Baseline series: one change per step (bar = mean of the runs, dot = one run)",
                 x=0.01, ha="left", color=INK2, fontsize=9)
    fig.tight_layout()
    return _save(fig, out_dir, "baselines.png")


def score_breakdown(out_dir, order, conds):
    """Horizontal stacked bars: weight x component (points of the score); the bar length is the score."""
    rows = [c for c in order if conds[c]["sum"]["score"] is not None]
    fig, ax = plt.subplots(figsize=(9, 0.8 + 0.42 * len(rows)))
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    for i, c in enumerate(rows):
        left = 0
        for k, comp in enumerate(COMPONENTS):
            v = SCORE_WEIGHTS[comp] * (conds[c]["sum"][comp] or 0)
            ax.barh(i, v, left=left, height=0.5, color=SERIES[k], edgecolor=SURFACE, linewidth=2, zorder=2,
                    label=f"{comp} (weight {SCORE_WEIGHTS[comp]:.2f})" if i == 0 else None)
            left += v
        ax.text(left + 1, i, f"{conds[c]['sum']['score']:.1f}", va="center", color=INK, fontsize=8)
    ax.set_yticks(range(len(rows)), [f"{_short(c)} {conds[c]['level']}" for c in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 105)
    ax.set_xlabel("score points (weight x component, mean of the runs)")
    ax.set_title("What the score is made of, per condition", loc="left")
    ax.legend(ncol=3, loc="upper left", bbox_to_anchor=(0, -0.18 - 0.6 / max(len(rows), 1)))
    fig.tight_layout()
    return _save(fig, out_dir, "score_breakdown.png")


def cost_vs_score(out_dir, order, conds, runs):
    """Tokens per seed (x) vs. score (y). Per condition one large marker (mean of the runs, labelled) with a vertical
    line for the spread between its runs; every run as a small dot. Colour AND marker by level."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.grid(axis="both")
    seen = set()
    for n, c in enumerate(order):
        cs, lv = conds[c]["sum"], conds[c]["level"]
        if cs["score"] is None:
            continue
        colour, marker = LEVEL_COLOR.get(lv, SERIES[4]), LEVEL_MARKER.get(lv, "o")
        pts = [(runs[u]["sum"]["tokens"], runs[u]["sum"]["score"]) for u in conds[c]["runs"]
               if runs[u]["sum"]["score"] is not None]
        if len(pts) > 1:
            ys = [y for _, y in pts]
            ax.plot([cs["tokens"]] * 2, [min(ys), max(ys)], color=colour, linewidth=2, zorder=2)
            ax.scatter(*zip(*pts), s=14, color=colour, marker=marker, edgecolor=SURFACE, linewidth=0.8, zorder=3)
        ax.scatter(cs["tokens"], cs["score"], s=90 if lv == "2c" else 70, color=colour, marker=marker,
                   edgecolor=SURFACE, linewidth=1.5, zorder=4, label=lv if lv not in seen else None)
        seen.add(lv)
        ax.annotate(_short(c), (cs["tokens"], cs["score"]), textcoords="offset points", fontsize=8, color=INK2,
                    xytext=(8, 5 if n % 2 else -11))        # alternate above / below: neighbours do not collide
    ax.set_xlabel("tokens per seed (prompt + completion)")
    ax.set_ylabel("success score (0-100)")
    ax.set_ylim(0, 105)
    ax.set_title("Quality vs. cost: large marker = mean of the runs, line = range of the runs, small dot = one run",
                 loc="left")
    ax.legend(title="level", loc="upper left")          # top left stays empty: baselines are cheap and low
    fig.tight_layout()
    return _save(fig, out_dir, "cost_vs_score.png")


def build_all(out_dir, conds, runs, order):
    """All figures. conds/runs as built by analyze.summaries(); order = conditions in start order."""
    _style()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    chains = {c: [c] + sorted((o for o in order if conds[o]["base_condition"] == c), key=lambda o: conds[o]["level"])
              for c in order if conds[c]["level"] == "baseline"}
    for base, chain in chains.items():
        if len(chain) > 1:
            paths += [chain_score(out_dir, base, chain, conds, runs), chain_transitions(out_dir, base, chain, conds),
                      chain_funnel(out_dir, base, chain, conds), chain_facts(out_dir, base, chain, conds)]
    paths += [baselines(out_dir, list(chains), conds, runs), score_breakdown(out_dir, order, conds),
              cost_vs_score(out_dir, order, conds, runs)]
    return [p for p in paths if p]
