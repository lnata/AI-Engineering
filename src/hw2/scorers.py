"""Three-layer RAG scoring suite: Deterministic, Calibrated Judge, and Claim Faithfulness."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Literal, Protocol

from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel, Field

from src.hw2.bm25_index import tokenize_bm25
from src.hw2.models import PackedContext, RAGAnswer
from src.hw2.verifier import ABSTAIN_MESSAGE_UK

ROOT = Path(__file__).resolve().parents[2]
_NUM_OR_CODE_RE = re.compile(
    r"\b(?:\d+(?:[.,]\d+)?%?|[A-Z]{2,}(?:-[A-Z0-9]+)+|[a-z]+_[a-z0-9_]+|(?:mart|wh|stg|ref)\.[a-z0-9_*]+)\b"
)
_NEGATION_RE = re.compile(
    r"\b(?:не|немає|ніколи|жодн\w*|заборон\w*|виключ\w*|скасован\w*|без|мимо|минуя|обхід"
    r"|неможлив\w*|not|never|without|forbid\w*|prohibit\w*|exclud\w*|false)\b",
    re.IGNORECASE,
)
_RU_TICKET_HINT_RE = re.compile(
    r"\b(?:отчёт\w*|спек[еуи]|надо|похоже|сразу|минуя|ждём|нужен|кто-то|показывает|движения|хотят)\b",
    re.IGNORECASE,
)


def _has_polarity_inversion(claim_stmt: str, cited_text: str) -> bool:
    """Detect negation/prohibition polarity inversions between a claim and its cited [Si] text."""
    claim_neg = bool(_NEGATION_RE.search(claim_stmt))
    any_ctx_neg = bool(_NEGATION_RE.search(cited_text))
    if claim_neg and not any_ctx_neg:
        return True

    c_toks = set(tokenize_bm25(claim_stmt))
    if not c_toks:
        return False

    best_overlap = 0.0
    best_line = ""
    clause_split_re = re.compile(
        r"[\n.!?;]+|,(?=\s*(?:а|але)\s+не\b)|\((?=\s*якщо\s+не\b)",
        re.IGNORECASE,
    )
    for line in clause_split_re.split(cited_text):
        ln = line.strip()
        if len(ln) < 12 or ln.startswith("[S"):
            continue
        l_toks = set(tokenize_bm25(ln))
        if not l_toks:
            continue
        if not claim_neg and re.match(r"^(?:(?:а|але|якщо)\s+не\b)", ln, re.IGNORECASE):
            if len(c_toks & l_toks) / len(l_toks) >= 0.75:
                return True
        ov = len(c_toks & l_toks) / len(c_toks)
        if ov > best_overlap:
            best_overlap = ov
            best_line = ln

    if best_line and best_overlap >= 0.65:
        line_neg = bool(_NEGATION_RE.search(best_line))
        if claim_neg != line_neg:
            return True
    return False


class RAGTestCase(BaseModel):
    """Single item in evals/hw2_rag_testset.json."""

    id: str
    category: str
    human_verified: bool = True
    curator_note: str = ""
    question: str
    expected_abstain: bool
    expected_sources: list[str] = Field(default_factory=list)
    required_source_groups: list[list[str]] = Field(default_factory=list)
    expected_sections: list[str] = Field(default_factory=list)
    required_facts: list[str] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    reference_answer: str


class DeterministicScores(BaseModel):
    """Layer A deterministic metrics for a single RAG answer."""

    abstention_accuracy: float
    citation_source_hit: float
    citation_section_hit: float
    fact_coverage: float
    no_forbidden_facts: float
    matched_facts: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    triggered_forbidden_facts: list[str] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    """Layer B structured verdict returned by LLM-as-a-Judge or calibrated rubric judge."""

    label: Literal["pass", "partial", "fail"]
    correctness: float
    completeness: float
    rationale: str


class FaithfulnessReport(BaseModel):
    """Layer C per-claim faithfulness check against cited [Si] context blocks."""

    faithfulness_score: float
    total_claims: int
    supported_claims: int
    unsupported_claims: list[str] = Field(default_factory=list)


def match_fact_pattern(text: str, pattern: str) -> bool:
    """Deterministic case-insensitive check supporting `alt1|alt2` surface variants."""
    norm_text = " ".join(text.casefold().split())
    for alt in pattern.split("|"):
        cand = " ".join(alt.strip().casefold().split())
        if cand and cand in norm_text:
            return True
    return False


def score_deterministic(case: RAGTestCase, answer: RAGAnswer | None) -> DeterministicScores:
    """Layer A: Compute exact abstention, citation source/section hits, and fact checks."""
    if answer is None:
        return DeterministicScores(
            abstention_accuracy=0.0,
            citation_source_hit=0.0,
            citation_section_hit=0.0,
            fact_coverage=0.0,
            no_forbidden_facts=0.0,
            missing_facts=list(case.required_facts),
        )

    if case.expected_abstain:
        clean_abstain = (
            answer.abstained
            and ABSTAIN_MESSAGE_UK.casefold() in answer.answer.casefold()
            and not answer.claims
            and not answer.citations
        )
        triggered = [f for f in case.forbidden_facts if match_fact_pattern(answer.answer, f)]
        return DeterministicScores(
            abstention_accuracy=1.0 if clean_abstain else 0.0,
            citation_source_hit=1.0 if not answer.citations else 0.0,
            citation_section_hit=1.0 if not answer.citations else 0.0,
            fact_coverage=1.0 if clean_abstain else 0.0,
            no_forbidden_facts=1.0 if not triggered else 0.0,
            triggered_forbidden_facts=triggered,
        )

    abstain_acc = 1.0 if not answer.abstained else 0.0
    exp_srcs = set(case.expected_sources)
    exp_secs = set(case.expected_sections)
    has_legacy_cite = any(not c.is_latest for c in answer.citations)
    forbid_legacy = case.category == "trap_legacy_version" or "v1.0" not in case.question.casefold()

    cited_set = {c.source for c in answer.citations}
    groups_ok = all(bool(cited_set & set(grp)) for grp in case.required_source_groups)
    src_ok = (
        any(c.source in exp_srcs for c in answer.citations)
        and groups_ok
        and not (forbid_legacy and has_legacy_cite)
    )
    sec_ok = any(
        c.source in exp_srcs and (not exp_secs or c.section in exp_secs)
        for c in answer.citations
    ) and not (forbid_legacy and has_legacy_cite)

    matched = [f for f in case.required_facts if match_fact_pattern(answer.answer, f)]
    missing = [f for f in case.required_facts if f not in matched]
    cov = round(len(matched) / len(case.required_facts), 4) if case.required_facts else (1.0 if not answer.abstained else 0.0)
    triggered = [f for f in case.forbidden_facts if match_fact_pattern(answer.answer, f)]

    return DeterministicScores(
        abstention_accuracy=abstain_acc,
        citation_source_hit=1.0 if (not answer.abstained and src_ok) else 0.0,
        citation_section_hit=1.0 if (not answer.abstained and sec_ok) else 0.0,
        fact_coverage=0.0 if answer.abstained else cov,
        no_forbidden_facts=1.0 if not triggered else 0.0,
        matched_facts=matched,
        missing_facts=missing,
        triggered_forbidden_facts=triggered,
    )


def score_faithfulness(answer: RAGAnswer | None, packed: PackedContext) -> FaithfulnessReport:
    """Layer C: Verify that 100% of claims and their numbers/codes are grounded in cited [Si] blocks."""
    if answer is None:
        return FaithfulnessReport(faithfulness_score=0.0, total_claims=0, supported_claims=0)
    if answer.abstained:
        ok = not answer.claims and not answer.citations
        return FaithfulnessReport(
            faithfulness_score=1.0 if ok else 0.0,
            total_claims=len(answer.claims),
            supported_claims=0,
            unsupported_claims=[c.statement for c in answer.claims],
        )
    if not answer.claims:
        return FaithfulnessReport(faithfulness_score=0.0, total_claims=0, supported_claims=0)

    src_blocks = {s.source_id: s.formatted_block for s in packed.included_sources}
    supported = 0
    unsupported: list[str] = []

    for claim in answer.claims:
        cited_text = "\n".join(src_blocks.get(sid, "") for sid in claim.source_ids)
        if not cited_text.strip():
            unsupported.append(claim.statement)
            continue
        cited_low = cited_text.casefold()
        # Every number, percentage, table name, or code in the claim must appear in cited context
        anchors = [
            a for a in _NUM_OR_CODE_RE.findall(claim.statement)
            if not re.fullmatch(r"S\d+", a)
        ]
        anchors_ok = all(a.casefold() in cited_low for a in anchors)
        polarity_ok = not _has_polarity_inversion(claim.statement, cited_text)
        c_toks = set(tokenize_bm25(claim.statement))
        ctx_toks = set(tokenize_bm25(cited_text))
        overlap = (len(c_toks & ctx_toks) / len(c_toks)) if c_toks else 0.0
        min_overlap = 0.35 if _RU_TICKET_HINT_RE.search(cited_text) else 0.55
        if anchors_ok and polarity_ok and overlap >= min_overlap:
            supported += 1
        else:
            unsupported.append(claim.statement)

    total = len(answer.claims)
    return FaithfulnessReport(
        faithfulness_score=round(supported / total, 4),
        total_claims=total,
        supported_claims=supported,
        unsupported_claims=unsupported,
    )
