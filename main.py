#!/usr/bin/env python3
"""Run structured extraction over exported Jira tickets."""

from __future__ import annotations

import argparse

from pathlib import Path

from dotenv import load_dotenv

from src.config import ROOT, load_config
from src.extract import run_extraction


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="HW1 structured extraction runner")
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
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.sampling:
        cfg.run.sampling_profile = args.sampling
    if args.prompt_version:
        cfg.run.prompt_version = args.prompt_version

    run_extraction(cfg=cfg, limit=args.limit, ticket_ids=args.ids)


if __name__ == "__main__":
    main()
