from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from reprobox.exceptions import LLMRateLimitExceeded, LLMTransportError
from reprobox.settings import settings

logger = logging.getLogger(__name__)

_last_call_timestamp: float = 0.0


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model

        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.rate_limit_count = 0

    def _parse_duration(self, val: str | None) -> float:
        if not val:
            return 0.0
        val = val.strip()
        try:
            return float(val)
        except ValueError:
            pass

        # Handle durations like 2s, 500ms, 1m
        total = 0.0
        num = ""
        for ch in val:
            if ch.isdigit() or ch == ".":
                num += ch
            elif ch == "s":
                if num:
                    total += float(num)
                    num = ""
            elif ch == "m":
                if num:
                    total += float(num) * 60.0
                    num = ""
            elif ch == "h":
                if num:
                    total += float(num) * 3600.0
                    num = ""
            elif ch == "m" and num:
                total += float(num) * 60.0
                num = ""
        return total

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_retries: int = 8,
        timeout: float = 45.0,
    ) -> LLMResponse:
        global _last_call_timestamp

        # Enforce minimum gap between calls across the process
        min_interval = getattr(settings, "llm_min_interval_s", 0.0) or 0.0
        if min_interval > 0:
            elapsed_since_last = time.monotonic() - _last_call_timestamp
            if elapsed_since_last < min_interval:
                time.sleep(min_interval - elapsed_since_last)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 1500,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        backoff = 2.0
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            _last_call_timestamp = time.monotonic()
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("usage", {})
                    p_tok = usage.get("prompt_tokens", 0)
                    c_tok = usage.get("completion_tokens", 0)

                    self.total_prompt_tokens += p_tok
                    self.total_completion_tokens += c_tok

                    choice = data["choices"][0]
                    msg = choice.get("message", {})
                    content = msg.get("content")

                    parsed_calls: list[ToolCall] = []
                    for tc in msg.get("tool_calls", []):
                        fn = tc.get("function", {})
                        args_raw = fn.get("arguments", "{}")
                        try:
                            args = json.loads(args_raw)
                        except json.JSONDecodeError:
                            args = {"raw": args_raw}
                        parsed_calls.append(
                            ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args)
                        )

                    return LLMResponse(
                        content=content,
                        tool_calls=parsed_calls,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                    )

                if resp.status_code == 429:
                    self.rate_limit_count += 1
                    retry_after = self._parse_duration(resp.headers.get("retry-after"))
                    reset_tokens = self._parse_duration(
                        resp.headers.get("x-ratelimit-reset-tokens")
                    )
                    reset_reqs = self._parse_duration(
                        resp.headers.get("x-ratelimit-reset-requests")
                    )

                    wait_s = max(retry_after, reset_tokens, reset_reqs, backoff)
                    wait_s = min(90.0, max(1.0, wait_s))

                    logger.warning(
                        "Rate limit 429 received (attempt %d/%d). Sleeping %.1fs...",
                        attempt,
                        max_retries,
                        wait_s,
                    )
                    time.sleep(wait_s)
                    backoff = min(90.0, backoff * 2.0)
                    continue

                if resp.status_code >= 500:
                    logger.warning(
                        "LLM server error %d (attempt %d/%d). Backing off %.1fs...",
                        resp.status_code,
                        attempt,
                        max_retries,
                        backoff,
                    )
                    time.sleep(min(90.0, backoff))
                    backoff = min(90.0, backoff * 2.0)
                    continue

                raise LLMTransportError(
                    f"LLM API returned client error {resp.status_code}: {resp.text}"
                )

            except httpx.RequestError as exc:
                last_error = exc
                logger.warning(
                    "HTTP connection error: %s (attempt %d/%d)", exc, attempt, max_retries
                )
                time.sleep(min(90.0, backoff))
                backoff = min(90.0, backoff * 2.0)

        if self.rate_limit_count >= max_retries:
            raise LLMRateLimitExceeded(f"Rate limit retries exhausted after {max_retries} attempts")
        raise LLMTransportError(f"LLM call failed after {max_retries} attempts: {last_error}")
