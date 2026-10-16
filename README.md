# HW1 — Structured Extraction Service

Сервис вытягивает структурированный JSON из «грязных» Jira-тикетов про отчётность
**SAP Fiori → Databricks → Power BI** (bugs + change requests), сравнивает cloud и
локальные модели и обосновывает выбор для продакшна.

Опис проєкту на курс: [`docs/PROJECT.md`](docs/PROJECT.md)  
Сквозной план (кейсы 1–4): [`docs/COURSE_ROADMAP.md`](docs/COURSE_ROADMAP.md)  
Домен и роли: [`docs/DOMAIN.md`](docs/DOMAIN.md)  
Отчёт с метриками: [`REPORT.md`](REPORT.md)

## Quick start (одна команда после setup)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # → вписать GEMINI_API_KEY
make run               # или: python main.py
```

`make run` / `python main.py` гоняет **весь корпус** (53 тикета) на Gemini + prompt **v2** + sampling **default**.

Другие цели Makefile: `make golden` · `make creative` · `make ollama` · `make lmstudio` · `make eval RUN=results/<dir>`

## Данные

| Item | Value |
|------|--------|
| Источник | Jira `BUGS` (`nlamonova.atlassian.net`) |
| Корпус | 53 тикета в `data/raw/` (RU+EN, опечатки, пропуски) |
| Golden set | 10 вручную размеченных: `BUGS-41`…`BUGS-50` → `data/golden.json` |
| Схема | `src/schema.py` (`TicketExtraction`, enums + nested objects) |

## Модели

| Provider | Model | Config |
|----------|-------|--------|
| Gemini (cloud) | `gemini-3.5-flash-lite` | `config.yaml` |
| Ollama (local) | `llama3.2` | `config.ollama.yaml` |
| LM Studio (local) | `llama-3.2-3b-instruct` | `config.lmstudio.yaml` |

Промпты: `prompts/v1`, `prompts/v2` + [`prompts/CHANGELOG.md`](prompts/CHANGELOG.md).  
Семплинг в конфиге: `default` (T=0.0) и `creative` (T=0.4).

## Layout

```
data/raw/          исходные тикеты
data/golden.json   golden set
data/reference/    teams, reports, pipeline, deployment
prompts/v1|v2/     system + user templates
results/           выходы прогонов + метрики
src/               schema, clients, extract, evaluate
REPORT.md          сравнение моделей / продакшн-выбор
```

## Checklist HW1

- [x] Схема ≥6 полей, enum + nested object (`src/schema.py`)
- [x] Baseline-промпт + provider structured output (retry/timeout)
- [x] Локальная модель через общий интерфейс (Ollama + LM Studio)
- [x] ≥2 профиля семплинга в конфиге
- [x] Метрики на golden: field accuracy, % valid, latency p50/p95, cost/1k
- [x] Промпты v1/v2 + changelog; schema repair ×1 → failed
- [x] Лог: model, prompt version, sampling на каждый результат
- [x] `REPORT.md` + `README.md` + `.env.example` (ключи не в git)
