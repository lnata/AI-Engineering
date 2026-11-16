"""Data structures for synthetic Analytics Ticket Copilot domain corpus."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SectionSpec:
    """One structured section inside a corpus document."""

    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    table_headers: list[str] = field(default_factory=list)
    table_rows: list[list[str]] = field(default_factory=list)


@dataclass(frozen=True)
class CorpusDocSpec:
    """Complete declarative specification for one raw document."""

    filename: str
    fmt: str  # "pdf" | "docx" | "html" | "md"
    doc_id: str
    title: str
    version: str
    date: str  # YYYY-MM-DD
    doc_type: str
    report_id: str | None
    is_latest: bool
    sections: list[SectionSpec]
    header_banner: str = "INTERNAL ANALYTICS KB — SAP / DATABRICKS / POWER BI"
    mirror_variant: bool = False
    utf8_bom: bool = False
