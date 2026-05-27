from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from infra.gemini import GeminiClient, GeminiQuotaExhausted, GeminiResponse


class SimpleSchema(BaseModel):
    value: int


@dataclass(frozen=True)
class FakeHTTPError(Exception):
    status_code: int

    def __str__(self) -> str:
        return f"HTTP {self.status_code}"


class FakeTransport:
    def __init__(self, responses: list[GeminiResponse | Exception]) -> None:
        self._responses = responses
        self.api_keys: list[str] = []
        self.prompts: list[str] = []
        self.response_mime_types: list[str | None] = []

    async def generate(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        temperature: float,
        response_mime_type: str | None,
        timeout: float,
    ) -> GeminiResponse:
        del model, temperature, timeout
        self.api_keys.append(api_key)
        self.prompts.append(prompt)
        self.response_mime_types.append(response_mime_type)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


async def no_sleep(delay: float) -> None:
    del delay


@pytest.mark.asyncio
async def test_round_robin_uses_keys_in_order() -> None:
    transport = FakeTransport(
        [
            GeminiResponse(text="one"),
            GeminiResponse(text="two"),
            GeminiResponse(text="three"),
        ]
    )
    client = GeminiClient(["key-0", "key-1"], transport=transport, sleep=no_sleep)

    assert await client.generate_text("prompt 1") == "one"
    assert await client.generate_text("prompt 2") == "two"
    assert await client.generate_text("prompt 3") == "three"

    assert transport.api_keys == ["key-0", "key-1", "key-0"]


@pytest.mark.asyncio
async def test_cooldown_after_429_skips_failed_key() -> None:
    transport = FakeTransport(
        [
            FakeHTTPError(status_code=429),
            GeminiResponse(text="ok"),
        ]
    )
    client = GeminiClient(["key-0", "key-1"], transport=transport, sleep=no_sleep)

    assert await client.generate_text("prompt") == "ok"
    assert transport.api_keys == ["key-0", "key-1"]


@pytest.mark.asyncio
async def test_schema_validation_failure_triggers_one_retry_with_error_context() -> None:
    transport = FakeTransport(
        [
            GeminiResponse(text='{"value": "not-an-int"}'),
            GeminiResponse(text='{"value": 7}'),
        ]
    )
    client = GeminiClient(["key-0"], transport=transport, sleep=no_sleep)

    result = await client.generate_json("return a value", SimpleSchema)

    assert result == SimpleSchema(value=7)
    assert len(transport.prompts) == 2
    assert "failed schema validation" in transport.prompts[1]
    assert transport.response_mime_types == ["application/json", "application/json"]


@pytest.mark.asyncio
async def test_all_keys_exhausted_raises_immediately() -> None:
    transport = FakeTransport(
        [
            FakeHTTPError(status_code=429),
            FakeHTTPError(status_code=429),
        ]
    )
    client = GeminiClient(["key-0", "key-1"], transport=transport, sleep=no_sleep)

    with pytest.raises(GeminiQuotaExhausted, match="cooling down"):
        await client.generate_text("prompt")

    assert transport.api_keys == ["key-0", "key-1"]
