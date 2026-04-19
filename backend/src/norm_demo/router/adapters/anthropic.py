from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from compliance_workflow_demo.router.types import (
    CompletionRequest,
    CompletionResponse,
    PermanentError,
    TransientError,
)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_BASE_URL = "https://api.anthropic.com/v1"
_ANTHROPIC_VERSION = "2023-06-01"
_TRANSIENT_STATUS = {429, 502, 503, 504, 529}
_PERMANENT_STATUS = {400, 401, 403, 404, 422}


@dataclass
class AnthropicAdapter:
    provider: str = "anthropic"
    model: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL))
    api_key: str | None = None
    base_url: str = _BASE_URL
    timeout_s: float = 30.0
    transport: httpx.AsyncBaseTransport | None = None

    def __post_init__(self) -> None:
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise PermanentError("ANTHROPIC_API_KEY is not set")
        self.api_key = key

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "system": req.system,
            "messages": [{"role": "user", "content": req.user}],
            "temperature": req.temperature,
        }

        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self.transport) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/messages", json=payload, headers=headers
                )
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.RemoteProtocolError,
                httpx.NetworkError,
            ) as e:
                raise TransientError(f"anthropic transport error: {e}") from e

        return _parse_response(resp, fallback_model=self.model)


def _parse_response(resp: httpx.Response, *, fallback_model: str) -> CompletionResponse:
    status = resp.status_code
    if status in _TRANSIENT_STATUS:
        raise TransientError(f"anthropic {status}: {resp.text[:300]}")
    if status in _PERMANENT_STATUS:
        raise PermanentError(f"anthropic {status}: {resp.text[:300]}")
    if status >= 500:
        raise TransientError(f"anthropic {status}: {resp.text[:300]}")
    if status >= 400:
        raise PermanentError(f"anthropic {status}: {resp.text[:300]}")

    data = resp.json()
    text = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    )
    usage = data.get("usage") or {}
    return CompletionResponse(
        text=text,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        model=data.get("model", fallback_model),
        provider="anthropic",
    )
