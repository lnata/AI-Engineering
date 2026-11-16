"""Pydantic schemas for HW2 corpus manifest, chunks, and chunking comparison."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedDocument(BaseModel):
    """Cleaned, normalized document with extracted structural Markdown and metadata."""

    source: str
    raw_hash: str
    doc_hash: str
    doc_id: str
    title: str
    doc_type: str
    format: str
    date: str
    version: str
    report_id: str | None = None
    is_latest: bool = True
    cleaned_markdown: str


class ChunkRecord(BaseModel):
    """Single output chunk stored in data/hw2_corpus/chunks.jsonl."""

    chunk_id: str
    source: str
    title: str
    section: str
    date: str
    version: str
    doc_hash: str
    doc_type: str
    format: str
    report_id: str | None = None
    is_latest: bool = True
    token_count: int
    text: str


class SkippedDuplicate(BaseModel):
    """Audit record for an exact content duplicate skipped during ingestion."""

    source: str
    format: str
    raw_hash: str
    doc_hash: str
    canonical_source: str


class ManifestDocEntry(BaseModel):
    """Per-document entry inside data/hw2_corpus/manifest.json."""

    source: str
    doc_id: str
    title: str
    format: str
    doc_type: str
    version: str
    date: str
    report_id: str | None = None
    is_latest: bool = True
    raw_hash: str
    doc_hash: str
    char_count: int
    chunk_count: int


class CorpusManifest(BaseModel):
    """Top-level manifest written to data/hw2_corpus/manifest.json."""

    pipeline_version: str = "hw2-step1-v1.0"
    generated_at: str
    total_raw_files: int
    unique_ingested_docs: int
    skipped_duplicates_count: int
    total_chunks: int
    format_counts_raw: dict[str, int]
    format_counts_unique: dict[str, int]
    skipped_duplicates: list[SkippedDuplicate] = Field(default_factory=list)
    documents: list[ManifestDocEntry] = Field(default_factory=list)


class ChunkStrategyMetrics(BaseModel):
    """Quantitative quality metrics for a chunking strategy."""

    strategy: str
    parameters: dict[str, int | str]
    chunk_count: int
    avg_tokens: float
    min_tokens: int
    max_tokens: int
    p50_tokens: int
    p95_tokens: int
    broken_table_count: int
    mid_sentence_split_count: int
    mid_sentence_split_rate: float
    cross_section_bleed_count: int


class SampleChunkDefect(BaseModel):
    """Concrete example illustrating why naive fixed-size chunking degrades retrieval."""

    source: str
    chunk_id: str
    defect_type: str
    excerpt: str


class ChunkingComparison(BaseModel):
    """Comparison artifact written to data/hw2_corpus/chunking_comparison.json."""

    tokenizer: str = "cl100k_base"
    evaluated_documents: int
    structure_aware: ChunkStrategyMetrics
    fixed_size_baseline: ChunkStrategyMetrics
    fixed_size_defect_samples: list[SampleChunkDefect] = Field(default_factory=list)
