.PHONY: setup run hw1-run golden creative ollama lmstudio eval hw2-corpus hw2-ingest hw2-step1 hw2-index hw2-eval-retrieval hw2-step2 hw2-rag-demo hw2-step3 hw2-calibrate-judge hw2-eval-rag hw2-step4 hw2-llm hw2-all test help

PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

help:
	@echo "make setup               — venv + deps + .env from .env.example"
	@echo "make run                 — HW2 default single-command pipeline (cloud if .env set, else local $0)"
	@echo "make hw2-llm             — HW2 live cloud LLM run (requires GEMINI_API_KEY / OPENAI_API_KEY in .env)"
	@echo "make hw2-all             — HW2 full rebuild from raw docs (Steps 1–4)"
	@echo "make hw2-step1..hw2-step4 — run individual HW2 steps"
	@echo "make hw1-run             — HW1 full corpus extraction (Gemini v2, default sampling)"
	@echo "make golden              — HW1 golden set BUGS-41..50"
	@echo "make creative            — HW1 golden set with creative sampling"
	@echo "make ollama / lmstudio   — HW1 local models on golden set"
	@echo "make eval RUN=results/<dir> — HW1 score a run vs golden.json"
	@echo "make test                — run all HW1 + HW2 pytest suites"

setup:
	python3.11 -m venv .venv || python3 -m venv .venv
	$(PIP) install -r requirements.txt
	@test -f .env || cp .env.example .env
	@echo "Setup ready. Optional: edit .env and set GEMINI_API_KEY for live cloud LLM runs."

run:
	$(PYTHON) main.py

hw1-run:
	$(PYTHON) main.py --hw1

golden:
	$(PYTHON) main.py --ids BUGS-41 BUGS-42 BUGS-43 BUGS-44 BUGS-45 BUGS-46 BUGS-47 BUGS-48 BUGS-49 BUGS-50

creative:
	$(PYTHON) main.py --sampling creative --ids BUGS-41 BUGS-42 BUGS-43 BUGS-44 BUGS-45 BUGS-46 BUGS-47 BUGS-48 BUGS-49 BUGS-50

ollama:
	$(PYTHON) main.py --config config.ollama.yaml --ids BUGS-41 BUGS-42 BUGS-43 BUGS-44 BUGS-45 BUGS-46 BUGS-47 BUGS-48 BUGS-49 BUGS-50

lmstudio:
	$(PYTHON) main.py --config config.lmstudio.yaml --ids BUGS-41 BUGS-42 BUGS-43 BUGS-44 BUGS-45 BUGS-46 BUGS-47 BUGS-48 BUGS-49 BUGS-50

eval:
	@test -n "$(RUN)" || (echo "Usage: make eval RUN=results/<dir>"; exit 1)
	$(PYTHON) -c "from pathlib import Path; from src.evaluate import compare_run; import json; print(json.dumps(compare_run(Path('$(RUN)')), indent=2))"

hw2-corpus:
	$(PYTHON) scripts/build_hw2_corpus.py

hw2-ingest:
	$(PYTHON) -m src.hw2.ingest

hw2-step1: hw2-corpus hw2-ingest

hw2-index:
	$(PYTHON) -m src.hw2.index

hw2-eval-retrieval:
	$(PYTHON) -m src.hw2.eval_retrieval

hw2-step2: hw2-index hw2-eval-retrieval

hw2-rag-demo:
	$(PYTHON) -m src.hw2.rag --demo

hw2-step3: hw2-index hw2-rag-demo

hw2-calibrate-judge:
	$(PYTHON) -m src.hw2.calibrate_judge --min-agreement 0.85

hw2-eval-rag:
	$(PYTHON) -m evals.run_evals --min-overall-score 0.85 --min-faithfulness 0.90 --min-abstention-accuracy 0.90 --min-judge-agreement 0.85

hw2-step4: hw2-index hw2-calibrate-judge hw2-eval-rag

hw2-llm:
	$(PYTHON) main.py --hw2-llm

hw2-all: hw2-step1 hw2-step2 hw2-rag-demo hw2-eval-rag

test:
	$(PYTHON) -m pytest tests -q
