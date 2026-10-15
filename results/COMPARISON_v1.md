# Comparison — prompt v1 / sampling default

Golden set: `BUGS-41` … `BUGS-50` (10 tickets).

| Model | Valid JSON | Field accuracy | Latency p50 | Latency p95 |
|-------|------------|----------------|-------------|-------------|
| **Gemini** (`gemini-3.5-flash-lite`) | 100% (10/10) | **79.3%** | ~2.0s | ~2.6s |
| **Ollama** (`llama3.2`) | 90% (9/10) | 51.4% | ~8.7s | ~19.5s |
| **LM Studio** (`llama-3.2-3b-instruct`) | 80% (8/10) | 38.6% | ~7.8s | ~18.5s |

## Takeaways

- Cloud Gemini is clearly best on quality and speed for this schema-heavy task.
- Local models are usable for the homework comparison, but struggle with enums / nested required fields.
- Cost: Gemini uses API quota; Ollama / LM Studio are free locally (compute only).

## Provisional production choice

Prefer **Gemini** for production extraction unless offline / cost constraints force a local model.

## Prompt v1 → v2 (Gemini only)

| Metric | v1 | v2 |
|--------|----|----|
| Overall field accuracy | 79.3% | **88.6%** |
| priority | 40% | **80%** |
| report.name | 20% | **80%** |
| deployment.status | 30% | 40% |

`deployment.status` stays hard when the ticket text does not explicitly mention deploy progress (golden labels are richer than some source texts).
