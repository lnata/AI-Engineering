# REPORT — Кейс 2: RAG на власних даних + Evals (HW2)

Цей звіт підсумовує архітектуру, метрики пошуку й генерації, калібрування судді та розбір помилок для другого зрізу проєкту **Analytics Ticket Copilot** (`SAP Fiori → Databricks → Semantic Models → Power BI + SPEC-*`). Повний архівний звіт Кейсу 1 (HW1) збережено нижче в розділі **«Архів Кейсу 1 (HW1)»**.

---

## 1. Огляд наскрізної архітектури HW1 + HW2 (Кроки 1–4)

Відповідно до [`docs/COURSE_ROADMAP.md`](docs/COURSE_ROADMAP.md) (*«Кейс 2. RAG: Пошук по тікетах / спеках / reference; відповідь з посиланням на джерело»*), пайплайн об'єднує технічні документи HW2 (`PDF`, `DOCX`, `HTML`, `MD`) із канонічними аналітичними Jira-тікетами HW1 (`data/raw/BUGS-41..53.json`) та довідниками (`data/reference/*.json`), не змінюючи жодного вхідного файлу HW1:

```text
data/hw2_corpus/raw/ (38 файлів) + data/raw/BUGS-41..53.json (13) + data/reference/*.json (4)
  → Ingestion + NFKC + Strip Headers/HTML Chrome + Role Anonymization + SHA-256 Dedup (53 унікальні доки)
  → Structure-Aware Chunking (cl100k_base, max=360, overlap=45 → 97 чанків + метадані)
  → Qdrant (MiniLM-L12-v2, 384d) + Domain BM25 + RRF (k=60) + BGE-M3 Reranker + SearchFilters
  → Context Packer (<=1200 токенів) + Gate 1/2 «не знаю» + Prompt v2 + 1-Retry Citation Verifier
  → Evals у GitHub Actions CI (28 питань: Детерміновані + Calibrated Judge + Faithfulness Gate)
```

- **Корпус і chunking (Крок 1):** `55` сирих файлів у **5 форматах** (`12 PDF`, `10 DOCX`, `10 HTML`, `6 MD`, `17 JSON`) → `53` унікальні документи після `SHA-256 doc_hash` дедуплікації (`2` точні дублікати відсіяно; `4` версіоновані пари `v1.0` проти `v1.2`/`v1.3`/`v2.0`). Персональні імена з HW1 JSON анонімізуються на етапі ingestion у ролі (`RD-01`, `FA-01`, `DP-01`). Структурний чанкінг (`97` чанків) дає **`0` розірваних таблиць** і **`0%` розривів речень** проти `59` розірваних таблиць (`41.8%`) та `65.2%` розривів речень у `fixed-size` (`data/hw2_corpus/chunking_comparison.json`).
- **Індекс і Hybrid Search (Крок 2):** локальний `Qdrant` + багатомовні ONNX-ембеддинги `paraphrase-multilingual-MiniLM-L12-v2` + доменний `BM25Okapi` + `RRF` + багатомовний крос-енкодер **`BAAI/bge-reranker-v2-m3-int8`** + синхронні фільтри `SearchFilters` (`is_latest`, `doc_type="jira_ticket"|"reference"|"kpi_spec"|...`, `report_id`, `date_from/to`).
- **RAG з джерелами (Крок 3):** `tiktoken` пакувальник у бюджеті `1200` токенів, ізоляція `<context>` у `prompts/rag/v2`, дворівнева відмова «не знаю» (`Gate 1` + `Gate 2`), cross-source синтез `BUGS-* + SPEC-*` із верифікацією `[Si] (документ — розділ)` та **1-retry repair**.

---

## 2. Метрики якості Retrieval (Крок 2 — 18 питань, `evals/hw2_retrieval_results.json`)

| Конфігурація | `Recall@1` | `Recall@3` | `Recall@5` | `MRR@5` | `Ver-Recall@1` (4 верс. питання) | Забруднення `v1.0` у Top-3 |
|--------------|-----------|-----------|-----------|--------|----------------------------------|----------------------------|
| `vector_only` | 0.333 | 0.556 | 0.611 | 0.440 | 0.500 | 75.0% |
| `bm25_only` | 0.833 | 1.000 | 1.000 | 0.907 | 0.500 | 100.0% |
| `hybrid_rrf` | 0.611 | 0.778 | 0.944 | 0.727 | 0.500 | 100.0% |
| `hybrid_rrf_rerank` | 0.889 | 1.000 | 1.000 | 0.944 | 0.500 | 100.0% |
| **`hybrid_rrf_rerank_latest` (`is_latest=True`)** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **0.0%** |

---

## 3. Метрики наскрізного RAG та калібрування судді (Крок 4 — 28 питань)

Тестсет `evals/hw2_rag_testset.json` (`28` вручну вивірених питань) містить:
- **12 стандартних / табличних питань** (`QA-01..12` по `PDF`, `DOCX`, `HTML`, `MD`);
- **5 питань без відповіді в корпусі («не знаю»):** 3 позадоменні (`QA-13..15`) + 2 внутрішньодоменні пастки зі справжніми кодами `SPEC-FIN-030` / `RUNBOOK-DBX-001` (`QA-16..17`);
- **7 питань із пастками:** 4 на застарілі версії `v1.0` проти чинних (`QA-18..21`) + 3 на схожі документи виторгу й SLA (`QA-22..24`);
- **4 cross-source питання HW1 + HW2 (`QA-25..28`):** вимагають одночасно процитувати історичний Jira-тікет (`BUGS-41`, `BUGS-44`, `BUGS-47`, `BUGS-53`) та відповідну специфікацію/регламент (`SPEC-FIN-014`, `SPEC-FIN-021`, `SPEC-FIN-041`, `POL-DEP-001` / `deployment.json`).

### 3.1 Порівняння Baseline (`v1`, без фільтра) проти Production (`v2`, `hybrid_rerank + is_latest=True`)

*(Джерело: `evals/hw2_rag_eval_results.json`, поріг проходження CI: `Overall >= 0.85`, `Faithfulness >= 0.90`, `Abstention >= 0.90`)*

| Метрика | `baseline_unfiltered_v1` (`vector`, `520` tok, `v1`) | `production_filtered_v2` (`hybrid_rerank`, `is_latest`, `1200` tok, `v2`) | Приріст ($\Delta$) |
|---------|------------------------------------------------------|---------------------------------------------------------------------------|--------------------|
| **Overall Composite Score** | 0.578 | **0.926** | **+0.348** |
| **Abstention Accuracy («не знаю»)** | 0.893 | **1.000** | **+10.7 pp** |
| **Citation Source Hit Rate** | 0.429 | **1.000** | **+57.1 pp** |
| **Citation Section Hit Rate** | 0.357 | **1.000** | **+64.3 pp** |
| **Required Fact Coverage** | 0.217 | **0.804** | **+58.7 pp** |
| **No Forbidden / Legacy `v1.0` Facts** | 0.964 | **1.000** | **+3.6 pp** |
| **Claim Faithfulness** | 1.000 | **1.000** | **0.0 pp (100% grounded)** |
| **Calibrated Judge Mean Score** | 0.161 | **0.768** | **+60.7 pp** |

Розріз `Overall Composite Score` за категоріями у `production_filtered_v2`: `standard = 0.942`, `unanswerable_out_of_domain = 1.000`, `unanswerable_in_domain_trap = 1.000`, `trap_similar_docs = 0.942`, `trap_legacy_version = 0.877`, `cross_source_ticket_spec = 0.823` (`100%` подвійне цитування `BUGS-* + SPEC-*/POL-*`).

### 3.2 Калібрування судді на ручній розмітці (`evals/hw2_judge_calibration_results.json`)

На `14` вручну розмічених прикладах (`evals/hw2_judge_calibration.json`: ідеальні відповіді, часткові відповіді, просочування `v1.0`, галюцинація цифр, відсутні цитати, хибна та коректна відмова):
- **Точний збіг (`Exact Agreement`):** **`13 / 14` (`92.9%`)** при порозі CI `>= 85.0%`.
- **Коефіцієнт згоди Каппа Коена ($\kappa$):** **`0.887`** (*almost perfect agreement*), середня абсолютна похибка балу `MAD = 0.036`.
- **Єдина розбіжність (`CAL-14`):** людина поставила `pass (1.0)`, зарахувавши синонім *«попереднє тестове середовище»* як еквівалент `DEV`, тоді як суворий рубричний суддя поставив консервативний `partial (0.5)` через відсутність буквального маркера `DEV` (жодного хибного пропуску `fail → pass`: усі `6/6` помилкових відповідей відбраковано).

---

## 4. Розбір 4 характерних помилок (Що мало бути → Що вийшло → Чому → Висновки)

1. **Просочування скасованої редакції `v1.0` у відповідь (`QA-20` та `QA-21` у `baseline_unfiltered_v1`)**
   - *Що мало бути:* зріз `wh.inventory_snapshot` до `05:30 UTC`, SLA `2 години`, включення `in_transit_qty` (`SPEC-OPS-007 v2.0`).
   - *Що вийшло:* baseline процитував `SPEC-OPS-007_v1.0_daily_inventory_legacy.pdf` із застарілим часом `23:00 UTC` (спрацював тригер `forbidden_facts`, `judge = fail`).
   - *Чому:* архівний документ містить ті самі ключові терміни й має високу косинусну близькість до запиту.
   - *Як виправлено:* синхронний фільтр метаданих `is_latest=True` у `Qdrant` та `BM25` повністю усунув `v1.0` із видачі (`NoForb = 1.000`).

2. **Втрата точних технічних кодів при суто векторному пошуку (`QA-05`, `QA-08`, `QA-09`, `QA-22` у `baseline_unfiltered_v1`)**
   - *Що мало бути:* знаходження `RUNBOOK-DQ-007` за назвою перевірки `chk_margin_sap_delta` та `SPEC-REV-012` за кодами `BO01` / `G2`.
   - *Що вийшло:* `vector_only` повернув загальні чанки про маржу й клієнтів (`Citation Source Hit = 0.500`).
   - *Чому:* рідкісні snake_case / SAP коди розбиваються subword-токенізатором ембеддера і «розмиваються» в dense-векторі.
   - *Як виправлено:* доменний `BM25` + `RRF` + багатомовний `BAAI/bge-reranker-v2-m3-int8` підняли `Citation Source Hit` до **`1.000` (`24/24`)**.

3. **Відповідь замість «не знаю» на внутрішньодоменних пастках (`QA-16`, `QA-17` у `baseline_unfiltered_v1`)**
   - *Що мало бути:* чесна відмова `«У наданих документах цієї інформації немає.»` на питання про ставку податку на прибуток у `SPEC-FIN-030` та розмір `Snowflake Warehouse` у `RUNBOOK-DBX-001`.
   - *Що вийшло:* через наявність у запиті реальних кодів `SPEC-FIN-030` і `RUNBOOK-DBX-001` документи пройшли `Gate 1`, і наївний `v1` генератор видав перший речення спеки замість відмови (`Abstention = 0.875`).
   - *Як виправлено:* `Gate 2` (перевірка специфічних термінів запиту в контексті + суворе правило відмови в `prompts/rag/v2`) підняв `Abstention Accuracy` до **`1.000` (`5/5`)**.

4. **Неповне покриття багатофактних питань локальним екстрактивним генератором (`QA-19`, `QA-20`, `QA-22` у `production_filtered_v2`)**
   - *Що мало бути:* у `QA-19` навести і шар `mart.fact_payments`, і дату курсу `payment_date`; у `QA-22` — і `BO01`, і `G2`.
   - *Що вийшло:* ретрівер знайшов правильний чанк `[S1]` (`CiteSrc = 1.000`), але безкоштовний локальний `ExtractiveRAGGenerator` (обмежений 2 реченнями/рядками за лексичним перетином) у `QA-19` обрав вступне речення з назвою звіту замість булетів із `payment_date` (`FactCov = 0.861` по корпусу).
   - *Що покращити далі (план на Блок 3):* у продакшні з підключеним `GEMINI_API_KEY` (`gemini-3.5-flash-lite` + `prompts/rag/v2`) LLM синтезує всі булети й рядки таблиці `[S1]` в одну повну відповідь; для офлайн-режиму варто додати `MMR`-диверсифікацію вибраних речень, щоб уникати дублювання вступної тези.

---

## 5. Економіка рішення (вартість на 1000 питань) та висновки

| Компонент / Режим | Модель | Вартість на **1000 питань** | Примітка |
|-------------------|--------|-----------------------------|----------|
| Індексація + Пошук + Rerank | `MiniLM-L12-v2` + `BM25` + `bge-reranker-v2-m3-int8` (ONNX) | **$0.00** | Локально на CPU (включно з GitHub Actions CI) |
| Генерація (Offline / CI default) | `ExtractiveRAGGenerator` + `CalibratedRubricJudge` | **$0.00** | Детермінований прогін у CI без секретів |
| Генерація (Cloud Production) | `gemini-3.5-flash-lite` (~2.6k in + ~421 out tok/q) | **~$1.83** *(Free tier: $0)* | Найкращий синтез багатоходових табличних відповідей |
| Альтернатива Cloud | `gpt-4o-mini` ($0.15 / $0.60 за 1M) | **~$0.64** | Економний хмарний резерв через OpenAI / OpenRouter |

---

# Архів Кейсу 1 (HW1) — Structured Extraction Service

## 0. Review notes (2026-10-19)

Feedback from course review — what we found and fixed:

1. **Golden / schema inventing facts** — yes, earlier golden had fields the model
   cannot take from the ticket (`dataset_name`, invented CDS ids, spec titles,
   normalized `anna.k` logins, deploy statuses with no progress in text).  
   **Fix:** `data/golden.json` cleaned to only grounded labels; optional unknowns → `null`;
   status `reviewed`.

2. **Prompt v2 leaking golden answers** — yes: v2 listed concrete report titles
   that appear in the golden set.  
   **Fix:** `prompts/v2` rewritten (v2.1) without those examples; rules say “only this ticket”.

3. **Unequal model comparison** — partially true:
   - Fair table (`results/comparison_v1.json`): Gemini / Ollama / LM Studio all on **prompt v1**.
   - Production pick used Gemini **v2**, while local configs still defaulted to **v1**.
   - Schema delivery differs by stack: Gemini = native `response_json_schema`;
     local = compact JSON contract in the user message + `json_object` / plain JSON
     (full JSON Schema hangs small local models). Same Pydantic validation after parse.  
   **Fix:** local configs now default to **v2**; this caveat documented below.

## 0.1 Review notes (2026-10-27)

1. **Gemini repair was a blind retry (−1)** — on `ValidationError` the same request was re-sent.  
   **Fix:** `src/llm/gemini_client.py` now makes exactly one repair call with the original request,
   the invalid JSON and the validation errors; a second failure is final (`repair failed: ...`).
   Backoff retries remain only for `429` / quota / timeout / unavailable. Tests: `make test`.
2. **Gemini `timeout_sec` ignored** — **Fix:** passed to the SDK via `HttpOptions(timeout=ms)`.
3. **Local models not re-run on v2.1** — **Fix (Ollama):** re-run on golden with prompt v2.1
   (`results/ollama_v2_default_20261027T103403Z/`, side-by-side in `results/comparison_v2_1.json`).
   LM Studio is a desktop GUI app and was not re-run on the headless review VM; its row stays on v1.

## 1. Task & data

Domain: Jira tickets about **SAP Fiori → Databricks (Data Pull) → Power BI** reporting, plus **specification** ownership and **DEV → approval → PROD** deployment.

| Item | Value |
|------|--------|
| Source | Jira project `BUGS` (`nlamonova.atlassian.net`) |
| Corpus | 53 dirty tickets in `data/raw/` (bugs + change requests) |
| Golden set | 10 tickets `BUGS-41`…`BUGS-50` in `data/golden.json` |
| Schema | `src/schema.py` (`TicketExtraction`) |
| Prompts | `prompts/v1`, `prompts/v2` (+ `prompts/CHANGELOG.md`) |

## 2. Models & configs compared

| Model | Runtime | Config | Prompt | Sampling |
|-------|---------|--------|--------|----------|
| Gemini `gemini-3.5-flash-lite` | cloud API | `config.yaml` | v1, **v2** | `default` (T=0.0), `creative` (T=0.4) |
| Ollama `llama3.2` | local | `config.ollama.yaml` | v1 | `default` |
| LM Studio `llama-3.2-3b-instruct` | local `:1235` | `config.lmstudio.yaml` | v1 | `default` |

Shared interface: `src/llm/base.py` + provider clients. Gemini and local clients make exactly one schema-repair attempt on validation failure: the follow-up prompt contains the original request, the model's invalid JSON and the Pydantic validation errors; if the repaired output is still invalid the ticket is recorded as failed (`repair failed: ...`). Transient errors (`429`, timeouts) are still retried with backoff. Covered by `tests/test_gemini_repair.py`.

## 3. Metrics on golden set

### 3.1 Model × prompt × sampling

> **Fair provider comparison (same prompt v1):** `results/comparison_v1.json`.  
> **After review cleanup (golden + prompt v2.1):** Gemini and Ollama re-run below (`results/comparison_v2_1.json`). LM Studio not re-run (GUI app, no headless host); its config defaults to **v2**.

| Model × prompt × sampling | Valid JSON | Field accuracy | Latency p50 | Latency p95 | Est. cost / 1k docs | Same prompt? | Schema path |
|---------------------------|------------|----------------|-------------|-------------|---------------------|--------------|-------------|
| Gemini × **v2.1** × **default** (post-review) | **100%** | **93.6%** | ~2.5s | ~7.7s | ~$1.6 / $0 free | — | native JSON Schema |
| Ollama × **v2.1** × default (2026-10-27) | **100%** | **62.1%** | ~39.4s† | ~42.5s† | **$0** | yes (vs Gemini v2.1) | compact contract + json_object |
| Gemini × v2 × default (pre-review) | 100% | 88.6% | ~1.9s | ~2.3–2.6s | ~$1.62 / $0 | vs local: no* | native JSON Schema |
| Gemini × v1 × default | 100% | 79.3% | ~2.0s | ~2.6s | ~$1.6 / $0 | **yes** | native JSON Schema |
| Ollama × v1 × default | 90% | 51.4% | ~8.7s | ~19.5s | **$0** | **yes** | compact contract + json_object |
| LM Studio × v1 × default | 80% | 38.6% | ~7.8s | ~18.5s | **$0** | **yes** | compact contract + plain JSON |

\*Local configs previously stayed on v1 while production pick used Gemini v2 — fixed in `config.ollama.yaml` / `config.lmstudio.yaml`.  
Post-review run folder: `results/gemini_v2_default_20261019T163625Z/` · metrics: `results/prompt_v2_after_review.json`.  
†Ollama v2.1 ran CPU-only (4 vCPU, no GPU) on the review VM, so its latency is not comparable to the earlier v1 local runs. v1 rows were scored against the pre-cleanup golden set (rescored on the current golden: Gemini v1 85.0%, Ollama v1 50.0%).

**Cost method (Gemini):** avg ~885 input + ~542 output tokens/ticket on golden  
([Flash-Lite list price](https://ai.google.dev/gemini-api/docs/pricing): $0.30 / $2.50 per 1M tokens).  
Homework runs used the **free tier** (billed **$0**); paid-tier estimate ≈ **$1.50–1.62 per 1k docs**.

Field accuracy = exact match rate across scored schema paths vs `data/golden.json`
(`ticket_type`, `priority`, `issue_category`, report/spec/ownership/reconciliation/deployment key fields, `is_blocker`).

**Sampling takeaway:** on this schema-heavy extraction task, `creative` (T=0.4) did **not** beat `default` (T=0.0) on golden accuracy — keep temperature 0 for production.

Result folders:
- `results/gemini_v1_default_20261015T192358Z/`
- `results/gemini_v2_default_20261015T202136Z/`
- `results/gemini_v2_creative_20261015T202815Z/`
- `results/ollama_v1_default_20261015T201620Z/`
- `results/lmstudio_v1_default_20261015T201805Z/`
- `results/gemini_v2_default_20261015T202845Z/` — **full corpus** (53 tickets)
- summary tables: `results/comparison_v1.json`, `results/prompt_v1_vs_v2.json`, `results/full_run_meta.json`

### 3.2 Prompt v1 → v2 (Gemini)

| Field / metric | v1 | v2 | Δ |
|----------------|----|----|---|
| Overall field accuracy | 79.3% | **88.6%** | +9.3 pp |
| `priority` | 40% | **80%** | +40 pp |
| `report.name` | 20% | **80%** | +60 pp |
| `deployment.status` | 30% | 40% | +10 pp |

v2 added explicit rules for priority bands, human report titles (not `.pbix`), and deployment state machine.

### 3.3 Full corpus run (Gemini × v2 × default)

| Metric | Value |
|--------|--------|
| Tickets | 53 / 53 |
| Valid JSON | **100%** (after retrying 13 rate-limited `429` calls) |
| Latency p50 / p95 | ~1.8s / ~2.3s |
| Output | `results/gemini_v2_default_20261015T202845Z/` |

Note: Free-tier Gemini rate limits appear under burst load; client now backs off longer on `429`.

## 4. Characteristic errors (3–5)

1. **`deployment.status` under-predicted as `not_started`**  
   Golden often encodes a lifecycle state (e.g. `approved_for_prod`, `deployed_to_prod`) that is only weakly present in the raw ticket text. Model stays conservative → false negatives on status.  
   *Example:* `BUGS-49`, `BUGS-50` (v2 still misses status).

2. **`report.name` near-miss naming**  
   Model returns a close variant (`Gross Margin` vs `Gross Margin Dashboard`, `Inventory Report` vs `Inventory Snapshot`). Semantically right, exact-match metric fails.

3. **Local models break enums / nesting**  
   Ollama/LM Studio invent enum values (`priority=unknown`), put names into lists, or omit required nested fields → invalid JSON after repair, or valid JSON with low field accuracy.

4. **`priority` medium vs high on CRs / softer bugs**  
   Even on Gemini v2, some CR/spec tickets stay `medium` while golden marks `high` (`BUGS-42`, `BUGS-47`) — severity without explicit blocker language is ambiguous.

5. **LM Studio prose wrapping**  
   Small instruct models wrap JSON in markdown/commentary; mitigated by JSON extraction + one repair pass, but still more failed tickets than Gemini.

## 5. Production choice

**Ship Gemini (`gemini-3.5-flash-lite`) + prompt `v2`/`v2.1` + sampling `default` (temperature 0).**

Why: best field accuracy (**93.6%** after grounded golden; 88.6% pre-review), perfect schema validity on the golden set, ~2–3s latency, and acceptable API cost. On the **same prompt v1**, Gemini still beats Ollama/LM Studio (79% vs 51%/39%); on the **same prompt v2.1**, Gemini beats Ollama 93.6% vs 62.1% (both 100% valid JSON). Schema wiring is not identical (native JSON Schema vs compact contract) — a known platform limit for small local models; validation target is still the same Pydantic model.

**I would change this decision if:**
- we must run fully offline / air-gapped → then Ollama with a larger instruct model (8B+) and stricter post-validation;
- Gemini cost/quota becomes painful at high volume → try a stronger paid Flash/Pro tier only if quality drops, or hybrid (local prefilter + Gemini on low-confidence);
- `deployment.status` becomes a hard SLA field → enrich tickets with explicit workflow fields in Jira instead of inferring from free text.

## 6. How to reproduce

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set GEMINI_API_KEY

make run        # full corpus — Gemini × v2 × default (config default)
make golden     # golden set only
make creative   # golden + creative sampling
make ollama     # local baseline
make lmstudio   # second local baseline
make eval RUN=results/gemini_v2_default_20261015T202136Z
```

Default config (`config.yaml`) is already **prompt v2 + sampling default** — production choice.
