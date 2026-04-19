from __future__ import annotations

from dataclasses import dataclass, field

from compliance_workflow_demo.router.breaker import CircuitBreaker
from compliance_workflow_demo.router.retry import RetryPolicy
from compliance_workflow_demo.router.types import (
    CompletionRequest,
    CompletionResponse,
    PermanentError,
    ProviderAdapter,
    ProviderUnavailable,
    TransientError,
)


@dataclass
class Router:
    """Outage-resilient LLM router.

    Nesting (CLAUDE.md is emphatic — do not reorder):
        for adapter in self.adapters:        # FAILOVER  (outermost)
            if breaker.allow():              # BREAKER   (middle gate)
                async for attempt in retry:  # RETRY     (innermost)
                    adapter.complete(req)

    Why this order:
      - Retry handles "this call got unlucky, back off and try again." It runs
        against the same provider.
      - Breaker handles "this provider is persistently sick — stop hammering
        it." It short-circuits *before* retry burns more attempts.
      - Failover handles "primary is sick, try the next provider." It runs
        outside the breaker because the whole point is to skip the open one.

    Reverse any pair and the layers cancel each other out.
    """

    adapters: list[ProviderAdapter]
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    breaker_threshold: int = 3
    breaker_cooldown_s: float = 10.0

    _breakers: dict[str, CircuitBreaker] = field(init=False)

    def __post_init__(self) -> None:
        if not self.adapters:
            raise ValueError("Router needs at least one adapter")
        self._breakers = {
            a.provider: CircuitBreaker(
                failure_threshold=self.breaker_threshold,
                cooldown_s=self.breaker_cooldown_s,
                name=a.provider,
            )
            for a in self.adapters
        }

    def breaker_for(self, provider: str) -> CircuitBreaker:
        return self._breakers[provider]

    async def route(self, req: CompletionRequest) -> CompletionResponse:
        last_transient: Exception | None = None

        for adapter in self.adapters:
            breaker = self._breakers[adapter.provider]
            if not await breaker.allow():
                continue

            try:
                async for attempt in self.retry.attempts():
                    with attempt:
                        resp = await adapter.complete(req)
                await breaker.record_success()
                return resp
            except PermanentError:
                # Permanent = bad config / bad request. Don't retry, don't fail
                # over, don't trip the breaker. Bubble up so the caller sees it.
                raise
            except TransientError as e:
                # Retries already exhausted. Count it against this provider's
                # breaker and try the next adapter.
                await breaker.record_failure()
                last_transient = e
                continue

        raise ProviderUnavailable(
            f"all {len(self.adapters)} providers exhausted"
        ) from last_transient
