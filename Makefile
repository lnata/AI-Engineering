.PHONY: setup run golden creative ollama lmstudio eval hw2-corpus hw2-ingest hw2-step1 hw2-index hw2-eval-retrieval hw2-step2 hw2-rag-demo hw2-step3 hw2-calibrate-judge hw2-eval-rag hw2-step4 hw2-all test help

PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

help:
	@echo "make setup               — venv + deps"
	@echo "make run                 — HW1 full corpus (Gemini v2, default sampling)"
	@echo "make golden              — HW1 golden set BUGS-41..50"
	@echo "make creative            — HW1 golden set with creative sampling"
	@echo "make ollama              — HW1 local Ollama on golden set"
	@echo "make lmstudio            — HW1 local LM Studio on golden set"
	@echo "make eval RUN=results/<dir> — HW1 score a run vs golden.json"
	@echo "make hw2-step1           — HW2 Step 1: corpus + ingestion & chunking"
	@echo "make hw2-step2           — HW2 Step 2: Qdrant index + 15-query retrieval eval"
	@echo "make hw2-step3           — HW2 Step 3: Qdrant index + cited RAG demo"
	@echo "make hw2-step4           — HW2 Step 4: judge calibration + 24-query RAG CI gate"
	@echo "make hw2-all             — HW2 single-command end-to-end pipeline (Steps 1–4)"
	@echo "make test                — run all HW1 + HW2 Step 1–4 pytest suites"

setup:
	python3.11 -m venv .venv || python3 -m venv .venv
	$(PIP) install -r requirements.txt
	@test -f .env || cp .env.example .env
	@echo "Edit .env and set GEMINI_API_KEY (optional for HW2 local mode)"

run:
	$(PYTHON) main.py

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
	$(PYTHON) -m src.hw2.eval_rag --min-overall-score 0.85 --min-faithfulness 0.90 --min-abstention-accuracy 0.90 --min-judge-agreement 0.85

hw2-step4: hw2-index hw2-calibrate-judge hw2-eval-rag

hw2-all: hw2-step1 hw2-step2 hw2-rag-demo hw2-eval-rag

test:
	$(PYTHON) -m pytest tests -q
