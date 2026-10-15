from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import ROOT


def _get(d: dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


# Fields we score for HW1 field-level accuracy
SCORE_FIELDS = [
    "ticket_type",
    "priority",
    "issue_category",
    "report.deploy_stage",
    "report.name",
    "specification.spec_id",
    "ownership.primary_assignee_role",
    "reconciliation.mismatch_suspected_at",
    "reconciliation.compare_sap_vs_databricks",
    "reconciliation.compare_databricks_vs_power_bi",
    "reconciliation.compare_report_vs_spec",
    "deployment.status",
    "deployment.requires_dev_deploy_first",
    "is_blocker",
]


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def compare_run(results_dir: Path, golden_path: Path | None = None) -> dict[str, Any]:
    golden_path = golden_path or (ROOT / "data" / "golden.json")
    golden_rows = json.loads(golden_path.read_text(encoding="utf-8"))
    golden = {row["id"]: row["label"] for row in golden_rows}

    summary_path = results_dir / "summary.json"
    if summary_path.exists():
        results = json.loads(summary_path.read_text(encoding="utf-8"))["results"]
    else:
        results = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(results_dir.glob("BUGS-*.json"))
        ]

    per_ticket: list[dict[str, Any]] = []
    field_hits = {f: 0 for f in SCORE_FIELDS}
    field_total = {f: 0 for f in SCORE_FIELDS}
    latencies: list[float] = []
    ok_count = 0
    scored = 0

    for row in results:
        tid = row["id"]
        if tid not in golden:
            continue
        scored += 1
        ok = bool(row.get("ok") and row.get("extraction"))
        if ok:
            ok_count += 1
        if row.get("latency_ms") is not None:
            latencies.append(float(row["latency_ms"]))

        pred = row.get("extraction") or {}
        gold = golden[tid]
        matches: dict[str, bool] = {}
        for field in SCORE_FIELDS:
            g = _norm(_get(gold, field))
            p = _norm(_get(pred, field))
            # skip scoring if golden value is null/empty for optional-ish strings
            if g in (None, ""):
                continue
            field_total[field] += 1
            hit = g == p
            if hit:
                field_hits[field] += 1
            matches[field] = hit

        per_ticket.append(
            {
                "id": tid,
                "ok": ok,
                "field_accuracy": (
                    sum(matches.values()) / len(matches) if matches else None
                ),
                "matches": matches,
            }
        )

    def pct(values: list[float], p: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        idx = min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1))))
        return ordered[idx]

    field_accuracy = {
        f: (field_hits[f] / field_total[f] if field_total[f] else None)
        for f in SCORE_FIELDS
    }
    scored_pairs = sum(field_total.values())
    overall = (
        sum(field_hits.values()) / scored_pairs if scored_pairs else None
    )

    report = {
        "results_dir": str(results_dir),
        "golden_tickets_scored": scored,
        "valid_json_pct": (ok_count / scored) if scored else None,
        "overall_field_accuracy": overall,
        "field_accuracy": field_accuracy,
        "latency_ms": {
            "p50": pct(latencies, 50),
            "p95": pct(latencies, 95),
            "mean": (sum(latencies) / len(latencies)) if latencies else None,
        },
        "per_ticket": per_ticket,
    }

    out = results_dir / "metrics.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def latest_gemini_run() -> Path:
    runs = sorted((ROOT / "results").glob("gemini_*"))
    if not runs:
        raise FileNotFoundError("No gemini results found under results/")
    return runs[-1]
