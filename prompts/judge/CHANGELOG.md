# Judge Prompt Changelog (HW2 — Крок 4 «Evals у CI»)

Версіоновані промпти для модуля `LLM-as-a-Judge` (`src/hw2/scorers.py` та `src/hw2/calibrate_judge.py`).

## v1 — 2026-11-17

- Трирівнева рубрика вердикту `JudgeVerdict` (`pass` = `1.0`, `partial` = `0.5`, `fail` = `0.0`) із окремими полями `correctness`, `completeness` та поясненням `rationale`.
- Чітке розмежування двох класів кейсів:
  1. `expected_abstain = true` (перевірка чесної відмови без галюцинацій);
  2. `expected_abstain = false` (перевірка точності фактів проти `reference_answer`, відсутності застарілих правил `v1.0`, валідності джерел та відсутності домислів поза `packed_context`).
- Відкалібровано на 14 вручну розмічених прикладах (`evals/hw2_judge_calibration.json` → `evals/hw2_judge_calibration_results.json`).
