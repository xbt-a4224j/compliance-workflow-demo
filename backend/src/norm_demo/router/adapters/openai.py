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

_DEFAULT_MODEL = "gpt-4o-mini"
_BASE_URL = "https://api.openai.com/v1"
_TRANSIENT_STATUS = {429, 502, 503, 504}
_PERMANENT_STATUS = {400, 401, 403, 404, 422}


@dataclass
class OpenAIAdapter:
    provider: str = "openai"
    model: str = field(default_factory=lambda: os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL))
    api_key: str | None = None
    base_url: str = _BASE_URL
    timeout_s: float = 30.0
    transport: httpx.AsyncBaseTransport | None = None

    def __post_init__(self) -> None:
        key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise PermanentError("OPENAI_API_KEY is not set")
        self.api_key = key

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "temperature": req.temperature,
        }

        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self.transport) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.RemoteProtocolError,
                httpx.NetworkError,
            ) as e:
                raise TransientError(f"openai transport error: {e}") from e

        return _parse_response(resp, fallback_model=self.model)


def _parse_response(resp: httpx.Response, *, fallback_model: str) -> CompletionResponse:
    status = resp.status_code
    if status in _TRANSIENT_STATUS:
        raise TransientError(f"openai {status}: {resp.text[:300]}")
    if status in _PERMANENT_STATUS:
        raise PermanentError(f"openai {status}: {resp.text[:300]}")
    if status >= 500:
        raise TransientError(f"openai {status}: {resp.text[:300]}")
    if status >= 400:
        raise PermanentError(f"openai {status}: {resp.text[:300]}")

    data = resp.json()
    choices = data.get("choices") or []
    text = choices[0]["message"]["content"] if choices else ""
    usage = data.get("usage") or {}
    return CompletionResponse(
        text=text,
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        model=data.get("model", fallback_model),
        provider="openai",
    )
