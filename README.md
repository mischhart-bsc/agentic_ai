# Agentic AI – Setup
1. Start Docker Desktop, install Ollama, `ollama pull qwen3:4b`
2. `python -m venv .venv` and activate, `pip install -r requirements.txt`
3. `docker build -t agai-sandbox sandbox/`
4. `python get_data.py`
5. `python smoke_test.py`  -> Output + runs/<id>/trace.jsonl
