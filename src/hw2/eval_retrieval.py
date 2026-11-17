"""Quantitative retrieval benchmark (Recall@1/3/5, MRR@5, Legacy Contamination) for HW2 Step 2."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.hw2.index import DEFAULT_QDRANT_PATH, ROOT
from src.hw2.models import SearchFilters, SearchHit
from src.hw2.search import HybridSearchEngine, SearchMode

DEFAULT_EVALSET_PATH = ROOT / "evals" / "hw2_retrieval_evalset.json"
DEFAULT_RESULTS_PATH = ROOT / "evals" / "hw2_retrieval_results.json"


class EvalQuestion(BaseModel):
    """One human-curated retrieval benchmark item."""

    id: str
    category: str
    version_sensitive: bool = False
    query: str
    expected_chunk_ids: list[str]
    expected_sources: list[str]
    notes: str = ""


class PerQueryEvalResult(BaseModel):
    """Per-question outcome for a given retrieval configuration."""

    id: str
    category: str
    version_sensitive: bool
    first_relevant_rank: int | None
    hit_at_1: bool
    hit_at_3: bool
    hit_at_5: bool
    reciprocal_rank_at_5: float
    legacy_in_top_3: bool
    top_5_chunk_ids: list[str]


class ConfigEvalSummary(BaseModel):
    """Aggregated retrieval quality metrics for one configuration."""

    config_name: str
    mode: SearchMode
    only_latest: bool
    total_queries: int
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr_at_5: float
    version_sensitive_queries: int
    version_sensitive_recall_at_1: float
    version_sensitive_mrr_at_5: float
    version_sensitive_legacy_top3_rate: float
    per_query: list[PerQueryEvalResult] = Field(default_factory=list)


class RetrievalBenchmarkReport(BaseModel):
    """Top-level evaluation report saved to evals/hw2_retrieval_results.json."""

    evaluated_at: str
    embedding_model: str
    reranker_model: str
    total_chunks_indexed: int
    evalset_size: int
    configurations: list[ConfigEvalSummary]


def score_hits_for_question(q: EvalQuestion, hits: Sequence[SearchHit]) -> PerQueryEvalResult:
    """Compute rank of first expected chunk, Recall@1/3/5, MRR@5, and legacy contamination."""
    expected = set(q.expected_chunk_ids)
    top5 = list(hits[:5])
    first_rank: int | None = None
    for idx, h in enumerate(top5, start=1):
        if h.chunk_id in expected:
            first_rank = idx
            break

    rr5 = round(1.0 / first_rank, 4) if first_rank is not None else 0.0
    legacy_top3 = any(not h.is_latest for h in top5[:3])
    return PerQueryEvalResult(
        id=q.id,
        category=q.category,
        version_sensitive=q.version_sensitive,
        first_relevant_rank=first_rank,
        hit_at_1=first_rank == 1,
        hit_at_3=first_rank is not None and first_rank <= 3,
        hit_at_5=first_rank is not None and first_rank <= 5,
        reciprocal_rank_at_5=rr5,
        legacy_in_top_3=legacy_top3,
        top_5_chunk_ids=[h.chunk_id for h in top5],
    )


def evaluate_configuration(
    engine: HybridSearchEngine,
    questions: Sequence[EvalQuestion],
    config_name: str,
    mode: SearchMode,
    only_latest: bool = False,
    candidate_pool: int = 12,
) -> ConfigEvalSummary:
    """Run all benchmark queries under one retrieval configuration and aggregate metrics."""
    filters = SearchFilters(is_latest=True) if only_latest else None
    per_query: list[PerQueryEvalResult] = []
    for q in questions:
        hits = engine.search(
            query=q.query,
            mode=mode,
            top_k=5,
            candidate_pool=candidate_pool,
            filters=filters,
        )
        per_query.append(score_hits_for_question(q, hits))

    n = len(per_query) or 1
    vs_items = [r for r in per_query if r.version_sensitive]
    vn = len(vs_items) or 1
    return ConfigEvalSummary(
        config_name=config_name,
        mode=mode,
        only_latest=only_latest,
        total_queries=len(per_query),
        recall_at_1=round(sum(r.hit_at_1 for r in per_query) / n, 4),
        recall_at_3=round(sum(r.hit_at_3 for r in per_query) / n, 4),
        recall_at_5=round(sum(r.hit_at_5 for r in per_query) / n, 4),
        mrr_at_5=round(sum(r.reciprocal_rank_at_5 for r in per_query) / n, 4),
        version_sensitive_queries=len(vs_items),
        version_sensitive_recall_at_1=round(sum(r.hit_at_1 for r in vs_items) / vn, 4),
        version_sensitive_mrr_at_5=round(sum(r.reciprocal_rank_at_5 for r in vs_items) / vn, 4),
        version_sensitive_legacy_top3_rate=round(sum(r.legacy_in_top_3 for r in vs_items) / vn, 4),
        per_query=per_query,
    )


def load_evalset(path: Path = DEFAULT_EVALSET_PATH) -> list[EvalQuestion]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [EvalQuestion.model_validate(item) for item in raw]


def run_retrieval_benchmark(
    evalset_path: Path = DEFAULT_EVALSET_PATH,
    out_path: Path = DEFAULT_RESULTS_PATH,
    qdrant_location: str | Path = DEFAULT_QDRANT_PATH,
) -> RetrievalBenchmarkReport:
    """Execute all 5 comparison configurations and persist evals/hw2_retrieval_results.json."""
    questions = load_evalset(evalset_path)
    engine = HybridSearchEngine(qdrant_location=qdrant_location)
    try:
        configs: list[tuple[str, SearchMode, bool]] = [
            ("vector_only", "vector", False),
            ("bm25_only", "bm25", False),
            ("hybrid_rrf", "hybrid", False),
            ("hybrid_rrf_rerank", "hybrid_rerank", False),
            ("hybrid_rrf_rerank_latest", "hybrid_rerank", True),
        ]
        summaries = [
            evaluate_configuration(engine, questions, name, mode, only_latest=latest)
            for name, mode, latest in configs
        ]
        report = RetrievalBenchmarkReport(
            evaluated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            embedding_model=engine.embedder.model_name,
            reranker_model=engine.reranker.model_name,
            total_chunks_indexed=len(engine.chunks),
            evalset_size=len(questions),
            configurations=summaries,
        )
    finally:
        engine.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Evaluate HW2 Step 2 retrieval quality")
    parser.add_argument("--evalset", type=Path, default=DEFAULT_EVALSET_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument(
        "--qdrant-path",
        default=os.getenv("HW2_QDRANT_PATH", str(DEFAULT_QDRANT_PATH)),
    )
    args = parser.parse_args()

    report = run_retrieval_benchmark(
        evalset_path=args.evalset, out_path=args.out, qdrant_location=args.qdrant_path
    )
    header = (
        f"{'Configuration':<28} {'R@1':>7} {'R@3':>7} {'R@5':>7} {'MRR@5':>8} "
        f"{'Ver-R@1':>9} {'Legacy@3':>9}"
    )
    print(header)
    print("-" * len(header))
    for cfg in report.configurations:
        print(
            f"{cfg.config_name:<28} {cfg.recall_at_1:>7.3f} {cfg.recall_at_3:>7.3f} "
            f"{cfg.recall_at_5:>7.3f} {cfg.mrr_at_5:>8.3f} "
            f"{cfg.version_sensitive_recall_at_1:>9.3f} {cfg.version_sensitive_legacy_top3_rate:>9.3f}"
        )


if __name__ == "__main__":
    main()
