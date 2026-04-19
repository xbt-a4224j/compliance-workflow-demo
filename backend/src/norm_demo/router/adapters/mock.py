from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from compliance_workflow_demo.router.types import CompletionRequest, CompletionResponse


@dataclass
class MockAdapter:
    """Deterministic adapter for tests and offline development.

    Pass `responder` to return a custom CompletionResponse per request. Pass
    `raises` to throw the same exception on every call. Without either, the
    adapter returns a bland stub.
    """

    provider: str = "mock"
    model: str = "mock-model"
    responder: Callable[[CompletionRequest], CompletionResponse] | None = None
    raises: Exception | None = None
    calls: list[CompletionRequest] = field(default_factory=list)

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        self.calls.append(req)
        if self.raises is not None:
            raise self.raises
        if self.responder is not None:
            return self.responder(req)
        return CompletionResponse(
            text=f"mock:{req.user[:40]}",
            input_tokens=len(req.system.split()) + len(req.user.split()),
            output_tokens=4,
            model=self.model,
            provider=self.provider,
        )
