"""End-to-end RAG evaluation runner across configurations with CI threshold gates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.hw2.calibrate_judge import JudgeCalibrationReport, run_judge_calibration
from src.hw2.chunking import count_tokens
from src.hw2.generator import _split_units
from src.hw2.index import DEFAULT_QDRANT_PATH, ROOT
from src.hw2.judge import JudgeProtocol, JudgeProviderChoice, build_judge
from src.hw2.models import PackedContext, RAGClaim, RAGLLMResponse, SearchFilters
from src.hw2.rag import ProviderChoice, RAGPipeline
from src.hw2.scorers import (
    DeterministicScores,
    FaithfulnessReport,
    JudgeVerdict,
    RAGTestCase,
    score_deterministic,
    score_faithfulness,
)
from src.hw2.search import HybridSearchEngine, SearchMode

DEFAULT_TESTSET_PATH = ROOT / "evals" / "hw2_rag_testset.json"
DEFAULT_EVAL_OUT = ROOT / "evals" / "hw2_rag_eval_results.json"


class NaiveV1ExtractiveGenerator:
    """Baseline v1 local generator without Gate-2 specificity guard or is_latest awareness."""

    provider_name = "extractive_v1_baseline"
    model_name = "naive-extractive-v1"

    def __init__(self, packed: PackedContext) -> None:
        self._packed = packed

    def generate(self, *, system_prompt: str, user_prompt: str) -> tuple[str, dict[str, int], float]:
        top_src = self._packed.included_sources[0]
        body = top_src.formatted_block.split("\n", 1)[1] if "\n" in top_src.formatted_block else top_src.formatted_block
        units = _split_units(body)
        stmt = units[0] if units else body.strip()
        short_doc = top_src.source.rsplit("/", 1)[-1]
        resp = RAGLLMResponse(
            abstained=False,
            answer=f"{stmt} [{top_src.source_id}] ({short_doc} — {top_src.section}).",
            claims=[RAGClaim(statement=stmt, source_ids=[top_src.source_id])],
        )
        raw = json.dumps(resp.model_dump(mode="json"), ensure_ascii=False)
        in_t, out_t = count_tokens(system_prompt) + count_tokens(user_prompt), count_tokens(raw)
        return raw, {"input_tokens": in_t, "output_tokens": out_t, "total_tokens": in_t + out_t}, 0.5


class PerQuestionRAGScore(BaseModel):
    id: str
    category: str
    question: str
    expected_abstain: bool
    abstained: bool
    cited_sources: list[str]
    answer: str
    deterministic: DeterministicScores
    faithfulness: FaithfulnessReport
    judge: JudgeVerdict
    composite_score: float


class RAGEvalConfigSummary(BaseModel):
    config_name: str
    search_mode: SearchMode
    only_latest: bool
    prompt_version: str
    max_context_tokens: int
    total_questions: int
    overall_composite_score: float
    abstention_accuracy: float
    citation_source_hit_rate: float
    citation_section_hit_rate: float
    fact_coverage_mean: float
    no_forbidden_facts_rate: float
    faithfulness_mean: float
    judge_correctness_mean: float
    judge_pass_rate: float
    category_scores: dict[str, float]
    per_question: list[PerQuestionRAGScore] = Field(default_factory=list)


class EndToEndRAGEvalReport(BaseModel):
    evaluated_at: str
    rag_provider: str
    judge_name: str
    judge_calibration_agreement: float
    judge_calibration_kappa: float
    testset_size: int
    configurations: list[RAGEvalConfigSummary]


def load_rag_testset(path: Path = DEFAULT_TESTSET_PATH) -> list[RAGTestCase]:
    return [RAGTestCase.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def evaluate_rag_config(
    pipeline: RAGPipeline,
    judge: JudgeProtocol,
    cases: Sequence[RAGTestCase],
    *,
    config_name: str,
    search_mode: SearchMode,
    only_latest: bool,
    prompt_version: str,
    max_context_tokens: int,
    provider: ProviderChoice = "auto",
    use_naive_v1_baseline: bool = False,
) -> RAGEvalConfigSummary:
    filters = SearchFilters(is_latest=True) if only_latest else None
    rows: list[PerQuestionRAGScore] = []

    for case in cases:
        gen_override = None
        if use_naive_v1_baseline and provider in ("auto", "extractive") and not (
            os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        ):
            hits = pipeline.engine.search(case.question, mode=search_mode, top_k=5, filters=filters)
            from src.hw2.context_packer import pack_retrieved_context

            preview = pack_retrieved_context(case.question, hits, max_context_tokens=max_context_tokens)
            if preview.gate_passed:
                gen_override = NaiveV1ExtractiveGenerator(preview)

        run = pipeline.answer(
            case.question,
            provider=provider,
            prompt_version=prompt_version,
            mode=search_mode,
            max_context_tokens=max_context_tokens,
            filters=filters,
            generator_override=gen_override,
        )
        ans = run.rag_answer
        det = score_deterministic(case, ans)
        faith = score_faithfulness(ans, run.context)
        cited = [c.chunk_id for c in (ans.citations if ans else [])]
        j_verdict = judge.evaluate(
            question=case.question,
            expected_abstain=case.expected_abstain,
            required_facts=case.required_facts,
            forbidden_facts=case.forbidden_facts,
            reference_answer=case.reference_answer,
            packed_context=run.context.context_text,
            candidate_abstained=ans.abstained if ans else False,
            candidate_citations=cited,
            candidate_answer=ans.answer if ans else "",
        )
        comp = round(
            0.20 * det.abstention_accuracy
            + 0.20 * det.citation_source_hit
            + 0.20 * det.fact_coverage
            + 0.10 * det.no_forbidden_facts
            + 0.15 * faith.faithfulness_score
            + 0.15 * j_verdict.correctness,
            4,
        )
        rows.append(
            PerQuestionRAGScore(
                id=case.id,
                category=case.category,
                question=case.question,
                expected_abstain=case.expected_abstain,
                abstained=ans.abstained if ans else False,
                cited_sources=cited,
                answer=ans.answer if ans else "",
                deterministic=det,
                faithfulness=faith,
                judge=j_verdict,
                composite_score=comp,
            )
        )

    n = len(rows) or 1
    cats = sorted({r.category for r in rows})
    cat_scores = {
        cat: round(sum(r.composite_score for r in rows if r.category == cat) / sum(1 for r in rows if r.category == cat), 4)
        for cat in cats
    }
    return RAGEvalConfigSummary(
        config_name=config_name,
        search_mode=search_mode,
        only_latest=only_latest,
        prompt_version=prompt_version,
        max_context_tokens=max_context_tokens,
        total_questions=len(rows),
        overall_composite_score=round(sum(r.composite_score for r in rows) / n, 4),
        abstention_accuracy=round(sum(r.deterministic.abstention_accuracy for r in rows) / n, 4),
        citation_source_hit_rate=round(sum(r.deterministic.citation_source_hit for r in rows) / n, 4),
        citation_section_hit_rate=round(sum(r.deterministic.citation_section_hit for r in rows) / n, 4),
        fact_coverage_mean=round(sum(r.deterministic.fact_coverage for r in rows) / n, 4),
        no_forbidden_facts_rate=round(sum(r.deterministic.no_forbidden_facts for r in rows) / n, 4),
        faithfulness_mean=round(sum(r.faithfulness.faithfulness_score for r in rows) / n, 4),
        judge_correctness_mean=round(sum(r.judge.correctness for r in rows) / n, 4),
        judge_pass_rate=round(sum(1 for r in rows if r.judge.label == "pass") / n, 4),
        category_scores=cat_scores,
        per_question=rows,
    )


def check_ci_thresholds(
    prod: RAGEvalConfigSummary,
    calib: JudgeCalibrationReport,
    *,
    min_overall_score: float = 0.85,
    min_faithfulness: float = 0.90,
    min_abstention_accuracy: float = 0.90,
    min_judge_agreement: float = 0.85,
) -> list[str]:
    """Return list of human-readable CI threshold failures (empty list = PASS)."""
    failures: list[str] = []
    if prod.overall_composite_score < min_overall_score:
        failures.append(
            f"overall_composite_score {prod.overall_composite_score:.3f} < {min_overall_score:.3f}"
        )
    if prod.faithfulness_mean < min_faithfulness:
        failures.append(f"faithfulness_mean {prod.faithfulness_mean:.3f} < {min_faithfulness:.3f}")
    if prod.abstention_accuracy < min_abstention_accuracy:
        failures.append(
            f"abstention_accuracy {prod.abstention_accuracy:.3f} < {min_abstention_accuracy:.3f}"
        )
    if calib.agreement_rate < min_judge_agreement:
        failures.append(
            f"judge_agreement_rate {calib.agreement_rate:.3f} < {min_judge_agreement:.3f}"
        )
    return failures


def run_end_to_end_rag_eval(
    testset_path: Path = DEFAULT_TESTSET_PATH,
    out_path: Path = DEFAULT_EVAL_OUT,
    provider: ProviderChoice = "auto",
    judge_provider: JudgeProviderChoice = "auto",
    qdrant_location: str | Path = DEFAULT_QDRANT_PATH,
) -> tuple[EndToEndRAGEvalReport, JudgeCalibrationReport]:
    calib = run_judge_calibration(judge_provider=judge_provider)
    cases = load_rag_testset(testset_path)
    judge = build_judge(provider=judge_provider)
    engine = HybridSearchEngine(qdrant_location=qdrant_location)
    pipe = RAGPipeline(search_engine=engine)
    try:
        baseline = evaluate_rag_config(
            pipe,
            judge,
            cases,
            config_name="baseline_unfiltered_v1",
            search_mode="vector",
            only_latest=False,
            prompt_version="v1",
            max_context_tokens=520,
            provider=provider,
            use_naive_v1_baseline=True,
        )
        production = evaluate_rag_config(
            pipe,
            judge,
            cases,
            config_name="production_filtered_v2",
            search_mode="hybrid_rerank",
            only_latest=True,
            prompt_version="v2",
            max_context_tokens=1200,
            provider=provider,
            use_naive_v1_baseline=False,
        )
    finally:
        engine.close()

    report = EndToEndRAGEvalReport(
        evaluated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        rag_provider=provider,
        judge_name=judge.name,
        judge_calibration_agreement=calib.agreement_rate,
        judge_calibration_kappa=calib.cohens_kappa,
        testset_size=len(cases),
        configurations=[baseline, production],
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report, calib


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="HW2 Step 4 End-to-End RAG Evals & CI Gate")
    parser.add_argument("--testset", type=Path, default=DEFAULT_TESTSET_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_EVAL_OUT)
    parser.add_argument("--provider", choices=["auto", "extractive", "gemini", "openai", "openrouter"], default="auto")
    parser.add_argument("--judge-provider", choices=["auto", "rubric", "gemini", "openai", "openrouter"], default="auto")
    parser.add_argument("--min-overall-score", type=float, default=0.85)
    parser.add_argument("--min-faithfulness", type=float, default=0.90)
    parser.add_argument("--min-abstention-accuracy", type=float, default=0.90)
    parser.add_argument("--min-judge-agreement", type=float, default=0.85)
    args = parser.parse_args()

    report, calib = run_end_to_end_rag_eval(
        testset_path=args.testset,
        out_path=args.out,
        provider=args.provider,
        judge_provider=args.judge_provider,
    )
    hdr = f"{'Configuration':<26} {'Overall':>8} {'Abstain':>8} {'CiteSrc':>8} {'FactCov':>8} {'NoForb':>7} {'Faith':>7} {'Judge':>7}"
    print(hdr)
    print("-" * len(hdr))
    for cfg in report.configurations:
        print(
            f"{cfg.config_name:<26} {cfg.overall_composite_score:>8.3f} {cfg.abstention_accuracy:>8.3f} "
            f"{cfg.citation_source_hit_rate:>8.3f} {cfg.fact_coverage_mean:>8.3f} "
            f"{cfg.no_forbidden_facts_rate:>7.3f} {cfg.faithfulness_mean:>7.3f} {cfg.judge_correctness_mean:>7.3f}"
        )
    print(f"Judge calibration: agreement={calib.agreement_rate:.1%}, kappa={calib.cohens_kappa:.3f}")

    prod = report.configurations[-1]
    failures = check_ci_thresholds(
        prod,
        calib,
        min_overall_score=args.min_overall_score,
        min_faithfulness=args.min_faithfulness,
        min_abstention_accuracy=args.min_abstention_accuracy,
        min_judge_agreement=args.min_judge_agreement,
    )
    if failures:
        print("CI QUALITY GATE FAILED:", "; ".join(failures), file=sys.stderr)
        sys.exit(1)
    print("CI QUALITY GATE PASSED.")


if __name__ == "__main__":
    main()
