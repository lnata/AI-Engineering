from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import ROOT, AppConfig, load_config
from src.llm.base import LLMClient
from src.llm.gemini_client import GeminiClient
from src.llm.openai_client import OpenAIClient
from src.llm.openai_compatible import LMStudioClient, OllamaClient
from src.prompts import load_prompt, render_user_prompt
from src.schema import TicketExtraction


def build_client(cfg: AppConfig) -> LLMClient:
    if cfg.provider.name == "openai":
        return OpenAIClient(cfg.provider)
    if cfg.provider.name == "gemini":
        return GeminiClient(cfg.provider)
    if cfg.provider.name == "ollama":
        return OllamaClient(cfg.provider, base_url=cfg.provider.base_url)
    if cfg.provider.name == "lmstudio":
        return LMStudioClient(cfg.provider, base_url=cfg.provider.base_url)
    raise ValueError(f"Unsupported provider: {cfg.provider.name}")


def load_tickets(index_path: Path) -> list[dict[str, Any]]:
    return json.loads(index_path.read_text(encoding="utf-8"))


def run_extraction(
    *,
    cfg: AppConfig | None = None,
    limit: int | None = None,
    ticket_ids: list[str] | None = None,
) -> Path:
    cfg = cfg or load_config()
    client = build_client(cfg)
    sampling = cfg.sampling_for()
    system_prompt, user_template = load_prompt(cfg.run.prompt_version)

    tickets = load_tickets(ROOT / cfg.run.input_index)
    if ticket_ids:
        wanted = set(ticket_ids)
        tickets = [t for t in tickets if t["id"] in wanted]
    if limit is not None:
        tickets = tickets[:limit]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / cfg.run.output_dir / f"{cfg.provider.name}_{cfg.run.prompt_version}_{cfg.run.sampling_profile}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for ticket in tickets:
        user_prompt = render_user_prompt(
            user_template,
            ticket_id=ticket["id"],
            ticket_text=ticket.get("text") or "",
            jira_issue_type=ticket.get("issue_type"),
        )
        result = client.extract(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=TicketExtraction,
            sampling=sampling,
        )
        row = {
            "id": ticket["id"],
            "ok": result.ok,
            "error": result.error,
            "latency_ms": result.latency_ms,
            "model": result.model,
            "prompt_version": cfg.run.prompt_version,
            "sampling_profile": cfg.run.sampling_profile,
            "sampling": sampling.model_dump(),
            "usage": result.usage,
            "raw_text": result.raw_text,
            "extraction": result.data,
        }
        rows.append(row)
        (out_dir / f"{ticket['id']}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        status = "ok" if result.ok else f"FAIL ({result.error})"
        print(f"{ticket['id']}: {status}")

    summary = {
        "created_at": stamp,
        "provider": cfg.provider.model_dump(),
        "prompt_version": cfg.run.prompt_version,
        "sampling_profile": cfg.run.sampling_profile,
        "count": len(rows),
        "ok_count": sum(1 for r in rows if r["ok"]),
        "results": rows,
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {summary_path}")
    return out_dir
