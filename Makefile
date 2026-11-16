.PHONY: setup run golden creative ollama lmstudio eval hw2-corpus hw2-ingest hw2-step1 test help

PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

help:
	@echo "make setup       — venv + deps"
	@echo "make run         — HW1 full corpus (Gemini v2, default sampling)"
	@echo "make golden      — HW1 golden set BUGS-41..50"
	@echo "make creative    — HW1 golden set with creative sampling"
	@echo "make ollama      — HW1 local Ollama on golden set"
	@echo "make lmstudio    — HW1 local LM Studio on golden set"
	@echo "make eval RUN=results/<dir> — HW1 score a run vs golden.json"
	@echo "make hw2-corpus  — HW2 generate 38 raw domain docs (PDF/DOCX/HTML/MD)"
	@echo "make hw2-ingest  — HW2 ingest, clean, deduplicate & chunk corpus"
	@echo "make hw2-step1   — HW2 full Step 1 pipeline (corpus + ingest)"
	@echo "make test        — run all HW1 + HW2 pytest suites"

setup:
	python3.11 -m venv .venv || python3 -m venv .venv
	$(PIP) install -r requirements.txt
	@test -f .env || cp .env.example .env
	@echo "Edit .env and set GEMINI_API_KEY"

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

test:
	$(PYTHON) -m pytest tests -q
