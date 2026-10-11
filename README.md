# Agentic AI – Setup
1. Start Docker Desktop, install Ollama, `ollama pull qwen3:4b-instruct`
2. `ollama create qwen3-4b-instruct-16k -f Modelfile`   (= qwen3 instruct with 16k context)
3. `python -m venv .venv` and activate, `pip install -r requirements.txt`
4. `docker build -t agai-sandbox sandbox/`
5. `python get_data.py`
6. `python smoke_test.py`  -> Output + runs/<id>/trace.jsonl

## Workflow after setup
- Step 1 baseline: `python step1_baseline.py` (blind) or `python step1_baseline.py --schema`, 5 runs each -> `runs/<id>/`
- Cost and fact metrics per config: `python analyze_runs.py [--details]`
- Report quality (5 dimensions, flags): `python evaluate_reports.py [--details | --run <id>]`
- Read the traces: `runs/<id>/trace.jsonl` (one line per LLM call/execution), generated code in `runs/<id>/code/`
- Log of decisions and results: `docs/logbook.md`, checklist: `arbeitsprotokoll.txt`

