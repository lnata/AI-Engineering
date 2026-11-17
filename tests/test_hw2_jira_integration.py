"""Integration tests for unified HW1 Jira tickets + reference JSONs inside HW2 RAG."""

from __future__ import annotations

import json

import pytest

from src.hw2.extractors import extract_document_markdown
from src.hw2.index import ROOT, load_chunks_jsonl, open_qdrant_client
from src.hw2.json_extractor import is_analytics_domain_ticket
from src.hw2.models import ChunkRecord, SearchFilters
from src.hw2.rag import RAGPipeline
from src.hw2.search import HybridSearchEngine
from tests.test_hw2_retrieval import DeterministicEmbedder, KeywordBoostReranker


@pytest.fixture(scope="module")
def all_chunks() -> list[ChunkRecord]:
    return load_chunks_jsonl()


@pytest.fixture(scope="module")
def unified_engine(all_chunks: list[ChunkRecord]):
    client = open_qdrant_client(":memory:")
    engine = HybridSearchEngine(
        chunks=all_chunks,
        qdrant_client=client,
        collection_name="test_unified_hw1_hw2",
        embedder=DeterministicEmbedder(),
        reranker=KeywordBoostReranker(),
    )
    yield engine
    client.close()


def test_hw1_jira_and_reference_json_extraction_and_domain_selection():
    # Non-analytics web bug BUGS-1 is excluded; Analytics ticket BUGS-41 is included
    b1 = json.loads((ROOT / "data" / "raw" / "BUGS-1.json").read_text(encoding="utf-8"))
    b41 = json.loads((ROOT / "data" / "raw" / "BUGS-41.json").read_text(encoding="utf-8"))
    assert not is_analytics_domain_ticket(b1)
    assert is_analytics_domain_ticket(b41)

    md_41 = extract_document_markdown(ROOT / "data" / "raw" / "BUGS-41.json")
    assert "# BUGS-41:" in md_41
    assert "Type: jira_ticket | Report: RPT-SALES-001" in md_41
    assert "1.31M" in md_41 and "1.24M" in md_41 and "SPEC-FIN-014" in md_41
    # Personal names from HW1 raw JSON are anonymized into role slots
    for raw_name in ("Maria", "Anna", "Dmytro"):
        assert raw_name not in md_41
    assert "FA-01" in md_41 and "RD-01" in md_41 and "DP-01" in md_41

    md_ref = extract_document_markdown(ROOT / "data" / "reference" / "reports.json")
    assert "# REF-REPORTS:" in md_ref
    assert "Type: reference" in md_ref
    assert "| RPT-SALES-001 |" in md_ref and "| RPT-FX-005 |" in md_ref
    assert "anna.k" not in md_ref and "RD-01" in md_ref


def test_qdrant_and_bm25_filtering_by_jira_ticket_and_reference_doc_types(
    unified_engine: HybridSearchEngine,
):
    for mode in ("vector", "bm25", "hybrid_rerank"):
        ticket_hits = unified_engine.search(
            "Customers_Prod.pbix 12040 11802 soft-deleted",
            mode=mode,
            top_k=5,
            filters=SearchFilters(doc_type="jira_ticket"),
        )
        assert ticket_hits
        assert all(h.doc_type == "jira_ticket" and h.format == "json" for h in ticket_hits)
        assert any(h.chunk_id == "BUGS-44.json#00" for h in ticket_hits)

        ref_hits = unified_engine.search(
            "sap_fiori databricks power_bi_report owner_role",
            mode=mode,
            top_k=4,
            filters=SearchFilters(doc_type="reference"),
        )
        assert ref_hits
        assert all(h.doc_type == "reference" and h.format == "json" for h in ref_hits)


def test_cross_source_rag_cites_both_hw1_jira_ticket_and_hw2_policy(
    unified_engine: HybridSearchEngine,
):
    pipe = RAGPipeline(search_engine=unified_engine)
    res = pipe.answer(
        "Яке порушення процесу деплою для звіту Inventory Snapshot описано в тікеті BUGS-53 "
        "і який обов'язковий маршрут викатки встановлює регламент POL-DEP-001 v1.3?",
        provider="extractive",
        prompt_version="v2",
        filters=SearchFilters(is_latest=True),
    )
    assert res.ok and res.rag_answer is not None
    assert res.rag_answer.abstained is False
    cited_sources = {c.source for c in res.rag_answer.citations}
    assert "data/raw/BUGS-53.json" in cited_sources
    assert any(
        s.endswith("POL-DEP-001_v1.3_deployment_and_reconciliation_policy.docx") or s == "data/reference/deployment.json"
        for s in cited_sources
    )
