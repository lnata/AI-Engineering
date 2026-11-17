"""Domain-aware multilingual BM25 lexical index preserving technical identifiers."""

from __future__ import annotations

import re
from typing import Sequence

from rank_bm25 import BM25Okapi

from src.hw2.models import ChunkRecord, SearchFilters

_TECH_TOKEN_RE = re.compile(
    r"""
    [A-Za-z0-9]+(?:[-_.][A-Za-z0-9*]+)+   # SPEC-FIN-030, mart.fact_orders, v1.3, Z_SD_SALES_ORDER
    | [A-Za-zА-Яа-яІіЇїЄєҐґ0-9']+         # Ukrainian, English, alphanumeric words
    """,
    re.VERBOSE,
)

_STOPWORDS = frozenset(
    {
        # Ukrainian function words
        "та",
        "і",
        "й",
        "у",
        "в",
        "на",
        "до",
        "з",
        "із",
        "зі",
        "за",
        "по",
        "для",
        "від",
        "про",
        "при",
        "як",
        "що",
        "це",
        "чи",
        "або",
        "але",
        "не",
        "який",
        "яка",
        "яке",
        "які",
        "яких",
        "якому",
        "між",
        "під",
        "час",
        # English function words
        "the",
        "and",
        "or",
        "of",
        "in",
        "to",
        "for",
        "on",
        "with",
        "by",
        "is",
        "are",
        "vs",
    }
)


def _light_uk_en_stem(word: str) -> str:
    """Conservative stemmer for Ukrainian/English prose words (>= 6 chars) to bridge inflections."""
    if len(word) < 6 or not word.isalpha():
        return word
    for suffix in (
        "ями",
        "ами",
        "ості",
        "ість",
        "ення",
        "ання",
        "ого",
        "ому",
        "ими",
        "ією",
        "ією",
        "ій",
        "ої",
        "ів",
        "їв",
        "ам",
        "ах",
        "ях",
        "ою",
        "ею",
        "ує",
        "ють",
        "ing",
        "tion",
        "ed",
        "es",
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    if len(word) >= 6 and word[-1] in "аяиіїуеоs":
        return word[:-1]
    return word


def tokenize_bm25(text: str) -> list[str]:
    """Extract normalized technical compounds, sub-parts, and lightly stemmed NL words."""
    tokens: list[str] = []
    for raw_match in _TECH_TOKEN_RE.findall(text):
        low = raw_match.casefold().strip("._-'")
        if not low or low in _STOPWORDS:
            continue
        is_compound = any(sep in low for sep in ("-", "_", "."))
        if is_compound:
            tokens.append(low)
            for sub in re.split(r"[-_.*]+", low):
                if len(sub) >= 2 and sub not in _STOPWORDS:
                    tokens.append(sub)
        else:
            tokens.append(low)
            stemmed = _light_uk_en_stem(low)
            if stemmed != low:
                tokens.append(stemmed)
    return tokens


def chunk_matches_filters(chunk: ChunkRecord, filters: SearchFilters | None) -> bool:
    """Evaluate SearchFilters identically against in-memory BM25 candidates."""
    if filters is None:
        return True
    if filters.is_latest is not None and chunk.is_latest != filters.is_latest:
        return False
    if not _match_scalar_or_list(chunk.doc_type, filters.doc_type):
        return False
    if not _match_scalar_or_list(chunk.format, filters.format):
        return False
    if not _match_scalar_or_list(chunk.report_id, filters.report_id):
        return False
    if not _match_scalar_or_list(chunk.source, filters.source):
        return False
    if filters.date_from and chunk.date < filters.date_from:
        return False
    if filters.date_to and chunk.date > filters.date_to:
        return False
    return True


def _match_scalar_or_list(val: str | None, allowed: str | list[str] | None) -> bool:
    if allowed is None:
        return True
    if val is None:
        return False
    if isinstance(allowed, str):
        return val == allowed
    return val in allowed


class BM25LexicalIndex:
    """Filtered BM25Okapi lexical retriever over ChunkRecord entries."""

    def __init__(self, chunks: Sequence[ChunkRecord]) -> None:
        self.chunks: list[ChunkRecord] = list(chunks)
        self._tokenized_corpus: list[list[str]] = [tokenize_bm25(c.text) for c in self.chunks]
        self._bm25 = BM25Okapi(self._tokenized_corpus) if self.chunks else None

    def search(
        self,
        query: str,
        top_k: int = 20,
        filters: SearchFilters | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        if not self._bm25 or top_k <= 0:
            return []
        q_tokens = tokenize_bm25(query)
        if not q_tokens:
            return []
        raw_scores = self._bm25.get_scores(q_tokens)
        scored: list[tuple[ChunkRecord, float]] = []
        for chunk, score in zip(self.chunks, raw_scores):
            if score <= 0.0:
                continue
            if not chunk_matches_filters(chunk, filters):
                continue
            scored.append((chunk, float(score)))
        scored.sort(key=lambda item: (-item[1], item[0].chunk_id))
        return scored[:top_k]
