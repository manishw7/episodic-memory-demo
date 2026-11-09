.PHONY: help setup run test eval smoke clean

help:
	@echo "make setup   - create .venv and install dependencies"
	@echo "make run     - start the Streamlit app"
	@echo "make test    - run the 27 unit tests (no Ollama needed)"
	@echo "make eval    - run the full 51-case benchmark (real models)"
	@echo "make smoke   - real-model smoke test of the demo conversation"
	@echo "make clean   - remove caches and generated benchmark output"

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt
	@test -f .env || cp .env.example .env

run:
	. .venv/bin/activate && streamlit run app.py

test:
	. .venv/bin/activate && python -m pytest -q

eval:
	. .venv/bin/activate && python evaluate.py

smoke:
	. .venv/bin/activate && python -m memory_engine

clean:
	rm -rf __pycache__ .pytest_cache
	rm -f eval_results/eval_report.md eval_results/raw.json
