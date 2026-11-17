"""Shared cloud LLM runtime helpers: .env model resolution, 429/5xx backoff, and disk cache."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, TypeVar

from dotenv import load_dotenv

from src.config import ROOT, load_config

T = TypeVar("T")
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_CACHE_DIR = ROOT / ".cache" / "hw2_llm"

_RETRY_IN_SEC_RE = re.compile(
    r"(?:retry\s+in\s+|retrydelay['\"\s:=]+)(\d+(?:\.\d+)?)\s*s",
    re.IGNORECASE,
)


def resolve_cloud_provider(requested: str = "auto", require_cloud: bool = False) -> str:
    """Resolve cloud provider ('gemini'|'openai'|'openrouter') or 'extractive'/'rubric'."""
    load_dotenv(ROOT / ".env")
    if requested not in ("auto", "cloud"):
        return requested
    if (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip():
        return "gemini"
    if (os.getenv("OPENAI_API_KEY") or "").strip():
        return "openai"
    if (os.getenv("OPENROUTER_API_KEY") or "").strip():
        return "openrouter"
    if require_cloud or requested == "cloud":
        raise RuntimeError(
            "Cloud LLM key missing! Set GEMINI_API_KEY (or OPENAI_API_KEY / OPENROUTER_API_KEY) in .env"
        )
    return "auto"


def resolve_gemini_model(explicit_model: str | None = None, env_var: str = "HW2_RAG_MODEL") -> str:
    """Honor explicit model -> HW2_*_MODEL -> GEMINI_MODEL -> config.yaml model."""
    load_dotenv(ROOT / ".env")
    for candidate in (
        explicit_model,
        os.getenv(env_var),
        os.getenv("GEMINI_MODEL"),
    ):
        if candidate and candidate.strip():
            return candidate.strip()
    try:
        cfg = load_config()
        if cfg.provider.name == "gemini" and cfg.provider.model:
            return cfg.provider.model
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_GEMINI_MODEL


def parse_retry_after_seconds(message: str) -> float | None:
    """Parse server-suggested retry delay from Gemini / OpenAI error payloads."""
    m = _RETRY_IN_SEC_RE.search(message or "")
    return float(m.group(1)) if m else None


def is_retryable_llm_error(exc: BaseException) -> tuple[bool, bool]:
    """Return (is_retryable, is_rate_limit_429)."""
    if isinstance(exc, TimeoutError):
        return True, False
    cls_name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if any(code in msg for code in ("401", "403", "invalid api key", "api_key_invalid")):
        return False, False
    is_429 = (
        "ratelimit" in cls_name
        or "429" in msg
        or "resource_exhausted" in msg
        or "resource exhausted" in msg
        or "too many requests" in msg
        or "quota" in msg
    )
    if is_429:
        return True, True
    is_transient = any(
        tok in msg or tok in cls_name
        for tok in ("500", "502", "503", "504", "unavailable", "overloaded", "timeout", "connection")
    )
    return is_transient, False


def call_with_llm_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = 6,
    base_backoff_sec: float = 3.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    """Execute a cloud LLM call with exponential backoff and 429 retry-after cooldown."""
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            retryable, is_429 = is_retryable_llm_error(exc)
            if not retryable or attempt >= max_attempts:
                raise
            parsed_wait = parse_retry_after_seconds(str(exc))
            if is_429:
                delay = max(
                    (parsed_wait + 1.5) if parsed_wait is not None else 0.0,
                    20.0 * attempt,
                    base_backoff_sec * attempt,
                )
            else:
                delay = max(
                    parsed_wait or 0.0,
                    base_backoff_sec * (2 ** (attempt - 1)),
                )
            sleep_fn(delay)
    assert last_exc is not None
    raise last_exc


class LLMDiskCache:
    """Untracked SHA-256 disk cache (.cache/hw2_llm/) for resumable cloud LLM runs."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR, enabled: bool | None = None) -> None:
        self.cache_dir = cache_dir
        env_flag = os.getenv("HW2_LLM_CACHE", "1").strip().lower()
        self.enabled = (env_flag not in {"0", "false", "no"}) if enabled is None else enabled

    def _path_for(self, namespace: str, model: str, system_prompt: str, user_prompt: str) -> Path:
        raw_key = json.dumps([namespace, model, system_prompt, user_prompt], ensure_ascii=False)
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get(self, namespace: str, model: str, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        p = self._path_for(namespace, model, system_prompt, user_prompt)
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def put(self, namespace: str, model: str, system_prompt: str, user_prompt: str, value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        p = self._path_for(namespace, model, system_prompt, user_prompt)
        p.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
