from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CompletionRequest:
    system: str
    user: str
    max_tokens: int = 1024
    temperature: float = 0.0


@dataclass(frozen=True)
class CompletionResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


class RouterError(Exception):
    """Base class for all router-layer errors."""


class TransientError(RouterError):
    """Retryable: rate limits, overload, timeouts, transient 5xx."""


class PermanentError(RouterError):
    """Non-retryable: auth failures, bad request, schema mismatches."""


class ProviderUnavailable(RouterError):
    """Raised by the router when every provider exhausts its retries/breaker."""


class ProviderAdapter(Protocol):
    provider: str
    model: str

    async def complete(self, req: CompletionRequest) -> CompletionResponse: ...
