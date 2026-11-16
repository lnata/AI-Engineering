"""Unit and integration tests for HW2 Step 1 corpus, ingestion, cleaning, and chunking."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import shutil

from src.hw2.chunking import count_tokens
from src.hw2.cleaning import (
    decode_text_bytes,
    normalize_unicode,
    repair_hyphenation,
    scrub_pii,
    strip_pdf_headers_footers,
)
from src.hw2.extractors import extract_document_markdown
from src.hw2.ingest import ROOT, run_ingestion

CORPUS_DIR = ROOT / "data" / "hw2_corpus"
RAW_DIR = CORPUS_DIR / "raw"


def test_generated_corpus_inventory_and_versioned_pairs():
    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert 36 <= manifest["total_raw_files"] <= 38
    assert manifest["unique_ingested_docs"] >= 30
    assert manifest["skipped_duplicates_count"] >= 2

    fmts = manifest["format_counts_unique"]
    for required_fmt in ("pdf", "docx", "html", "md"):
        assert fmts.get(required_fmt, 0) >= 5

    # Verify >= 3 versioned pairs (legacy v1.0 is_latest=False vs current is_latest=True)
    by_doc_id: dict[str, list[dict]] = defaultdict(list)
    for doc in manifest["documents"]:
        by_doc_id[doc["doc_id"]].append(doc)
    versioned_pairs = [
        doc_id
        for doc_id, entries in by_doc_id.items()
        if len(entries) >= 2 and {e["is_latest"] for e in entries} == {True, False}
    ]
    assert len(versioned_pairs) >= 3, f"Expected >=3 versioned pairs, got {versioned_pairs}"


def test_pdf_docx_html_extraction_cleans_boilerplate_and_keeps_tables():
    pdf_md = extract_document_markdown(RAW_DIR / "SPEC-FIN-030_v1.3_gross_margin_rules.pdf")
    assert "INTERNAL ANALYTICS KB" not in pdf_md
    assert "Page 1 of" not in pdf_md and "Page 2 of" not in pdf_md
    assert "регламент" in pdf_md and "регла-\nмент" not in pdf_md
    assert "intercompany" in pdf_md and "inter-\ncompany" not in pdf_md
    assert "SPEC-FIN-030" in pdf_md and "non-GAAP" in pdf_md
    assert "| Компонент |" in pdf_md and "mart.fact_revenue" in pdf_md

    docx_md = extract_document_markdown(
        RAW_DIR / "POL-DEP-001_v1.3_deployment_and_reconciliation_policy.docx"
    )
    assert "## 1. Обов'язковий маршрут релізу змін" in docx_md
    assert "- Крок 1 (in_development)" in docx_md
    assert "| Етап | Середовище |" in docx_md

    html_md = extract_document_markdown(RAW_DIR / "RUNBOOK-DBX-001_sap_sales_orders_ingest.html")
    assert "Cookie policy" not in html_md
    assert "Sign Out" not in html_md
    assert "__PORTAL_TELEMETRY__" not in html_md
    assert "All rights reserved" not in html_md
    assert "## 1. Конфігурація пайплайну dag_sap_sales_orders_cdpos" in html_md
    assert "| Симптом інциденту |" in html_md


def test_hyphenation_unicode_encoding_and_pii_scrubbing():
    sample = (
        "Перевірка регла-\nменту та inter-\ncompany операцій у SPEC-\nFIN-030, "
        "non-\nGAAP метрик і soft-\ndeleted записів."
    )
    repaired = repair_hyphenation(sample)
    assert "регламенту" in repaired
    assert "intercompany" in repaired
    assert "SPEC-FIN-030" in repaired
    assert "non-GAAP" in repaired
    assert "soft-deleted" in repaired

    pages = [
        "INTERNAL ANALYTICS KB\n# Doc\nBody p1\nPage 1 of 2",
        "INTERNAL ANALYTICS KB\n## Sec 2\nBody p2\nPage 2 of 2",
    ]
    cleaned_pages = strip_pdf_headers_footers(pages)
    assert all("INTERNAL ANALYTICS KB" not in p and "Page " not in p for p in cleaned_pages)

    cp1251_bytes = "Перевірка кирилиці у вітрині mart.fact_orders".encode("cp1251")
    assert "вітрині mart.fact_orders" in decode_text_bytes(cp1251_bytes)
    assert normalize_unicode("A\u00a0B\ufeffﬁ") == "A Bfi"

    pii_text = (
        "Contact maria.bondar@corp-example.ua or +380 (67) 123-45-67 / (044) 234-56-78 "
        "regarding SPEC-FIN-030 on 2025-03-15."
    )
    scrubbed = scrub_pii(pii_text)
    assert "[EMAIL_REDACTED]" in scrubbed
    assert scrubbed.count("[PHONE_REDACTED]") == 2
    assert "maria.bondar@corp-example.ua" not in scrubbed
    assert "SPEC-FIN-030" in scrubbed and "2025-03-15" in scrubbed


def test_chunks_metadata_contract_zero_pii_and_table_integrity():
    lines = (CORPUS_DIR / "chunks.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 60
    required_fields = {
        "chunk_id",
        "source",
        "title",
        "section",
        "date",
        "version",
        "doc_hash",
        "doc_type",
        "format",
        "report_id",
        "is_latest",
        "token_count",
        "text",
    }
    for raw_line in lines:
        rec = json.loads(raw_line)
        assert required_fields.issubset(rec.keys())
        for mandatory in ("source", "title", "section", "date", "version", "doc_hash"):
            assert isinstance(rec[mandatory], str) and rec[mandatory].strip()
        assert len(rec["doc_hash"]) == 64
        assert rec["token_count"] == count_tokens(rec["text"])
        assert 50 <= rec["token_count"] <= 380
        assert "[EMAIL_REDACTED]" not in rec["text"] and "@" not in rec["text"]


def test_structure_aware_outperforms_fixed_size_and_deduplicates_tmp_run(tmp_path: Path):
    comp = json.loads((CORPUS_DIR / "chunking_comparison.json").read_text(encoding="utf-8"))
    sa = comp["structure_aware"]
    fs = comp["fixed_size_baseline"]

    assert sa["broken_table_count"] == 0
    assert sa["cross_section_bleed_count"] == 0
    assert sa["mid_sentence_split_rate"] == 0.0
    assert fs["broken_table_count"] > 0
    assert fs["cross_section_bleed_count"] > 0
    assert fs["mid_sentence_split_rate"] > sa["mid_sentence_split_rate"]

    # End-to-end mini-pipeline test on isolated directory with an exact duplicate
    mini_raw = tmp_path / "raw"
    mini_out = tmp_path / "out"
    mini_raw.mkdir()
    for fname in (
        "SPEC-FIN-030_v1.3_gross_margin_rules.pdf",
        "SPEC-FIN-030_v1.3_gross_margin_rules_mirror.pdf",
        "RUNBOOK-DBX-001_sap_sales_orders_ingest.html",
        "POL-DEP-001_v1.3_deployment_and_reconciliation_policy.docx",
    ):
        shutil.copy2(RAW_DIR / fname, mini_raw / fname)

    manifest, chunks, _ = run_ingestion(raw_dir=mini_raw, out_dir=mini_out)
    assert manifest.total_raw_files == 4
    assert manifest.unique_ingested_docs == 3
    assert manifest.skipped_duplicates_count == 1
    assert len(chunks) >= 5
    assert (mini_out / "manifest.json").is_file()
    assert (mini_out / "chunks.jsonl").is_file()
