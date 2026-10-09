"""Step 2: reflection levels on the frozen v1 of a baseline experiment.

Per seed: load v1 (prompt, answer, run artifacts) from the base experiment -> critique -> revise
-> execute the revised code -> evaluate. v1 is never regenerated: the same seed does not give the same
long answer twice (tested 2026-10-09), so every level must start from the stored v1 to be comparable.

    2a  critic sees only its own code
    2b  + artifacts of the v1 run (exit code, stdout, traceback, plot descriptions)
    2c  + external check of the RESULTS_JSON claims (supported / refuted / missing)

Run:  python step2_reflection.py --exp E02_2a_schema --level 2a --base E01_baseline_schema
      python step2_reflection.py --exp E03_2b_schema --level 2b --base E01_baseline_schema
      python step2_reflection.py --exp E04_2c_schema --level 2c --base E01_baseline_schema
      (seeds default to all seeds of the base; same command again = resume)
"""
import argparse
import json

import config
from src.evaluate import evaluate_version, summary_line
from src.experiment import Experiment, load, parse_seeds
from src.feedback import build_feedback, prompt_texts
from src.llm import chat
from src.runner import run_code
from src.trace import Case
from step1_baseline import extract_code

LEVELS = ("2a", "2b", "2c")
CRITIQUE = (config.ROOT / "prompts" / "step2a_critique.txt").read_text(encoding="utf-8")
REVISE = (config.ROOT / "prompts" / "step2a_revise.txt").read_text(encoding="utf-8")


def load_v1(base_id, seed):
    """The frozen v1 of one seed: folder, generate messages, answer and result. None if it is not usable."""
    case_dir = config.EXPERIMENTS_DIR / base_id / "cases" / f"s{seed}"
    v1_dir = case_dir / "v1"
    if not (v1_dir / "result.json").exists():
        return None
    result = json.loads((v1_dir / "result.json").read_text(encoding="utf-8"))
    entries = [json.loads(l) for l in (case_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    gen = [e for e in entries if e["kind"] == "llm" and e.get("version") == "v1" and e.get("stage") == "generate"]
    if result.get("llm_error") or not gen:
        return None                     # v1 has no answer (LLM failed): nothing to reflect on
    return {"dir": v1_dir, "messages": gen[-1]["messages"], "answer": gen[-1]["response"], "result": result}


def reflect(case, base_id, v1, level):
    """critique -> revise -> execute -> evaluate for one seed. Returns the result of this level."""
    ver = case.version(level, parent=f"{base_id}/s{case.seed}/v1")
    feedback = build_feedback(level, v1["dir"])
    ver.save("feedback.md", feedback)

    critique_prompt = f"{feedback}\n\n{CRITIQUE}" if feedback else CRITIQUE
    messages = v1["messages"] + [{"role": "assistant", "content": v1["answer"]},
                                 {"role": "user", "content": critique_prompt}]
    try:
        critique = chat(ver, messages, label="critique", seed=case.seed)
        ver.save("critique.md", critique)
        # a new list, so the messages of the critique call stay as they were sent
        messages = messages + [{"role": "assistant", "content": critique}, {"role": "user", "content": REVISE}]
        answer = chat(ver, messages, label="revise", seed=case.seed)
    except Exception as e:
        # LLM call failed (timeout, connection lost, ...): record it and go on with the next seed
        ver.log("error", stage="reflection", error_type=type(e).__name__, error=str(e))
        return evaluate_version(ver, None, llm_error=type(e).__name__)

    ver.save("response.md", answer)
    code = extract_code(answer)
    res = run_code(ver, code) if code is not None else None
    return evaluate_version(ver, code, res)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, help="experiment id, e.g. E02_2a_schema")
    ap.add_argument("--level", required=True, choices=LEVELS)
    ap.add_argument("--base", required=True, help="baseline experiment whose v1 is reflected on")
    ap.add_argument("--seeds", help="default: all seeds of the base, e.g. 101-105")
    ap.add_argument("--note", default="", help="free text for the manifest")
    args = ap.parse_args()

    base = load(args.base)
    if base["level"] != "baseline":
        raise SystemExit(f"--base must be a baseline experiment, '{args.base}' has level {base['level']}")
    seeds = parse_seeds(args.seeds) if args.seeds else base["seeds"]
    missing = [s for s in seeds if s not in base["seeds"]]
    if missing:
        raise SystemExit(f"Seeds {missing} are not in the base experiment {args.base}")

    prompts = {"critique": CRITIQUE, "revise": REVISE, **prompt_texts(args.level)}
    exp = Experiment(args.exp, args.level, prompts, seeds, base=args.base,
                     data_context=base["data_context"], note=args.note)

    print(f"Experiment {exp.id}: level {args.level} on {args.base}, seeds {exp.seeds}")
    for seed in exp.seeds:
        if exp.is_done(seed, args.level):
            print(f"s{seed} {args.level}  already done, skipped")
            continue
        v1 = load_v1(args.base, seed)
        if v1 is None:
            print(f"s{seed} {args.level}  skipped: v1 of {args.base} has no usable answer")
            continue
        print(summary_line(reflect(Case(exp, seed), args.base, v1, args.level)))
    exp.finish()
    print(f"\nDone: {exp.dir}")
    