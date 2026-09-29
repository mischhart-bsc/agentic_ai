# Agentic AI – Setup
1. Start Docker Desktop, install Ollama, `ollama pull qwen3:4b-instruct`
2. `ollama create qwen3-4b-instruct-16k -f Modelfile`   (= qwen3 instruct with 16k context)
3. `python -m venv .venv` and activate, `pip install -r requirements.txt`
4. `docker build -t agai-sandbox sandbox/`
5. `python get_data.py`
6. `python smoke_test.py`  -> Output + runs/<id>/trace.jsonl
