from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from src.config import ProviderConfig, SamplingParams
from src.llm.gemini_client import GeminiClient


class Ticket(BaseModel):
    summary: str
    priority: int


VALID = '{"summary": "broken report", "priority": 2}'
INVALID = '{"summary": "broken report", "priority": "high"}'


class FakeModels:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def generate_content(self, *, model, contents, config):
        self.prompts.append(contents)
        return SimpleNamespace(text=self.replies.pop(0), usage_metadata=None)


def make_client(replies: list[str]) -> tuple[GeminiClient, FakeModels]:
    client = GeminiClient(ProviderConfig(name="gemini", model="fake", max_retries=3), api_key="test")
    fake = FakeModels(replies)
    client.client = SimpleNamespace(models=fake)
    return client, fake


def run(client: GeminiClient):
    return client.extract(
        system_prompt="sys",
        user_prompt="ORIGINAL TICKET",
        schema=Ticket,
        sampling=SamplingParams(),
    )


def test_valid_first_response():
    client, fake = make_client([VALID])
    result = run(client)
    assert result.ok
    assert result.data == {"summary": "broken report", "priority": 2}
    assert len(fake.prompts) == 1


def test_invalid_then_corrected_with_feedback():
    client, fake = make_client([INVALID, VALID])
    result = run(client)
    assert result.ok
    assert result.data["priority"] == 2
    assert len(fake.prompts) == 2

    repair_prompt = fake.prompts[1]
    assert "ORIGINAL TICKET" in repair_prompt
    assert INVALID in repair_prompt
    assert "priority" in repair_prompt
    assert "Input should be a valid integer" in repair_prompt


def test_invalid_twice_is_final_failure():
    client, fake = make_client([INVALID, INVALID, VALID])
    result = run(client)
    assert not result.ok
    assert result.data is None
    assert result.error.startswith("repair failed: ValidationError")
    assert result.raw_text == INVALID
    # exactly one correction attempt, no blind retries afterwards
    assert len(fake.prompts) == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
