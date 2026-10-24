from __future__ import annotations


class ReproboxError(Exception):
    """Base exception for reprobox."""


class CommandBlocked(ReproboxError):
    def __init__(self, rule_id: str, reason: str, command: str) -> None:
        self.rule_id = rule_id
        self.reason = reason
        self.command = command
        super().__init__(f"Command blocked by security guard [{rule_id}]: {reason}")


class PolicyUnavailable(ReproboxError):
    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"Policy unavailable on provider {provider}: {reason}")


class LLMRateLimitExceeded(ReproboxError):
    def __init__(self, message: str = "LLM rate limit retries exhausted") -> None:
        super().__init__(message)


class LLMTransportError(ReproboxError):
    def __init__(self, message: str = "LLM transport or connection error") -> None:
        super().__init__(message)
