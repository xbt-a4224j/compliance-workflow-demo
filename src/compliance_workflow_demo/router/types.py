from __future__ import annotations

from collections.abc import Awaitable, Callable
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


@dataclass(frozen=True)
class RouterCallRecord:
    """One LLM attempt as seen by the Router, with enough metadata to
    persist into the `router_calls` table. Retries + failover produce one
    record per underlying `adapter.complete()` invocation."""
    run_id: str | None
    check_id: str | None
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    attempt: int
    cost_usd: float | None = None


# Optional callback Router invokes after each LLM attempt (success or failure).
# Used by the API to collect records for end-of-run persistence.
OnCallHook = Callable[[RouterCallRecord], Awaitable[None]]
