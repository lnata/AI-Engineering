"""Structured Markdown extractors for HW1 Jira tickets (BUGS-*.json) and reference catalogs."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from src.hw2.cleaning import clean_markdown_text, decode_text_bytes

# Anonymize personal names/handles from HW1 exports into role-coded team slots (zero PII)
_HANDLE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:Anna\s+Kovalska|anna\.k|Anna\s+K\.?|Anna)\b", re.I), "RD-01"),
    (re.compile(r"\b(?:Oleh\s+Petrenko|oleh\.p|Oleh\s+P\.?|Oleh)\b", re.I), "RD-02"),
    (re.compile(r"\b(?:Maria\s+Bondar|maria\.b|Maria\s+B\.?|Maria)\b", re.I), "FA-01"),
    (re.compile(r"\b(?:Ihor\s+Sydorenko|ihor\.s|Ihor\s+S\.?|Ihor)\b", re.I), "FA-02"),
    (re.compile(r"\b(?:Dmytro\s+Shevchenko|dmytro\.s|Dmytro\s+S\.?|Dmytro)\b", re.I), "DP-01"),
    (re.compile(r"\b(?:Kateryna\s+Melnyk|katya\.m|Katya\s+M\.?|Katya)\b", re.I), "DP-02"),
)

_REPORT_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("RPT-SALES-001", ("sales overview", "sales_overview", "fact_orders", "c_salesorder_q1", "spec-fin-014")),
    ("RPT-INV-002", ("inventory", "wh.inventory_snapshot", "stock overview", "spec-ops-007")),
    ("RPT-CUST-003", ("customers by region", "customers_prod", "dim_customer", "spec-fin-021")),
    ("RPT-FIN-004", ("gross margin", "finance_dev", "fact_revenue", "spec-fin-030")),
    ("RPT-FX-005", ("fx_revenue", "fx revenue", "fx double", "fact_payments", "spec-fin-041")),
)
_SPEC_RE = re.compile(r"\b(SPEC-(?:FIN|OPS|REV)-\d{3})\b", re.IGNORECASE)


def anonymize_team_handles(text: str) -> str:
    out = text
    for pat, slot in _HANDLE_REPLACEMENTS:
        out = pat.sub(slot, out)
    return out


def is_analytics_domain_ticket(data: dict[str, Any]) -> bool:
    """Select canonical SAP -> Databricks -> Power BI + SPEC/deployment tickets (BUGS-41..53)."""
    labels = {str(lbl).lower() for lbl in (data.get("labels") or [])}
    if labels & {"pipeline-sap", "pipeline-databricks", "pipeline-pbi", "pipeline-spec", "change-request", "deployment"}:
        return True
    blob = f"{data.get('summary', '')} {data.get('description', '')}".lower()
    return any(tok in blob for tok in ("sap fiori", "databricks", "spec-fin-", "spec-ops-"))


def _infer_report_id(blob: str) -> str | None:
    low = blob.lower()
    for rep_id, hints in _REPORT_HINTS:
        if any(h in low for h in hints):
            return rep_id
    return None


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    h_line = "| " + " | ".join(headers) + " |"
    s_line = "| " + " | ".join("---" for _ in headers) + " |"
    b_lines = ["| " + " | ".join(c.replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join([h_line, s_line, *b_lines])


def _extract_jira_ticket(data: dict[str, Any]) -> str:
    tid = str(data.get("id") or "BUGS-UNKNOWN").strip()
    summary = anonymize_team_handles(str(data.get("summary") or tid).strip())
    desc = anonymize_team_handles(str(data.get("description") or data.get("text") or "").strip())
    created = str(data.get("created") or "2025-04-15")[:10]
    # Normalize synthetic 2026 export timestamp into corpus timeline (2025-04-15) while keeping ISO format
    eff_date = "2025-04-15" if created.startswith("2026-") else created
    blob = f"{summary}\n{desc}"
    rep_id = _infer_report_id(blob)
    spec_matches = sorted({m.upper() for m in _SPEC_RE.findall(blob)})
    labels_str = ", ".join(str(x) for x in (data.get("labels") or [])) or "none"

    meta = (
        f"Doc ID: {tid} | Version: 1.0 | Effective Date: {eff_date} | "
        f"Type: jira_ticket | Report: {rep_id or 'PLATFORM-WIDE'} | Status: ACTIVE"
    )
    passport_tbl = _md_table(
        ["Ticket ID", "Issue Type", "Status", "Linked Report", "Linked Specs", "Labels"],
        [[
            tid,
            str(data.get("issue_type") or "Bug"),
            str(data.get("status") or "To Do"),
            rep_id or "PLATFORM-WIDE",
            ", ".join(spec_matches) or "-",
            labels_str,
        ]],
    )
    paragraphs: list[str] = []
    for raw_p in desc.split("\n\n"):
        joined = " ".join(raw_p.splitlines()).strip()
        if not joined:
            continue
        if joined[0].islower():
            joined = joined[0].upper() + joined[1:]
        if not joined.endswith((".", "!", "?", ":", ")", '"', "'", "»")):
            joined = f"{joined}."
        paragraphs.append(joined)
    body = "\n\n".join(paragraphs)
    return clean_markdown_text(
        f"# {tid}: {summary}\n\n{meta}\n\n"
        f"## 1. Картка та опис Jira-тікета {tid}\n\n{passport_tbl}\n\n{body}"
    )


def _extract_reference_catalog(path: Path, data: dict[str, Any]) -> str:
    stem = path.stem.lower()
    doc_id = f"REF-{stem.upper()}"
    meta = f"Doc ID: {doc_id} | Version: 1.0 | Effective Date: 2025-04-15 | Type: reference | Report: PLATFORM-WIDE | Status: ACTIVE"

    if "reports" in data:
        rows = []
        for r in data["reports"]:
            sf = r.get("sap_fiori") or {}
            sp = r.get("specification") or {}
            dbx = ", ".join(r.get("databricks_objects") or [])
            owners = r.get("owners") or {}
            own_str = anonymize_team_handles(
                f"dev={owners.get('report_developer')}, fa={owners.get('financial_analyst')}, dp={owners.get('data_pull_owner')}"
            )
            rows.append([
                r["id"],
                f"{r['name']} ({r['pbix']} / {r['dataset']})",
                f"{sf.get('app_name')} ({sf.get('transaction_or_cds')})",
                dbx,
                f"{sp.get('spec_id')} ({sp.get('title')})",
                own_str,
            ])
        tbl = _md_table(["Report ID", "Power BI PBIX / Dataset", "SAP Fiori / CDS", "Databricks Objects", "Specification", "Owners"], rows)
        return clean_markdown_text(f"# {doc_id}: Canonical Analytics Reports Reference Catalog\n\n{meta}\n\n## 1. Каталог звітів та зв'язків SAP -> Databricks -> Power BI\n\n{tbl}")

    if "steps" in data and "rule" in data:
        rows = [[s["id"], s["name"], str(s.get("environment") or "local"), s["owner_role"], s["exit_criteria"]] for s in data["steps"]]
        tbl = _md_table(["Step ID", "Stage Name", "Environment", "Owner Role", "Exit Criteria"], rows)
        forb = "\n".join(f"- Заборонено: {f}" for f in (data.get("forbidden") or []))
        return clean_markdown_text(f"# {doc_id}: Deployment Workflow Reference (DEV -> Approval -> PROD)\n\n{meta}\n\n## 1. Правило промоушену релізів та контрольні етапи\n\n{data['rule']}\n\n{forb}\n\n{tbl}")

    if "pipeline" in data:
        rows = [[p["stage"], p["owner_role"], p["description"], "; ".join(p.get("typical_issues") or [])] for p in data["pipeline"]]
        tbl = _md_table(["Pipeline Stage", "Owner Role", "Description", "Typical Issues"], rows)
        notes = f"{data.get('reconciliation_rule', '')}\n\n{data.get('deployment_rule', '')}".strip()
        return clean_markdown_text(f"# {doc_id}: Reporting Pipeline Stages & Root-Cause Reference\n\n{meta}\n\n## 1. Ланки пайплайну звітності та типові причини багів\n\n{notes}\n\n{tbl}")

    if "teams" in data:
        rows = []
        for t in data["teams"]:
            slots = ", ".join(anonymize_team_handles(m.get("handle", "")) for m in (t.get("members") or []))
            rows.append([t["id"], t["name"], t["role"], t["responsibility"], slots])
        tbl = _md_table(["Team ID", "Team Name", "Role Key", "Responsibility", "Role Slots"], rows)
        return clean_markdown_text(f"# {doc_id}: Analytics Platform Teams & Roles Reference\n\n{meta}\n\n## 1. Матриця команд та зон відповідальності\n\n{tbl}")

    raise ValueError(f"Unrecognized JSON reference schema in {path}")


def extract_json(path: Path) -> str:
    """Convert structured HW1 Jira ticket JSON or reference catalog JSON to clean Markdown."""
    data = json.loads(decode_text_bytes(path.read_bytes()))
    if isinstance(data, dict) and "id" in data and str(data["id"]).startswith("BUGS-"):
        return _extract_jira_ticket(data)
    if isinstance(data, dict):
        return _extract_reference_catalog(path, data)
    raise ValueError(f"Unsupported JSON structure in {path}")
