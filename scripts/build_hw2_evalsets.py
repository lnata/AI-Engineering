#!/usr/bin/env python3
"""Materialize evals/hw2_rag_testset.json (24 Qs) and evals/hw2_judge_calibration.json (14 cases)."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval_data import ALL_RAG_TESTSET_QUESTIONS, JUDGE_CALIBRATION_CASES

EVALS_DIR = ROOT / "evals"


def build_evalsets(out_dir: Path = EVALS_DIR) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    testset_path = out_dir / "hw2_rag_testset.json"
    calib_path = out_dir / "hw2_judge_calibration.json"

    testset_path.write_text(
        json.dumps(ALL_RAG_TESTSET_QUESTIONS, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    calib_path.write_text(
        json.dumps(JUDGE_CALIBRATION_CASES, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return testset_path, calib_path


if __name__ == "__main__":
    tp, cp = build_evalsets()
    print(f"Wrote {len(ALL_RAG_TESTSET_QUESTIONS)} RAG testset questions -> {tp}")
    print(f"Wrote {len(JUDGE_CALIBRATION_CASES)} judge calibration cases -> {cp}")
