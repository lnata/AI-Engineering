from __future__ import annotations

import json
import os
import time
from typing import TypeVar

from openai import APITimeoutError, OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from src.config import ProviderConfig, SamplingParams
from src.llm.base import ExtractionResult, LLMClient

T = TypeVar("T", bound=BaseModel)


class OpenAIClient(LLMClient):
    name = "openai"

    def __init__(self, provider: ProviderConfig, api_key: str | None = None):
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is missing. Put it in .env")
        self.provider = provider
        self.client = OpenAI(api_key=key, timeout=provider.timeout_sec)

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
                completion = self.client.chat.completions.parse(
                    model=self.provider.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format=schema,
                    temperature=sampling.temperature,
                    top_p=sampling.top_p,
                )
                latency_ms = (time.perf_counter() - started) * 1000
                message = completion.choices[0].message
                parsed = message.parsed
                raw_text = message.content
                if parsed is None:
                    if message.refusal:
                        raise ValidationError.from_exception_data(
                            "TicketExtraction",
                            [
                                {
                                    "type": "value_error",
                                    "loc": ("refusal",),
                                    "input": message.refusal,
                                    "ctx": {"error": message.refusal},
                                }
                            ],
                        )
                    parsed = schema.model_validate_json(raw_text or "{}")

                usage = {}
                if completion.usage:
                    usage = {
                        "input_tokens": completion.usage.prompt_tokens,
                        "output_tokens": completion.usage.completion_tokens,
                        "total_tokens": completion.usage.total_tokens,
                    }
                return ExtractionResult(
                    ok=True,
                    data=parsed.model_dump(mode="json"),
                    raw_text=raw_text,
                    latency_ms=latency_ms,
                    model=self.provider.model,
                    usage=usage,
                )
            except (APITimeoutError, RateLimitError, ValidationError, json.JSONDecodeError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.provider.max_retries:
                    time.sleep(self.provider.retry_backoff_sec * attempt)
                    continue
            except Exception as exc:  # noqa: BLE001 — surface into results JSON
                last_error = f"{type(exc).__name__}: {exc}"
                break

        return ExtractionResult(
            ok=False,
            data=None,
            raw_text=None,
            error=last_error or "unknown error",
            model=self.provider.model,
        )
