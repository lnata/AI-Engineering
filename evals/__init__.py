"""HW2 Evaluation package: testsets, 3-layer scoring functions, calibration, and run results."""

from evals.scorers import (
    CalibratedRubricJudge,
    CloudLLMJudge,
    DeterministicScores,
    FaithfulnessReport,
    JudgeProtocol,
    JudgeVerdict,
    RAGTestCase,
    build_judge,
    compute_cohens_kappa,
    match_fact_pattern,
    run_judge_calibration,
    score_deterministic,
    score_faithfulness,
)

__all__ = [
    "CalibratedRubricJudge",
    "CloudLLMJudge",
    "DeterministicScores",
    "FaithfulnessReport",
    "JudgeProtocol",
    "JudgeVerdict",
    "RAGTestCase",
    "build_judge",
    "compute_cohens_kappa",
    "match_fact_pattern",
    "run_judge_calibration",
    "score_deterministic",
    "score_faithfulness",
]
