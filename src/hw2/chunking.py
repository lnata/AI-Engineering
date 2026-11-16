"""Structure-aware Markdown chunking vs fixed-size baseline with quality metrics."""

from __future__ import annotations

import math
import re

import tiktoken

from src.hw2.models import (
    ChunkingComparison,
    ChunkRecord,
    ChunkStrategyMetrics,
    ExtractedDocument,
    SampleChunkDefect,
)

ENCODING_NAME = "cl100k_base"
_ENC = tiktoken.get_encoding(ENCODING_NAME)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_SENTENCE_END_CHARS = (".", "!", "?", "|", ":", ")", '"', "'", "»")


def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _context_header(doc: ExtractedDocument, section: str) -> str:
    return f"[{doc.title} | v{doc.version} ({doc.date}) | {section}]"


def _parse_sections(cleaned_md: str) -> list[tuple[str, list[str]]]:
    """Split cleaned Markdown into (section_title, structural_blocks)."""
    current_sec = "Overview"
    raw_lines_by_sec: list[tuple[str, list[str]]] = []
    buf: list[str] = []

    for ln in cleaned_md.splitlines():
        if ln.startswith("# "):
            continue
        if ln.startswith("Doc ID:") and "| Version:" in ln:
            continue
        if ln.startswith("## ") or ln.startswith("### "):
            if any(x.strip() for x in buf):
                raw_lines_by_sec.append((current_sec, buf))
            current_sec = ln.lstrip("#").strip()
            buf = []
        else:
            buf.append(ln)
    if any(x.strip() for x in buf):
        raw_lines_by_sec.append((current_sec, buf))

    parsed: list[tuple[str, list[str]]] = []
    for sec_title, lines in raw_lines_by_sec:
        blocks: list[str] = []
        cur: list[str] = []
        in_table = False
        for ln in lines:
            stripped = ln.strip()
            is_tbl_line = stripped.startswith("|") and stripped.endswith("|")
            if not stripped:
                if cur:
                    blocks.append("\n".join(cur))
                    cur = []
                in_table = False
            elif is_tbl_line:
                if cur and not in_table:
                    blocks.append("\n".join(cur))
                    cur = []
                in_table = True
                cur.append(stripped)
            else:
                if in_table and cur:
                    blocks.append("\n".join(cur))
                    cur = []
                    in_table = False
                cur.append(stripped)
        if cur:
            blocks.append("\n".join(cur))
        if blocks:
            parsed.append((sec_title, blocks))
    return parsed


def _split_oversized_block(block: str, budget: int) -> list[str]:
    if count_tokens(block) <= budget:
        return [block]
    lines = block.splitlines()
    if len(lines) >= 3 and lines[0].startswith("|") and lines[1].startswith("| ---"):
        hdr = f"{lines[0]}\n{lines[1]}"
        out, cur_rows = [], [hdr]
        for row in lines[2:]:
            cand = "\n".join([*cur_rows, row])
            if len(cur_rows) > 1 and count_tokens(cand) > budget:
                out.append("\n".join(cur_rows))
                cur_rows = [hdr, row]
            else:
                cur_rows.append(row)
        if len(cur_rows) > 1:
            out.append("\n".join(cur_rows))
        return out

    sentences = _SENTENCE_SPLIT_RE.split(" ".join(lines))
    out, cur = [], []
    for sent in sentences:
        cand = " ".join([*cur, sent]).strip()
        if cur and count_tokens(cand) > budget:
            out.append(" ".join(cur))
            cur = [cur[-1], sent] if count_tokens(cur[-1]) <= 45 else [sent]
        else:
            cur.append(sent)
    if cur:
        out.append(" ".join(cur))
    return out


def _last_sentence_overlap(block: str, max_overlap_tokens: int) -> str:
    if block.startswith("|") or max_overlap_tokens <= 0:
        return ""
    sents = _SENTENCE_SPLIT_RE.split(block.strip())
    last = sents[-1].strip() if sents else ""
    return last if last and count_tokens(last) <= max_overlap_tokens else ""


def chunk_document_structure_aware(
    doc: ExtractedDocument,
    max_tokens: int = 360,
    overlap_tokens: int = 45,
) -> list[ChunkRecord]:
    """Heading/section-aware chunker preserving Markdown tables and sentence boundaries."""
    records: list[ChunkRecord] = []
    file_name = doc.source.rsplit("/", 1)[-1]
    idx = 0
    for sec_title, blocks in _parse_sections(doc.cleaned_markdown):
        hdr = _context_header(doc, sec_title)
        body_budget = max(120, max_tokens - count_tokens(hdr) - 4)
        expanded: list[str] = []
        for blk in blocks:
            expanded.extend(_split_oversized_block(blk, body_budget))

        cur_blocks: list[str] = []
        for blk in expanded:
            candidate = "\n\n".join([*cur_blocks, blk])
            if cur_blocks and count_tokens(candidate) > body_budget:
                full_txt = f"{hdr}\n\n" + "\n\n".join(cur_blocks)
                records.append(_make_record(doc, file_name, idx, sec_title, full_txt))
                idx += 1
                ov = _last_sentence_overlap(cur_blocks[-1], overlap_tokens)
                cur_blocks = [ov, blk] if ov and count_tokens(f"{ov}\n\n{blk}") <= body_budget else [blk]
            else:
                cur_blocks.append(blk)
        if cur_blocks:
            full_txt = f"{hdr}\n\n" + "\n\n".join(cur_blocks)
            records.append(_make_record(doc, file_name, idx, sec_title, full_txt))
            idx += 1
    return records


def chunk_document_fixed_size(
    doc: ExtractedDocument,
    chunk_tokens: int = 240,
    overlap_tokens: int = 40,
) -> list[ChunkRecord]:
    """Naive fixed-size sliding token window baseline."""
    tokens = _ENC.encode(doc.cleaned_markdown)
    step = max(1, chunk_tokens - overlap_tokens)
    file_name = doc.source.rsplit("/", 1)[-1]
    records: list[ChunkRecord] = []
    for idx, start in enumerate(range(0, len(tokens), step)):
        window = tokens[start : start + chunk_tokens]
        if not window:
            break
        txt = _ENC.decode(window, errors="replace").strip()
        records.append(_make_record(doc, file_name, idx, "fixed_window", txt))
        if start + chunk_tokens >= len(tokens):
            break
    return records


def _make_record(
    doc: ExtractedDocument, file_name: str, idx: int, section: str, text: str
) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=f"{file_name}#{idx:02d}",
        source=doc.source,
        title=doc.title,
        section=section,
        date=doc.date,
        version=doc.version,
        doc_hash=doc.doc_hash,
        doc_type=doc.doc_type,
        format=doc.format,
        report_id=doc.report_id,
        is_latest=doc.is_latest,
        token_count=count_tokens(text),
        text=text,
    )
