"""Unit and integration tests for HW2 Step 2 Qdrant index, BM25, RRF, reranking, and evals."""

from __future__ import annotations

import hashlib
import json
from typing import Sequence

import pytest

from src.hw2.bm25_index import BM25LexicalIndex, tokenize_bm25
from src.hw2.embeddings import FastEmbedProvider, FastRerankProvider, _is_e5_family
from src.hw2.eval_retrieval import (
    DEFAULT_EVALSET_PATH,
    DEFAULT_RESULTS_PATH,
    EvalQuestion,
    load_evalset,
    score_hits_for_question,
)
from src.hw2.index import load_chunks_jsonl, open_qdrant_client
from src.hw2.models import ChunkRecord, SearchFilters
from src.hw2.search import HybridSearchEngine, reciprocal_rank_fusion


class DeterministicEmbedder:
    """Fast deterministic hash-projection embedder for unit tests."""

    model_name = "deterministic-unit-test-embedder"
    dim = 32

    def _vec(self, text: str) -> list[float]:
        acc = [0.0] * self.dim
        for tok in tokenize_bm25(text):
            digest = hashlib.sha256(tok.encode("utf-8")).digest()
            for i in range(self.dim):
                acc[i] += (digest[i] - 127.5) / 127.5
        norm = sum(x * x for x in acc) ** 0.5 or 1.0
        return [x / norm for x in acc]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._vec(query)


class KeywordBoostReranker:
    """Lightweight test reranker scoring overlap + active-version preference."""

    model_name = "keyword-boost-test-reranker"

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        q_set = set(tokenize_bm25(query))
        return [float(len(q_set & set(tokenize_bm25(p)))) for p in passages]


@pytest.fixture(scope="module")
def corpus_chunks() -> list[ChunkRecord]:
    return load_chunks_jsonl()


@pytest.fixture(scope="module")
def memory_engine(corpus_chunks: list[ChunkRecord]):
    client = open_qdrant_client(":memory:")
    engine = HybridSearchEngine(
        chunks=corpus_chunks,
        qdrant_client=client,
        collection_name="test_hw2_chunks",
        embedder=DeterministicEmbedder(),
        reranker=KeywordBoostReranker(),
    )
    yield engine
    client.close()


def test_bm25_tokenizer_preserves_technical_identifiers(corpus_chunks: list[ChunkRecord]):
    tokens = tokenize_bm25(
        "Перевірити SPEC-FIN-030 v1.3 у mart.fact_revenue та Z_SD_SALES_ORDER проти C_PROFITCENTER_Q"
    )
    assert "spec-fin-030" in tokens
    assert "mart.fact_revenue" in tokens
    assert "z_sd_sales_order" in tokens
    assert "c_profitcenter_q" in tokens
    assert "v1.3" in tokens
    assert _is_e5_family("intfloat/multilingual-e5-small")
    assert not _is_e5_family("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    bm25 = BM25LexicalIndex(corpus_chunks)
    hits = bm25.search("DM_GWPipeline_Gateway_Timeout", top_k=3)
    assert hits and hits[0][0].chunk_id == "RUNBOOK-PBI-006_gateway_and_dataset_refresh.html#01"


def test_qdrant_indexing_and_consistent_metadata_filters(memory_engine: HybridSearchEngine):
    count = memory_engine.client.count(collection_name="test_hw2_chunks").count
    assert count == len(memory_engine.chunks) == 97

    # Legacy filter check: without filter, legacy v1.0 appears; with is_latest=True, zero legacy hits
    unfiltered = memory_engine.search(
        "SPEC-FIN-030 inbound_freight_eur v1.0 v1.3", mode="hybrid", top_k=10
    )
    assert any(not h.is_latest for h in unfiltered)

    filtered_latest = memory_engine.search(
        "SPEC-FIN-030 inbound_freight_eur v1.0 v1.3",
        mode="hybrid_rerank",
        top_k=10,
        filters=SearchFilters(is_latest=True),
    )
    assert filtered_latest
    assert all(h.is_latest for h in filtered_latest)
    assert all("v1.0" not in h.chunk_id for h in filtered_latest)

    # Combined doc_type + report_id + date_from filters across both vector and bm25
    scoped_filters = SearchFilters(
        is_latest=True,
        doc_type=["kpi_spec", "runbook"],
        report_id="RPT-FX-005",
        date_from="2025-04-01",
    )
    for mode in ("vector", "bm25", "hybrid"):
        hits = memory_engine.search("payment_date ref.fx_rates", mode=mode, top_k=5, filters=scoped_filters)
        assert hits
        for h in hits:
            assert h.is_latest is True
            assert h.doc_type in {"kpi_spec", "runbook"}
            assert h.report_id == "RPT-FX-005"
            assert h.date >= "2025-04-01"


def test_rrf_fusion_combines_disjoint_and_overlapping_candidates(corpus_chunks: list[ChunkRecord]):
    c0, c1, c2 = corpus_chunks[0], corpus_chunks[1], corpus_chunks[2]
    fused = reciprocal_rank_fusion(
        dense_hits=[(c0, 0.91), (c1, 0.85)],
        bm25_hits=[(c1, 14.2), (c2, 11.0)],
        rrf_k=60,
    )
    # c1 appears in both lists (ranks 2 and 1) -> highest RRF score 1/62 + 1/61
    assert fused[0].chunk_id == c1.chunk_id
    assert fused[0].vector_rank == 2 and fused[0].bm25_rank == 1
    assert {h.chunk_id for h in fused} == {c0.chunk_id, c1.chunk_id, c2.chunk_id}


def test_real_multilingual_embedder_and_reranker_on_ukrainian_query(corpus_chunks: list[ChunkRecord]):
    embedder = FastEmbedProvider()
    reranker = FastRerankProvider()
    client = open_qdrant_client(":memory:")
    subset = [
        c
        for c in corpus_chunks
        if c.chunk_id
        in {
            "SPEC-FIN-030_v1.3_gross_margin_rules.pdf#01",
            "SPEC-FIN-030_v1.0_gross_margin_rules_legacy.pdf#01",
            "RUNBOOK-DBX-003_customer_master_scd2.html#00",
            "SPEC-OPS-011_v1.2_order_fulfillment_otif.pdf#01",
        }
    ]
    engine = HybridSearchEngine(
        chunks=subset,
        qdrant_client=client,
        collection_name="test_real_models",
        embedder=embedder,
        reranker=reranker,
    )
    try:
        hits = engine.search(
            "Як обліковуються витрати на вхідну логістику inbound_freight_eur та який поріг 0.15% у чинній SPEC-FIN-030?",
            mode="hybrid_rerank",
            top_k=3,
            filters=SearchFilters(is_latest=True),
        )
        assert hits[0].chunk_id == "SPEC-FIN-030_v1.3_gross_margin_rules.pdf#01"
        assert hits[0].rerank_score is not None
    finally:
        client.close()


def test_evalset_integrity_and_saved_benchmark_metrics(corpus_chunks: list[ChunkRecord]):
    known_ids = {c.chunk_id for c in corpus_chunks}
    questions = load_evalset(DEFAULT_EVALSET_PATH)
    assert len(questions) == 18
    assert sum(q.version_sensitive for q in questions) >= 4
    for q in questions:
        assert q.expected_chunk_ids
        assert set(q.expected_chunk_ids).issubset(known_ids)

    # Unit check of metric math (rank 2 -> Recall@1=0, Recall@3=1, MRR@5=0.5)
    dummy_q = EvalQuestion(
        id="Q-TEST",
        category="unit",
        query="test",
        expected_chunk_ids=[corpus_chunks[1].chunk_id],
        expected_sources=[corpus_chunks[1].source],
    )
    fake_hits = reciprocal_rank_fusion([(corpus_chunks[0], 0.9), (corpus_chunks[1], 0.8)], [])
    scored = score_hits_for_question(dummy_q, fake_hits)
    assert scored.first_relevant_rank == 2
    assert not scored.hit_at_1 and scored.hit_at_3 and scored.reciprocal_rank_at_5 == 0.5

    saved = json.loads(DEFAULT_RESULTS_PATH.read_text(encoding="utf-8"))
    by_name = {c["config_name"]: c for c in saved["configurations"]}
    assert {"vector_only", "bm25_only", "hybrid_rrf", "hybrid_rrf_rerank", "hybrid_rrf_rerank_latest"} <= set(by_name)
    assert by_name["hybrid_rrf"]["recall_at_5"] > by_name["vector_only"]["recall_at_5"]
    assert by_name["hybrid_rrf_rerank"]["mrr_at_5"] > by_name["hybrid_rrf"]["mrr_at_5"]
    assert by_name["hybrid_rrf_rerank_latest"]["version_sensitive_legacy_top3_rate"] == 0.0
    assert by_name["hybrid_rrf_rerank_latest"]["mrr_at_5"] >= by_name["hybrid_rrf_rerank"]["mrr_at_5"]
