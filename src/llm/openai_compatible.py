from __future__ import annotations

import json
import time
from typing import Any, Optional, TypeVar

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from src.config import ProviderConfig, SamplingParams
from src.llm.base import ExtractionResult, LLMClient

T = TypeVar("T", bound=BaseModel)


def _extract_json_text(raw_text: str) -> str:
    """Pull a JSON object out of prose / markdown fences from local models."""
    cleaned = (raw_text or "").strip()
    if not cleaned:
        raise json.JSONDecodeError("empty response", cleaned, 0)

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # drop first fence line and optional trailing fence
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        if lines and lines[0].strip().lower() in {"json", "jsonc"}:
            lines = lines[1:]
        cleaned = "\n".join(lines).strip()

    # If model added commentary, keep the outermost {...}
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return cleaned


def _normalize_null_strings(value: Any) -> Any:
    """Local models often emit the string 'null' instead of JSON null."""
    if isinstance(value, dict):
        return {k: _normalize_null_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_null_strings(v) for v in value]
    if isinstance(value, str) and value.strip().lower() in {"null", "none", "n/a"}:
        return None
    return value


def _parse_schema(schema: type[T], raw_text: str) -> T:
    cleaned = _extract_json_text(raw_text)
    data = json.loads(cleaned)
    return schema.model_validate(_normalize_null_strings(data))


class OpenAICompatibleClient(LLMClient):
    """Local OpenAI-compatible servers: Ollama, LM Studio, etc."""

    def __init__(
        self,
        provider: ProviderConfig,
        *,
        name: str,
        base_url: str,
        api_key: str = "local",
        json_response_format: bool = True,
    ):
        self.name = name
        self.provider = provider
        self.json_response_format = json_response_format
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=provider.timeout_sec,
        )

    def _chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        sampling: SamplingParams,
    ) -> tuple[str, dict[str, Any], float]:
        started = time.perf_counter()
        kwargs: dict[str, Any] = {
            "model": self.provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": sampling.temperature,
            "top_p": sampling.top_p,
            "max_tokens": 2500,
        }
        # Ollama accepts json_object; LM Studio wants json_schema or plain text
        if self.json_response_format:
            kwargs["response_format"] = {"type": "json_object"}
        completion = self.client.chat.completions.create(**kwargs)
        latency_ms = (time.perf_counter() - started) * 1000
        message = completion.choices[0].message
        raw_text = message.content or ""
        if not raw_text.strip():
            # Some LM Studio builds put text in non-standard fields
            raw_text = getattr(message, "reasoning_content", None) or ""
            if not raw_text and hasattr(message, "model_extra") and message.model_extra:
                raw_text = str(
                    message.model_extra.get("reasoning_content")
                    or message.model_extra.get("content")
                    or ""
                )
        usage: dict[str, Any] = {}
        if completion.usage:
            usage = {
                "input_tokens": completion.usage.prompt_tokens,
                "output_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
            }
        return raw_text, usage, latency_ms

    def extract(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
        sampling: SamplingParams,
    ) -> ExtractionResult:
        # Full JSON Schema is huge and makes small local models hang.
        # Send a compact contract instead; Pydantic still validates the result.
        compact_contract = (
            "Return ONLY one JSON object with these keys:\n"
            "ticket_type (bug|change_request),\n"
            "summary (string),\n"
            "priority (low|medium|high|critical),\n"
            "issue_category (data_mismatch|spec_mismatch|refresh_failure|"
            "transform_logic|filter_rls|performance|enhancement|other),\n"
            "report: {name, deploy_stage(dev|prod|both|unknown), dataset_name},\n"
            "sap_fiori: {app_name, transaction_or_cds},\n"
            "specification: {spec_id, version, title},\n"
            "ownership: {report_developer, financial_analyst, data_pull_owner, "
            "primary_assignee_role(report_developer|financial_analyst|data_pull|unknown)},\n"
            "reconciliation: {compare_sap_vs_databricks(bool), "
            "compare_databricks_vs_power_bi(bool), compare_report_vs_spec(bool), "
            "mismatch_suspected_at(sap_fiori|databricks|power_bi_report|"
            "specification|unknown), notes},\n"
            "deployment: {status(not_started|in_development|deployed_to_dev|"
            "pending_approval|approved_for_prod|deployed_to_prod|unknown), "
            "requires_dev_deploy_first(bool), awaiting_approval(bool), "
            "approved_for_prod(bool|null), approver_role, deployed_to_dev(bool|null), "
            "deployed_to_prod(bool|null), notes},\n"
            "repro_steps (array of strings), labels (array), is_blocker (bool), "
            "confidence_notes.\n"
            "Use null for unknown optional strings. Never emit the string 'null'."
        )
        guided_user = f"{user_prompt}\n\n{compact_contract}"

        last_error: str | None = None
        total_latency = 0.0
        total_usage: dict[str, Any] = {}
        last_raw: str | None = None

        for attempt in range(1, self.provider.max_retries + 1):
            try:
                raw_text, usage, latency_ms = self._chat(
                    system_prompt=system_prompt,
                    user_prompt=guided_user,
                    sampling=sampling,
                )
                total_latency += latency_ms
                for k, v in usage.items():
                    if isinstance(v, (int, float)):
                        total_usage[k] = total_usage.get(k, 0) + v
                last_raw = raw_text
                parsed = _parse_schema(schema, raw_text)
                return ExtractionResult(
                    ok=True,
                    data=parsed.model_dump(mode="json"),
                    raw_text=raw_text,
                    latency_ms=total_latency,
                    model=self.provider.model,
                    usage=total_usage,
                )
            except (ValidationError, json.JSONDecodeError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                # One schema-repair attempt (HW requirement)
                try:
                    repair_user = (
                        "Your previous JSON failed schema validation.\n"
                        f"Validation errors:\n{exc}\n\n"
                        f"Previous JSON:\n{last_raw}\n\n"
                        "Return a corrected FULL JSON object. "
                        f"{compact_contract}"
                    )
                    raw_text, usage, latency_ms = self._chat(
                        system_prompt=system_prompt,
                        user_prompt=repair_user,
                        sampling=sampling,
                    )
                    total_latency += latency_ms
                    for k, v in usage.items():
                        if isinstance(v, (int, float)):
                            total_usage[k] = total_usage.get(k, 0) + v
                    last_raw = raw_text
                    parsed = _parse_schema(schema, raw_text)
                    return ExtractionResult(
                        ok=True,
                        data=parsed.model_dump(mode="json"),
                        raw_text=raw_text,
                        latency_ms=total_latency,
                        model=self.provider.model,
                        usage=total_usage,
                    )
                except Exception as repair_exc:  # noqa: BLE001
                    last_error = f"repair failed: {type(repair_exc).__name__}: {repair_exc}"
                    if attempt < self.provider.max_retries:
                        time.sleep(self.provider.retry_backoff_sec * attempt)
                        continue
            except (APITimeoutError, APIConnectionError, RateLimitError, json.JSONDecodeError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.provider.max_retries:
                    time.sleep(self.provider.retry_backoff_sec * attempt)
                    continue
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
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


class OllamaClient(OpenAICompatibleClient):
    def __init__(self, provider: ProviderConfig, base_url: Optional[str] = None):
        super().__init__(
            provider,
            name="ollama",
            base_url=base_url or "http://localhost:11434/v1",
            api_key="ollama",
            json_response_format=True,
        )


class LMStudioClient(OpenAICompatibleClient):
    def __init__(self, provider: ProviderConfig, base_url: Optional[str] = None):
        super().__init__(
            provider,
            name="lmstudio",
            base_url=base_url or "http://localhost:1234/v1",
            api_key="lmstudio",
            json_response_format=False,
        )
