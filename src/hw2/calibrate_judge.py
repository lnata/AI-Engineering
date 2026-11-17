"""Judge calibration runner: agreement %, Cohen's kappa, confusion matrix, and CI gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Sequence

from dotenv import load_dotenv
from pydantic import BaseModel

from src.hw2.judge import (
    DEFAULT_CALIB_OUT,
    DEFAULT_CALIB_PATH,
    CalibrationCase,
    JudgeProtocol,
    JudgeProviderChoice,
    ROOT,
    build_judge,
)

LABELS: tuple[str, ...] = ("pass", "partial", "fail")


class CalibrationItemResult(BaseModel):
    id: str
    scenario: str
    human_label: str
    human_score: float
    judge_label: str
    judge_score: float
    agreed: bool
    judge_rationale: str


class JudgeCalibrationReport(BaseModel):
    calibrated_at: str
    judge_name: str
    total_cases: int
    exact_matches: int
    agreement_rate: float
    cohens_kappa: float
    mean_abs_score_diff: float
    confusion_matrix: dict[str, dict[str, int]]
    cases: list[CalibrationItemResult]


def compute_cohens_kappa(human_labels: Sequence[str], judge_labels: Sequence[str]) -> float:
    """Compute unweighted multi-class Cohen's kappa across ('pass', 'partial', 'fail')."""
    n = len(human_labels)
    if n == 0:
        return 0.0
    p_o = sum(1 for h, j in zip(human_labels, judge_labels) if h == j) / n
    p_e = 0.0
    for lbl in LABELS:
        p_h = sum(1 for h in human_labels if h == lbl) / n
        p_j = sum(1 for j in judge_labels if j == lbl) / n
        p_e += p_h * p_j
    if abs(1.0 - p_e) < 1e-9:
        return 1.0
    return round((p_o - p_e) / (1.0 - p_e), 4)


def run_judge_calibration(
    calib_path: Path = DEFAULT_CALIB_PATH,
    out_path: Path = DEFAULT_CALIB_OUT,
    judge_provider: JudgeProviderChoice = "auto",
    judge_override: JudgeProtocol | None = None,
) -> JudgeCalibrationReport:
    raw_items = json.loads(calib_path.read_text(encoding="utf-8"))
    cases = [CalibrationCase.model_validate(x) for x in raw_items]
    judge = judge_override or build_judge(provider=judge_provider)

    matrix: dict[str, dict[str, int]] = {
        h_lbl: {j_lbl: 0 for j_lbl in LABELS} for h_lbl in LABELS
    }
    results: list[CalibrationItemResult] = []
    human_seq: list[str] = []
    judge_seq: list[str] = []

    for c in cases:
        verdict = judge.evaluate(
            question=c.question,
            expected_abstain=c.expected_abstain,
            required_facts=c.required_facts,
            forbidden_facts=c.forbidden_facts,
            reference_answer=c.reference_answer,
            packed_context=c.packed_context,
            candidate_abstained=c.candidate_abstained,
            candidate_citations=c.candidate_citations,
            candidate_answer=c.candidate_answer,
        )
        j_score = round((verdict.correctness + verdict.completeness) / 2.0, 4)
        agreed = c.human_label == verdict.label
        matrix[c.human_label][verdict.label] += 1
        human_seq.append(c.human_label)
        judge_seq.append(verdict.label)
        results.append(
            CalibrationItemResult(
                id=c.id,
                scenario=c.scenario,
                human_label=c.human_label,
                human_score=c.human_score,
                judge_label=verdict.label,
                judge_score=j_score,
                agreed=agreed,
                judge_rationale=verdict.rationale,
            )
        )

    n = len(results) or 1
    matches = sum(1 for r in results if r.agreed)
    mad = sum(abs(r.human_score - r.judge_score) for r in results) / n
    report = JudgeCalibrationReport(
        calibrated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        judge_name=judge.name,
        total_cases=len(results),
        exact_matches=matches,
        agreement_rate=round(matches / n, 4),
        cohens_kappa=compute_cohens_kappa(human_seq, judge_seq),
        mean_abs_score_diff=round(mad, 4),
        confusion_matrix=matrix,
        cases=results,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Calibrate HW2 LLM-as-a-Judge on human labels")
    parser.add_argument("--calib-set", type=Path, default=DEFAULT_CALIB_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_CALIB_OUT)
    parser.add_argument("--judge-provider", choices=["auto", "cloud", "rubric", "gemini", "openai", "openrouter"], default="auto")
    parser.add_argument("--min-agreement", type=float, default=0.85)
    args = parser.parse_args()

    rep = run_judge_calibration(
        calib_path=args.calib_set, out_path=args.out, judge_provider=args.judge_provider
    )
    print(
        f"Judge Calibration ({rep.judge_name}): {rep.exact_matches}/{rep.total_cases} exact matches "
        f"| agreement={rep.agreement_rate:.1%} | kappa={rep.cohens_kappa:.3f} | MAD={rep.mean_abs_score_diff:.3f}"
    )
    if rep.agreement_rate < args.min_agreement:
        print(
            f"FAIL: Judge agreement {rep.agreement_rate:.3f} < threshold {args.min_agreement:.3f}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
