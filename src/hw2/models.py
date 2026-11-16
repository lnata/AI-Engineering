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


class SearchFilters(BaseModel):
    """Structured metadata filters applied consistently in Qdrant and BM25."""

    is_latest: bool | None = None
    doc_type: str | list[str] | None = None
    format: str | list[str] | None = None
    report_id: str | list[str] | None = None
    source: str | list[str] | None = None
    date_from: str | None = None  # ISO YYYY-MM-DD inclusive
    date_to: str | None = None  # ISO YYYY-MM-DD inclusive


class SearchHit(BaseModel):
    """Unified retrieval result carrying per-stage ranks, scores, and chunk payload."""

    rank: int
    score: float
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
    vector_rank: int | None = None
    vector_score: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


class IndexMeta(BaseModel):
    """Metadata describing a built Qdrant + BM25 index."""

    pipeline_version: str = "hw2-step2-v1.0"
    built_at: str
    collection_name: str
    embedding_model: str
    embedding_dim: int
    chunks_count: int
    chunks_sha256: str


class PackedSource(BaseModel):
    """One numbered [Si] context block packed within the token budget."""

    source_id: str
    chunk_id: str
    source: str
    title: str
    section: str
    version: str
    date: str
    is_latest: bool
    score: float
    rerank_score: float | None = None
    packed_tokens: int
    formatted_block: str


class PackedContext(BaseModel):
    """Telemetry and formatted context produced by deterministic context packing."""

    budget_tokens: int
    used_tokens: int
    gate_passed: bool
    gate_reason: str | None = None
    included_sources: list[PackedSource] = Field(default_factory=list)
    dropped_for_budget: list[str] = Field(default_factory=list)
    dropped_for_low_relevance: list[str] = Field(default_factory=list)
    context_text: str = ""


class RAGClaim(BaseModel):
    """Single factual statement grounded in one or more packed [Si] sources."""

    statement: str
    source_ids: list[str] = Field(default_factory=list)


class RAGCitation(BaseModel):
    """Resolved source document + section citation attached to a RAGAnswer."""

    source_id: str
    chunk_id: str
    source: str
    title: str
    section: str
    version: str
    date: str
    is_latest: bool


class RAGLLMResponse(BaseModel):
    """Strict structured output contract requested from the LLM generator."""

    abstained: bool
    abstain_reason: str | None = None
    answer: str
    claims: list[RAGClaim] = Field(default_factory=list)


class RAGAnswer(BaseModel):
    """Verified, citation-resolved RAG answer."""

    abstained: bool
    abstain_reason: str | None = None
    answer: str
    claims: list[RAGClaim] = Field(default_factory=list)
    citations: list[RAGCitation] = Field(default_factory=list)
    prompt_version: str


class RAGRunResult(BaseModel):
    """Full end-to-end execution trace for one RAG question."""

    ok: bool
    question: str
    provider: str
    model: str
    prompt_version: str
    repair_used: bool = False
    error: str | None = None
    latency_ms: float = 0.0
    usage: dict[str, int] = Field(default_factory=dict)
    estimated_cost_per_1k_usd: float = 0.0
    context: PackedContext
    rag_answer: RAGAnswer | None = None


