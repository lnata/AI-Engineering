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

### Склад об'єднаного корпусу HW1 + HW2 (`55` файлів → `53` унікальні у 5 форматах, `97` чанків, 0 PII)

Згідно з наскрізним планом [`docs/COURSE_ROADMAP.md`](docs/COURSE_ROADMAP.md) (*«Пошук по тікетах / спеках / reference; відповідь з посиланням на джерело»*), корпус об'єднує технічні специфікації/ранбуки HW2 та канонічні Jira-тікети й довідники з HW1 (без жодних змін сирих файлів `data/raw/` чи `data/reference/`):

| Формат | Сирих файлів | Унікальних | Що входить у корпус |
|--------|--------------|------------|---------------------|
| `PDF` | 12 | 11 | Специфікації KPI `SPEC-FIN-014`, `SPEC-FIN-021`, `SPEC-FIN-030` (`v1.0` + `v1.3` + mirror), `SPEC-FIN-041` (`v1.0` + `v1.2`), `SPEC-OPS-007` (`v1.0` + `v2.0`), `SPEC-OPS-011`, `SPEC-REV-012`, `SPEC-REV-019` |
| `DOCX` | 10 | 9 | Регламент релізів `POL-DEP-001` (`v1.0` + `v1.3`), playbooks тріажу `BUGS` (`+ backup`), 4-рівневої звірки та SLA закриття місяця, гайди Power BI / Parent-Child моделей |
| `HTML` | 10 | 10 | Внутрішній портал runbooks Airflow/Databricks (`dag_sap_*`), Power BI Gateway, каталог Data Lineage, postmortems інцидентів (`BUGS-41/49/50`), DQ gates |
| `MD` | 6 | 6 | Архітектурні рішення `ADR-001..003`, доменний глосарій, Release Notes Q1 2025, FAQ аналітиків |
| `JSON` *(HW1)* | 17 | 17 | Канонічні аналітичні Jira-тікети `data/raw/BUGS-41..53.json` (`doc_type="jira_ticket"`, із анонімізацією імен у ролі `RD-01`/`FA-01`/`DP-01`) + довідники `data/reference/{reports,pipeline,deployment,teams}.json` (`doc_type="reference"`) |
| **Разом** | **55** | **53** | **2 точні дублікати** відсіяно за `SHA-256 doc_hash`; **4 версіоновані пари** (`v1.0` deprecated проти актуальної `v1.2`/`v1.3`/`v2.0`) |

### Архітектура Ingestion та очищення (`src/hw2/`)

```text
data/hw2_corpus/raw/ (PDF/DOCX/HTML/MD) + data/raw/BUGS-41..53.json + data/reference/*.json
  → src/hw2/extractors.py + json_extractor.py (заголовки #, списки, таблиці | col |, анонімізація ролей)
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

#### Кількісне порівняння на всіх 53 унікальних документах (`data/hw2_corpus/chunking_comparison.json`)

| Метрика (`cl100k_base`) | Structure-Aware (`max=360, overlap=45`) | Fixed-Size Baseline (`size=240, overlap=40`) |
|-------------------------|-----------------------------------------|----------------------------------------------|
| Кількість чанків | **97** | 141 |
| Середній розмір (токенів) | **253.98** | 193.60 |
| Min / P50 / P95 / Max токенів | **121 / 252 / 345 / 353** | 41 / 240 / 240 / 241 |
| Розірвані таблиці (`broken_table_count`) | **0** | 59 (41.8% чанків) |
| Розрив посеред речення/слова (`mid_sentence_split_rate`) | **0.0% (0 / 97)** | 65.2% (92 / 141) |
| Змішування розділів (`cross_section_bleed_count`) | **0** | 18 |

Приклад реального дефекту `fixed-size` на `ADR-002_single_fx_conversion_in_databricks.md#01`: вікно токенів обриває українське слово на початку (`«рхітектурний інваріант...»`) і розрізає шапку таблиці посередині (`«| Критерій | Перерахунок у DAX (Від»`), а рядки таблиці опиняються в наступному чанку `#02` вже без заголовків колонок.

---

## HW2 — Крок 2. Індекс, Hybrid Search, Reranking та фільтри метаданих

Другий крок (чекпоінт Блоку 2) будує поверх `data/hw2_corpus/chunks.jsonl` (`79` чанків) повноцінний двоступеневий гібридний пошук із локальними багатомовними ONNX-моделями (**$0.00 / 1000 запитів**, без платних API-ключів).

### Швидкий запуск HW2 Step 2 (однією командою)

```bash
make hw2-step2
# або окремими командами:
python -m src.hw2.index
python -m src.hw2.search --query "Який поріг звірки у чинній SPEC-FIN-030?" --mode hybrid_rerank --only-latest
python -m src.hw2.eval_retrieval
make test
```

### Архітектура Індексу та Пошуку (`src/hw2/`)

1. **Dense Vector DB (`Qdrant` + багатомовні embeddings):**
   - Векторна база `qdrant-client` (локальна персистентна колекція `data/hw2_index/qdrant` + `:memory:` для швидких тестів; бінарне сховище в `.gitignore`, детермінований паспорт індексу в `data/hw2_index/index_meta.json`).
   - Модель ембеддингів: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (`384`-dim ONNX через `fastembed`, налаштовується через `HW2_EMBEDDING_MODEL`, також підтримуються `e5-*` префікси `query: ` / `passage: `).
   - У `payload` кожної точки Qdrant зберігаються текст і всі поля метаданих (`chunk_id`, `source`, `title`, `section`, `date`, `version`, `doc_hash`, `doc_type`, `format`, `report_id`, `is_latest`, `token_count`).
2. **Lexical Search (`BM25Okapi` з доменним токенізатором):**
   - Кастомний токенізатор `src/hw2/bm25_index.py` зберігає неподільними технічні ідентифікатори (`SPEC-FIN-030`, `mart.fact_revenue`, `DM_GWPipeline_Gateway_Timeout`, `v1.3`) разом із їхніми складовими та легким стемінгом українських/англійських слів.
3. **Reciprocal Rank Fusion (`RRF`, `k = 60`):**
   - Об'єднує ранги `Qdrant` та `BM25` за формулою \(\sum \frac{1}{60 + \text{rank}}\) і повертає прозорі оцінки кожного етапу (`vector_score`, `bm25_score`, `rrf_score`, `rerank_score`).
4. **Багатомовний Cross-Encoder Reranker + Фільтри метаданих (`SearchFilters`):**
   - Щоб уникнути пастки англомовних `ms-marco` моделей на кирилиці, використано багатомовний крос-енкодер **`BAAI/bge-reranker-v2-m3-int8`** (`fastembed` ONNX, налаштовується через `HW2_RERANKER_MODEL`).
   - Фільтри `SearchFilters` (`is_latest`, `doc_type`, `format`, `report_id`, `source`, `date_from`, `date_to`) застосовуються **синхронно і в Qdrant (`FieldCondition`), і в `BM25`** ще до `RRF`. Фільтр `is_latest=True` повністю відсікає архівні документи `v1.0` (`SPEC-FIN-030 v1.0`, `SPEC-FIN-041 v1.0`, `SPEC-OPS-007 v1.0`, `POL-DEP-001 v1.0`).

### Оцінка якості Retrieval на 18 питаннях (`evals/hw2_retrieval_evalset.json` → `evals/hw2_retrieval_results.json`)

Набір із **18 вручну перевірених питань** охоплює семантичні перефразування (`RET-01..03`), точні ідентифікатори SAP/Databricks/Gateway (`RET-04..07`), табличні KPI/SLA пороги (`RET-08..11`), версіоновані пастки `v1.0` vs `v1.2/v1.3/v2.0` (`RET-12..15`) та пошук історичних Jira-тікетів `BUGS-*` і довідників `data/reference/` (`RET-16..18`).

| Конфігурація | `Recall@1` | `Recall@3` | `Recall@5` | `MRR@5` | `Ver-Recall@1` (4 питання) | `Legacy v1.0 у Top-3` |
|--------------|-----------|-----------|-----------|--------|----------------------------|-----------------------|
| `vector_only` | 0.333 | 0.556 | 0.611 | 0.440 | 0.500 | 75.0% |
| `bm25_only` | 0.833 | 1.000 | 1.000 | 0.907 | 0.500 | 100.0% |
| `hybrid_rrf` | 0.611 | 0.778 | 0.944 | 0.727 | 0.500 | 100.0% |
| `hybrid_rrf_rerank` | 0.889 | 1.000 | 1.000 | 0.944 | 0.500 | 100.0% |
| **`hybrid_rrf_rerank_latest` (`is_latest=True`)** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **0.0%** |

**Ключові висновки з експерименту:**
- Тільки векторний пошук (`vector_only`) втрачає точні коди помилок і полів (`DM_GWPipeline_Gateway_Timeout`, `LOEVM`, `BO01`), даючи `Recall@5 = 0.600`.
- `hybrid_rrf` піднімає повноту кандидатів `Recall@5` до **`1.000`**, а багатомовний `BAAI/bge-reranker-v2-m3-int8` (`hybrid_rrf_rerank`) піднімає `MRR@5` з `0.680` до **`0.933`** (випереджаючи і чистий векторний пошук, і чистий `BM25`).
- Без фільтра метаданих застарілі редакції `v1.0` потрапляють у Top-3 у `75%–100%` версіонованих запитів. Додавання `is_latest=True` (`hybrid_rrf_rerank_latest`) знижує забруднення застарілими версіями до **`0.0%`** і доводить `Recall@1` та `MRR@5` до **`1.000`**.

---

## HW2 — Крок 3. RAG з цитуванням джерел, контролем контексту та «не знаю»

Третій крок будує поверх гібридного пошуку (`Qdrant + BM25 + RRF + BGE-M3 Reranker`) надійний генератор відповідей із жорсткою верифікацією посилань на джерела (документ і розділ), контролем бюджету токенів та дворівневим захистом від галюцинацій.

### Швидкий запуск HW2 Step 3 (однією командою)

```bash
make hw2-step3
# або окремими командами:
python -m src.hw2.rag --demo
python -m src.hw2.rag --question "Який поріг звірки діє у чинній SPEC-FIN-030?" --prompt-version v2 --max-context-tokens 1200 --only-latest
python main.py --hw2-rag --question "Який бюджет відряджень у маркетингу?"
make test
```

> За замовчуванням `--provider auto` використовує хмарну модель із `.env` (`GEMINI_API_KEY` → `gemini-3.5-flash-lite`, `OPENAI_API_KEY` → `gpt-4o-mini`, `OPENROUTER_API_KEY` → `openai/gpt-4o-mini`), а за відсутності ключів (локально чи в CI) автоматично перемикається на детермінований grounded-режим `extractive` (**$0.00**).

### Архітектура RAG-контуру (`src/hw2/` + `prompts/rag/`)

1. **Версіоновані промпти (`prompts/rag/v1`, `prompts/rag/v2`, [`prompts/rag/CHANGELOG.md`](prompts/rag/CHANGELOG.md)):**
   - **`v1` (Baseline):** базовий промпт генерації JSON зі списком `claims` та посиланнями `[S1]..[Sk]`.
   - **`v2` (Production Default):** ізоляція недовірених чанків у `<context>...</context>` із захистом від *Indirect Prompt Injection* (`OWASP LLM01`), явний перелік дозволених ID `{{allowed_source_ids}}`, обов'язковий формат цитат `[Si] (документ — розділ)`, контроль `is_latest=true/false` проти архівних `v1.0` та нульовий витік відповідей із тестсету.
2. **Детермінований Context Packer (`src/hw2/context_packer.py`):**
   - Рахує точні токени заголовка і тіла кожного блока `[Si]` через `tiktoken` (`cl100k_base`) і гарантує `used_tokens <= max_context_tokens` (за замовчуванням `1200` токенів).
   - Фіксує повну телеметрію пакування: `budget_tokens`, `used_tokens`, `included_sources`, `dropped_for_budget`, `dropped_for_low_relevance`.
3. **Дворівневий механізм «не знаю» (Abstention Gates):**
   - **Gate 1 (Pre-LLM Retrieval Gate):** якщо жоден чанк не проходить поріг релевантності крос-енкодера (`rerank_score < -4.5`) або лексико-семантичного перетину (наприклад, питання про бюджет маркетингу чи Tableau SSO), система миттєво повертає `abstained=True` (`«У наданих документах цієї інформації немає.»`) і витрачає **0 токенів LLM**.
   - **Gate 2 (In-LLM / Grounding Gate):** якщо питання-пастка містить реальний код спеки (`SPEC-FIN-030`), але питає про відсутню в корпусі метрику (наприклад, ставку податку на прибуток), генератор повертає `abstained=True`, `abstain_reason="missing_in_corpus"`, `claims=[]`.
4. **Верифікатор цитат + 1-Retry Schema/Citation Repair (`src/hw2/verifier.py`, `src/hw2/rag.py`):**
   - Перевіряє валідність схеми `RAGLLMResponse`, непорожність `claims` і `source_ids`, відсутність вигаданих посилань на кшталт `[S99]`, перевірку `finish_reason != "length"` та підставляє повні метадані `(документ — розділ)` у `RAGCitation`.
   - При помилці JSON, `ValidationError` або `CitationVerificationError` виконується **рівно 1 спроба repair** із передачею тексту помилки моделі (за патерном HW1).

### Економіка токенів та вартість на 1000 запитань

На демо-прогоні (`data/hw2_rag/sample_answers.json`, бюджет контексту `1200` токенів, `prompt v2`) середній обсяг запиту, що доходить до генератора, становить **~2 603 вхідних** (`system + <context> + <question>`) та **~421 вихідний** токен (а Gate-1 відсікання позадоменних питань коштує **0 токенів**):

| Режим / Модель | Embeddings + Reranker | Тариф LLM (Input / Output за 1M) | Оцінка вартості на **1000 питань** |
|----------------|-----------------------|----------------------------------|------------------------------------|
| Local `extractive` + `fastembed` ONNX | Локально ONNX ($0) | $0 / $0 | **$0.00** |
| Cloud `gemini-3.5-flash-lite` (Free Tier) | Локально ONNX ($0) | Free tier ($0) | **$0.00** |
| Cloud `gemini-3.5-flash-lite` (Paid Tier) | Локально ONNX ($0) | $0.30 / $2.50 | **~$1.83 / 1k питань** |
| Cloud `gpt-4o-mini` (OpenAI / OpenRouter) | Локально ONNX ($0) | $0.15 / $0.60 | **~$0.64 / 1k питань** |

---

## HW2 — Крок 4. Тестсет, Evals, Калібрування Судді та CI Gate

Четвертий крок замикає інженерний контур автоматичною оцінкою якості RAG у GitHub Actions CI ([`.github/workflows/hw2-evals.yml`](.github/workflows/hw2-evals.yml)) із блокуючим порогом (`exit 1`) та підсумковим звітом у [`REPORT.md`](REPORT.md).

### Повний запуск усього ДЗ-2 однією командою

```bash
make hw2-all          # Кроки 1–4: корпус → ingestion/chunks → Qdrant індекс → retrieval eval → RAG demo → RAG CI gate
# або лише Крок 4 + тести:
make hw2-step4
python main.py --hw2-eval
make test
```

### Склад Eval-пайплайну (`evals/` + `src/hw2/`)

1. **Тестсет із 28 вручну перевірених питань (`evals/hw2_rag_testset.json`):**
   - `12` стандартних і табличних питань (`PDF`, `DOCX`, `HTML`, `MD`),
   - `5` питань без відповіді в корпусі («не знаю»: `3` позадоменні + `2` внутрішньодоменні пастки зі справжніми кодами `SPEC-FIN-030` / `RUNBOOK-DBX-001`),
   - `7` питань із пастками (`4` версіоновані пастки `v1.0` vs `v1.2/v1.3/v2.0` із `forbidden_facts` + `3` пастки на схожі документи виторгу й SLA),
   - `4` наскрізні **cross-source HW1 + HW2** питання (`QA-25..28`), що вимагають одночасно процитувати історичний Jira-тікет (`BUGS-41`, `BUGS-44`, `BUGS-47`, `BUGS-53`) та відповідну специфікацію/регламент (`SPEC-FIN-014`, `SPEC-FIN-021`, `SPEC-FIN-041`, `POL-DEP-001` / `deployment.json`).
2. **Три рівні Scoring-функцій (`src/hw2/scorers.py`, `src/hw2/judge.py`, `src/hw2/calibrate_judge.py`):**
   - **Детерміновані метрики:** `abstention_accuracy`, `citation_source_hit` (включно з обов'язковими групами джерел `required_source_groups`), `citation_section_hit`, `fact_coverage`, `no_forbidden_facts`.
   - **LLM-as-a-Judge (`prompts/judge/v1/`) з калібруванням на 14 ручних прикладах (`evals/hw2_judge_calibration.json`):** точний збіг із ручною розміткою **`92.9%` (`13/14`)**, Каппа Коена **$\kappa = 0.887$** (`evals/hw2_judge_calibration_results.json`).
   - **Faithfulness (`score_faithfulness`):** перевіряє кожне окреме твердження в `claims` (числа, коди об'єктів, лексичне підґрунтя) проти процитованого блока `[Si]`.
3. **Результати на 28 питаннях (`evals/hw2_rag_eval_results.json`) та CI Gate:**

| Конфігурація | Overall | Abstention | Cite Source | Cite Section | Fact Coverage | No Forbidden (`v1.0`) | Faithfulness | Judge Score |
|--------------|---------|------------|-------------|--------------|---------------|-----------------------|--------------|-------------|
| `baseline_unfiltered_v1` | 0.578 | 0.893 | 0.429 | 0.357 | 0.217 | 0.964 | 1.000 | 0.161 |
| **`production_filtered_v2`** | **0.926** | **1.000** | **1.000** | **1.000** | **0.804** | **1.000** | **1.000** | **0.768** |
| *Поріг падіння у CI (`exit 1`)* | `>= 0.85` | `>= 0.90` | — | — | — | — | `>= 0.90` | Agreement `>= 0.85` |

Повний розбір метрик і 4 характерних помилок див. у [`REPORT.md`](REPORT.md).




