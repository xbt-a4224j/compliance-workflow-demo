from __future__ import annotations

import json

import httpx
import pytest

from compliance_workflow_demo.router import (
    AnthropicAdapter,
    CompletionRequest,
    MockAdapter,
    OpenAIAdapter,
    PermanentError,
    TransientError,
)


def _req() -> CompletionRequest:
    return CompletionRequest(system="you are a strict auditor", user="is 'foo' present?")


class TestMockAdapter:
    @pytest.mark.asyncio
    async def test_default_response(self):
        adapter = MockAdapter()
        resp = await adapter.complete(_req())
        assert resp.provider == "mock"
        assert resp.text.startswith("mock:")
        assert adapter.calls == [_req()]

    @pytest.mark.asyncio
    async def test_raises_configured_exception(self):
        adapter = MockAdapter(raises=TransientError("rate limited"))
        with pytest.raises(TransientError):
            await adapter.complete(_req())

    @pytest.mark.asyncio
    async def test_custom_responder(self):
        from compliance_workflow_demo.router import CompletionResponse

        def responder(req: CompletionRequest) -> CompletionResponse:
            return CompletionResponse(
                text="PASS", input_tokens=1, output_tokens=1, model="x", provider="mock"
            )

        adapter = MockAdapter(responder=responder)
        resp = await adapter.complete(_req())
        assert resp.text == "PASS"


def _anthropic_body(text: str = "ok") -> bytes:
    return json.dumps(
        {
            "id": "msg_x",
            "model": "claude-haiku-4-5-20251001",
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 7, "output_tokens": 2},
        }
    ).encode()


def _openai_body(text: str = "ok") -> bytes:
    return json.dumps(
        {
            "id": "chatcmpl_x",
            "model": "gpt-4o-mini",
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2},
        }
    ).encode()


def _transport(status: int, body: bytes = b"{}") -> httpx.MockTransport:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    return httpx.MockTransport(handler)


class TestAnthropicAdapter:
    @pytest.mark.asyncio
    async def test_happy_path(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        adapter = AnthropicAdapter(transport=_transport(200, _anthropic_body("yes")))
        resp = await adapter.complete(_req())
        assert resp.text == "yes"
        assert resp.input_tokens == 7
        assert resp.output_tokens == 2
        assert resp.provider == "anthropic"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [429, 502, 503, 504, 529, 599])
    async def test_transient_statuses(self, monkeypatch, status):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        adapter = AnthropicAdapter(transport=_transport(status))
        with pytest.raises(TransientError):
            await adapter.complete(_req())

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    async def test_permanent_statuses(self, monkeypatch, status):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        adapter = AnthropicAdapter(transport=_transport(status))
        with pytest.raises(PermanentError):
            await adapter.complete(_req())

    @pytest.mark.asyncio
    async def test_missing_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(PermanentError):
            AnthropicAdapter()

    @pytest.mark.asyncio
    async def test_network_error_is_transient(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        adapter = AnthropicAdapter(transport=httpx.MockTransport(handler))
        with pytest.raises(TransientError):
            await adapter.complete(_req())


class TestOpenAIAdapter:
    @pytest.mark.asyncio
    async def test_happy_path(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        adapter = OpenAIAdapter(transport=_transport(200, _openai_body("yes")))
        resp = await adapter.complete(_req())
        assert resp.text == "yes"
        assert resp.input_tokens == 7
        assert resp.output_tokens == 2
        assert resp.provider == "openai"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [429, 502, 503, 504, 599])
    async def test_transient_statuses(self, monkeypatch, status):
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        adapter = OpenAIAdapter(transport=_transport(status))
        with pytest.raises(TransientError):
            await adapter.complete(_req())

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    async def test_permanent_statuses(self, monkeypatch, status):
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        adapter = OpenAIAdapter(transport=_transport(status))
        with pytest.raises(PermanentError):
            await adapter.complete(_req())

    @pytest.mark.asyncio
    async def test_missing_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(PermanentError):
            OpenAIAdapter()

    @pytest.mark.asyncio
    async def test_network_error_is_transient(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        adapter = OpenAIAdapter(transport=httpx.MockTransport(handler))
        with pytest.raises(TransientError):
            await adapter.complete(_req())
