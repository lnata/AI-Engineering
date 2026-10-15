from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from src.config import SamplingParams

T = TypeVar("T", bound=BaseModel)


@dataclass
class ExtractionResult:
    ok: bool
    data: dict[str, Any] | None
    raw_text: str | None
    error: str | None = None
    latency_ms: float | None = None
    model: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class LLMClient(ABC):
    """Shared interface for provider and local models."""

    name: str

    @abstractmethod
    def extract(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
        sampling: SamplingParams,
    ) -> ExtractionResult:
        raise NotImplementedError
