# HW1 — Structured Extraction Service

Extract structured JSON from dirty Jira tickets about **SAP → Databricks → Power BI** reporting (bugs + change requests), compare provider vs local models, justify production choice.

## Domain (short)

```
SAP Fiori  →  Databricks (Data Pull team)  →  Power BI report (DEV / PROD)
                         ↑
              Specification (financial analysts)
```

| Role | Responsibility |
|------|----------------|
| Financial analyst | Specification / acceptance |
| Report developer | Power BI report & dataset |
| Data Pull | SAP → Databricks pipelines |

Every ticket belongs to a **report** on **DEV/PROD**, references **SAP Fiori** + **spec**, and must declare reconciliation checks:

1. SAP vs Databricks  
2. Databricks vs Power BI  
3. Power BI vs **specification** (spec mismatch can be the root cause)

**Deployment rule:** fix/CR → deploy **DEV** → **approval** → deploy **PROD** (never skip).

Details: [`docs/DOMAIN.md`](docs/DOMAIN.md)

## Layout

```
data/
  raw/                 exported Jira tickets (BUGS-1 …)
  raw_index.json
  golden.json          10 manually labeled tickets (draft)
  reference/
    teams.json         developers, FA, Data Pull
    reports.json       reports ↔ SAP ↔ spec ↔ owners
    pipeline.json      stages where bugs can appear
    deployment.json    DEV → approval → PROD release path
docs/
  DOMAIN.md
prompts/               prompt versions + changelog (later)
results/               model outputs (later)
src/
  schema.py            Pydantic TicketExtraction
```

## Data status

- Jira project: `BUGS` on `nlamonova.atlassian.net`
- ~50+ tickets: classic dirty bugs + Power BI mismatches + **pipeline bugs** + **change requests** + deploy/approval cases
- Golden set: `BUGS-41` … `BUGS-50` (draft labels under new schema)

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# put GEMINI_API_KEY into .env (Google AI Studio)
```

Default provider in `config.yaml` is **Gemini** (`gemini-3.5-flash-lite`). OpenAI remains supported. For a stronger model, try `gemini-3.8-flash` or `gemini-pro-latest`.

## Run

```bash
# Gemini (cloud provider) — default config.yaml
python main.py --ids BUGS-41 BUGS-42

# Ollama (local #1) — install app, then: ollama pull llama3.2
python main.py --config config.ollama.yaml --ids BUGS-41 BUGS-42

# LM Studio (local #2, later) — start server on :1234 first
python main.py --config config.lmstudio.yaml --ids BUGS-41 BUGS-42

# alternate sampling profile
python main.py --sampling creative --limit 5
```

Outputs go to `results/<provider>_<prompt>_<sampling>_<timestamp>/`.

Evaluate a run against golden set:

```bash
python -c "from src.evaluate import compare_run; from pathlib import Path; print(compare_run(Path('results/<run_dir>')))"
```

## Status

- [x] Domain model + reference data (teams, reports, pipeline, deployment)
- [x] Schema: ticket type, report DEV/PROD, SAP Fiori, spec, ownership, reconciliation, deployment
- [x] Jira sample bugs + change requests exported to `data/raw`
- [x] Golden set reviewed
- [x] Baseline provider prompt + Gemini/OpenAI structured output (retry/timeout)
- [x] Shared interface for Ollama + LM Studio (code ready)
- [ ] Install Ollama, pull model, run local metrics
- [ ] LM Studio run (after Ollama)
- [x] Prompt v2 (Gemini field accuracy 79% → 89%)
- [x] Second sampling profile (`default` vs `creative`)
- [x] Full corpus run (53/53 valid JSON after 429 retries)
- [x] REPORT.md final write-up
