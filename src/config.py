from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]


class SamplingParams(BaseModel):
    temperature: float = 0.0
    top_p: float = 1.0


class ProviderConfig(BaseModel):
    name: str = "openai"
    model: str = "gpt-4o-mini"
    base_url: Optional[str] = None
    timeout_sec: float = 60
    max_retries: int = 3
    retry_backoff_sec: float = 2


class RunConfig(BaseModel):
    prompt_version: str = "v1"
    sampling_profile: str = "default"
    input_index: str = "data/raw_index.json"
    output_dir: str = "results"


class AppConfig(BaseModel):
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    sampling: Dict[str, SamplingParams] = Field(default_factory=dict)
    run: RunConfig = Field(default_factory=RunConfig)

    def sampling_for(self, profile: Optional[str] = None) -> SamplingParams:
        name = profile or self.run.sampling_profile
        if name not in self.sampling:
            raise KeyError(f"Unknown sampling profile: {name}")
        return self.sampling[name]


def load_config(path: Path | str | None = None) -> AppConfig:
    cfg_path = Path(path) if path else (ROOT / "config.yaml")
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)
