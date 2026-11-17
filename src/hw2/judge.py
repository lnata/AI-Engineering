"""LLM-as-a-Judge + calibrated rubric judge and 14-case human agreement calibration."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Callable, Literal, Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel

from src.hw2.bm25_index import tokenize_bm25
from src.hw2.llm_runtime import (
    LLMDiskCache,
    call_with_llm_retry,
    resolve_cloud_provider,
    resolve_gemini_model,
)
from src.hw2.scorers import JudgeVerdict, match_fact_pattern

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALIB_PATH = ROOT / "evals" / "hw2_judge_calibration.json"
DEFAULT_CALIB_OUT = ROOT / "evals" / "hw2_judge_calibration_results.json"
JudgeProviderChoice = Literal["auto", "cloud", "rubric", "gemini", "openai", "openrouter"]

_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
_LEGACY_CITATION_RE = re.compile(r"_v1\.0_|legacy", re.IGNORECASE)


class CalibrationCase(BaseModel):
    id: str
    scenario: str
    question: str
    expected_abstain: bool
    required_facts: list[str]
    forbidden_facts: list[str]
    reference_answer: str
    packed_context: str
    candidate_abstained: bool
    candidate_citations: list[str]
    candidate_answer: str
    human_label: Literal["pass", "partial", "fail"]
    human_score: float
    human_rationale: str


class JudgeProtocol(Protocol):
    name: str

    def evaluate(
        self,
        *,
        question: str,
        expected_abstain: bool,
        required_facts: list[str],
        forbidden_facts: list[str],
        reference_answer: str,
        packed_context: str,
        candidate_abstained: bool,
        candidate_citations: list[str],
        candidate_answer: str,
    ) -> JudgeVerdict: ...


def load_judge_prompt(version: str = "v1") -> tuple[str, str]:
    base = ROOT / "prompts" / "judge" / version
    return (
        (base / "system.txt").read_text(encoding="utf-8").strip(),
        (base / "user_template.txt").read_text(encoding="utf-8").strip(),
    )


def render_judge_user_prompt(tmpl: str, **kwargs: object) -> str:
    rendered = tmpl
    for k, v in kwargs.items():
        val = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, bool)) else str(v)
        rendered = rendered.replace(f"{{{{{k}}}}}", val)
    return rendered


class CloudLLMJudge:
    """Cloud LLM-as-a-Judge supporting Gemini/OpenAI/OpenRouter with 429 backoff & disk cache."""

    _FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash")

    def __init__(
        self,
        provider: str = "gemini",
        model: str | None = None,
        prompt_version: str = "v1",
        sleep_fn: Callable[[float], None] = time.sleep,
        cache: LLMDiskCache | None = None,
    ):
        load_dotenv(ROOT / ".env")
        self.provider = provider
        self.prompt_version = prompt_version
        self._sleep_fn = sleep_fn
        self._cache = cache if cache is not None else LLMDiskCache()
        self.sys_prompt, self.usr_tmpl = load_judge_prompt(prompt_version)
        if provider == "gemini":
            key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not key:
                raise RuntimeError("GEMINI_API_KEY missing for CloudLLMJudge")
            self.model = resolve_gemini_model(model, env_var="HW2_JUDGE_MODEL")
            self._gemini = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=120_000))
            self._openai = None
        else:
            env_var = "OPENROUTER_API_KEY" if provider == "openrouter" else "OPENAI_API_KEY"
            key = os.getenv(env_var)
            if not key:
                raise RuntimeError(f"{env_var} missing for CloudLLMJudge")
            default_m = "openai/gpt-4o-mini" if provider == "openrouter" else "gpt-4o-mini"
            self.model = model or os.getenv("HW2_JUDGE_MODEL") or default_m
            url = "https://openrouter.ai/api/v1" if provider == "openrouter" else None
            self._openai = OpenAI(api_key=key, base_url=url, timeout=120.0)
            self._gemini = None
        self.name = f"{provider}:{self.model}"

    def _invoke_gemini(self, usr: str) -> str:
        assert self._gemini is not None
        candidates = [self.model, *[m for m in self._FALLBACK_MODELS if m != self.model]]
        for idx, m_name in enumerate(candidates):
            try:
                resp = self._gemini.models.generate_content(
                    model=m_name,
                    contents=usr,
                    config=types.GenerateContentConfig(
                        system_instruction=self.sys_prompt,
                        temperature=0.0,
                        response_mime_type="application/json",
                        response_json_schema=JudgeVerdict.model_json_schema(),
                    ),
                )
                self.model = m_name
                self.name = f"{self.provider}:{self.model}"
                return resp.text or "{}"
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                if ("404" in msg or "not_found" in msg or "not found" in msg) and idx + 1 < len(candidates):
                    continue
                raise
        return "{}"

    def evaluate(self, **kwargs: object) -> JudgeVerdict:
        usr = render_judge_user_prompt(self.usr_tmpl, **kwargs)
        ns = f"{self.provider}_judge"
        cached = self._cache.get(ns, self.model, self.sys_prompt, usr)
        if cached is not None:
            return JudgeVerdict.model_validate_json(str(cached["raw_text"]))

        if self._gemini is not None:
            raw_text = call_with_llm_retry(
                lambda: self._invoke_gemini(usr), max_attempts=6, sleep_fn=self._sleep_fn
            )
            verdict = JudgeVerdict.model_validate_json(raw_text)
            self._cache.put(ns, self.model, self.sys_prompt, usr, {"raw_text": raw_text})
            return verdict

        assert self._openai is not None
        hint = '\nReturn ONLY JSON: {"label": "pass"|"partial"|"fail", "correctness": float, "completeness": float, "rationale": string}.'
        comp = call_with_llm_retry(
            lambda: self._openai.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.sys_prompt},
                    {"role": "user", "content": usr + hint},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            ),
            max_attempts=6,
            sleep_fn=self._sleep_fn,
        )
        raw_text = comp.choices[0].message.content or "{}"
        verdict = JudgeVerdict.model_validate_json(raw_text)
        self._cache.put(ns, self.model, self.sys_prompt, usr, {"raw_text": raw_text})
        return verdict


class CalibratedRubricJudge:
    """Deterministic rubric judge aligned with prompts/judge/v1 ($0 CI & offline execution)."""

    name = "rubric:calibrated-v1"

    def evaluate(
        self,
        *,
        question: str,
        expected_abstain: bool,
        required_facts: list[str],
        forbidden_facts: list[str],
        reference_answer: str,
        packed_context: str,
        candidate_abstained: bool,
        candidate_citations: list[str],
        candidate_answer: str,
    ) -> JudgeVerdict:
        if expected_abstain:
            if candidate_abstained and not candidate_citations:
                return JudgeVerdict(label="pass", correctness=1.0, completeness=1.0, rationale="Коректна відмова на запитанні без відповіді в корпусі.")
            return JudgeVerdict(label="fail", correctness=0.0, completeness=0.0, rationale="Модель не відмовилася на питанні без даних у корпусі.")

        if candidate_abstained:
            return JudgeVerdict(label="fail", correctness=0.0, completeness=0.0, rationale="Хибна відмова за наявності релевантних даних.")
        if not candidate_citations:
            return JudgeVerdict(label="fail", correctness=0.0, completeness=0.0, rationale="Відсутні обов'язкові посилання на джерела.")
        if any(match_fact_pattern(candidate_answer, f) for f in forbidden_facts):
            return JudgeVerdict(label="fail", correctness=0.0, completeness=0.0, rationale="Виявлено заборонені або застарілі (v1.0) твердження.")
        if "v1.0" not in question.casefold() and any(_LEGACY_CITATION_RE.search(c) for c in candidate_citations):
            return JudgeVerdict(label="fail", correctness=0.0, completeness=0.0, rationale="Процитовано скасовану архівну версію v1.0 замість чинної.")

        # Check context grounding of numbers in candidate_answer (ignoring [Si] markers)
        ctx_low = packed_context.casefold()
        cleaned_ans = re.sub(r"\[S\d+\]", "", candidate_answer, flags=re.IGNORECASE)
        ans_nums = _NUMBER_RE.findall(cleaned_ans)
        if ctx_low and any(num.casefold() not in ctx_low for num in ans_nums):
            return JudgeVerdict(label="fail", correctness=0.0, completeness=0.0, rationale="Числа у відповіді не підтверджені переданим контекстом.")

        if required_facts:
            hits = sum(1 for f in required_facts if match_fact_pattern(candidate_answer, f))
            ratio = hits / len(required_facts)
            if ratio >= 0.999:
                return JudgeVerdict(label="pass", correctness=1.0, completeness=1.0, rationale="Усі ключові факти та джерела повністю узгоджені з еталоном.")
            if ratio >= 0.45:
                return JudgeVerdict(label="partial", correctness=0.5, completeness=0.5, rationale="Відповідь часткова: розкрито не всі обов'язкові умови еталону.")
            return JudgeVerdict(label="fail", correctness=0.0, completeness=0.0, rationale="Відповідь не містить очікуваних фактів еталону.")

        ref_toks = set(tokenize_bm25(reference_answer))
        ans_toks = set(tokenize_bm25(candidate_answer))
        overlap = len(ref_toks & ans_toks) / max(1, len(ref_toks))
        if overlap >= 0.45:
            return JudgeVerdict(label="pass", correctness=1.0, completeness=1.0, rationale="Семантично й фактично збігається з еталоном.")
        if overlap >= 0.25:
            return JudgeVerdict(label="partial", correctness=0.5, completeness=0.5, rationale="Частковий збіг із еталонною відповіддю.")
        return JudgeVerdict(label="fail", correctness=0.0, completeness=0.0, rationale="Низька відповідність еталону.")


def build_judge(provider: JudgeProviderChoice = "auto", model: str | None = None) -> JudgeProtocol:
    resolved = resolve_cloud_provider(provider, require_cloud=(provider == "cloud"))
    chosen = "rubric" if resolved == "auto" else resolved
    if chosen == "rubric":
        return CalibratedRubricJudge()
    return CloudLLMJudge(provider=chosen, model=model)
