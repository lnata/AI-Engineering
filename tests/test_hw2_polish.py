"""Tests for HW2 audit polish: 429 retry/cache, polarity faithfulness, evals.scorers, and CLI defaults."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

import evals
from evals import scorers as eval_scorers
from src.hw2.llm_runtime import (
    LLMDiskCache,
    call_with_llm_retry,
    parse_retry_after_seconds,
    resolve_cloud_provider,
    resolve_gemini_model,
)
from src.hw2.models import PackedContext, PackedSource, RAGAnswer, RAGCitation, RAGClaim


def test_evals_package_exports_all_three_scoring_layers():
    assert callable(evals.score_deterministic)
    assert callable(evals.score_faithfulness)
    assert callable(evals.build_judge)
    assert callable(eval_scorers.run_judge_calibration)
    assert callable(eval_scorers.compute_cohens_kappa)


def test_faithfulness_penalizes_negation_and_polarity_inversion():
    packed = PackedContext(
        budget_tokens=600,
        used_tokens=120,
        gate_passed=True,
        included_sources=[
            PackedSource(
                source_id="S1",
                chunk_id="SPEC-FIN-030_v1.3_gross_margin_rules.pdf#01",
                source="data/hw2_corpus/raw/SPEC-FIN-030_v1.3_gross_margin_rules.pdf",
                title="SPEC-FIN-030",
                section="2. Формула Gross Margin % та виключення оборотів",
                version="1.3",
                date="2025-03-15",
                is_latest=True,
                score=4.2,
                packed_tokens=120,
                formatted_block=(
                    "[S1] source=data/hw2_corpus/raw/SPEC-FIN-030_v1.3_gross_margin_rules.pdf\n"
                    "У версії 1.3 витрати inbound_freight_eur обов'язково включаються до COGS, а поріг становить 0.15%."
                ),
            )
        ],
        context_text="У версії 1.3 витрати inbound_freight_eur обов'язково включаються до COGS, а поріг становить 0.15%.",
    )
    cite = RAGCitation(
        source_id="S1",
        chunk_id="SPEC-FIN-030_v1.3_gross_margin_rules.pdf#01",
        source="data/hw2_corpus/raw/SPEC-FIN-030_v1.3_gross_margin_rules.pdf",
        title="SPEC-FIN-030",
        section="2. Формула Gross Margin % та виключення оборотів",
        version="1.3",
        date="2025-03-15",
        is_latest=True,
    )

    # Polarity flip ("НЕ включаються" vs affirmative source) despite identical numbers & words
    inverted = RAGAnswer(
        abstained=False,
        answer="У версії 1.3 витрати inbound_freight_eur не включаються до COGS, а поріг становить 0.15% [S1].",
        claims=[
            RAGClaim(
                statement="У версії 1.3 витрати inbound_freight_eur не включаються до COGS, а поріг становить 0.15%.",
                source_ids=["S1"],
            )
        ],
        citations=[cite],
        prompt_version="v2",
    )
    rep = eval_scorers.score_faithfulness(inverted, packed)
    assert rep.faithfulness_score == 0.0
    assert len(rep.unsupported_claims) == 1

    # Affirmative main clause from a contrast sentence ("X, а не Y") must remain faithful (1.0),
    # while claiming the negated contrast branch ("Y") must be flagged as unfaithful (0.0).
    contrast_ctx = PackedContext(
        budget_tokens=600,
        used_tokens=120,
        gate_passed=True,
        included_sources=[
            PackedSource(
                source_id="S1",
                chunk_id="SPEC-FIN-041_v1.2_fx_conversion_timing_rates.pdf#00",
                source="data/hw2_corpus/raw/SPEC-FIN-041_v1.2_fx_conversion_timing_rates.pdf",
                title="SPEC-FIN-041",
                section="1. Єдиний стандарт валютної конвертації у FX Revenue",
                version="1.2",
                date="2025-04-05",
                is_latest=True,
                score=4.5,
                packed_tokens=120,
                formatted_block=(
                    "[S1] source=data/hw2_corpus/raw/SPEC-FIN-041_v1.2_fx_conversion_timing_rates.pdf\n"
                    "Курс визначається за датою фактичної оплати (payment_date / AUGDT), а не за датою виставлення інвойсу."
                ),
            )
        ],
        context_text="Курс визначається за датою фактичної оплати (payment_date / AUGDT), а не за датою виставлення інвойсу.",
    )
    cite_fx = RAGCitation(
        source_id="S1",
        chunk_id="SPEC-FIN-041_v1.2_fx_conversion_timing_rates.pdf#00",
        source="data/hw2_corpus/raw/SPEC-FIN-041_v1.2_fx_conversion_timing_rates.pdf",
        title="SPEC-FIN-041",
        section="1. Єдиний стандарт валютної конвертації у FX Revenue",
        version="1.2",
        date="2025-04-05",
        is_latest=True,
    )
    valid_main = RAGAnswer(
        abstained=False,
        answer="Курс визначається за датою фактичної оплати (payment_date / AUGDT) [S1].",
        claims=[
            RAGClaim(
                statement="Курс визначається за датою фактичної оплати (payment_date / AUGDT).",
                source_ids=["S1"],
            )
        ],
        citations=[cite_fx],
        prompt_version="v2",
    )
    assert eval_scorers.score_faithfulness(valid_main, contrast_ctx).faithfulness_score == 1.0

    invalid_contrast = RAGAnswer(
        abstained=False,
        answer="Курс визначається за датою виставлення інвойсу [S1].",
        claims=[
            RAGClaim(
                statement="Курс визначається за датою виставлення інвойсу.",
                source_ids=["S1"],
            )
        ],
        citations=[cite_fx],
        prompt_version="v2",
    )
    assert eval_scorers.score_faithfulness(invalid_contrast, contrast_ctx).faithfulness_score == 0.0


def test_cloud_llm_429_503_retry_backoff_disk_cache_and_gemini_model_env(tmp_path: Path, monkeypatch):
    assert parse_retry_after_seconds("429 RESOURCE_EXHAUSTED. Please retry in 24.5s.") == 24.5

    sleeps: list[float] = []
    calls = {"n": 0}

    def flaky_call() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota limit, retry in 22s")
        if calls["n"] == 2:
            raise RuntimeError("503 Service Unavailable")
        return "ok-payload"

    out = call_with_llm_retry(flaky_call, max_attempts=5, base_backoff_sec=2.0, sleep_fn=sleeps.append)
    assert out == "ok-payload"
    assert calls["n"] == 3
    assert sleeps[0] >= 23.5  # honors retry-after >= 22 + 1.5s and >= 20*1
    assert sleeps[1] >= 4.0   # exponential backoff on 503

    # Non-retryable 401 fails immediately with zero sleeps
    sleeps.clear()
    with pytest.raises(RuntimeError, match="401"):
        call_with_llm_retry(lambda: (_ for _ in ()).throw(RuntimeError("401 Invalid API key")), sleep_fn=sleeps.append)
    assert sleeps == []

    # Disk cache roundtrip
    cache = LLMDiskCache(cache_dir=tmp_path / "cache", enabled=True)
    assert cache.get("ns", "m1", "sys", "usr") is None
    cache.put("ns", "m1", "sys", "usr", {"raw_text": '{"ok":1}', "usage": {"total_tokens": 10}})
    assert cache.get("ns", "m1", "sys", "usr")["raw_text"] == '{"ok":1}'

    # GEMINI_MODEL env var compatibility
    monkeypatch.delenv("HW2_RAG_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    assert resolve_gemini_model(None, env_var="HW2_RAG_MODEL") == "gemini-2.5-flash"


def test_main_cli_defaults_to_hw2_and_guards_hw2_llm_without_key(monkeypatch):
    import main as root_main

    called: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        root_main,
        "_run_hw2_pipeline",
        lambda *, require_cloud, prompt_version: called.append((prompt_version, require_cloud)),
    )
    monkeypatch.setattr(sys, "argv", ["main.py"])
    root_main.main()
    assert called == [("v2", False)]

    # --hw2-llm without API keys raises clear RuntimeError via resolve_cloud_provider
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("src.hw2.llm_runtime.load_dotenv", lambda *a, **kw: False)
    with pytest.raises(RuntimeError, match="Cloud LLM key missing"):
        resolve_cloud_provider("cloud", require_cloud=True)
