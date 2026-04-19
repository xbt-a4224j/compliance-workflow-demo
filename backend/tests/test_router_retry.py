from __future__ import annotations

import pytest

from compliance_workflow_demo.router import (
    CompletionRequest,
    CompletionResponse,
    MockAdapter,
    PermanentError,
    RetryPolicy,
    TransientError,
)


def _req() -> CompletionRequest:
    return CompletionRequest(system="s", user="u")


def _resp() -> CompletionResponse:
    return CompletionResponse(
        text="ok", input_tokens=1, output_tokens=1, model="m", provider="mock"
    )


def _fast_policy(max_attempts: int = 3) -> RetryPolicy:
    # Near-zero waits keep the test fast while still exercising the retry loop.
    return RetryPolicy(max_attempts=max_attempts, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0)


@pytest.mark.asyncio
async def test_retries_transient_then_succeeds():
    attempts = {"n": 0}

    def responder(_req):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TransientError("blip")
        return _resp()

    adapter = MockAdapter(responder=responder)
    policy = _fast_policy()

    async for attempt in policy.attempts():
        with attempt:
            result = await adapter.complete(_req())

    assert attempts["n"] == 3
    assert result.text == "ok"


@pytest.mark.asyncio
async def test_permanent_error_short_circuits():
    attempts = {"n": 0}

    def responder(_req):
        attempts["n"] += 1
        raise PermanentError("auth failed")

    adapter = MockAdapter(responder=responder)
    policy = _fast_policy()

    with pytest.raises(PermanentError):
        async for attempt in policy.attempts():
            with attempt:
                await adapter.complete(_req())

    assert attempts["n"] == 1


@pytest.mark.asyncio
async def test_exhausting_attempts_raises_transient():
    attempts = {"n": 0}

    def responder(_req):
        attempts["n"] += 1
        raise TransientError("still down")

    adapter = MockAdapter(responder=responder)
    policy = _fast_policy(max_attempts=4)

    with pytest.raises(TransientError):
        async for attempt in policy.attempts():
            with attempt:
                await adapter.complete(_req())

    assert attempts["n"] == 4
