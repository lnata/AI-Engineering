"""RAG prompt loader, deterministic citation & grounding verifier, and cost estimator."""

from __future__ import annotations

from pathlib import Path
import re

from src.hw2.models import (
    PackedContext,
    PackedSource,
    RAGAnswer,
    RAGCitation,
    RAGClaim,
    RAGLLMResponse,
)

ROOT = Path(__file__).resolve().parents[2]
ABSTAIN_MESSAGE_UK = "У наданих документах цієї інформації немає."

_INLINE_SID_RE = re.compile(r"\[(S\d+)\]")
_RAW_SID_CLEAN_RE = re.compile(r"^\[?(S\d+)\]?$", re.IGNORECASE)

# USD per 1M tokens (input, output) for paid cloud providers; local/extractive = $0.00
MODEL_PRICING_PER_1M_USD: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "openai/gpt-4o-mini": (0.15, 0.60),
}


class CitationVerificationError(ValueError):
    """Raised when LLM output violates citation, grounding, or abstention invariants."""


def load_rag_prompt(version: str = "v2", prompts_root: Path | None = None) -> tuple[str, str]:
    """Load versioned RAG (system.txt, user_template.txt) from prompts/rag/<version>/."""
    base = (prompts_root or (ROOT / "prompts" / "rag")) / version
    sys_path = base / "system.txt"
    usr_path = base / "user_template.txt"
    if not sys_path.is_file() or not usr_path.is_file():
        raise FileNotFoundError(f"RAG prompt version '{version}' not found under {base}")
    return sys_path.read_text(encoding="utf-8").strip(), usr_path.read_text(encoding="utf-8").strip()


def render_rag_user_prompt(template: str, *, packed: PackedContext, question: str) -> str:
    """Render user prompt with packed [S1]..[Sk] blocks, allowed IDs, and user question."""
    allowed_ids = ", ".join(s.source_id for s in packed.included_sources) or "NONE"
    return (
        template.replace("{{context_blocks}}", packed.context_text)
        .replace("{{allowed_source_ids}}", allowed_ids)
        .replace("{{question}}", question.strip())
    )


def _normalize_sid(raw_sid: str) -> str:
    m = _RAW_SID_CLEAN_RE.match(raw_sid.strip())
    if not m:
        raise CitationVerificationError(
            f"Invalid source_id format '{raw_sid}'. Expected 'S1', 'S2', etc."
        )
    return m.group(1).upper()


def _short_doc_name(source_path: str) -> str:
    return source_path.rsplit("/", 1)[-1]


def _ensure_doc_section_labels(answer_text: str, source_map: dict[str, PackedSource]) -> str:
    """Ensure every inline [Si] citation explicitly displays `(document — section)`."""

    def _enrich(match: re.Match[str]) -> str:
        sid = match.group(1)
        src = source_map[sid]
        short_doc = _short_doc_name(src.source)
        tail = answer_text[match.end() : match.end() + 140]
        if short_doc in tail or src.section in tail:
            return match.group(0)
        return f"[{sid}] ({short_doc} — {src.section})"

    return _INLINE_SID_RE.sub(_enrich, answer_text)


def verify_and_resolve_rag_output(
    raw_resp: RAGLLMResponse,
    packed: PackedContext,
    prompt_version: str,
) -> RAGAnswer:
    """Validate claims, source_ids, inline citations, and abstention consistency."""
    source_map: dict[str, PackedSource] = {s.source_id: s for s in packed.included_sources}
    inline_sids = _INLINE_SID_RE.findall(raw_resp.answer or "")

    if raw_resp.abstained:
        if raw_resp.claims:
            raise CitationVerificationError(
                "Abstained response must have an empty `claims` list ([]), got non-empty claims."
            )
        if inline_sids:
            raise CitationVerificationError(
                f"Abstained response must not contain inline citations, found {inline_sids}."
            )
        return RAGAnswer(
            abstained=True,
            abstain_reason=raw_resp.abstain_reason or "missing_in_corpus",
            answer=ABSTAIN_MESSAGE_UK,
            claims=[],
            citations=[],
            prompt_version=prompt_version,
        )

    if not source_map:
        raise CitationVerificationError("Cannot produce a non-abstained answer with empty context.")

    if not raw_resp.claims:
        raise CitationVerificationError(
            "Non-abstained answer must contain at least one grounded claim in `claims`."
        )

    verified_claims: list[RAGClaim] = []
    used_sids_in_order: list[str] = []

    for idx, claim in enumerate(raw_resp.claims, start=1):
        stmt = claim.statement.strip()
        if not stmt:
            raise CitationVerificationError(f"Claim #{idx} has an empty statement.")
        if not claim.source_ids:
            raise CitationVerificationError(
                f"Claim #{idx} ('{stmt[:50]}...') has empty `source_ids`; every claim must cite [Si]."
            )
        norm_sids: list[str] = []
        for raw_sid in claim.source_ids:
            sid = _normalize_sid(raw_sid)
            if sid not in source_map:
                raise CitationVerificationError(
                    f"Claim #{idx} cites nonexistent source '{sid}'. Allowed: {sorted(source_map)}."
                )
            if sid not in norm_sids:
                norm_sids.append(sid)
            if sid not in used_sids_in_order:
                used_sids_in_order.append(sid)
        verified_claims.append(RAGClaim(statement=stmt, source_ids=norm_sids))

    for sid in inline_sids:
        if sid not in source_map:
            raise CitationVerificationError(
                f"Answer text cites nonexistent inline [{sid}]. Allowed: {sorted(source_map)}."
            )
        if sid not in used_sids_in_order:
            used_sids_in_order.append(sid)

    ans = (raw_resp.answer or "").strip()
    if not ans:
        raise CitationVerificationError("Non-abstained `answer` cannot be empty.")
    if not inline_sids:
        raise CitationVerificationError(
            "Non-abstained `answer` must include inline `[Si]` citations referencing packed sources."
        )

    enriched_answer = _ensure_doc_section_labels(ans, source_map)
    citations = [
        RAGCitation(
            source_id=sid,
            chunk_id=source_map[sid].chunk_id,
            source=source_map[sid].source,
            title=source_map[sid].title,
            section=source_map[sid].section,
            version=source_map[sid].version,
            date=source_map[sid].date,
            is_latest=source_map[sid].is_latest,
        )
        for sid in used_sids_in_order
    ]

    return RAGAnswer(
        abstained=False,
        abstain_reason=None,
        answer=enriched_answer,
        claims=verified_claims,
        citations=citations,
        prompt_version=prompt_version,
    )


def estimate_cost_per_1k_usd(model_name: str, usage: dict[str, int]) -> float:
    """Compute estimated USD cost per 1,000 queries from token usage ($0.00 for local)."""
    key = (model_name or "").strip().lower()
    rates = MODEL_PRICING_PER_1M_USD.get(key)
    if rates is None:
        for known_prefix, pair in MODEL_PRICING_PER_1M_USD.items():
            if known_prefix in key:
                rates = pair
                break
    if rates is None:
        return 0.0
    in_rate, out_rate = rates
    in_toks = float(usage.get("input_tokens") or 0)
    out_toks = float(usage.get("output_tokens") or 0)
    single_usd = (in_toks / 1_000_000.0) * in_rate + (out_toks / 1_000_000.0) * out_rate
    return round(single_usd * 1000.0, 4)
