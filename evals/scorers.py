"""Public scoring interface under `evals/` per HW2 repository layout specification.

Exposes all 3 mandatory scoring layers:
1. Deterministic scorers (`score_deterministic`, `match_fact_pattern`, `DeterministicScores`)
2. LLM-as-a-Judge + manual calibration (`CloudLLMJudge`, `CalibratedRubricJudge`, `build_judge`, `run_judge_calibration`, `compute_cohens_kappa`)
3. Claim-level Faithfulness + polarity verification (`score_faithfulness`, `FaithfulnessReport`)
"""

from __future__ import annotations

from src.hw2.calibrate_judge import (
    CalibrationItemResult,
    JudgeCalibrationReport,
    compute_cohens_kappa,
    run_judge_calibration,
)
from src.hw2.judge import (
    CalibratedRubricJudge,
    CalibrationCase,
    CloudLLMJudge,
    JudgeProtocol,
    JudgeProviderChoice,
    build_judge,
    load_judge_prompt,
    render_judge_user_prompt,
)
from src.hw2.scorers import (
    DeterministicScores,
    FaithfulnessReport,
    JudgeVerdict,
    RAGTestCase,
    _has_polarity_inversion,
    match_fact_pattern,
    score_deterministic,
    score_faithfulness,
)

__all__ = [
    "CalibrationCase",
    "CalibrationItemResult",
    "CalibratedRubricJudge",
    "CloudLLMJudge",
    "DeterministicScores",
    "FaithfulnessReport",
    "JudgeCalibrationReport",
    "JudgeProtocol",
    "JudgeProviderChoice",
    "JudgeVerdict",
    "RAGTestCase",
    "_has_polarity_inversion",
    "build_judge",
    "compute_cohens_kappa",
    "load_judge_prompt",
    "match_fact_pattern",
    "render_judge_user_prompt",
    "run_judge_calibration",
    "score_deterministic",
    "score_faithfulness",
]
