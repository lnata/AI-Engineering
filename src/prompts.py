from __future__ import annotations

from pathlib import Path

from src.config import ROOT


def load_prompt(version: str) -> tuple[str, str]:
    base = ROOT / "prompts" / version
    system = (base / "system.txt").read_text(encoding="utf-8").strip()
    user_template = (base / "user_template.txt").read_text(encoding="utf-8").strip()
    return system, user_template


def render_user_prompt(
    template: str,
    *,
    ticket_id: str,
    ticket_text: str,
    jira_issue_type: str | None,
) -> str:
    return (
        template.replace("{{ticket_id}}", ticket_id)
        .replace("{{ticket_text}}", ticket_text)
        .replace("{{jira_issue_type}}", jira_issue_type or "unknown")
    )
