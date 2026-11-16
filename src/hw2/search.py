"""Hybrid retriever (Dense Qdrant + BM25 + RRF + Multilingual Reranker) and search CLI."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Literal, Sequence

from dotenv import load_dotenv
from qdrant_client import QdrantClient

from src.hw2.bm25_index import BM25LexicalIndex
from src.hw2.embeddings import (
    EmbedderProtocol,
    FastEmbedProvider,
    FastRerankProvider,
    RerankerProtocol,
)
from src.hw2.index import (
    DEFAULT_CHUNKS_PATH,
    DEFAULT_COLLECTION,
    DEFAULT_QDRANT_PATH,
    ROOT,
    index_chunks_to_qdrant,
    load_chunks_jsonl,
    open_qdrant_client,
    query_qdrant_dense,
)
from src.hw2.models import ChunkRecord, SearchFilters, SearchHit

SearchMode = Literal["vector", "bm25", "hybrid", "hybrid_rerank"]


def reciprocal_rank_fusion(
    dense_hits: Sequence[tuple[ChunkRecord, float]],
    bm25_hits: Sequence[tuple[ChunkRecord, float]],
    rrf_k: int = 60,
) -> list[SearchHit]:
    """Combine dense vector and BM25 rankings using Reciprocal Rank Fusion: sum(1 / (k + rank))."""
    by_id: dict[str, ChunkRecord] = {}
    vec_rank_map: dict[str, tuple[int, float]] = {}
    bm25_rank_map: dict[str, tuple[int, float]] = {}
    rrf_scores: dict[str, float] = {}

    for rank, (chunk, score) in enumerate(dense_hits, start=1):
        cid = chunk.chunk_id
        by_id[cid] = chunk
        vec_rank_map[cid] = (rank, score)
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)

    for rank, (chunk, score) in enumerate(bm25_hits, start=1):
        cid = chunk.chunk_id
        by_id[cid] = chunk
        bm25_rank_map[cid] = (rank, score)
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)

    ordered_ids = sorted(rrf_scores.keys(), key=lambda cid: (-rrf_scores[cid], cid))
    fused: list[SearchHit] = []
    for idx, cid in enumerate(ordered_ids, start=1):
        ch = by_id[cid]
        v_info = vec_rank_map.get(cid)
        b_info = bm25_rank_map.get(cid)
        r_score = round(rrf_scores[cid], 6)
        fused.append(
            _build_hit(
                chunk=ch,
                rank=idx,
                score=r_score,
                vector_rank=v_info[0] if v_info else None,
                vector_score=round(v_info[1], 6) if v_info else None,
                bm25_rank=b_info[0] if b_info else None,
                bm25_score=round(b_info[1], 6) if b_info else None,
                rrf_score=r_score,
            )
        )
    return fused


def _build_hit(
    chunk: ChunkRecord,
    rank: int,
    score: float,
    vector_rank: int | None = None,
    vector_score: float | None = None,
    bm25_rank: int | None = None,
    bm25_score: float | None = None,
    rrf_score: float | None = None,
    rerank_score: float | None = None,
) -> SearchHit:
    return SearchHit(
        rank=rank,
        score=score,
        chunk_id=chunk.chunk_id,
        source=chunk.source,
        title=chunk.title,
        section=chunk.section,
        date=chunk.date,
        version=chunk.version,
        doc_hash=chunk.doc_hash,
        doc_type=chunk.doc_type,
        format=chunk.format,
        report_id=chunk.report_id,
        is_latest=chunk.is_latest,
        token_count=chunk.token_count,
        text=chunk.text,
        vector_rank=vector_rank,
        vector_score=vector_score,
        bm25_rank=bm25_rank,
        bm25_score=bm25_score,
        rrf_score=rrf_score,
        rerank_score=rerank_score,
    )


class HybridSearchEngine:
    """Unified retriever supporting vector, BM25, hybrid RRF, and multilingual reranking."""

    def __init__(
        self,
        chunks: Sequence[ChunkRecord] | None = None,
        qdrant_client: QdrantClient | None = None,
        qdrant_location: str | Path = DEFAULT_QDRANT_PATH,
        collection_name: str = DEFAULT_COLLECTION,
        embedder: EmbedderProtocol | None = None,
        reranker: RerankerProtocol | None = None,
        rrf_k: int = 60,
    ) -> None:
        self.chunks = list(chunks) if chunks is not None else load_chunks_jsonl()
        self.collection_name = collection_name
        self.embedder = embedder or FastEmbedProvider()
        self._reranker = reranker
        self.rrf_k = rrf_k
        self._owns_client = qdrant_client is None
        self.client = qdrant_client or open_qdrant_client(qdrant_location)
        if not self.client.collection_exists(self.collection_name):
            index_chunks_to_qdrant(
                self.chunks, self.client, self.embedder, self.collection_name, recreate=False
            )
        self.bm25 = BM25LexicalIndex(self.chunks)

    @property
    def reranker(self) -> RerankerProtocol:
        if self._reranker is None:
            self._reranker = FastRerankProvider()
        return self._reranker

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def search(
        self,
        query: str,
        mode: SearchMode = "hybrid_rerank",
        top_k: int = 5,
        candidate_pool: int = 20,
        filters: SearchFilters | None = None,
    ) -> list[SearchHit]:
        pool_k = max(top_k, candidate_pool)
        if mode == "vector":
            dense = query_qdrant_dense(
                self.client, self.embedder, query, top_k=top_k, filters=filters, collection_name=self.collection_name
            )
            return [
                _build_hit(ch, r, round(sc, 6), vector_rank=r, vector_score=round(sc, 6))
                for r, (ch, sc) in enumerate(dense, start=1)
            ]

        if mode == "bm25":
            lex = self.bm25.search(query, top_k=top_k, filters=filters)
            return [
                _build_hit(ch, r, round(sc, 6), bm25_rank=r, bm25_score=round(sc, 6))
                for r, (ch, sc) in enumerate(lex, start=1)
            ]

        dense_pool = query_qdrant_dense(
            self.client, self.embedder, query, top_k=pool_k, filters=filters, collection_name=self.collection_name
        )
        bm25_pool = self.bm25.search(query, top_k=pool_k, filters=filters)
        fused = reciprocal_rank_fusion(dense_pool, bm25_pool, rrf_k=self.rrf_k)

        if mode == "hybrid":
            return fused[:top_k]

        if mode == "hybrid_rerank":
            shortlist = fused[:pool_k]
            if not shortlist:
                return []
            ce_scores = self.reranker.score(query, [h.text for h in shortlist])
            reranked = sorted(
                zip(shortlist, ce_scores),
                key=lambda pair: (-pair[1], -(pair[0].rrf_score or 0.0), pair[0].chunk_id),
            )
            results: list[SearchHit] = []
            for idx, (hit, ce_sc) in enumerate(reranked[:top_k], start=1):
                updated = hit.model_copy(
                    update={"rank": idx, "score": round(ce_sc, 6), "rerank_score": round(ce_sc, 6)}
                )
                results.append(updated)
            return results

        raise ValueError(f"Unsupported search mode: {mode}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="HW2 Step 2 Hybrid Search CLI")
    parser.add_argument("--query", required=True, help="Search question in Ukrainian or English")
    parser.add_argument(
        "--mode",
        choices=["vector", "bm25", "hybrid", "hybrid_rerank"],
        default="hybrid_rerank",
        help="Retrieval mode",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of hits to return")
    parser.add_argument("--only-latest", action="store_true", help="Filter is_latest=True")
    parser.add_argument("--doc-type", default=None, help="Filter by doc_type (e.g. kpi_spec, runbook)")
    parser.add_argument("--format", dest="fmt", default=None, help="Filter by format (pdf, docx, html, md)")
    parser.add_argument("--report-id", default=None, help="Filter by report_id (e.g. RPT-FIN-004)")
    parser.add_argument("--date-from", default=None, help="Filter date >= YYYY-MM-DD")
    parser.add_argument("--date-to", default=None, help="Filter date <= YYYY-MM-DD")
    parser.add_argument(
        "--qdrant-path",
        default=os.getenv("HW2_QDRANT_PATH", str(DEFAULT_QDRANT_PATH)),
        help="Qdrant storage path or :memory:",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON output")
    args = parser.parse_args()

    filters = SearchFilters(
        is_latest=True if args.only_latest else None,
        doc_type=args.doc_type,
        format=args.fmt,
        report_id=args.report_id,
        date_from=args.date_from,
        date_to=args.date_to,
    )
    engine = HybridSearchEngine(qdrant_location=args.qdrant_path)
    try:
        hits = engine.search(query=args.query, mode=args.mode, top_k=args.top_k, filters=filters)
    finally:
        engine.close()

    if args.json:
        print(json.dumps([h.model_dump(mode="json") for h in hits], ensure_ascii=False, indent=2))
        return
    for h in hits:
        print(
            f"[{h.rank}] {h.chunk_id} (score={h.score:.4f}, v={h.version}, latest={h.is_latest}) "
            f"— {h.title} › {h.section}"
        )


if __name__ == "__main__":
    main()
