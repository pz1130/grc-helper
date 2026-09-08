import httpx
import pytest

from app.crypto import encrypt
from app.llm.models import LLMProviderConfig, ProviderKind
from app.llm.providers.base import (
    CompletionRequest,
    EmbeddingRequest,
    ProviderError,
)
from app.llm.providers.factory import DEFAULT_BASE_URLS, build_provider
from app.llm.providers.openai_compat import OpenAICompatProvider


def _config(kind: ProviderKind = ProviderKind.OPENAI, base_url: str | None = None):
    return LLMProviderConfig(
        id=1,
        name="p",
        kind=kind,
        model="gpt-4o",
        base_url=base_url,
        api_key_encrypted=encrypt("sk-test"),
    )


def _provider_with(handler) -> OpenAICompatProvider:
    provider = OpenAICompatProvider(_config(base_url="https://example.invalid/v1"))
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return provider


@pytest.mark.asyncio
async def test_complete_parses_openai_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    resp = await _provider_with(handler).complete(
        CompletionRequest(system="s", prompt="p", model="gpt-4o")
    )
    assert resp.text == '{"ok": true}'
    assert resp.tokens_in == 11
    assert resp.tokens_out == 7


@pytest.mark.asyncio
async def test_embed_parses_and_preserves_order():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/embeddings")
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ],
                "usage": {"prompt_tokens": 9},
            },
        )

    resp = await _provider_with(handler).embed(
        EmbeddingRequest(texts=["a", "b"], model="text-embedding-3-large")
    )
    # 服务端可能乱序返回，必须按 index 归位
    assert resp.vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert resp.tokens_in == 9


@pytest.mark.asyncio
async def test_http_429_is_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    with pytest.raises(ProviderError) as exc:
        await _provider_with(handler).complete(
            CompletionRequest(system="s", prompt="p", model="gpt-4o")
        )
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_http_401_is_not_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(ProviderError) as exc:
        await _provider_with(handler).complete(
            CompletionRequest(system="s", prompt="p", model="gpt-4o")
        )
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_error_message_never_leaks_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(ProviderError) as exc:
        await _provider_with(handler).complete(
            CompletionRequest(system="s", prompt="p", model="gpt-4o")
        )
    assert "sk-test" not in str(exc.value)


def test_factory_returns_anthropic_for_anthropic_kind():
    from app.llm.providers.anthropic import AnthropicProvider

    assert isinstance(build_provider(_config(kind=ProviderKind.ANTHROPIC)), AnthropicProvider)


@pytest.mark.parametrize(
    "kind",
    [
        ProviderKind.OPENAI,
        ProviderKind.AZURE_OPENAI,
        ProviderKind.DEEPSEEK,
        ProviderKind.QWEN,
        ProviderKind.OLLAMA,
        ProviderKind.OPENAI_COMPATIBLE,
    ],
)
def test_factory_returns_openai_compat_for_all_compatible_kinds(kind):
    assert isinstance(build_provider(_config(kind=kind)), OpenAICompatProvider)


def test_every_kind_except_custom_has_a_default_base_url():
    for kind in ProviderKind:
        if kind in {ProviderKind.OPENAI_COMPATIBLE, ProviderKind.AZURE_OPENAI}:
            continue  # 这两种必须由用户显式填 base_url
        assert kind in DEFAULT_BASE_URLS
