"""Multilingual dense embeddings and cross-encoder reranking (local ONNX via fastembed)."""

from __future__ import annotations

from functools import lru_cache
import os
from typing import Protocol, Sequence

from dotenv import load_dotenv
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3-int8"


class EmbedderProtocol(Protocol):
    """Minimal protocol allowing lightweight test doubles in unit tests."""

    model_name: str
    dim: int

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, query: str) -> list[float]: ...


class RerankerProtocol(Protocol):
    """Minimal protocol for cross-encoder rerankers."""

    model_name: str

    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


def _is_e5_family(model_name: str) -> bool:
    lowered = model_name.lower()
    return "e5-" in lowered or lowered.endswith("/e5")


class FastEmbedProvider:
    """Multilingual ONNX dense embedder backed by fastembed ($0 local cost)."""

    def __init__(self, model_name: str | None = None) -> None:
        load_dotenv()
        self.model_name = model_name or os.getenv("HW2_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        self._use_e5_prefix = _is_e5_family(self.model_name)
        self._model = _load_fastembed_model(self.model_name)
        probe = next(iter(self._model.embed(["probe"])))
        self.dim = int(len(probe))

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        prepared = [f"passage: {t}" for t in texts] if self._use_e5_prefix else list(texts)
        return [[float(x) for x in vec] for vec in self._model.embed(prepared)]

    def embed_query(self, query: str) -> list[float]:
        prepared = f"query: {query}" if self._use_e5_prefix else query
        vec = next(iter(self._model.embed([prepared])))
        return [float(x) for x in vec]


class FastRerankProvider:
    """Multilingual ONNX cross-encoder reranker backed by fastembed ($0 local cost)."""

    def __init__(self, model_name: str | None = None) -> None:
        load_dotenv()
        self.model_name = model_name or os.getenv("HW2_RERANKER_MODEL", DEFAULT_RERANKER_MODEL)
        self._model = _load_reranker_model(self.model_name)

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        return [float(s) for s in self._model.rerank(query, list(passages))]


@lru_cache(maxsize=2)
def _load_fastembed_model(model_name: str) -> TextEmbedding:
    return TextEmbedding(model_name=model_name)


@lru_cache(maxsize=2)
def _load_reranker_model(model_name: str) -> TextCrossEncoder:
    return TextCrossEncoder(model_name=model_name)
