"""Unit and integration tests for HW2 Step 4 RAG testset, 3-layer scorers, judge calibration, and CI gate."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from src.hw2.calibrate_judge import compute_cohens_kappa, run_judge_calibration
from src.hw2.eval_rag import (
    DEFAULT_EVAL_OUT,
    DEFAULT_TESTSET_PATH,
    RAGEvalConfigSummary,
    check_ci_thresholds,
    load_rag_testset,
)
from src.hw2.index import ROOT, load_chunks_jsonl
from src.hw2.models import PackedContext, PackedSource, RAGAnswer, RAGCitation, RAGClaim
from src.hw2.scorers import score_deterministic, score_faithfulness
from src.hw2.verifier import ABSTAIN_MESSAGE_UK


def test_rag_testset_schema_distribution_and_corpus_alignment():
    cases = load_rag_testset(DEFAULT_TESTSET_PATH)
    assert len(cases) >= 20
    assert len(cases) == 24
    assert all(c.human_verified for c in cases)

    unanswerable = [c for c in cases if c.expected_abstain]
    legacy_traps = [c for c in cases if c.category == "trap_legacy_version"]
    similar_traps = [c for c in cases if c.category == "trap_similar_docs"]
    assert len(unanswerable) >= 5
    assert len(legacy_traps) >= 4
    assert len(similar_traps) >= 3

    corpus_sources = {ch.source for ch in load_chunks_jsonl()}
    for c in cases:
        if not c.expected_abstain:
            assert c.expected_sources
            assert set(c.expected_sources).issubset(corpus_sources)


def test_deterministic_and_faithfulness_scorers_catch_hallucinations_and_legacy_bleed():
    case = load_rag_testset(DEFAULT_TESTSET_PATH)[17]  # QA-18: SPEC-FIN-030 v1.3 trap
    assert case.id == "QA-18"

    packed = PackedContext(
        budget_tokens=600,
        used_tokens=120,
        gate_passed=True,
        included_sources=[
            PackedSource(
                source_id="S1",
                chunk_id="SPEC-FIN-030_v1.3_gross_margin_rules.pdf#01",
                source="data/hw2_corpus/raw/SPEC-FIN-030_v1.3_gross_margin_rules.pdf",
                title="SPEC-FIN-030: Gross Margin % Calculation Rules",
                section="2. Формула Gross Margin % та виключення оборотів",
                version="1.3",
                date="2025-03-15",
                is_latest=True,
                score=4.2,
                packed_tokens=120,
                formatted_block=(
                    "[S1] source=data/hw2_corpus/raw/SPEC-FIN-030_v1.3_gross_margin_rules.pdf\n"
                    "У версії 1.3 витрати inbound_freight_eur включаються до COGS, а поріг звірки становить 0.15%."
                ),
            )
        ],
        context_text="У версії 1.3 витрати inbound_freight_eur включаються до COGS, а поріг звірки становить 0.15%.",
    )

    good_ans = RAGAnswer(
        abstained=False,
        answer="У версії 1.3 витрати inbound_freight_eur включаються до COGS, а поріг звірки становить 0.15% [S1].",
        claims=[
            RAGClaim(
                statement="У версії 1.3 витрати inbound_freight_eur включаються до COGS, а поріг звірки становить 0.15%.",
                source_ids=["S1"],
            )
        ],
        citations=[
            RAGCitation(
                source_id="S1",
                chunk_id="SPEC-FIN-030_v1.3_gross_margin_rules.pdf#01",
                source="data/hw2_corpus/raw/SPEC-FIN-030_v1.3_gross_margin_rules.pdf",
                title="SPEC-FIN-030",
                section="2. Формула Gross Margin % та виключення оборотів",
                version="1.3",
                date="2025-03-15",
                is_latest=True,
            )
        ],
        prompt_version="v2",
    )
    det_ok = score_deterministic(case, good_ans)
    faith_ok = score_faithfulness(good_ans, packed)
    assert det_ok.abstention_accuracy == 1.0
    assert det_ok.citation_source_hit == 1.0 and det_ok.citation_section_hit == 1.0
    assert det_ok.fact_coverage == 1.0 and det_ok.no_forbidden_facts == 1.0
    assert faith_ok.faithfulness_score == 1.0

    # Hallucinated percentage (0.02% not in context) -> faithfulness drops to 0.0
    unfaithful_ans = good_ans.model_copy(
        update={
            "claims": [
                RAGClaim(
                    statement="У версії 1.3 витрати inbound_freight_eur включаються до COGS, а поріг становить 0.02%.",
                    source_ids=["S1"],
                )
            ]
        }
    )
    faith_bad = score_faithfulness(unfaithful_ans, packed)
    assert faith_bad.faithfulness_score == 0.0
    assert len(faith_bad.unsupported_claims) == 1

    # Legacy v1.0 citation + forbidden OPEX rule -> source_hit=0.0 and no_forbidden_facts=0.0
    legacy_ans = good_ans.model_copy(
        update={
            "answer": "Inbound freight списується в OPEX [S1].",
            "citations": [good_ans.citations[0].model_copy(update={"is_latest": False})],
        }
    )
    det_leg = score_deterministic(case, legacy_ans)
    assert det_leg.citation_source_hit == 0.0
    assert det_leg.no_forbidden_facts == 0.0

    # Unanswerable case check
    unans_case = load_rag_testset(DEFAULT_TESTSET_PATH)[12]
    clean_abstain = RAGAnswer(abstained=True, answer=ABSTAIN_MESSAGE_UK, claims=[], citations=[], prompt_version="v2")
    assert score_deterministic(unans_case, clean_abstain).abstention_accuracy == 1.0


def test_judge_calibration_agreement_kappa_and_saved_eval_lift(tmp_path):
    calib_out = tmp_path / "calib_out.json"
    rep = run_judge_calibration(out_path=calib_out, judge_provider="rubric")
    assert rep.total_cases == 14
    assert rep.agreement_rate >= 0.85
    assert rep.cohens_kappa >= 0.80
    assert sum(sum(row.values()) for row in rep.confusion_matrix.values()) == 14
    assert compute_cohens_kappa(["pass", "fail"], ["pass", "fail"]) == 1.0

    saved = json.loads(DEFAULT_EVAL_OUT.read_text(encoding="utf-8"))
    by_cfg = {c["config_name"]: RAGEvalConfigSummary.model_validate(c) for c in saved["configurations"]}
    base = by_cfg["baseline_unfiltered_v1"]
    prod = by_cfg["production_filtered_v2"]

    assert prod.overall_composite_score > base.overall_composite_score + 0.25
    assert prod.abstention_accuracy >= 0.95
    assert prod.faithfulness_mean >= 0.95
    assert check_ci_thresholds(prod, rep) == []


def test_ci_threshold_gate_fails_with_nonzero_exit_code(tmp_path):
    calib_rep = run_judge_calibration(out_path=tmp_path / "c.json", judge_provider="rubric")
    saved = json.loads(DEFAULT_EVAL_OUT.read_text(encoding="utf-8"))
    prod = RAGEvalConfigSummary.model_validate(saved["configurations"][-1])

    # Unit check: impossible threshold triggers failure message
    failures = check_ci_thresholds(prod, calib_rep, min_overall_score=0.999)
    assert failures and "overall_composite_score" in failures[0]

    # Subprocess check: calibrate_judge exits with code 1 when --min-agreement > actual agreement
    proc = subprocess.run(
        [sys.executable, "-m", "src.hw2.calibrate_judge", "--out", str(tmp_path / "c2.json"), "--min-agreement", "0.99"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "FAIL: Judge agreement" in proc.stderr
