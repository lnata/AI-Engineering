from __future__ import annotations

import json
import os
import time
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from src.config import ProviderConfig, SamplingParams
from src.llm.base import ExtractionResult, LLMClient

T = TypeVar("T", bound=BaseModel)


class GeminiClient(LLMClient):
    name = "gemini"

    def __init__(self, provider: ProviderConfig, api_key: str | None = None):
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is missing. Put it in .env")
        self.provider = provider
        self.client = genai.Client(api_key=key)

    def extract(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
        sampling: SamplingParams,
    ) -> ExtractionResult:
        last_error: str | None = None
        for attempt in range(1, self.provider.max_retries + 1):
            started = time.perf_counter()
            try:
                response = self.client.models.generate_content(
                    model=self.provider.model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=sampling.temperature,
                        top_p=sampling.top_p,
                        response_mime_type="application/json",
                        response_json_schema=schema.model_json_schema(),
                    ),
                )
                latency_ms = (time.perf_counter() - started) * 1000
                raw_text = response.text or ""
                parsed = schema.model_validate_json(raw_text)

                usage = {}
                meta = getattr(response, "usage_metadata", None)
                if meta is not None:
                    usage = {
                        "input_tokens": getattr(meta, "prompt_token_count", None),
                        "output_tokens": getattr(meta, "candidates_token_count", None),
                        "total_tokens": getattr(meta, "total_token_count", None),
                    }

                return ExtractionResult(
                    ok=True,
                    data=parsed.model_dump(mode="json"),
                    raw_text=raw_text,
                    latency_ms=latency_ms,
                    model=self.provider.model,
                    usage=usage,
                )
            except (ValidationError, json.JSONDecodeError, TimeoutError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.provider.max_retries:
                    time.sleep(self.provider.retry_backoff_sec * attempt)
                    continue
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                msg = str(exc).lower()
                retryable = any(
                    token in msg
                    for token in ("429", "resource exhausted", "quota", "timeout", "unavailable")
                )
                if retryable and attempt < self.provider.max_retries:
                    # Rate limits need longer cooldown than generic retries
                    delay = self.provider.retry_backoff_sec * attempt
                    if "429" in msg or "resource exhausted" in msg:
                        delay = max(delay, 20 * attempt)
                    time.sleep(delay)
                    continue
                break

        return ExtractionResult(
            ok=False,
            data=None,
            raw_text=None,
            error=last_error or "unknown error",
            model=self.provider.model,
        )
