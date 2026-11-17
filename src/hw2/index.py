"""Qdrant vector index builder, metadata filter translator, and CLI (`python -m src.hw2.index`)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Sequence
import uuid

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Condition,
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from src.hw2.embeddings import EmbedderProtocol, FastEmbedProvider
from src.hw2.models import ChunkRecord, IndexMeta, SearchFilters

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS_PATH = ROOT / "data" / "hw2_corpus" / "chunks.jsonl"
DEFAULT_INDEX_DIR = ROOT / "data" / "hw2_index"
DEFAULT_QDRANT_PATH = DEFAULT_INDEX_DIR / "qdrant"
DEFAULT_COLLECTION = "hw2_analytics_chunks"

_POINT_NAMESPACE = uuid.UUID("9f32e1a4-7b12-4d91-8a4c-2c1f7e50b211")


def load_chunks_jsonl(chunks_path: Path = DEFAULT_CHUNKS_PATH) -> list[ChunkRecord]:
    """Load validated ChunkRecord entries from chunks.jsonl."""
    if not chunks_path.is_file():
        raise FileNotFoundError(f"Chunks file not found: {chunks_path}")
    records: list[ChunkRecord] = []
    for line in chunks_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(ChunkRecord.model_validate_json(line))
    return records


def chunk_point_uuid(chunk_id: str) -> str:
    """Deterministic UUIDv5 from chunk_id for idempotent Qdrant upserts."""
    return str(uuid.uuid5(_POINT_NAMESPACE, chunk_id))


def open_qdrant_client(qdrant_location: str | Path = DEFAULT_QDRANT_PATH) -> QdrantClient:
    """Open an in-memory (`:memory:`), remote URL, or persistent local Qdrant client."""
    loc = str(qdrant_location)
    if loc == ":memory:":
        return QdrantClient(location=":memory:")
    if loc.startswith(("http://", "https://")):
        return QdrantClient(url=loc)
    path = Path(loc)
    path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(path))


def build_qdrant_filter(filters: SearchFilters | None) -> Filter | None:
    """Translate structured SearchFilters into a Qdrant Filter."""
    if filters is None:
        return None
    must: list[Condition] = []
    if filters.is_latest is not None:
        must.append(FieldCondition(key="is_latest", match=MatchValue(value=filters.is_latest)))

    for field_name in ("doc_type", "format", "report_id", "source"):
        val = getattr(filters, field_name)
        if val is None:
            continue
        if isinstance(val, str):
            must.append(FieldCondition(key=field_name, match=MatchValue(value=val)))
        elif val:
            must.append(FieldCondition(key=field_name, match=MatchAny(any=list(val))))

    return Filter(must=must) if must else None


def _date_in_range(date_str: str, filters: SearchFilters | None) -> bool:
    if filters is None:
        return True
    if filters.date_from and date_str < filters.date_from:
        return False
    if filters.date_to and date_str > filters.date_to:
        return False
    return True


def index_chunks_to_qdrant(
    chunks: Sequence[ChunkRecord],
    client: QdrantClient,
    embedder: EmbedderProtocol,
    collection_name: str = DEFAULT_COLLECTION,
    recreate: bool = True,
) -> IndexMeta:
    """Embed chunks and upsert full payload metadata into Qdrant."""
    if recreate and client.collection_exists(collection_name):
        client.delete_collection(collection_name)
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=embedder.dim, distance=Distance.COSINE),
        )

    vectors = embedder.embed_passages([c.text for c in chunks])
    points = [
        PointStruct(
            id=chunk_point_uuid(chunk.chunk_id),
            vector=vec,
            payload=chunk.model_dump(mode="json"),
        )
        for chunk, vec in zip(chunks, vectors)
    ]
    if points:
        client.upsert(collection_name=collection_name, points=points, wait=True)

    canonical_blob = "\n".join(c.chunk_id + ":" + c.doc_hash for c in chunks).encode("utf-8")
    return IndexMeta(
        built_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        collection_name=collection_name,
        embedding_model=embedder.model_name,
        embedding_dim=embedder.dim,
        chunks_count=len(chunks),
        chunks_sha256=hashlib.sha256(canonical_blob).hexdigest(),
    )


def query_qdrant_dense(
    client: QdrantClient,
    embedder: EmbedderProtocol,
    query: str,
    top_k: int = 20,
    filters: SearchFilters | None = None,
    collection_name: str = DEFAULT_COLLECTION,
) -> list[tuple[ChunkRecord, float]]:
    """Run dense cosine similarity search in Qdrant with payload filters."""
    if top_k <= 0:
        return []
    q_vec = embedder.embed_query(query)
    q_filter = build_qdrant_filter(filters)
    fetch_limit = top_k * 3 if (filters and (filters.date_from or filters.date_to)) else top_k
    resp = client.query_points(
        collection_name=collection_name,
        query=q_vec,
        query_filter=q_filter,
        limit=fetch_limit,
        with_payload=True,
    )
    hits: list[tuple[ChunkRecord, float]] = []
    for pt in resp.points:
        payload = pt.payload or {}
        if not _date_in_range(str(payload.get("date", "")), filters):
            continue
        hits.append((ChunkRecord.model_validate(payload), float(pt.score)))
        if len(hits) >= top_k:
            break
    return hits


def build_persistent_index(
    chunks_path: Path = DEFAULT_CHUNKS_PATH,
    qdrant_path: str | Path = DEFAULT_QDRANT_PATH,
    collection_name: str = DEFAULT_COLLECTION,
    embedder: EmbedderProtocol | None = None,
) -> IndexMeta:
    """Build or refresh the persistent local Qdrant collection and write index_meta.json."""
    chunks = load_chunks_jsonl(chunks_path)
    emb = embedder or FastEmbedProvider()
    client = open_qdrant_client(qdrant_path)
    try:
        meta = index_chunks_to_qdrant(
            chunks=chunks,
            client=client,
            embedder=emb,
            collection_name=collection_name,
            recreate=True,
        )
    finally:
        client.close()

    if str(qdrant_path) != ":memory:" and not str(qdrant_path).startswith(("http://", "https://")):
        meta_path = Path(qdrant_path).parent / "index_meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(meta.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return meta


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Build HW2 Step 2 Qdrant vector index")
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_PATH, help="Path to chunks.jsonl")
    parser.add_argument(
        "--qdrant-path",
        default=os.getenv("HW2_QDRANT_PATH", str(DEFAULT_QDRANT_PATH)),
        help="Local Qdrant directory or :memory:",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("HW2_QDRANT_COLLECTION", DEFAULT_COLLECTION),
        help="Qdrant collection name",
    )
    args = parser.parse_args()

    meta = build_persistent_index(
        chunks_path=args.chunks,
        qdrant_path=args.qdrant_path,
        collection_name=args.collection,
    )
    print(
        f"Indexed {meta.chunks_count} chunks into Qdrant collection '{meta.collection_name}' "
        f"(model={meta.embedding_model}, dim={meta.embedding_dim}) at {args.qdrant_path}"
    )


if __name__ == "__main__":
    main()
