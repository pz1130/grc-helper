"""覆盖所有 OpenAI 兼容端点的单一实现。

OpenAI / Azure OpenAI / DeepSeek / 通义千问 / Ollama / 任意自建兼容服务，
它们的差别只在 base_url 和模型名。为每家写一个类是重复代码，
且会让"新增一家厂商"变成改代码而不是改配置。
"""

import httpx

from app.crypto import decrypt
from app.llm.models import LLMProviderConfig
from app.llm.providers.base import (
    CompletionRequest,
    CompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ProviderError,
    classify,
)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class OpenAICompatProvider:
    def __init__(self, config: LLMProviderConfig) -> None:
        from app.llm.providers.factory import DEFAULT_BASE_URLS

        self._config = config
        self._api_key = decrypt(config.api_key_encrypted)
        self._base_url = (config.base_url or DEFAULT_BASE_URLS.get(config.kind, "")).rstrip("/")
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            response = await self._client.post(
                f"{self._base_url}{path}", json=payload, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"网络错误: {type(exc).__name__}", retryable=True) from exc

        if response.status_code >= 400:
            # 刻意不回显请求体或请求头——里面有 API key。
            raise ProviderError(
                f"上游返回 {response.status_code}",
                retryable=classify(response.status_code),
            )
        return response.json()

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        body = await self._post(
            "/chat/completions",
            {
                "model": req.model,
                "temperature": req.temperature,
                "max_tokens": req.max_tokens,
                "messages": [
                    {"role": "system", "content": req.system},
                    {"role": "user", "content": req.prompt},
                ],
            },
        )
        usage = body.get("usage", {})
        return CompletionResponse(
            text=body["choices"][0]["message"]["content"] or "",
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
        )

    async def embed(self, req: EmbeddingRequest) -> EmbeddingResponse:
        body = await self._post("/embeddings", {"model": req.model, "input": req.texts})
        # 服务端不保证顺序，按 index 归位
        items = sorted(body["data"], key=lambda item: item["index"])
        return EmbeddingResponse(
            vectors=[item["embedding"] for item in items],
            tokens_in=body.get("usage", {}).get("prompt_tokens", 0),
        )
