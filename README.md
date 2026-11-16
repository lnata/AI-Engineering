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
tests/             pytest (Gemini schema repair)
REPORT.md          сравнение моделей / продакшн-выбор
```

## Checklist HW1

- [x] Схема ≥6 полей, enum + nested object (`src/schema.py`)
- [x] Baseline-промпт + provider structured output (retry/timeout)
- [x] Локальная модель через общий интерфейс (Ollama + LM Studio)
- [x] ≥2 профиля семплинга в конфиге
- [x] Метрики на golden: field accuracy, % valid, latency p50/p95, cost/1k
- [x] Промпты v1/v2 + changelog; schema repair ×1 → failed (Gemini и локальные модели:
  при `ValidationError` модели уходит исходный запрос + её невалидный JSON + текст ошибки;
  вторая неудача → `ok=false`). Тесты: `make test` (`tests/test_gemini_repair.py`)
- [x] Лог: model, prompt version, sampling на каждый результат
- [x] `REPORT.md` + `README.md` + `.env.example` (ключи не в git)

---

## HW2 — Кейс 2 («RAG на власних даних + Evals»): Крок 1. Корпус і chunking

Другий етап проєкту **Analytics Ticket Copilot** розширює сервіс із HW1 базою знань технічної документації ланцюжка **`SAP Fiori → Databricks (stg.* / mart.* / wh.*) → Parent/Child Semantic Models → Power BI + SPEC-*`**.

### Швидкий запуск HW2 Step 1 (однією командою, без API-ключів)

```bash
make hw2-step1
# або окремими кроками:
python scripts/build_hw2_corpus.py
python -m src.hw2.ingest
make test
```

### Склад корпусу (`data/hw2_corpus/raw/` — 38 файлів → 36 унікальних у 4 форматах, 0 PII)

| Формат | Сирих файлів | Унікальних | Що входить у корпус |
|--------|--------------|------------|---------------------|
| `PDF` | 12 | 11 | Специфікації KPI `SPEC-FIN-014`, `SPEC-FIN-021`, `SPEC-FIN-030` (`v1.0` + `v1.3` + mirror), `SPEC-FIN-041` (`v1.0` + `v1.2`), `SPEC-OPS-007` (`v1.0` + `v2.0`), `SPEC-OPS-011`, `SPEC-REV-012`, `SPEC-REV-019` |
| `DOCX` | 10 | 9 | Регламент релізів `POL-DEP-001` (`v1.0` + `v1.3`), playbooks тріажу `BUGS` (`+ backup`), 4-рівневої звірки та SLA закриття місяця, гайди Power BI / Parent-Child моделей |
| `HTML` | 10 | 10 | Внутрішній портал runbooks Airflow/Databricks (`dag_sap_*`), Power BI Gateway, каталог Data Lineage, postmortems інцидентів (`BUGS-41/49/50`), DQ gates |
| `MD` | 6 | 6 | Архітектурні рішення `ADR-001..003`, доменний глосарій, Release Notes Q1 2025, FAQ аналітиків |
| **Разом** | **38** | **36** | **2 точні дублікати** відсіяно за `SHA-256 doc_hash`; **4 версіоновані пари** (`v1.0` deprecated проти актуальної `v1.2`/`v1.3`/`v2.0`) |

### Архітектура Ingestion та очищення (`src/hw2/`)

```text
data/hw2_corpus/raw/ (PDF / DOCX / HTML / MD)
  → src/hw2/extractors.py   (заголовки #, списки, таблиці у GFM Markdown | col |)
  → src/hw2/cleaning.py     (Unicode NFKC, cp1251/BOM, strip PDF headers/footers & HTML chrome,
                             склеювання переносів зі збереженням SPEC-FIN-030 / non-GAAP, PII masking)
  → src/hw2/ingest.py       (SHA-256 raw_hash + канонічний doc_hash дедуплікатор → manifest.json)
  → src/hw2/chunking.py     (structure-aware chunking + contextual header → chunks.jsonl)
  → src/hw2/comparison.py   (кількісне порівняння з fixed-size baseline → chunking_comparison.json)
```

Кожен чанк у `data/hw2_corpus/chunks.jsonl` містить усі 5 обов'язкових полів рубрики (`source`, `title`, `section`, `date`, `version`, `doc_hash`) плюс додаткові поля для фільтрації у Кроці 2 (`chunk_id`, `doc_type`, `format`, `report_id`, `is_latest`, `token_count`).

### Обґрунтування стратегії chunking та порівняння з Fixed-Size

Для корпусу специфікацій та runbooks обрано **Structure-Aware Chunking** з токенізатором `tiktoken` (`cl100k_base`), бюджетом **`max_tokens = 360`** та легким перекриттям **`overlap_tokens = 45`** на межі цілих речень:

1. **Межі розділів (`##`):** документи `SPEC-*`, `POL-*` та `RUNBOOK-*` мають чітку структуру («Призначення», «Формула KPI / Мапінг», «Критерії звірки»). Різання строго по заголовках гарантує **0 змішувань сусідніх розділів (`cross-section bleed = 0`)**.
2. **Атомарність таблиць:** усі таблиці мапінгу полів SAP ↔ Databricks і правил DAX мають обсяг `102–298` токенів. Бюджет `360` токенів дозволяє зберігати кожну Markdown-таблицю цілісною разом із її шапкою `| --- |`, тоді як `fixed-size` розриває майже половину чанків посеред таблиці, відриваючи назву метрики від формули.
3. **Contextual Header (`[Title | vX.Y (Date) | Section]`):** кожен чанк отримує префікс із кодом документа, версією, датою чинності та розділом. Завдяки цьому короткий абзац про `inbound_freight_eur` або `in_transit_qty` не втрачає прив'язки до `SPEC-FIN-030 v1.3` під час векторного та BM25-пошуку.

#### Кількісне порівняння на всіх 36 унікальних документах (`data/hw2_corpus/chunking_comparison.json`)

| Метрика (`cl100k_base`) | Structure-Aware (`max=360, overlap=45`) | Fixed-Size Baseline (`size=240, overlap=40`) |
|-------------------------|-----------------------------------------|----------------------------------------------|
| Кількість чанків | **79** | 110 |
| Середній розмір (токенів) | **258.97** | 201.03 |
| Min / P50 / P95 / Max токенів | **121 / 260 / 345 / 353** | 41 / 240 / 240 / 241 |
| Розірвані таблиці (`broken_table_count`) | **0** | 52 (47.3% чанків) |
| Розрив посеред речення/слова (`mid_sentence_split_rate`) | **0.0% (0 / 79)** | 71.8% (79 / 110) |
| Змішування розділів (`cross_section_bleed_count`) | **0** | 18 |

Приклад реального дефекту `fixed-size` на `ADR-002_single_fx_conversion_in_databricks.md#01`: вікно токенів обриває українське слово на початку (`«рхітектурний інваріант...»`) і розрізає шапку таблиці посередині (`«| Критерій | Перерахунок у DAX (Від»`), а рядки таблиці опиняються в наступному чанку `#02` вже без заголовків колонок.

