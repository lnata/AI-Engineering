"""End-to-end HW2 Step 3 Cited RAG pipeline, 1-retry repair loop, and CLI."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import ValidationError

from src.hw2.context_packer import DEFAULT_MAX_CONTEXT_TOKENS, pack_retrieved_context
from src.hw2.generator import (
    ExtractiveRAGGenerator,
    GeminiRAGGenerator,
    OpenAIRAGGenerator,
    RAGGeneratorProtocol,
)
from src.hw2.index import DEFAULT_QDRANT_PATH, ROOT
from src.hw2.models import (
    PackedContext,
    RAGAnswer,
    RAGLLMResponse,
    RAGRunResult,
    SearchFilters,
)
from src.hw2.search import HybridSearchEngine, SearchMode
from src.hw2.verifier import (
    ABSTAIN_MESSAGE_UK,
    CitationVerificationError,
    estimate_cost_per_1k_usd,
    load_rag_prompt,
    render_rag_user_prompt,
    verify_and_resolve_rag_output,
)

ProviderChoice = Literal["auto", "extractive", "gemini", "openai", "openrouter"]
DEFAULT_DEMO_OUT = ROOT / "data" / "hw2_rag" / "sample_answers.json"

DEMO_QUESTIONS: list[dict[str, str]] = [
    {
        "id": "DEMO-01",
        "kind": "versioned_spec_latest",
        "question": "Як обліковуються витрати на вхідну доставку inbound_freight_eur та який поріг звірки SAP проти Databricks діє у чинній специфікації SPEC-FIN-030?",
    },
    {
        "id": "DEMO-02",
        "kind": "multi_chunk_table_runbook",
        "question": "Що означає помилка DM_GWPipeline_Gateway_Timeout і як її усунути при оновленні датасету Power BI?",
    },
    {
        "id": "DEMO-03",
        "kind": "sla_table_lookup",
        "question": "Який час першої реакції та цільовий час фіксу на DEV для Critical Blocker інцидентів під час закриття місяця WD1–WD5?",
    },
    {
        "id": "DEMO-04",
        "kind": "fx_architecture_invariant",
        "question": "На якому шарі та за якою датою виконується валютна конвертація у EUR за діючим стандартом SPEC-FIN-041?",
    },
    {
        "id": "DEMO-05",
        "kind": "abstain_gate1_out_of_domain",
        "question": "Який бюджет відряджень у відділу маркетингу на 2025 рік?",
    },
    {
        "id": "DEMO-06",
        "kind": "abstain_gate2_in_domain_trap",
        "question": "Яка ставка податку на прибуток підприємств закладена у формулу SPEC-FIN-030?",
    },
]


def _clean_json_fence(raw_text: str) -> str:
    txt = (raw_text or "").strip()
    if txt.startswith("```"):
        lines = txt.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        txt = "\n".join(lines).strip()
    start, end = txt.find("{"), txt.rfind("}")
    if start != -1 and end > start:
        return txt[start : end + 1]
    return txt


def generate_verified_rag_answer(
    *,
    generator: RAGGeneratorProtocol,
    system_prompt: str,
    user_prompt: str,
    packed: PackedContext,
    prompt_version: str,
) -> tuple[RAGAnswer | None, str | None, bool, dict[str, int], float]:
    """Run LLM generation + Pydantic & citation verification with 1 explicit repair retry."""
    total_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    total_latency = 0.0
    last_raw = ""

    def _add(u: dict[str, int], lat: float) -> None:
        nonlocal total_latency
        total_latency += lat
        for k in total_usage:
            total_usage[k] += int(u.get(k, 0) or 0)

    try:
        last_raw, u1, lat1 = generator.generate(system_prompt=system_prompt, user_prompt=user_prompt)
        _add(u1, lat1)
        parsed = RAGLLMResponse.model_validate_json(_clean_json_fence(last_raw))
        verified = verify_and_resolve_rag_output(parsed, packed, prompt_version)
        return verified, None, False, total_usage, round(total_latency, 2)
    except (json.JSONDecodeError, ValidationError, CitationVerificationError) as first_exc:
        allowed_ids = ", ".join(s.source_id for s in packed.included_sources)
        repair_prompt = (
            f"Original request:\n{user_prompt}\n\n"
            "Your previous JSON failed RAG schema or citation verification.\n"
            f"Verification errors:\n{first_exc}\n\n"
            f"Previous JSON:\n{last_raw}\n\n"
            "Return a corrected FULL JSON object matching RAGLLMResponse. "
            f"Allowed source_ids: [{allowed_ids}]. Every non-abstained claim MUST cite at least one "
            "valid source_id and `answer` MUST include inline `[Si]` markers; otherwise set "
            f"`abstained=true`, `claims=[]`, and `answer=\"{ABSTAIN_MESSAGE_UK}\"`."
        )
        try:
            raw2, u2, lat2 = generator.generate(system_prompt=system_prompt, user_prompt=repair_prompt)
            _add(u2, lat2)
            parsed2 = RAGLLMResponse.model_validate_json(_clean_json_fence(raw2))
            verified2 = verify_and_resolve_rag_output(parsed2, packed, prompt_version)
            return verified2, None, True, total_usage, round(total_latency, 2)
        except Exception as second_exc:  # noqa: BLE001
            err = f"repair failed: {type(second_exc).__name__}: {second_exc}"
            return None, err, True, total_usage, round(total_latency, 2)


def build_rag_generator(
    provider: ProviderChoice,
    packed: PackedContext,
    question: str,
    model_override: str | None = None,
    timeout_sec: float = 90.0,
) -> RAGGeneratorProtocol:
    """Resolve cloud LLM generator from .env or fall back to deterministic extractive mode."""
    chosen = provider
    if chosen == "auto":
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            chosen = "gemini"
        elif os.getenv("OPENAI_API_KEY"):
            chosen = "openai"
        elif os.getenv("OPENROUTER_API_KEY"):
            chosen = "openrouter"
        else:
            chosen = "extractive"

    if chosen == "gemini":
        model = model_override or os.getenv("HW2_RAG_MODEL", "gemini-3.5-flash-lite")
        return GeminiRAGGenerator(model_name=model, timeout_sec=timeout_sec)
    if chosen == "openai":
        model = model_override or os.getenv("HW2_RAG_MODEL", "gpt-4o-mini")
        return OpenAIRAGGenerator(provider_name="openai", model_name=model, timeout_sec=timeout_sec)
    if chosen == "openrouter":
        model = model_override or os.getenv("HW2_RAG_MODEL", "openai/gpt-4o-mini")
        return OpenAIRAGGenerator(provider_name="openrouter", model_name=model, timeout_sec=timeout_sec)
    return ExtractiveRAGGenerator(packed=packed, question=question)


class RAGPipeline:
    """Grounded RAG orchestrator over HybridSearchEngine + ContextPacker + CitationVerifier."""

    def __init__(
        self,
        search_engine: HybridSearchEngine | None = None,
        qdrant_location: str | Path = DEFAULT_QDRANT_PATH,
    ) -> None:
        self._owns_engine = search_engine is None
        self.engine = search_engine or HybridSearchEngine(qdrant_location=qdrant_location)

    def close(self) -> None:
        if self._owns_engine:
            self.engine.close()

    def answer(
        self,
        question: str,
        *,
        provider: ProviderChoice = "auto",
        model_override: str | None = None,
        prompt_version: str = "v2",
        mode: SearchMode = "hybrid_rerank",
        top_k: int = 5,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        filters: SearchFilters | None = None,
        generator_override: RAGGeneratorProtocol | None = None,
    ) -> RAGRunResult:
        hits = self.engine.search(query=question, mode=mode, top_k=top_k, filters=filters)
        packed = pack_retrieved_context(query=question, hits=hits, max_context_tokens=max_context_tokens)

        # Gate 1: Pre-LLM deterministic abstention (0 LLM tokens spent)
        if not packed.gate_passed:
            abstain_ans = RAGAnswer(
                abstained=True,
                abstain_reason=packed.gate_reason or "insufficient_retrieval_evidence",
                answer=ABSTAIN_MESSAGE_UK,
                claims=[],
                citations=[],
                prompt_version=prompt_version,
            )
            return RAGRunResult(
                ok=True,
                question=question,
                provider="gate1_pre_llm",
                model="none",
                prompt_version=prompt_version,
                usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                estimated_cost_per_1k_usd=0.0,
                context=packed,
                rag_answer=abstain_ans,
            )

        sys_prompt, usr_tmpl = load_rag_prompt(prompt_version)
        usr_prompt = render_rag_user_prompt(usr_tmpl, packed=packed, question=question)
        gen = generator_override or build_rag_generator(
            provider=provider, packed=packed, question=question, model_override=model_override
        )
        verified, err, repaired, usage, lat_ms = generate_verified_rag_answer(
            generator=gen,
            system_prompt=sys_prompt,
            user_prompt=usr_prompt,
            packed=packed,
            prompt_version=prompt_version,
        )
        return RAGRunResult(
            ok=verified is not None,
            question=question,
            provider=gen.provider_name,
            model=gen.model_name,
            prompt_version=prompt_version,
            repair_used=repaired,
            error=err,
            latency_ms=lat_ms,
            usage=usage,
            estimated_cost_per_1k_usd=estimate_cost_per_1k_usd(gen.model_name, usage),
            context=packed,
            rag_answer=verified,
        )


def run_demo_suite(
    out_path: Path = DEFAULT_DEMO_OUT,
    provider: ProviderChoice = "auto",
    prompt_version: str = "v2",
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
) -> dict:
    pipeline = RAGPipeline()
    try:
        items = []
        for item in DEMO_QUESTIONS:
            res = pipeline.answer(
                item["question"],
                provider=provider,
                prompt_version=prompt_version,
                max_context_tokens=max_context_tokens,
                filters=SearchFilters(is_latest=True),
            )
            items.append({"id": item["id"], "kind": item["kind"], **res.model_dump(mode="json")})
    finally:
        pipeline.close()

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prompt_version": prompt_version,
        "max_context_tokens": max_context_tokens,
        "total_questions": len(items),
        "results": items,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="HW2 Step 3 Grounded RAG with Citations CLI")
    parser.add_argument("--question", default=None, help="Single question to answer")
    parser.add_argument("--demo", action="store_true", help="Run 6-question demo suite -> sample_answers.json")
    parser.add_argument("--provider", choices=["auto", "extractive", "gemini", "openai", "openrouter"], default="auto")
    parser.add_argument("--model", default=None, help="Optional cloud model override")
    parser.add_argument("--prompt-version", default=os.getenv("HW2_RAG_PROMPT_VERSION", "v2"))
    parser.add_argument("--max-context-tokens", type=int, default=int(os.getenv("HW2_MAX_CONTEXT_TOKENS", "1200")))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--only-latest", action="store_true", default=True)
    parser.add_argument("--include-legacy", action="store_true", help="Disable default is_latest=True filter")
    parser.add_argument("--out", type=Path, default=DEFAULT_DEMO_OUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.demo or not args.question:
        report = run_demo_suite(
            out_path=args.out,
            provider=args.provider,
            prompt_version=args.prompt_version,
            max_context_tokens=args.max_context_tokens,
        )
        print(f"Wrote {report['total_questions']} grounded RAG demo answers to {args.out}")
        for r in report["results"]:
            ans = r["rag_answer"]
            status = f"ABSTAIN ({ans['abstain_reason']})" if ans["abstained"] else f"CITED ({len(ans['citations'])} sources)"
            print(f"  {r['id']} [{r['kind']}]: {status} | ctx={r['context']['used_tokens']}/{r['context']['budget_tokens']} tok")
        return

    filt = None if args.include_legacy else SearchFilters(is_latest=True)
    pipe = RAGPipeline()
    try:
        res = pipe.answer(
            args.question,
            provider=args.provider,
            model_override=args.model,
            prompt_version=args.prompt_version,
            top_k=args.top_k,
            max_context_tokens=args.max_context_tokens,
            filters=filt,
        )
    finally:
        pipe.close()

    if args.json:
        print(json.dumps(res.model_dump(mode="json"), ensure_ascii=False, indent=2))
    elif res.rag_answer:
        print(f"Provider: {res.provider} ({res.model}) | Prompt: {res.prompt_version} | Abstained: {res.rag_answer.abstained}")
        print(f"Context tokens: {res.context.used_tokens}/{res.context.budget_tokens}")
        print(f"\nAnswer:\n{res.rag_answer.answer}")


if __name__ == "__main__":
    main()
