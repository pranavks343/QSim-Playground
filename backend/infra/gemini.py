"""Hardened Gemini client wrapper with key rotation and schema validation."""

from __future__ import annotations

import asyncio
import random
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast

import google.generativeai as genai
import structlog
from pydantic import BaseModel, ValidationError

logger = structlog.get_logger(__name__)

TBaseModel = TypeVar("TBaseModel", bound=BaseModel)
SleepFn = Callable[[float], Awaitable[None]]
ClockFn = Callable[[], float]


GEMINI_BREAKER_THRESHOLD = 10
GEMINI_BREAKER_WINDOW_SECONDS = 60.0
GEMINI_BREAKER_COOLDOWN_SECONDS = 30.0

_breaker_lock = threading.Lock()
_breaker_recent_429s: deque[float] = deque()
_breaker_open_until: float = 0.0


class GeminiQuotaExhausted(RuntimeError):
    """Raised when every configured Gemini key is cooling down."""


class GeminiTransportError(RuntimeError):
    """Raised when the Gemini transport returns a non-retryable error."""


class GeminiCircuitOpen(RuntimeError):
    """Raised when the module-level Gemini circuit breaker is open."""

    def __init__(self, retry_after: float) -> None:
        self.retry_after = max(1.0, retry_after)
        super().__init__(f"Gemini circuit breaker open; retry in ~{int(self.retry_after)}s")


def is_gemini_circuit_open(clock: ClockFn = time.monotonic) -> tuple[bool, float]:
    """Return ``(open, seconds_remaining)`` for the module-level breaker."""

    with _breaker_lock:
        now = clock()
        remaining = _breaker_open_until - now
        return remaining > 0.0, max(0.0, remaining)


def reset_gemini_circuit_breaker() -> None:
    """Clear breaker state. Test helper; do not call from production code."""

    global _breaker_open_until
    with _breaker_lock:
        _breaker_recent_429s.clear()
        _breaker_open_until = 0.0


def _record_gemini_429(clock: ClockFn) -> None:
    """Append a 429 timestamp and open the breaker if the threshold trips."""

    global _breaker_open_until
    with _breaker_lock:
        now = clock()
        _breaker_recent_429s.append(now)
        cutoff = now - GEMINI_BREAKER_WINDOW_SECONDS
        while _breaker_recent_429s and _breaker_recent_429s[0] < cutoff:
            _breaker_recent_429s.popleft()
        if len(_breaker_recent_429s) > GEMINI_BREAKER_THRESHOLD:
            _breaker_open_until = now + GEMINI_BREAKER_COOLDOWN_SECONDS


def _raise_if_circuit_open(clock: ClockFn) -> None:
    open_, remaining = is_gemini_circuit_open(clock)
    if open_:
        raise GeminiCircuitOpen(retry_after=remaining)


@dataclass(frozen=True)
class GeminiResponse:
    """Normalized response data returned by a Gemini transport."""

    text: str
    prompt_token_count: int | None = None
    response_token_count: int | None = None
    model_version: str | None = None


class GeminiTransport(Protocol):
    """Async transport contract used by GeminiClient."""

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
        """Generate content with Gemini."""


class GoogleGenerativeAITransport:
    """Transport backed by the google-generativeai SDK."""

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
        """Generate content using the synchronous SDK in a worker thread."""

        return await asyncio.to_thread(
            self._generate_sync,
            api_key,
            model,
            prompt,
            temperature,
            response_mime_type,
            timeout,
        )

    def _generate_sync(
        self,
        api_key: str,
        model: str,
        prompt: str,
        temperature: float,
        response_mime_type: str | None,
        timeout: float,
    ) -> GeminiResponse:
        genai.configure(api_key=api_key)
        generation_config: dict[str, Any] = {"temperature": temperature}
        if response_mime_type is not None:
            generation_config["response_mime_type"] = response_mime_type

        response = genai.GenerativeModel(model).generate_content(
            prompt,
            generation_config=generation_config,
            request_options={"timeout": timeout},
        )
        usage_metadata = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage_metadata, "prompt_token_count", None)
        response_tokens = getattr(usage_metadata, "candidates_token_count", None)
        return GeminiResponse(
            text=str(getattr(response, "text", "")),
            prompt_token_count=cast("int | None", prompt_tokens),
            response_token_count=cast("int | None", response_tokens),
            model_version=cast("str | None", getattr(response, "model_version", None)),
        )


class GeminiClient:
    """Async Gemini wrapper with round-robin keys, cooldowns, and JSON validation."""

    def __init__(
        self,
        api_keys: list[str],
        model: str = "gemini-2.0-flash",
        default_timeout: float = 10.0,
        transport: GeminiTransport | None = None,
        clock: ClockFn = time.monotonic,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        keys = [key.strip() for key in api_keys if key.strip()]
        if not keys:
            raise ValueError("GeminiClient requires at least one API key")

        self._api_keys = keys
        self._model = model
        self._default_timeout = default_timeout
        self._transport = transport or GoogleGenerativeAITransport()
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._counter = 0
        self._cooldowns: dict[int, float] = {}

    async def generate_json(
        self,
        prompt: str,
        schema: type[TBaseModel],
        temperature: float = 0.2,
    ) -> TBaseModel:
        """Generate JSON content and validate it against a Pydantic model."""

        response = await self._generate(prompt, temperature, response_mime_type="application/json")
        try:
            return schema.model_validate_json(response.text)
        except ValidationError as exc:
            retry_prompt = (
                f"{prompt}\n\nThe previous response failed schema validation:\n{exc}\n"
                "Return only valid JSON matching the schema."
            )
            retry_response = await self._generate(
                retry_prompt,
                temperature,
                response_mime_type="application/json",
            )
            return schema.model_validate_json(retry_response.text)

    async def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        """Generate narrative text content."""

        response = await self._generate(prompt, temperature, response_mime_type=None)
        return response.text

    async def _generate(
        self,
        prompt: str,
        temperature: float,
        response_mime_type: str | None,
    ) -> GeminiResponse:
        _raise_if_circuit_open(self._clock)
        transient_attempts = 0
        while True:
            _raise_if_circuit_open(self._clock)
            key_index, api_key = await self._next_key()
            started_at = self._clock()
            try:
                response = await self._transport.generate(
                    api_key=api_key,
                    model=self._model,
                    prompt=prompt,
                    temperature=temperature,
                    response_mime_type=response_mime_type,
                    timeout=self._default_timeout,
                )
            except Exception as exc:
                latency_ms = round((self._clock() - started_at) * 1000, 3)
                if self._is_quota_error(exc):
                    _record_gemini_429(self._clock)
                    await self._mark_cooling_down(key_index)
                    logger.warning(
                        "gemini_call",
                        key_index=key_index,
                        prompt_token_count=self._estimate_tokens(prompt),
                        response_token_count=None,
                        latency_ms=latency_ms,
                        model_version=self._model,
                        error_type=type(exc).__name__,
                        cooling_down=True,
                    )
                    continue

                if self._is_transient_error(exc) and transient_attempts < 3:
                    delay = (2**transient_attempts) + random.uniform(0, 0.25)
                    transient_attempts += 1
                    logger.warning(
                        "gemini_call",
                        key_index=key_index,
                        prompt_token_count=self._estimate_tokens(prompt),
                        response_token_count=None,
                        latency_ms=latency_ms,
                        model_version=self._model,
                        error_type=type(exc).__name__,
                        retry_in_seconds=round(delay, 3),
                    )
                    await self._sleep(delay)
                    continue

                logger.error(
                    "gemini_call",
                    key_index=key_index,
                    prompt_token_count=self._estimate_tokens(prompt),
                    response_token_count=None,
                    latency_ms=latency_ms,
                    model_version=self._model,
                    error_type=type(exc).__name__,
                )
                raise GeminiTransportError(str(exc)) from exc

            latency_ms = round((self._clock() - started_at) * 1000, 3)
            logger.info(
                "gemini_call",
                key_index=key_index,
                prompt_token_count=response.prompt_token_count or self._estimate_tokens(prompt),
                response_token_count=response.response_token_count,
                latency_ms=latency_ms,
                model_version=response.model_version or self._model,
            )
            return response

    async def _next_key(self) -> tuple[int, str]:
        async with self._lock:
            now = self._clock()
            available_indices = [
                index
                for index in range(len(self._api_keys))
                if self._cooldowns.get(index, 0.0) <= now
            ]
            if not available_indices:
                raise GeminiQuotaExhausted("all Gemini API keys are cooling down")

            for _ in range(len(self._api_keys)):
                key_index = self._counter % len(self._api_keys)
                self._counter += 1
                if key_index in available_indices:
                    return key_index, self._api_keys[key_index]

            key_index = available_indices[0]
            self._counter = key_index + 1
            return key_index, self._api_keys[key_index]

    async def _mark_cooling_down(self, key_index: int) -> None:
        async with self._lock:
            self._cooldowns[key_index] = self._clock() + 60.0

    @staticmethod
    def _estimate_tokens(prompt: str) -> int:
        return max(1, len(prompt.split()))

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        return code if isinstance(code, int) else None

    @classmethod
    def _is_quota_error(cls, exc: Exception) -> bool:
        status_code = cls._status_code(exc)
        message = str(exc).lower()
        return status_code == 429 or "quota" in message or "rate limit" in message

    @classmethod
    def _is_transient_error(cls, exc: Exception) -> bool:
        status_code = cls._status_code(exc)
        if status_code in {500, 502, 503, 504}:
            return True
        if isinstance(exc, TimeoutError | ConnectionError | OSError):
            return True
        message = str(exc).lower()
        return any(token in message for token in ("timeout", "temporarily", "unavailable"))
