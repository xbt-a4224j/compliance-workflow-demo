from __future__ import annotations

import pytest

from compliance_workflow_demo.router import (
    BreakerState,
    CompletionRequest,
    CompletionResponse,
    MockAdapter,
    PermanentError,
    ProviderUnavailable,
    RetryPolicy,
    Router,
    TransientError,
)


def _req() -> CompletionRequest:
    return CompletionRequest(system="s", user="u")


def _resp(provider: str = "primary") -> CompletionResponse:
    return CompletionResponse(
        text=f"hello from {provider}",
        input_tokens=1,
        output_tokens=1,
        model="m",
        provider=provider,
    )


def _fast_retry(max_attempts: int = 2) -> RetryPolicy:
    return RetryPolicy(max_attempts=max_attempts, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0)


@pytest.mark.asyncio
async def test_primary_succeeds_no_failover():
    primary = MockAdapter(provider="primary", responder=lambda _r: _resp("primary"))
    fallback = MockAdapter(provider="fallback", responder=lambda _r: _resp("fallback"))
    router = Router(adapters=[primary, fallback], retry=_fast_retry())

    resp = await router.route(_req())

    assert resp.provider == "primary"
    assert len(primary.calls) == 1
    assert fallback.calls == []


@pytest.mark.asyncio
async def test_failover_when_primary_exhausts_transient():
    primary = MockAdapter(provider="primary", raises=TransientError("rate limit"))
    fallback = MockAdapter(provider="fallback", responder=lambda _r: _resp("fallback"))
    router = Router(adapters=[primary, fallback], retry=_fast_retry(max_attempts=2))

    resp = await router.route(_req())

    assert resp.provider == "fallback"
    assert len(primary.calls) == 2  # retry burned both attempts
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_permanent_error_does_not_failover():
    primary = MockAdapter(provider="primary", raises=PermanentError("auth"))
    fallback = MockAdapter(provider="fallback", responder=lambda _r: _resp("fallback"))
    router = Router(adapters=[primary, fallback], retry=_fast_retry(max_attempts=3))

    with pytest.raises(PermanentError):
        await router.route(_req())

    assert len(primary.calls) == 1  # no retries
    assert fallback.calls == []     # no failover


@pytest.mark.asyncio
async def test_all_providers_transient_raises_provider_unavailable():
    primary = MockAdapter(provider="primary", raises=TransientError("blip"))
    fallback = MockAdapter(provider="fallback", raises=TransientError("blip"))
    router = Router(adapters=[primary, fallback], retry=_fast_retry(max_attempts=2))

    with pytest.raises(ProviderUnavailable):
        await router.route(_req())

    assert len(primary.calls) == 2
    assert len(fallback.calls) == 2


@pytest.mark.asyncio
async def test_breaker_opens_after_repeated_failures_then_skips_provider():
    primary = MockAdapter(provider="primary", raises=TransientError("blip"))
    fallback = MockAdapter(provider="fallback", responder=lambda _r: _resp("fallback"))
    router = Router(
        adapters=[primary, fallback],
        retry=_fast_retry(max_attempts=2),
        breaker_threshold=2,           # trip on 2 consecutive transient exhaustions
        breaker_cooldown_s=999.0,      # don't recover during the test
    )

    # First two routes: primary attempted (and burns retries), fallback succeeds.
    await router.route(_req())
    await router.route(_req())

    # Primary breaker should now be OPEN.
    assert router.breaker_for("primary").state is BreakerState.OPEN

    # Third route: primary skipped entirely; primary call count unchanged.
    primary_calls_before = len(primary.calls)
    resp = await router.route(_req())

    assert resp.provider == "fallback"
    assert len(primary.calls) == primary_calls_before


@pytest.mark.asyncio
async def test_permanent_error_does_not_trip_breaker():
    primary = MockAdapter(provider="primary", raises=PermanentError("auth"))
    fallback = MockAdapter(provider="fallback", responder=lambda _r: _resp("fallback"))
    router = Router(
        adapters=[primary, fallback],
        retry=_fast_retry(),
        breaker_threshold=1,
    )

    for _ in range(3):
        with pytest.raises(PermanentError):
            await router.route(_req())

    # Breaker still CLOSED — permanent errors are not outage signals.
    assert router.breaker_for("primary").state is BreakerState.CLOSED


@pytest.mark.asyncio
async def test_single_adapter_router_works():
    only = MockAdapter(provider="only", responder=lambda _r: _resp("only"))
    router = Router(adapters=[only], retry=_fast_retry())
    resp = await router.route(_req())
    assert resp.provider == "only"


def test_empty_adapters_rejected():
    with pytest.raises(ValueError):
        Router(adapters=[])
