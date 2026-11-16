"""Registry of all 38 raw corpus documents for HW2 Step 1."""

from __future__ import annotations

from scripts.corpus_data.docx_bi_guides import DOCX_BI_GUIDES
from scripts.corpus_data.docx_policies_playbooks import DOCX_POLICIES_PLAYBOOKS
from scripts.corpus_data.fin_specs_a import FIN_SPECS_A
from scripts.corpus_data.fin_specs_b import FIN_SPECS_B
from scripts.corpus_data.markdown_docs import MARKDOWN_DOCS
from scripts.corpus_data.runbooks_html_a import RUNBOOKS_HTML_A
from scripts.corpus_data.runbooks_html_b import RUNBOOKS_HTML_B
from scripts.corpus_data.schema import CorpusDocSpec, SectionSpec

ALL_CORPUS_SPECS: list[CorpusDocSpec] = [
    *FIN_SPECS_A,
    *FIN_SPECS_B,
    *DOCX_POLICIES_PLAYBOOKS,
    *DOCX_BI_GUIDES,
    *RUNBOOKS_HTML_A,
    *RUNBOOKS_HTML_B,
    *MARKDOWN_DOCS,
]

__all__ = ["ALL_CORPUS_SPECS", "CorpusDocSpec", "SectionSpec"]
