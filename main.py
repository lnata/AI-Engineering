#!/usr/bin/env python3
"""Run HW1 structured extraction (default) or HW2 RAG & Evals (`--hw2-rag` / `--hw2-eval`)."""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from src.config import ROOT, load_config
from src.extract import run_extraction


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Analytics Ticket Copilot CLI (HW1 & HW2)")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Config file: config.yaml | config.ollama.yaml | config.lmstudio.yaml",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process only first N tickets")
    parser.add_argument(
        "--ids",
        nargs="*",
        default=None,
        help="Process only these ticket ids, e.g. BUGS-41 BUGS-42",
    )
    parser.add_argument(
        "--sampling",
        default=None,
        help="Override sampling profile from config (default|creative)",
    )
    parser.add_argument(
        "--prompt-version",
        default=None,
        help="Override prompt version folder under prompts/ (e.g. v1, v2)",
    )
    parser.add_argument(
        "--hw2-rag",
        action="store_true",
        help="Run HW2 Step 3 grounded RAG pipeline instead of HW1 ticket extraction",
    )
    parser.add_argument(
        "--hw2-eval",
        action="store_true",
        help="Run HW2 Step 4 judge calibration + 24-question end-to-end RAG evaluation",
    )
    parser.add_argument("--question", default=None, help="Question for --hw2-rag mode")
    args = parser.parse_args()

    if args.hw2_eval:
        import sys
        from src.hw2.eval_rag import check_ci_thresholds, run_end_to_end_rag_eval

        report, calib = run_end_to_end_rag_eval()
        prod = report.configurations[-1]
        print(
            f"HW2 RAG Eval: overall={prod.overall_composite_score:.3f}, "
            f"faithfulness={prod.faithfulness_mean:.3f}, abstention={prod.abstention_accuracy:.3f}, "
            f"judge_agreement={calib.agreement_rate:.1%}"
        )
        failures = check_ci_thresholds(prod, calib)
        if failures:
            raise SystemExit(1)
        sys.exit(0)

    if args.hw2_rag:
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

    cfg = load_config(args.config)
    if args.sampling:
        cfg.run.sampling_profile = args.sampling
    if args.prompt_version:
        cfg.run.prompt_version = args.prompt_version

    run_extraction(cfg=cfg, limit=args.limit, ticket_ids=args.ids)


if __name__ == "__main__":
    main()
