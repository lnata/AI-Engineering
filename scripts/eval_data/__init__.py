"""Modular human-verified datasets for HW2 Step 4 RAG evals and Judge calibration."""

from scripts.eval_data.calibration_cases import JUDGE_CALIBRATION_CASES
from scripts.eval_data.testset_jira_cross_source import JIRA_CROSS_SOURCE_QUESTIONS
from scripts.eval_data.testset_standard import STANDARD_QUESTIONS
from scripts.eval_data.testset_traps_unanswerable import UNANSWERABLE_AND_TRAP_QUESTIONS

ALL_RAG_TESTSET_QUESTIONS: list[dict] = [
    *STANDARD_QUESTIONS,
    *UNANSWERABLE_AND_TRAP_QUESTIONS,
    *JIRA_CROSS_SOURCE_QUESTIONS,
]

__all__ = ["ALL_RAG_TESTSET_QUESTIONS", "JUDGE_CALIBRATION_CASES"]
