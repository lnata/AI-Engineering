from __future__ import annotations

import json
import os
import time
from typing import Any, TypeVar

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

    def _generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
        sampling: SamplingParams,
    ) -> tuple[str, dict[str, Any], float]:
        started = time.perf_counter()
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
        usage: dict[str, Any] = {}
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            usage = {
                "input_tokens": getattr(meta, "prompt_token_count", None),
                "output_tokens": getattr(meta, "candidates_token_count", None),
                "total_tokens": getattr(meta, "total_token_count", None),
            }
        return response.text or "", usage, latency_ms

    def extract(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
        sampling: SamplingParams,
    ) -> ExtractionResult:
        last_error: str | None = None
        total_latency = 0.0
        total_usage: dict[str, Any] = {}
        last_raw: str | None = None

        def call(prompt: str) -> T:
            nonlocal total_latency, last_raw
            raw_text, usage, latency_ms = self._generate(
                system_prompt=system_prompt,
                user_prompt=prompt,
                schema=schema,
                sampling=sampling,
            )
            total_latency += latency_ms
            for k, v in usage.items():
                if isinstance(v, (int, float)):
                    total_usage[k] = total_usage.get(k, 0) + v
            last_raw = raw_text
            return schema.model_validate_json(raw_text)

        def success(parsed: T) -> ExtractionResult:
            return ExtractionResult(
                ok=True,
                data=parsed.model_dump(mode="json"),
                raw_text=last_raw,
                latency_ms=total_latency,
                model=self.provider.model,
                usage=total_usage,
            )

        for attempt in range(1, self.provider.max_retries + 1):
            try:
                return success(call(user_prompt))
            except (ValidationError, json.JSONDecodeError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                # Exactly one schema-repair attempt with validation feedback (HW requirement)
                try:
                    repair_user = (
                        f"Original request:\n{user_prompt}\n\n"
                        "Your previous JSON failed schema validation.\n"
                        f"Validation errors:\n{exc}\n\n"
                        f"Previous JSON:\n{last_raw}\n\n"
                        "Return a corrected FULL JSON object that matches the schema."
                    )
                    return success(call(repair_user))
                except Exception as repair_exc:  # noqa: BLE001
                    last_error = f"repair failed: {type(repair_exc).__name__}: {repair_exc}"
                break
            except TimeoutError as exc:
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
            raw_text=last_raw,
            error=last_error or "unknown error",
            latency_ms=total_latency or None,
            model=self.provider.model,
            usage=total_usage,
        )
