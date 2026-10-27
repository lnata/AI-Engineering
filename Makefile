.PHONY: setup run golden creative ollama lmstudio eval test help

PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

help:
	@echo "make setup     — venv + deps"
	@echo "make run       — full corpus (Gemini v2, default sampling)"
	@echo "make golden    — golden set BUGS-41..50"
	@echo "make creative  — golden set with creative sampling"
	@echo "make ollama    — local Ollama on golden set"
	@echo "make lmstudio  — local LM Studio on golden set"
	@echo "make eval RUN=results/<dir>  — score a run vs golden.json"
	@echo "make test      — unit tests"

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

test:
	$(PYTHON) -m pytest tests -q
