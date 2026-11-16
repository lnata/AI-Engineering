#!/usr/bin/env python3
"""Generate the 38-file multi-format HW2 raw corpus (PDF, DOCX, HTML, MD)."""

from __future__ import annotations

import html
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document as DocxDocument
import pymupdf

from scripts.corpus_data import ALL_CORPUS_SPECS, CorpusDocSpec, SectionSpec

RAW_DIR = ROOT / "data" / "hw2_corpus" / "raw"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _meta_line(spec: CorpusDocSpec) -> str:
    rep = spec.report_id or "PLATFORM-WIDE"
    status = "ACTIVE" if spec.is_latest else "DEPRECATED"
    return (
        f"Doc ID: {spec.doc_id} | Version: {spec.version} | Effective Date: {spec.date} "
        f"| Type: {spec.doc_type} | Report: {rep} | Status: {status}"
    )


def _draw_pdf_chrome(page: pymupdf.Page, banner: str, page_no: int, total_pages: int) -> None:
    page.insert_text((48, 30), banner, fontname="dv", fontfile=FONT_REG, fontsize=8.5, color=(0.35, 0.35, 0.35))
    footer = f"INTERNAL ANALYTICS KB — CONFIDENTIAL | Page {page_no} of {total_pages}"
    page.insert_text((48, 812), footer, fontname="dv", fontfile=FONT_REG, fontsize=8.5, color=(0.35, 0.35, 0.35))


def _fit_textbox(page: pymupdf.Page, rect: pymupdf.Rect, text: str, fname: str, ffile: str, size: float) -> None:
    cur = size
    while cur >= 5.5:
        rc = page.insert_textbox(rect, text, fontname=fname, fontfile=ffile, fontsize=cur)
        if rc >= 0:
            return
        cur -= 0.6
    raise RuntimeError(f"PDF textbox overflow even at min font size for: {text[:50]!r}")


def _draw_pdf_table(page: pymupdf.Page, y: float, sec: SectionSpec) -> float:
    rows = [sec.table_headers, *sec.table_rows]
    ncols = len(sec.table_headers)
    x0, total_w = 36.0, 523.0
    col_w = total_w / ncols
    for r_idx, row in enumerate(rows):
        row_h = 44.0
        for c_idx, cell in enumerate(row):
            rect = pymupdf.Rect(x0 + c_idx * col_w, y, x0 + (c_idx + 1) * col_w, y + row_h)
            fill = (0.92, 0.94, 0.98) if r_idx == 0 else None
            page.draw_rect(rect, color=(0.25, 0.25, 0.25), fill=fill, width=0.7)
            inner = pymupdf.Rect(rect.x0 + 3, rect.y0 + 3, rect.x1 - 3, rect.y1 - 2)
            fname, ffile = ("dvb", FONT_BOLD) if r_idx == 0 else ("dv", FONT_REG)
            _fit_textbox(page, inner, cell, fname, ffile, 7.6)
        y += row_h
    return y + 12.0


def render_pdf(spec: CorpusDocSpec, out_path: Path) -> None:
    doc = pymupdf.open()
    pad = 4.0 if spec.mirror_variant else 0.0
    page_groups = [spec.sections[:1], spec.sections[1:]]
    if not page_groups[1]:
        first = spec.sections[0]
        p1 = SectionSpec(heading=first.heading, paragraphs=first.paragraphs, bullets=first.bullets)
        p2 = SectionSpec(heading="2. Таблиця контрольних параметрів", table_headers=first.table_headers, table_rows=first.table_rows)
        page_groups = [[p1], [p2]]

    total_pages = len(page_groups)
    for idx, group in enumerate(page_groups, start=1):
        page = doc.new_page(width=595, height=842)
        _draw_pdf_chrome(page, spec.header_banner, idx, total_pages)
        y = 50.0 + pad
        if idx == 1:
            _fit_textbox(page, pymupdf.Rect(36, y, 559, y + 44), spec.title, "dvb", FONT_BOLD, 14.0)
            y += 40.0
            _fit_textbox(page, pymupdf.Rect(36, y, 559, y + 30), _meta_line(spec), "dv", FONT_REG, 8.5)
            y += 30.0
        for sec in group:
            _fit_textbox(page, pymupdf.Rect(36, y, 559, y + 30), sec.heading, "dvb", FONT_BOLD, 11.8)
            y += 26.0
            for para in sec.paragraphs:
                lines_est = max(2, len(para) // 68 + para.count("\n") + 2)
                h = lines_est * 14.5 + 10.0
                _fit_textbox(page, pymupdf.Rect(36, y, 559, y + h), para, "dv", FONT_REG, 9.6)
                y += h - 4.0
            for bullet in sec.bullets:
                h = max(2, len(bullet) // 66 + 2) * 14.0 + 8.0
                _fit_textbox(page, pymupdf.Rect(44, y, 559, y + h), f"• {bullet}", "dv", FONT_REG, 9.3)
                y += h - 4.0
            if sec.table_headers:
                y = _draw_pdf_table(page, y + 4.0, sec)
    doc.save(out_path)
    doc.close()


def render_docx(spec: CorpusDocSpec, out_path: Path) -> None:
    doc = DocxDocument()
    suffix = "\u00a0  " if spec.mirror_variant else ""
    doc.add_heading(spec.title + suffix, level=1)
    doc.add_paragraph(_meta_line(spec) + suffix)
    if spec.mirror_variant:
        doc.add_paragraph("")
    for sec in spec.sections:
        doc.add_heading(sec.heading + suffix, level=2)
        for para in sec.paragraphs:
            doc.add_paragraph(para + suffix)
        for bullet in sec.bullets:
            doc.add_paragraph(bullet + suffix, style="List Bullet")
        if sec.table_headers:
            tbl = doc.add_table(rows=1 + len(sec.table_rows), cols=len(sec.table_headers))
            for c_idx, h_text in enumerate(sec.table_headers):
                tbl.rows[0].cells[c_idx].text = h_text
            for r_idx, r_vals in enumerate(sec.table_rows, start=1):
                for c_idx, val in enumerate(r_vals):
                    tbl.rows[r_idx].cells[c_idx].text = val
    doc.save(out_path)


def render_html(spec: CorpusDocSpec, out_path: Path) -> None:
    parts = [
        "<!DOCTYPE html><html lang='uk'><head><meta charset='utf-8'>",
        f"<title>{html.escape(spec.title)}</title>",
        "<style>body{font-family:sans-serif} .cookie-banner{background:#eee}</style>",
        "<script>window.__PORTAL_TELEMETRY__={env:'internal',track:true};</script></head><body>",
        "<header class='portal-topbar'>INTERNAL ANALYTICS PORTAL | Navigation: Home / Runbooks / Lineage</header>",
        "<nav class='sidebar-nav'><ul><li>Dashboard Catalog</li><li>Airflow Status</li><li>Sign Out</li></ul></nav>",
        "<aside class='cookie-banner'>Internal SSO session active. Cookie policy accepted.</aside>",
        f"<main><article data-doc-id='{html.escape(spec.doc_id)}' data-version='{html.escape(spec.version)}'>",
        f"<h1>{html.escape(spec.title)}</h1>",
        f"<p class='doc-meta'>{html.escape(_meta_line(spec))}</p>",
    ]
    for sec in spec.sections:
        parts.append(f"<h2>{html.escape(sec.heading)}</h2>")
        for para in sec.paragraphs:
            parts.append(f"<p>{html.escape(para)}</p>")
        if sec.bullets:
            items = "".join(f"<li>{html.escape(b)}</li>" for b in sec.bullets)
            parts.append(f"<ul>{items}</ul>")
        if sec.table_headers:
            ths = "".join(f"<th>{html.escape(h)}</th>" for h in sec.table_headers)
            trs = [f"<tr>{ths}</tr>"]
            for row in sec.table_rows:
                tds = "".join(f"<td>{html.escape(c)}</td>" for c in row)
                trs.append(f"<tr>{tds}</tr>")
            parts.append(f"<table><thead>{trs[0]}</thead><tbody>{''.join(trs[1:])}</tbody></table>")
    parts.append("</article></main><footer class='portal-footer'>© 2025 Internal Analytics Platform KB — All rights reserved</footer></body></html>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


def render_md(spec: CorpusDocSpec, out_path: Path) -> None:
    lines = [f"# {spec.title}", "", _meta_line(spec), ""]
    for sec in spec.sections:
        lines.extend([f"## {sec.heading}", ""])
        for para in sec.paragraphs:
            lines.extend([para, ""])
        for bullet in sec.bullets:
            lines.append(f"- {bullet}")
        if sec.bullets:
            lines.append("")
        if sec.table_headers:
            lines.append("| " + " | ".join(spec.sections[0].table_headers if False else sec.table_headers) + " |")
            lines.append("| " + " | ".join("---" for _ in sec.table_headers) + " |")
            for row in sec.table_rows:
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
    encoding = "utf-8-sig" if spec.utf8_bom else "utf-8"
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding=encoding)


def build_corpus(out_dir: Path = RAW_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*"):
        if stale.is_file():
            stale.unlink()
    renderers = {"pdf": render_pdf, "docx": render_docx, "html": render_html, "md": render_md}
    written: list[Path] = []
    for spec in ALL_CORPUS_SPECS:
        dest = out_dir / spec.filename
        renderers[spec.fmt](spec, dest)
        written.append(dest)
    return written


if __name__ == "__main__":
    paths = build_corpus()
    print(f"Generated {len(paths)} raw corpus files in {RAW_DIR}")
