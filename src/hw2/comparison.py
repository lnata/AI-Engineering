"""Quality evaluation and comparison metrics for HW2 chunking strategies."""

from __future__ import annotations

import math
import re

from src.hw2.chunking import chunk_document_fixed_size, chunk_document_structure_aware
from src.hw2.models import (
    ChunkingComparison,
    ChunkRecord,
    ChunkStrategyMetrics,
    ExtractedDocument,
    SampleChunkDefect,
)

_TERMINAL_ENDINGS = (".", "!", "?", "|", ":", ")", '"', "'", "»")


def _has_broken_table(text: str) -> bool:
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("Doc ID:")
    ]
    pipe_lines = [
        ln
        for ln in lines
        if (ln.startswith("|") or ln.endswith("|") or re.search(r"\|\s*---", ln))
    ]
    if not pipe_lines:
        return False
    has_sep = any(re.match(r"^\|\s*---", ln) for ln in pipe_lines)
    if not has_sep:
        return True
    sep_idx = next(i for i, ln in enumerate(pipe_lines) if re.match(r"^\|\s*---", ln))
    expected_pipes = pipe_lines[sep_idx].count("|")
    if sep_idx == 0:
        return True
    return any(
        not (ln.startswith("|") and ln.endswith("|")) or ln.count("|") != expected_pipes
        for ln in pipe_lines
    )


def _has_mid_sentence_split(text: str) -> bool:
    body_lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not (ln.strip().startswith("[") and ln.strip().endswith("]"))
    ]
    if not body_lines:
        return False
    first = body_lines[0]
    last = body_lines[-1]
    starts_mid = bool(first) and first[0].islower()
    ends_mid = not last.endswith(_TERMINAL_ENDINGS) and not last.startswith(("#", "|"))
    return starts_mid or ends_mid


def _has_cross_section_bleed(chunk: ChunkRecord, doc_headings_by_source: dict[str, list[str]]) -> bool:
    headings = doc_headings_by_source.get(chunk.source, [])
    body = chunk.text
    if body.startswith("[") and "\n\n" in body:
        body = body.split("\n\n", 1)[1]
    if len(headings) >= 2 and sum(1 for h in headings if h in body) >= 2:
        return True
    lines = [
        ln.strip()
        for ln in body.splitlines()
        if ln.strip() and not ln.strip().startswith("# ") and not ln.strip().startswith("Doc ID:")
    ]
    seen_prior_section_body = False
    for ln in lines:
        if ln.startswith("## ") or ln.startswith("### "):
            if seen_prior_section_body:
                return True
        else:
            seen_prior_section_body = True
    return False


def _percentile(sorted_vals: list[int], pct: float) -> int:
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1, math.ceil((pct / 100.0) * len(sorted_vals)) - 1))
    return sorted_vals[k]


def compute_strategy_metrics(
    strategy: str,
    parameters: dict[str, int | str],
    chunks: list[ChunkRecord],
    headings_map: dict[str, list[str]],
) -> ChunkStrategyMetrics:
    toks = sorted(c.token_count for c in chunks)
    n = len(chunks)
    broken_tbl = sum(1 for c in chunks if _has_broken_table(c.text))
    mid_sent = sum(1 for c in chunks if _has_mid_sentence_split(c.text))
    bleed = sum(1 for c in chunks if _has_cross_section_bleed(c, headings_map))
    return ChunkStrategyMetrics(
        strategy=strategy,
        parameters=parameters,
        chunk_count=n,
        avg_tokens=round(sum(toks) / n, 2) if n else 0.0,
        min_tokens=toks[0] if toks else 0,
        max_tokens=toks[-1] if toks else 0,
        p50_tokens=_percentile(toks, 50),
        p95_tokens=_percentile(toks, 95),
        broken_table_count=broken_tbl,
        mid_sentence_split_count=mid_sent,
        mid_sentence_split_rate=round(mid_sent / n, 4) if n else 0.0,
        cross_section_bleed_count=bleed,
    )


def compare_chunking_strategies(
    docs: list[ExtractedDocument],
    sa_max_tokens: int = 360,
    sa_overlap_tokens: int = 45,
    fs_chunk_tokens: int = 240,
    fs_overlap_tokens: int = 40,
) -> tuple[list[ChunkRecord], ChunkingComparison]:
    """Run both chunkers over unique documents and build quantitative comparison report."""
    headings_map: dict[str, list[str]] = {}
    for doc in docs:
        headings_map[doc.source] = [
            ln.lstrip("#").strip()
            for ln in doc.cleaned_markdown.splitlines()
            if ln.startswith("## ")
        ]

    sa_chunks: list[ChunkRecord] = []
    fs_chunks: list[ChunkRecord] = []
    for doc in docs:
        sa_chunks.extend(chunk_document_structure_aware(doc, sa_max_tokens, sa_overlap_tokens))
        fs_chunks.extend(chunk_document_fixed_size(doc, fs_chunk_tokens, fs_overlap_tokens))

    sa_metrics = compute_strategy_metrics(
        "structure_aware",
        {"max_tokens": sa_max_tokens, "overlap_tokens": sa_overlap_tokens, "table_atomic": "true"},
        sa_chunks,
        headings_map,
    )
    fs_metrics = compute_strategy_metrics(
        "fixed_size",
        {"chunk_tokens": fs_chunk_tokens, "overlap_tokens": fs_overlap_tokens},
        fs_chunks,
        headings_map,
    )

    samples: list[SampleChunkDefect] = []
    for ch in fs_chunks:
        if len(samples) >= 5:
            break
        if _has_broken_table(ch.text):
            samples.append(
                SampleChunkDefect(
                    source=ch.source,
                    chunk_id=ch.chunk_id,
                    defect_type="broken_table",
                    excerpt=ch.text[:220].replace("\n", " ⏎ "),
                )
            )
        elif _has_cross_section_bleed(ch, headings_map):
            samples.append(
                SampleChunkDefect(
                    source=ch.source,
                    chunk_id=ch.chunk_id,
                    defect_type="cross_section_bleed",
                    excerpt=ch.text[:220].replace("\n", " ⏎ "),
                )
            )

    comparison = ChunkingComparison(
        evaluated_documents=len(docs),
        structure_aware=sa_metrics,
        fixed_size_baseline=fs_metrics,
        fixed_size_defect_samples=samples,
    )
    return sa_chunks, comparison
