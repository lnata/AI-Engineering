"""Text normalization, PDF header/footer removal, hyphenation repair, and PII masking."""

from __future__ import annotations

from collections import Counter
import hashlib
import re
import unicodedata

from charset_normalizer import from_bytes

_ZERO_WIDTH_RE = re.compile(r"[\ufeff\u200b\u200c\u200d\u00ad]")
_PAGE_NUMBER_RE = re.compile(
    r"^(?:page\s+\d+\s*(?:of|/)\s*\d+|сторінка\s+\d+\s*(?:з|із|/)\s*\d+)$",
    re.IGNORECASE,
)
_CHROME_BANNER_RE = re.compile(
    r"internal\s+analytics\s+(?:kb|portal)\b.*\b(?:page\s+\d+\s+of\s+\d+|confidential|archive\s+mirror|all\s+rights\s+reserved)?",
    re.IGNORECASE,
)
_HYPHEN_BREAK_RE = re.compile(
    r"([A-Za-zА-Яа-яІіЇїЄєҐґ0-9]+)-\n[ \t]*([A-Za-zА-Яа-яІіЇїЄєҐґ0-9]+)"
)
_KEEP_HYPHEN_PREFIXES = frozenset(
    {
        "non",
        "self",
        "cross",
        "soft",
        "hard",
        "multi",
        "post",
        "pre",
        "co",
        "ex",
        "sub",
        "anti",
        "end-to",
        "row",
        "visual",
        "real",
        "full",
        "part",
        "all",
        "low",
        "high",
    }
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[\s.-]?\(?\d{2,3}\)?[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}"
    r"|\+\d{1,2}[\s.-]\d{3}[\s.-]\d{3}[\s.-]\d{4}"
    r"|\(0\d{2}\)[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2})(?!\w)"
)


def decode_text_bytes(raw_bytes: bytes) -> str:
    """Decode bytes safely with BOM handling and Cyrillic-aware charset-normalizer fallback."""
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return raw_bytes.decode("utf-8-sig")
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        best = from_bytes(
            raw_bytes,
            cp_isolation=["utf_8", "cp1251", "koi8_u", "iso8859_5", "latin_1"],
        ).best()
        if best is not None:
            return str(best)
        return raw_bytes.decode("cp1251", errors="replace")


def normalize_unicode(text: str) -> str:
    """Apply Unicode NFKC normalization, unify line endings, and drop zero-width chars."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _ZERO_WIDTH_RE.sub("", cleaned)
    cleaned = unicodedata.normalize("NFKC", cleaned)
    return "\n".join(line.rstrip() for line in cleaned.split("\n"))


def _line_fingerprint(line: str) -> str:
    s = line.strip().casefold()
    return re.sub(r"\d+", "#", s)


def strip_pdf_headers_footers(pages: list[str]) -> list[str]:
    """Remove repeating PDF page headers/footers and standalone page X of Y markers."""
    edge_counts: Counter[str] = Counter()
    if len(pages) >= 2:
        for page_txt in pages:
            non_empty = [ln.strip() for ln in page_txt.splitlines() if ln.strip()]
            edges = set(_line_fingerprint(ln) for ln in (non_empty[:3] + non_empty[-3:]))
            for fp in edges:
                if fp and not fp.startswith(("#", "|", "- ")):
                    edge_counts[fp] += 1

    repeating = {fp for fp, cnt in edge_counts.items() if cnt >= 2}
    cleaned_pages: list[str] = []
    for page_txt in pages:
        kept: list[str] = []
        for ln in page_txt.splitlines():
            stripped = ln.strip()
            if not stripped:
                kept.append("")
                continue
            fp = _line_fingerprint(stripped)
            if (
                fp in repeating
                or _PAGE_NUMBER_RE.match(stripped)
                or _CHROME_BANNER_RE.fullmatch(stripped)
            ):
                continue
            kept.append(ln)
        cleaned_pages.append("\n".join(kept).strip())
    return cleaned_pages


def repair_hyphenation(text: str) -> str:
    """Repair line-end hyphenated word splits while preserving SPEC-FIN-030 and non-GAAP."""

    def _repl(match: re.Match[str]) -> str:
        left, right = match.group(1), match.group(2)
        has_digits = any(ch.isdigit() for ch in left) or any(ch.isdigit() for ch in right)
        is_acronym = len(left) >= 2 and left.isupper()
        right_capitalized = right[0].isupper()
        if (
            has_digits
            or is_acronym
            or right_capitalized
            or left.casefold() in _KEEP_HYPHEN_PREFIXES
        ):
            return f"{left}-{right}"
        return f"{left}{right}"

    return _HYPHEN_BREAK_RE.sub(_repl, text)


def scrub_pii(text: str) -> str:
    """Mask email addresses and phone numbers prior to indexing."""
    masked = _EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    return _PHONE_RE.sub("[PHONE_REDACTED]", masked)


def clean_markdown_text(text: str) -> str:
    """Full text normalization pipeline for extracted Markdown content."""
    step = normalize_unicode(text)
    step = repair_hyphenation(step)
    step = scrub_pii(step)
    step = re.sub(r"\n{3,}", "\n\n", step)
    return step.strip()


def compute_raw_hash(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def compute_doc_hash(cleaned_markdown: str) -> str:
    canonical = " ".join(cleaned_markdown.split()).casefold()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
