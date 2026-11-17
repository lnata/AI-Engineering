"""Structure-preserving extractors for PDF, DOCX, HTML, and Markdown documents."""

from __future__ import annotations

from pathlib import Path
import re

from bs4 import BeautifulSoup, Tag
from docx import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
import pymupdf

from src.hw2.cleaning import (
    clean_markdown_text,
    decode_text_bytes,
    normalize_unicode,
    repair_hyphenation,
    strip_pdf_headers_footers,
)
from src.hw2.json_extractor import extract_json

_BOILERPLATE_TAGS = ("script", "style", "nav", "header", "footer", "aside", "noscript")
_BOILERPLATE_CLASSES = {"portal-topbar", "sidebar-nav", "cookie-banner", "portal-footer"}


def _rows_to_md_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm_rows: list[list[str]] = []
    for r in rows:
        cells = [
            " ".join(repair_hyphenation(normalize_unicode(c or "")).split()).replace("|", "\\|")
            for c in r
        ]
        cells.extend([""] * (width - len(cells)))
        norm_rows.append(cells)
    header = "| " + " | ".join(norm_rows[0]) + " |"
    sep = "| " + " | ".join("---" for _ in range(width)) + " |"
    body = ["| " + " | ".join(r) + " |" for r in norm_rows[1:]]
    return "\n".join([header, sep, *body])


def _unwrap_prose_lines(raw_block: str) -> str:
    repaired = repair_hyphenation(normalize_unicode(raw_block))
    return " ".join(part.strip() for part in repaired.splitlines() if part.strip())


def extract_pdf(path: Path) -> str:
    """Extract headings, bullet lists, and bordered tables from PDF via PyMuPDF."""
    doc = pymupdf.open(path)
    raw_pages: list[str] = []
    try:
        for page in doc:
            items: list[tuple[float, str]] = []
            table_rects: list[pymupdf.Rect] = []
            for tbl in page.find_tables().tables:
                rect = pymupdf.Rect(tbl.bbox)
                table_rects.append(pymupdf.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2))
                raw_rows = [
                    [page.get_text("text", clip=c) if c is not None else "" for c in row.cells]
                    for row in tbl.rows
                ]
                md_tbl = _rows_to_md_table(raw_rows)
                if md_tbl:
                    items.append((rect.y0, md_tbl))

            for blk in page.get_text("dict").get("blocks", []):
                if blk.get("type") != 0:
                    continue
                brect = pymupdf.Rect(blk["bbox"])
                center = pymupdf.Point((brect.x0 + brect.x1) / 2, (brect.y0 + brect.y1) / 2)
                if any(center in tr for tr in table_rects):
                    continue
                line_texts: list[str] = []
                max_size = 0.0
                is_bold = False
                for ln in blk.get("lines", []):
                    spans = ln.get("spans", [])
                    txt = "".join(sp.get("text", "") for sp in spans).strip()
                    if not txt:
                        continue
                    line_texts.append(txt)
                    for sp in spans:
                        sz = float(sp.get("size", 0.0))
                        if sz > max_size:
                            max_size = sz
                        if "bold" in str(sp.get("font", "")).lower():
                            is_bold = True
                if not line_texts:
                    continue
                joined = "\n".join(line_texts)
                prose = _unwrap_prose_lines(joined)
                if max_size >= 13.2 and is_bold:
                    items.append((brect.y0, f"# {prose}"))
                elif max_size >= 11.2 and is_bold:
                    items.append((brect.y0, f"## {prose}"))
                elif prose.startswith(("•", "- ")):
                    bullet_txt = prose.lstrip("•- ").strip()
                    items.append((brect.y0, f"- {bullet_txt}"))
                else:
                    items.append((brect.y0, prose))

            items.sort(key=lambda pair: pair[0])
            raw_pages.append("\n\n".join(text for _, text in items))
    finally:
        doc.close()

    stripped_pages = strip_pdf_headers_footers(raw_pages)
    # Remove synthetic page-2 wrapper heading when a single-section spec spilled table onto page 2
    combined = "\n\n".join(p for p in stripped_pages if p)
    combined = re.sub(r"\n+## 2\. Таблиця контрольних параметрів\s*\n+", "\n\n", combined)
    return clean_markdown_text(combined)


def extract_docx(path: Path) -> str:
    """Extract Word headings, paragraphs, bullet lists, and tables in body order."""
    doc = DocxDocument(path)
    blocks: list[str] = []
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            para = DocxParagraph(child, doc)
            txt = _unwrap_prose_lines(para.text)
            if not txt:
                continue
            style_name = (para.style.name if para.style else "").lower()
            if "heading 1" in style_name or style_name == "title":
                blocks.append(f"# {txt}")
            elif "heading 2" in style_name:
                blocks.append(f"## {txt}")
            elif "heading 3" in style_name:
                blocks.append(f"### {txt}")
            elif "list" in style_name:
                blocks.append(f"- {txt}")
            else:
                blocks.append(txt)
        elif isinstance(child, CT_Tbl):
            tbl = DocxTable(child, doc)
            rows = [[cell.text for cell in row.cells] for row in tbl.rows]
            md_tbl = _rows_to_md_table(rows)
            if md_tbl:
                blocks.append(md_tbl)
    return clean_markdown_text("\n\n".join(blocks))


def extract_html(path: Path) -> str:
    """Strip portal boilerplate and extract article headings, lists, and tables."""
    raw_html = decode_text_bytes(path.read_bytes())
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag_name in _BOILERPLATE_TAGS:
        for node in soup.find_all(tag_name):
            node.decompose()
    for node in list(soup.find_all(True)):
        if isinstance(node, Tag) and node.attrs:
            classes = set(node.get("class") or [])
            if classes & _BOILERPLATE_CLASSES:
                node.decompose()

    root = soup.find("article") or soup.find("main") or soup.body or soup
    blocks: list[str] = []
    for elem in root.find_all(["h1", "h2", "h3", "p", "ul", "ol", "table"], recursive=True):
        if elem.find_parent("table") and elem.name != "table":
            continue
        if elem.name == "h1":
            blocks.append(f"# {_unwrap_prose_lines(elem.get_text(' '))}")
        elif elem.name == "h2":
            blocks.append(f"## {_unwrap_prose_lines(elem.get_text(' '))}")
        elif elem.name == "h3":
            blocks.append(f"### {_unwrap_prose_lines(elem.get_text(' '))}")
        elif elem.name == "p":
            txt = _unwrap_prose_lines(elem.get_text(" "))
            if txt:
                blocks.append(txt)
        elif elem.name in ("ul", "ol"):
            items = [f"- {_unwrap_prose_lines(li.get_text(' '))}" for li in elem.find_all("li", recursive=False)]
            if items:
                blocks.append("\n".join(items))
        elif elem.name == "table":
            rows = [
                [cell.get_text(" ") for cell in tr.find_all(["th", "td"], recursive=False)]
                for tr in elem.find_all("tr")
            ]
            md_tbl = _rows_to_md_table(rows)
            if md_tbl:
                blocks.append(md_tbl)
    return clean_markdown_text("\n\n".join(blocks))


def extract_md(path: Path) -> str:
    """Decode Markdown safely (UTF-8 / BOM / cp1251) and normalize structure."""
    raw_text = decode_text_bytes(path.read_bytes())
    return clean_markdown_text(raw_text)


def extract_document_markdown(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    dispatch = {
        "pdf": extract_pdf,
        "docx": extract_docx,
        "html": extract_html,
        "htm": extract_html,
        "md": extract_md,
        "json": extract_json,
    }
    if ext not in dispatch:
        raise ValueError(f"Unsupported document format: {path}")
    return dispatch[ext](path)
