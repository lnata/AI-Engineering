"""Deterministic tiktoken context packer and Gate-1 pre-LLM abstention check."""

from __future__ import annotations

from typing import Sequence

from src.hw2.bm25_index import tokenize_bm25
from src.hw2.chunking import count_tokens
from src.hw2.models import PackedContext, PackedSource, SearchHit

DEFAULT_MAX_CONTEXT_TOKENS = 1200
DEFAULT_MIN_RERANK_SCORE = -4.5
DEFAULT_MIN_VECTOR_SCORE = 0.35
DEFAULT_MIN_BM25_SCORE = 4.0

_GENERIC_QUERY_TERMS = frozenset(
    {
        "звіт",
        "звіті",
        "звіту",
        "дані",
        "даних",
        "правило",
        "правила",
        "компанії",
        "році",
        "рік",
        "відділ",
        "відділу",
        "система",
        "системі",
        "налаштувати",
        "корпоративній",
        "корпоративний",
    }
)


def _strip_embedded_context_header(chunk_text: str) -> str:
    """Strip the Step-1 bracket prefix `[Title | vX.Y | Section]` to avoid duplicating metadata."""
    if chunk_text.startswith("[") and "]\n\n" in chunk_text:
        return chunk_text.split("]\n\n", 1)[1].strip()
    return chunk_text.strip()


def format_source_block(source_id: str, hit: SearchHit) -> str:
    """Render one numbered [Si] block with explicit document, section, version, and status."""
    body = _strip_embedded_context_header(hit.text)
    header = (
        f"[{source_id}] source={hit.source} | title={hit.title} | "
        f"section={hit.section} | version={hit.version} | date={hit.date} | "
        f"is_latest={str(hit.is_latest).lower()}"
    )
    return f"{header}\n{body}"


def _passes_relevance_gate(
    query: str,
    hit: SearchHit,
    min_rerank_score: float = DEFAULT_MIN_RERANK_SCORE,
    min_vector_score: float = DEFAULT_MIN_VECTOR_SCORE,
    min_bm25_score: float = DEFAULT_MIN_BM25_SCORE,
) -> bool:
    """Check whether a retrieved chunk has sufficient domain evidence to enter <context>."""
    if hit.rerank_score is not None:
        return hit.rerank_score >= min_rerank_score

    q_terms = {t for t in tokenize_bm25(query) if t not in _GENERIC_QUERY_TERMS and not t.isdigit()}
    c_terms = set(tokenize_bm25(hit.text))
    has_lexical_overlap = bool(q_terms & c_terms)

    if hit.bm25_score is not None and hit.bm25_score >= min_bm25_score and has_lexical_overlap:
        return True
    if hit.vector_score is not None and hit.vector_score >= min_vector_score and has_lexical_overlap:
        return True
    return False


def pack_retrieved_context(
    query: str,
    hits: Sequence[SearchHit],
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    min_rerank_score: float = DEFAULT_MIN_RERANK_SCORE,
    min_vector_score: float = DEFAULT_MIN_VECTOR_SCORE,
    min_bm25_score: float = DEFAULT_MIN_BM25_SCORE,
) -> PackedContext:
    """Filter low-relevance hits and pack [S1]..[Sk] strictly within max_context_tokens."""
    if max_context_tokens <= 0:
        raise ValueError("max_context_tokens must be positive")

    if not hits:
        return PackedContext(
            budget_tokens=max_context_tokens,
            used_tokens=0,
            gate_passed=False,
            gate_reason="insufficient_retrieval_evidence",
        )

    relevant_hits: list[SearchHit] = []
    dropped_low_rel: list[str] = []
    for hit in hits:
        if _passes_relevance_gate(
            query,
            hit,
            min_rerank_score=min_rerank_score,
            min_vector_score=min_vector_score,
            min_bm25_score=min_bm25_score,
        ):
            relevant_hits.append(hit)
        else:
            dropped_low_rel.append(hit.chunk_id)

    if not relevant_hits:
        return PackedContext(
            budget_tokens=max_context_tokens,
            used_tokens=0,
            gate_passed=False,
            gate_reason="insufficient_retrieval_evidence",
            dropped_for_low_relevance=dropped_low_rel,
        )

    included: list[PackedSource] = []
    dropped_budget: list[str] = []
    blocks: list[str] = []
    used_tokens = 0
    sep = "\n\n"
    sep_tokens = count_tokens(sep)

    for hit in relevant_hits:
        next_sid = f"S{len(included) + 1}"
        block = format_source_block(next_sid, hit)
        block_toks = count_tokens(block)
        added_toks = block_toks if not blocks else (sep_tokens + block_toks)

        if used_tokens + added_toks > max_context_tokens:
            dropped_budget.append(hit.chunk_id)
            continue

        candidate_joined = sep.join([*blocks, block])
        exact_total = count_tokens(candidate_joined)
        if exact_total > max_context_tokens:
            dropped_budget.append(hit.chunk_id)
            continue

        blocks.append(block)
        used_tokens = exact_total
        included.append(
            PackedSource(
                source_id=next_sid,
                chunk_id=hit.chunk_id,
                source=hit.source,
                title=hit.title,
                section=hit.section,
                version=hit.version,
                date=hit.date,
                is_latest=hit.is_latest,
                score=hit.score,
                rerank_score=hit.rerank_score,
                packed_tokens=block_toks,
                formatted_block=block,
            )
        )

    if not included:
        return PackedContext(
            budget_tokens=max_context_tokens,
            used_tokens=0,
            gate_passed=False,
            gate_reason="context_budget_too_small",
            dropped_for_budget=dropped_budget,
            dropped_for_low_relevance=dropped_low_rel,
        )

    return PackedContext(
        budget_tokens=max_context_tokens,
        used_tokens=used_tokens,
        gate_passed=True,
        included_sources=included,
        dropped_for_budget=dropped_budget,
        dropped_for_low_relevance=dropped_low_rel,
        context_text=sep.join(blocks),
    )
