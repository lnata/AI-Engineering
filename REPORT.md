# REPORT — Structured Extraction Service (HW1)

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
