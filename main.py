#!/usr/bin/env python3
"""Unified CLI entrypoint for Analytics Ticket Copilot (branch `hw2`: defaults to HW2 RAG + Evals)."""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from src.config import ROOT, load_config
from src.extract import run_extraction


def _run_hw2_pipeline(*, require_cloud: bool, prompt_version: str) -> None:
    from src.hw2.eval_rag import check_ci_thresholds, run_end_to_end_rag_eval
    from src.hw2.index import DEFAULT_QDRANT_PATH, build_persistent_index
    from src.hw2.llm_runtime import resolve_cloud_provider
    from src.hw2.rag import run_demo_suite

    mode_prov = "cloud" if require_cloud else "auto"
    resolved = resolve_cloud_provider(mode_prov, require_cloud=require_cloud)
    label = resolved if resolved != "auto" else "local ONNX + extractive/rubric ($0)"
    print(f"=== Running HW2 Pipeline (provider={label}, prompt={prompt_version}) ===", flush=True)

    if not DEFAULT_QDRANT_PATH.exists() or not any(DEFAULT_QDRANT_PATH.iterdir()):
        meta = build_persistent_index()
        print(f"Built Qdrant index ({meta.chunks_count} chunks, dim={meta.embedding_dim}).", flush=True)

    demo = run_demo_suite(provider=mode_prov, prompt_version=prompt_version)  # type: ignore[arg-type]
    print(f"Generated {demo['total_questions']} cited RAG demo answers -> data/hw2_rag/sample_answers.json", flush=True)

    report, calib = run_end_to_end_rag_eval(
        provider=mode_prov,  # type: ignore[arg-type]
        judge_provider=mode_prov,  # type: ignore[arg-type]
    )
    prod = report.configurations[-1]
    print(
        f"HW2 Eval Complete ({report.rag_provider} | judge={report.judge_name}):\n"
        f"  overall={prod.overall_composite_score:.3f} | abstention={prod.abstention_accuracy:.3f} | "
        f"cite_source={prod.citation_source_hit_rate:.3f} | fact_cov={prod.fact_coverage_mean:.3f} | "
        f"faithfulness={prod.faithfulness_mean:.3f} | judge_score={prod.judge_correctness_mean:.3f}\n"
        f"  judge_calibration: {calib.exact_matches}/{calib.total_cases} ({calib.agreement_rate:.1%}, kappa={calib.cohens_kappa:.3f})"
    )
    failures = check_ci_thresholds(prod, calib)
    if failures:
        print("CI QUALITY GATE FAILED: " + "; ".join(failures), file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Analytics Ticket Copilot CLI (HW2 default; --hw1 for HW1)")
    parser.add_argument("--hw1", action="store_true", help="Run HW1 structured Jira ticket extraction")
    parser.add_argument("--hw2-rag", action="store_true", help="Run HW2 cited RAG demo or single --question")
    parser.add_argument("--hw2-eval", action="store_true", help="Run HW2 judge calibration + 28-question RAG eval")
    parser.add_argument(
        "--hw2-llm",
        action="store_true",
        help="Require GEMINI_API_KEY/OPENAI_API_KEY in .env and refresh all HW2 RAG & Judge artifacts with live LLM",
    )
    parser.add_argument("--question", default=None, help="Single question for --hw2-rag mode")
    parser.add_argument("--config", default=None, help="HW1 config: config.yaml | config.ollama.yaml | config.lmstudio.yaml")
    parser.add_argument("--limit", type=int, default=None, help="HW1: process only first N tickets")
    parser.add_argument("--ids", nargs="*", default=None, help="HW1: process only these ticket ids")
    parser.add_argument("--sampling", default=None, help="HW1: override sampling profile (default|creative)")
    parser.add_argument("--prompt-version", default=None, help="Override prompt version (e.g. v1, v2)")
    args = parser.parse_args()

    # Route explicit --hw1 or HW1-specific flags to HW1 extraction
    wants_hw1 = args.hw1 or args.ids is not None or args.limit is not None or args.sampling is not None or args.config is not None
    if wants_hw1 and not (args.hw2_rag or args.hw2_eval or args.hw2_llm):
        cfg = load_config(args.config or "config.yaml")
        if args.sampling:
            cfg.run.sampling_profile = args.sampling
        if args.prompt_version:
            cfg.run.prompt_version = args.prompt_version
        run_extraction(cfg=cfg, limit=args.limit, ticket_ids=args.ids)
        return

    if args.hw2_llm:
        _run_hw2_pipeline(require_cloud=True, prompt_version=args.prompt_version or "v2")
        return

    if args.hw2_eval:
        from src.hw2.eval_rag import check_ci_thresholds, run_end_to_end_rag_eval

        report, calib = run_end_to_end_rag_eval()
        prod = report.configurations[-1]
        print(
            f"HW2 RAG Eval ({report.rag_provider} | {report.judge_name}): overall={prod.overall_composite_score:.3f}, "
            f"faithfulness={prod.faithfulness_mean:.3f}, abstention={prod.abstention_accuracy:.3f}, "
            f"judge_agreement={calib.agreement_rate:.1%}"
        )
        if check_ci_thresholds(prod, calib):
            raise SystemExit(1)
        return

    if args.hw2_rag or args.question:
        from src.hw2.models import SearchFilters
        from src.hw2.rag import RAGPipeline, run_demo_suite

        pv = args.prompt_version or "v2"
        if not args.question:
            report = run_demo_suite(prompt_version=pv)
            print(f"Completed HW2 RAG demo suite ({report['total_questions']} questions).")
            return
        pipe = RAGPipeline()
        try:
            res = pipe.answer(args.question, prompt_version=pv, filters=SearchFilters(is_latest=True))
            print(res.rag_answer.answer if res.rag_answer else f"ERROR: {res.error}")
        finally:
            pipe.close()
        return

    # Default zero-flag invocation (`python main.py` / `make run`) executes HW2 cleanly
    _run_hw2_pipeline(require_cloud=False, prompt_version=args.prompt_version or "v2")


if __name__ == "__main__":
    main()
