"""End-to-end HW2 Step 1 ingestion CLI: raw corpus -> manifest, chunks, and comparison."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from src.hw2.cleaning import compute_doc_hash, compute_raw_hash
from src.hw2.comparison import compare_chunking_strategies
from src.hw2.extractors import extract_document_markdown
from src.hw2.json_extractor import is_analytics_domain_ticket
from src.hw2.models import (
    ChunkingComparison,
    ChunkRecord,
    CorpusManifest,
    ExtractedDocument,
    ManifestDocEntry,
    SkippedDuplicate,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = ROOT / "data" / "hw2_corpus" / "raw"
DEFAULT_HW1_TICKETS_DIR = ROOT / "data" / "raw"
DEFAULT_HW1_REF_DIR = ROOT / "data" / "reference"
DEFAULT_OUT_DIR = ROOT / "data" / "hw2_corpus"
SUPPORTED_EXTS = {".pdf", ".docx", ".html", ".htm", ".md", ".json"}

_META_LINE_RE = re.compile(
    r"Doc ID:\s*(?P<doc_id>[^|]+?)\s*\|\s*Version:\s*(?P<version>[^|]+?)\s*\|\s*"
    r"Effective Date:\s*(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*Type:\s*(?P<doc_type>[^|]+?)\s*\|\s*"
    r"Report:\s*(?P<report>[^|]+?)\s*\|\s*Status:\s*(?P<status>\S+)",
    re.IGNORECASE,
)
_FILENAME_VER_RE = re.compile(r"_v(\d+\.\d+)(?:_|$)", re.IGNORECASE)
_FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_MIRROR_HINT_RE = re.compile(r"(?:_mirror|_backup|_copy)\b", re.IGNORECASE)


def _normalize_ext(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return "html" if ext == "htm" else ext


def _sort_key_canonical_first(path: Path) -> tuple[int, str]:
    is_mirror = 1 if _MIRROR_HINT_RE.search(path.stem) else 0
    return (is_mirror, path.name)


def parse_document_metadata(path: Path, cleaned_md: str) -> dict[str, str | bool | None]:
    """Extract structured document metadata from header line with filename fallbacks."""
    title = path.stem
    for ln in cleaned_md.splitlines():
        if ln.startswith("# "):
            title = ln[2:].strip()
            break

    m = _META_LINE_RE.search(cleaned_md)
    if m:
        rep_raw = m.group("report").strip()
        report_id = None if rep_raw.upper() in {"NONE", "NULL", "PLATFORM-WIDE", "-"} else rep_raw
        is_latest = m.group("status").strip().upper() != "DEPRECATED"
        return {
            "doc_id": m.group("doc_id").strip(),
            "title": title,
            "version": m.group("version").strip(),
            "date": m.group("date").strip(),
            "doc_type": m.group("doc_type").strip().lower(),
            "report_id": report_id,
            "is_latest": is_latest,
        }

    ver_m = _FILENAME_VER_RE.search(path.stem)
    date_m = _FILENAME_DATE_RE.search(cleaned_md) or _FILENAME_DATE_RE.search(path.stem)
    stem_upper = path.stem.upper()
    doc_id = path.stem.split("_")[0]
    is_latest = "LEGACY" not in stem_upper and "DEPRECATED" not in cleaned_md.upper()
    return {
        "doc_id": doc_id,
        "title": title,
        "version": ver_m.group(1) if ver_m else "1.0",
        "date": date_m.group(1) if date_m else "2025-01-01",
        "doc_type": "document",
        "report_id": None,
        "is_latest": is_latest,
    }


def _discover_hw1_json_sources(
    tickets_dir: Path = DEFAULT_HW1_TICKETS_DIR,
    ref_dir: Path = DEFAULT_HW1_REF_DIR,
) -> list[Path]:
    """Collect Analytics domain Jira tickets (BUGS-41..53) and reference JSON catalogs."""
    found: list[Path] = []
    if ref_dir.is_dir():
        found.extend(sorted(ref_dir.glob("*.json")))
    if tickets_dir.is_dir():
        ticket_paths = sorted(
            tickets_dir.glob("BUGS-*.json"),
            key=lambda p: int(p.stem.split("-")[1]) if p.stem.split("-")[1].isdigit() else 9999,
        )
        for tp in ticket_paths:
            data = json.loads(tp.read_text(encoding="utf-8"))
            if isinstance(data, dict) and is_analytics_domain_ticket(data):
                found.append(tp)
    return found


def run_ingestion(
    raw_dir: Path = DEFAULT_RAW_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
    max_tokens: int = 360,
    overlap_tokens: int = 45,
    include_hw1_sources: bool | None = None,
) -> tuple[CorpusManifest, list[ChunkRecord], ChunkingComparison]:
    """Ingest raw multi-format corpus + HW1 Jira/reference JSONs, deduplicate, and chunk."""
    raw_files = sorted(
        (p for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS),
        key=_sort_key_canonical_first,
    )
    use_hw1 = (
        (raw_dir.resolve() == DEFAULT_RAW_DIR.resolve())
        if include_hw1_sources is None
        else include_hw1_sources
    )
    if use_hw1:
        raw_files.extend(_discover_hw1_json_sources())
    if not raw_files:
        raise FileNotFoundError(f"No supported corpus files found in {raw_dir}")

    format_counts_raw: Counter[str] = Counter()
    format_counts_unique: Counter[str] = Counter()
    seen_by_doc_hash: dict[str, str] = {}
    skipped_duplicates: list[SkippedDuplicate] = []
    unique_docs: list[ExtractedDocument] = []

    for path in raw_files:
        fmt = _normalize_ext(path)
        format_counts_raw[fmt] += 1
        try:
            rel_source = path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            rel_source = path.name

        raw_hash = compute_raw_hash(path.read_bytes())
        cleaned_md = extract_document_markdown(path)
        doc_hash = compute_doc_hash(cleaned_md)

        if doc_hash in seen_by_doc_hash:
            skipped_duplicates.append(
                SkippedDuplicate(
                    source=rel_source,
                    format=fmt,
                    raw_hash=raw_hash,
                    doc_hash=doc_hash,
                    canonical_source=seen_by_doc_hash[doc_hash],
                )
            )
            continue

        seen_by_doc_hash[doc_hash] = rel_source
        format_counts_unique[fmt] += 1
        meta = parse_document_metadata(path, cleaned_md)
        unique_docs.append(
            ExtractedDocument(
                source=rel_source,
                raw_hash=raw_hash,
                doc_hash=doc_hash,
                doc_id=str(meta["doc_id"]),
                title=str(meta["title"]),
                doc_type=str(meta["doc_type"]),
                format=fmt,
                date=str(meta["date"]),
                version=str(meta["version"]),
                report_id=meta["report_id"] if isinstance(meta["report_id"], str) else None,
                is_latest=bool(meta["is_latest"]),
                cleaned_markdown=cleaned_md,
            )
        )

    unique_docs.sort(key=lambda d: d.source)
    chunks, comparison = compare_chunking_strategies(
        unique_docs, sa_max_tokens=max_tokens, sa_overlap_tokens=overlap_tokens
    )
    chunk_counts = Counter(c.source for c in chunks)

    doc_entries = [
        ManifestDocEntry(
            source=d.source,
            doc_id=d.doc_id,
            title=d.title,
            format=d.format,
            doc_type=d.doc_type,
            version=d.version,
            date=d.date,
            report_id=d.report_id,
            is_latest=d.is_latest,
            raw_hash=d.raw_hash,
            doc_hash=d.doc_hash,
            char_count=len(d.cleaned_markdown),
            chunk_count=chunk_counts[d.source],
        )
        for d in unique_docs
    ]

    manifest = CorpusManifest(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_raw_files=len(raw_files),
        unique_ingested_docs=len(unique_docs),
        skipped_duplicates_count=len(skipped_duplicates),
        total_chunks=len(chunks),
        format_counts_raw=dict(sorted(format_counts_raw.items())),
        format_counts_unique=dict(sorted(format_counts_unique.items())),
        skipped_duplicates=skipped_duplicates,
        documents=doc_entries,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (out_dir / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for ch in chunks:
            fh.write(json.dumps(ch.model_dump(mode="json"), ensure_ascii=False) + "\n")
    (out_dir / "chunking_comparison.json").write_text(
        json.dumps(comparison.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest, chunks, comparison


def main() -> None:
    parser = argparse.ArgumentParser(description="HW2 Step 1 corpus ingestion & chunking CLI")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="Directory with raw documents")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory for artifacts")
    parser.add_argument("--max-tokens", type=int, default=360, help="Max cl100k_base tokens per chunk")
    parser.add_argument("--overlap-tokens", type=int, default=45, help="Sentence overlap budget in tokens")
    args = parser.parse_args()

    manifest, chunks, comparison = run_ingestion(
        raw_dir=args.raw_dir,
        out_dir=args.out_dir,
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    sa = comparison.structure_aware
    fs = comparison.fixed_size_baseline
    print(
        f"Ingested {manifest.unique_ingested_docs}/{manifest.total_raw_files} docs "
        f"(skipped {manifest.skipped_duplicates_count} exact duplicates) -> {len(chunks)} chunks."
    )
    print(
        f"Structure-aware: {sa.chunk_count} chunks, avg={sa.avg_tokens} tok, "
        f"broken_tables={sa.broken_table_count}, mid_sentence={sa.mid_sentence_split_rate:.1%}, "
        f"bleed={sa.cross_section_bleed_count}"
    )
    print(
        f"Fixed-size:      {fs.chunk_count} chunks, avg={fs.avg_tokens} tok, "
        f"broken_tables={fs.broken_table_count}, mid_sentence={fs.mid_sentence_split_rate:.1%}, "
        f"bleed={fs.cross_section_bleed_count}"
    )


if __name__ == "__main__":
    main()
