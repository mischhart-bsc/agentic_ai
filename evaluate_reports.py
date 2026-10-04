"""Bewertet die Report-Guete aller Runs (objektiv + optional LLM-Judge).

Run:  python evaluate_reports.py                     alle Runs in runs/, Zusammenfassung pro Config
      python evaluate_reports.py --details           + eine Zeile pro Run
      python evaluate_reports.py --run <run_id>      ein Run, alle Einzelmetriken
      python evaluate_reports.py --config step1_schema
      python evaluate_reports.py --judge             zusaetzlich LLM-Judge (braucht Ollama)
      python evaluate_reports.py --human-template    Vorlage human_scores.csv zum Selbstbewerten
      python evaluate_reports.py --agreement         Mensch vs. Judge vergleichen

Schreibt runs/<run_id>/evaluation.json und evaluation_summary.csv (eine Zeile pro Run).
Gewichte und Kriterien: src/report_eval.py (WEIGHTS) und src/judge.py (RUBRIC).
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from statistics import mean, stdev

import config
from src.report_eval import WEIGHTS, evaluate_run

DIMS = list(WEIGHTS)
SUMMARY_CSV = config.ROOT / "evaluation_summary.csv"
HUMAN_CSV = config.ROOT / "human_scores.csv"


def finished_runs():
    """Alle Run-Ordner mit 'result'-Eintrag (Smoke-Tests und abgebrochene Runs fallen weg)."""
    out = []
    for trace in sorted(config.RUNS_DIR.glob("*/trace.jsonl")):
        if '"kind": "result"' in trace.read_text(encoding="utf-8"):
            out.append(trace.parent)
    return out


def fmt(v):
    return "  -  " if v is None else f"{v:5.2f}"


def stats(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return "  -        "
    sd = stdev(vals) if len(vals) > 1 else 0.0
    return f"{mean(vals):.2f} ± {sd:.2f}"


def print_run(ev):
    print(f"\n=== {ev['run_id']}  ({ev['config']})   overall {fmt(ev['overall'])}")
    for d in DIMS:
        print(f"  {d:<13} {fmt(ev['dimensions'][d])}   (Gewicht {WEIGHTS[d]:.2f})")
    if ev.get("judge"):
        print(f"  judge         {ev['judge'].get('scores')}")
    print("  Flags:")
    for f in ev["flags"] or ["-"]:
        print(f"    - {f}")
    print("  Details:")
    for d, det in ev["details"].items():
        print(f"    [{d}] " + json.dumps(det, ensure_ascii=False, default=str))
    if ev["report_text"]:
        print("  Report-Text:\n    " + ev["report_text"][:1500].replace("\n", "\n    "))


def summarize(name, evs, details=False):
    print(f"\n=== {name}  ({len(evs)} runs)")
    print(f"  {'overall':<13} {stats([e['overall'] for e in evs])}")
    for d in DIMS:
        print(f"  {d:<13} {stats([e['dimensions'][d] for e in evs])}")
    js = [e["judge"]["score_0_1"] for e in evs if (e.get("judge") or {}).get("score_0_1") is not None]
    if js:
        print(f"  {'judge (0-1)':<13} {stats(js)}   (n={len(js)})")

    flags = Counter(f.split(":")[0] if f.startswith("Absturz") else f for e in evs for f in e["flags"])
    print("  Haeufigste Flags:")
    for f, n in flags.most_common(12):
        print(f"    {n:>2}/{len(evs):<2} {f}")

    if details:
        print("  runs:")
        for e in evs:
            dims = " ".join(f"{d[:4]}={fmt(e['dimensions'][d]).strip():>4}" for d in DIMS)
            print(f"    {e['run_id']:<40} overall={fmt(e['overall']).strip():>4}  {dims}")


def write_csv(evs):
    with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run_id", "config", "overall", *DIMS, "judge_0_1", "n_flags", "flags"])
        for e in evs:
            w.writerow([e["run_id"], e["config"], e["overall"], *[e["dimensions"][d] for d in DIMS],
                        (e.get("judge") or {}).get("score_0_1"), len(e["flags"]), " | ".join(e["flags"])])


def human_template(evs):
    from src.judge import CRITERIA
    if HUMAN_CSV.exists():
        print(f"{HUMAN_CSV.name} existiert schon - nicht ueberschrieben.")
        return
    with open(HUMAN_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run_id", "rater", *CRITERIA, "comment"])
        for e in evs:
            if e["report_text"]:
                w.writerow([e["run_id"], "", *[""] * len(CRITERIA), ""])
    print(f"Vorlage geschrieben: {HUMAN_CSV.name} (nur Runs mit Report-Text). Skala 1-5, siehe src/judge.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="nur diesen Run (run_id), mit allen Details")
    ap.add_argument("--config", help="nur diese Config, z.B. step1_schema")
    ap.add_argument("--details", action="store_true", help="eine Zeile pro Run")
    ap.add_argument("--judge", action="store_true", help="LLM-Judge zusaetzlich ausfuehren (Ollama)")
    ap.add_argument("--human-template", action="store_true", help="human_scores.csv anlegen")
    ap.add_argument("--agreement", action="store_true", help="human_scores.csv mit judge.json vergleichen")
    args = ap.parse_args()

    if args.agreement:
        from src.judge import agreement
        if not HUMAN_CSV.exists():
            raise SystemExit("human_scores.csv fehlt - zuerst --human-template und ausfuellen.")
        res = agreement(HUMAN_CSV, config.RUNS_DIR)
        print(json.dumps(res, indent=2) if res else "Keine gemeinsamen Bewertungen gefunden (judge.json fehlt?).")
        raise SystemExit(0)

    dirs = finished_runs()
    if args.run:
        dirs = [d for d in dirs if d.name == args.run]
    evs = []
    for d in dirs:
        ev = evaluate_run(d)
        if args.config and ev["config"] != args.config:
            continue
        if args.judge and ev["report_text"]:
            from src.judge import judge_report
            print(f"Judge: {d.name} ...")
            ev["judge"] = judge_report(d, ev["report_text"])
        elif (d / "judge.json").exists():
            ev["judge"] = json.loads((d / "judge.json").read_text(encoding="utf-8"))
        (d / "evaluation.json").write_text(json.dumps(ev, indent=2, ensure_ascii=False, default=str),
                                           encoding="utf-8")
        evs.append(ev)

    if not evs:
        raise SystemExit("Keine passenden Runs gefunden.")
    if args.human_template:
        human_template(evs)
        raise SystemExit(0)

    if args.run:
        print_run(evs[0])
    else:
        groups = defaultdict(list)
        for e in evs:
            groups[e["config"]].append(e)
        for name, group in sorted(groups.items()):
            summarize(name, group, details=args.details)
        write_csv(evs)
        print(f"\nCSV: {SUMMARY_CSV.name}   Einzelheiten: python evaluate_reports.py --run <run_id>")
