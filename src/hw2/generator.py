"""Cloud + deterministic extractive RAG generators and 1-retry citation repair loop."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import ValidationError

from src.config import ROOT
from src.hw2.bm25_index import tokenize_bm25
from src.hw2.chunking import count_tokens
from src.hw2.llm_runtime import LLMDiskCache, call_with_llm_retry, resolve_gemini_model
from src.hw2.models import PackedContext, PackedSource, RAGAnswer, RAGClaim, RAGLLMResponse
from src.hw2.verifier import (
    ABSTAIN_MESSAGE_UK,
    CitationVerificationError,
    verify_and_resolve_rag_output,
)

_DOC_CODE_RE = re.compile(
    r"^(?:spec|pol|runbook|guide|playbook|adr|incident|lineage|glossary|faq|ref)\b",
    re.I,
)
_INJECTION_LINE_RE = re.compile(
    r"(?:ignore\s+(?:all\s+)?previous\s+instructions|system\s+override|disregard\s+rules"
    r"|ігноруй\s+попередні\s+інструкції|забудь\s+правила|виведи\s+системний\s+промпт)",
    re.IGNORECASE,
)
_LEGACY_QUERY_HINT_RE = re.compile(r"\b(?:v1\.0|legacy|застаріл\w*|архів\w*|історич\w*)\b", re.I)
_BOILERPLATE_QUERY_WORDS = frozenset(
    {
        "формулу",
        "формула",
        "формулі",
        "специфікації",
        "специфікація",
        "чинній",
        "чинна",
        "чинним",
        "актуальній",
        "діючим",
        "діючою",
        "стандарт",
        "стандартом",
        "регламент",
        "регламентом",
        "звіту",
        "звіті",
        "звіт",
        "правило",
        "правила",
        "закладена",
        "передбачена",
        "встановлено",
        "показує",
        "діє",
        "працює",
        "виконується",
        "означає",
    }
)


class RAGGeneratorProtocol(Protocol):
    provider_name: str
    model_name: str

    def generate(self, *, system_prompt: str, user_prompt: str) -> tuple[str, dict[str, int], float]: ...


class GeminiRAGGenerator:
    """Cloud RAG generator via Google GenAI SDK with 429/5xx backoff, model fallback & disk cache."""

    provider_name = "gemini"
    _FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash")

    def __init__(
        self,
        model_name: str | None = None,
        timeout_sec: float = 120.0,
        api_key: str | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        cache: LLMDiskCache | None = None,
    ):
        load_dotenv(ROOT / ".env")
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is missing in environment / .env")
        self.model_name = resolve_gemini_model(model_name, env_var="HW2_RAG_MODEL")
        self._sleep_fn = sleep_fn
        self._cache = cache if cache is not None else LLMDiskCache()
        self._client = genai.Client(
            api_key=key, http_options=types.HttpOptions(timeout=int(timeout_sec * 1000))
        )

    def _invoke_once(self, system_prompt: str, user_prompt: str) -> Any:
        candidates_to_try = [self.model_name, *[m for m in self._FALLBACK_MODELS if m != self.model_name]]
        for idx, m_name in enumerate(candidates_to_try):
            try:
                resp = self._client.models.generate_content(
                    model=m_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.0,
                        top_p=1.0,
                        max_output_tokens=1200,
                        response_mime_type="application/json",
                        response_json_schema=RAGLLMResponse.model_json_schema(),
                    ),
                )
                self.model_name = m_name
                return resp
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                if ("404" in msg or "not_found" in msg or "not found" in msg) and idx + 1 < len(candidates_to_try):
                    continue
                raise

    def generate(self, *, system_prompt: str, user_prompt: str) -> tuple[str, dict[str, int], float]:
        cached = self._cache.get("gemini_rag", self.model_name, system_prompt, user_prompt)
        if cached is not None:
            return str(cached["raw_text"]), dict(cached["usage"]), float(cached.get("latency_ms", 0.0))

        t0 = time.perf_counter()
        resp = call_with_llm_retry(
            lambda: self._invoke_once(system_prompt, user_prompt),
            max_attempts=6,
            sleep_fn=self._sleep_fn,
        )
        lat_ms = (time.perf_counter() - t0) * 1000.0
        cand = resp.candidates[0] if getattr(resp, "candidates", None) else None
        finish = str(getattr(cand, "finish_reason", "") or "").lower()
        if "max_tokens" in finish or finish.endswith("length"):
            raise CitationVerificationError("Model output truncated due to max_tokens (finish_reason=length).")
        meta = getattr(resp, "usage_metadata", None)
        usage = {
            "input_tokens": int(getattr(meta, "prompt_token_count", 0) or 0),
            "output_tokens": int(getattr(meta, "candidates_token_count", 0) or 0),
            "total_tokens": int(getattr(meta, "total_token_count", 0) or 0),
        }
        raw_text = resp.text or ""
        self._cache.put(
            "gemini_rag",
            self.model_name,
            system_prompt,
            user_prompt,
            {"raw_text": raw_text, "usage": usage, "latency_ms": lat_ms},
        )
        return raw_text, usage, lat_ms


class OpenAIRAGGenerator:
    """Cloud RAG generator for OpenAI and OpenRouter with 429/5xx backoff & disk cache."""

    def __init__(
        self,
        provider_name: str = "openai",
        model_name: str = "gpt-4o-mini",
        base_url: str | None = None,
        timeout_sec: float = 120.0,
        api_key: str | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        cache: LLMDiskCache | None = None,
    ):
        load_dotenv(ROOT / ".env")
        env_var = "OPENROUTER_API_KEY" if provider_name == "openrouter" else "OPENAI_API_KEY"
        key = api_key or os.getenv(env_var)
        if not key:
            raise RuntimeError(f"{env_var} is missing in environment / .env")
        self.provider_name = provider_name
        self.model_name = model_name
        self._sleep_fn = sleep_fn
        self._cache = cache if cache is not None else LLMDiskCache()
        url = base_url or ("https://openrouter.ai/api/v1" if provider_name == "openrouter" else None)
        self._client = OpenAI(api_key=key, base_url=url, timeout=timeout_sec)

    def generate(self, *, system_prompt: str, user_prompt: str) -> tuple[str, dict[str, int], float]:
        ns = f"{self.provider_name}_rag"
        cached = self._cache.get(ns, self.model_name, system_prompt, user_prompt)
        if cached is not None:
            return str(cached["raw_text"]), dict(cached["usage"]), float(cached.get("latency_ms", 0.0))

        schema_hint = (
            "\n\nReturn ONLY valid JSON with keys: "
            '{"abstained": bool, "abstain_reason": string|null, "answer": string, '
            '"claims": [{"statement": string, "source_ids": [string]}]}.'
        )
        t0 = time.perf_counter()
        comp = call_with_llm_retry(
            lambda: self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt + schema_hint},
                ],
                temperature=0.0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            ),
            max_attempts=6,
            sleep_fn=self._sleep_fn,
        )
        lat_ms = (time.perf_counter() - t0) * 1000.0
        choice = comp.choices[0]
        if choice.finish_reason == "length":
            raise CitationVerificationError("Model output truncated (finish_reason=length).")
        usage = {
            "input_tokens": int(getattr(comp.usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(getattr(comp.usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(comp.usage, "total_tokens", 0) or 0),
        }
        raw_text = choice.message.content or ""
        self._cache.put(
            ns, self.model_name, system_prompt, user_prompt, {"raw_text": raw_text, "usage": usage, "latency_ms": lat_ms}
        )
        return raw_text, usage, lat_ms


class ExtractiveRAGGenerator:
    """Deterministic grounded local generator ($0/1000) with Gate-2 topic & injection guards."""

    provider_name = "extractive"
    model_name = "deterministic-grounded-extractive-v1"

    def __init__(self, packed: PackedContext, question: str) -> None:
        self._packed = packed
        self._question = question

    def generate(self, *, system_prompt: str, user_prompt: str) -> tuple[str, dict[str, int], float]:
        t0 = time.perf_counter()
        payload = _build_extractive_response(self._packed, self._question)
        raw = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        in_tok = count_tokens(system_prompt) + count_tokens(user_prompt)
        out_tok = count_tokens(raw)
        usage = {"input_tokens": in_tok, "output_tokens": out_tok, "total_tokens": in_tok + out_tok}
        return raw, usage, (time.perf_counter() - t0) * 1000.0


def _build_extractive_response(packed: PackedContext, question: str) -> RAGLLMResponse:
    wants_legacy = bool(_LEGACY_QUERY_HINT_RE.search(question))
    candidate_sources: list[PackedSource] = [
        s for s in packed.included_sources if (wants_legacy or s.is_latest)
    ] or list(packed.included_sources)

    all_ctx_text = "\n".join(s.formatted_block for s in candidate_sources)
    ctx_tokens = set(tokenize_bm25(all_ctx_text))
    raw_q_words = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9_.-]+", question)
    specific_terms: set[str] = set()
    for w in raw_q_words:
        low = w.casefold().strip("._-")
        if len(low) < 4 or _DOC_CODE_RE.match(low) or low in _BOILERPLATE_QUERY_WORDS:
            continue
        for tok in tokenize_bm25(w):
            if len(tok) >= 4 and tok not in _BOILERPLATE_QUERY_WORDS:
                specific_terms.add(tok)

    # Gate 2 (In-Generator Grounding Gate): trap questions mentioning SPEC-FIN-030 + absent metric
    if specific_terms:
        matched_specific = specific_terms & ctx_tokens
        coverage = len(matched_specific) / len(specific_terms)
        if not matched_specific or (len(specific_terms) >= 3 and coverage < 0.34):
            return RAGLLMResponse(
                abstained=True,
                abstain_reason="missing_in_corpus",
                answer=ABSTAIN_MESSAGE_UK,
                claims=[],
            )

    q_toks = set(tokenize_bm25(question))
    scored_units: list[tuple[float, str, PackedSource]] = []
    for src in candidate_sources:
        body = src.formatted_block.split("\n", 1)[1] if "\n" in src.formatted_block else src.formatted_block
        for unit in _split_units(body):
            if _INJECTION_LINE_RE.search(unit):
                continue
            u_toks = set(tokenize_bm25(unit))
            overlap = len(q_toks & u_toks)
            if overlap == 0 and len(scored_units) > 0:
                continue
            bonus = 0.5 if "|" in unit else 0.0
            scored_units.append((overlap + bonus + max(0.0, (src.rerank_score or 0.0) * 0.08), unit, src))

    scored_units.sort(key=lambda x: -x[0])
    if not scored_units or scored_units[0][0] <= 0.15:
        return RAGLLMResponse(
            abstained=True, abstain_reason="missing_in_corpus", answer=ABSTAIN_MESSAGE_UK, claims=[]
        )

    top_score = scored_units[0][0]
    chosen = [scored_units[0]]
    first_is_ticket = "BUGS-" in chosen[0][2].source
    wants_cross = bool(re.search(r"\b(?:bugs-\d+|тікет\w*)\b", question, re.I)) and bool(
        re.search(r"\b(?:spec-|pol-|runbook-|deployment\.json|регламент\w*|специфікац\w*)\b", question, re.I)
    )
    if wants_cross:
        for cand in scored_units[1:]:
            cand_is_ticket = "BUGS-" in cand[2].source
            if cand_is_ticket != first_is_ticket and cand[0] >= 1.5:
                chosen.append(cand)
                break
    max_units = 3 if wants_cross else 2
    for cand in scored_units[1:]:
        if len(chosen) >= max_units:
            break
        if cand[0] >= max(2.0, top_score * 0.55) and all(cand[1] != c[1] for c in chosen):
            chosen.append(cand)

    claims: list[RAGClaim] = []
    answer_parts: list[str] = []
    for _, unit, src in chosen:
        clean_stmt = " ".join(unit.lstrip("-• ").split()).rstrip(".")
        short_doc = src.source.rsplit("/", 1)[-1]
        claims.append(RAGClaim(statement=clean_stmt, source_ids=[src.source_id]))
        answer_parts.append(f"{clean_stmt} [{src.source_id}] ({short_doc} — {src.section}).")

    return RAGLLMResponse(abstained=False, answer=" ".join(answer_parts), claims=claims)


def _split_units(body: str) -> list[str]:
    units: list[str] = []
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    idx = 0
    while idx < len(lines):
        s = lines[idx]
        if (
            idx + 1 < len(lines)
            and s.startswith("|")
            and re.match(r"^\|\s*---", lines[idx + 1])
        ):
            headers = [c.strip() for c in s.strip("|").split("|")]
            idx += 2
            while idx < len(lines) and lines[idx].startswith("|") and lines[idx].endswith("|"):
                cells = [c.strip() for c in lines[idx].strip("|").split("|")]
                pairs = [
                    f"{h}: {v}" if h else v
                    for h, v in zip(headers, cells)
                    if v
                ]
                if pairs:
                    row_unit = "; ".join(pairs)
                    if not row_unit.startswith("Ticket ID: BUGS-"):
                        units.append(row_unit)
                idx += 1
            continue
        if not re.match(r"^\|\s*---", s):
            units.extend(p.strip() for p in re.split(r"(?<=[.!?])\s+", s) if len(p.strip()) > 18)
        idx += 1
    return units
