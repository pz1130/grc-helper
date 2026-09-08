"""llm 编排层——系统唯一的出网口（spec §4.4 铁律 1）。

顺序固定：路由 → 预算 → 脱敏 → 调用（重试+降级）→ 还原 → 提取 →
Schema 校验（纠错重试）→ 引用校验 → 留痕 → 返回纯数据。

返回值是纯数据（铁律 2）：本模块绝不写任何业务表。
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import budget, routing
from app.llm.models import LLMCall, LLMProviderConfig, RulesetName
from app.llm.pricing import estimate_cost
from app.llm.providers.base import (
    CompletionRequest,
    CompletionResponse,
    EmbeddingRequest,
    ProviderError,
)
from app.llm.providers.factory import build_provider
from app.llm.redaction import load_engine
from app.llm.validation import (
    CitationValidator,
    NullCitationValidator,
    ValidationFailure,
    correction_prompt,
    extract_json,
    validate,
)

MAX_CORRECTION_RETRIES = 2
MAX_PROVIDER_ATTEMPTS = 3
EMBEDDING_TASK_KEY = "embedding"


@dataclass(frozen=True)
class ValidatedResult:
    payload: dict[str, Any]
    confidence: float | None
    llm_call_id: int


async def _sleep(seconds: float) -> None:
    # 单独提出来是为了让测试能 patch 掉退避等待
    await asyncio.sleep(seconds)


async def _call_with_retry(
    session: AsyncSession,
    config: LLMProviderConfig,
    request: CompletionRequest,
) -> tuple[CompletionResponse, LLMProviderConfig]:
    """指数退避重试；耗尽后降级到备用 provider（spec §9）。"""
    last: ProviderError | None = None

    for candidate in (config, await routing.fallback_provider(session)):
        if candidate is None or (last is not None and candidate.id == config.id):
            continue
        provider = build_provider(candidate)
        req = request if candidate.id == config.id else CompletionRequest(
            system=request.system,
            prompt=request.prompt,
            model=candidate.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        for attempt in range(MAX_PROVIDER_ATTEMPTS):
            try:
                return await provider.complete(req), candidate
            except ProviderError as exc:
                last = exc
                if not exc.retryable:
                    break
                if attempt < MAX_PROVIDER_ATTEMPTS - 1:
                    await _sleep(2**attempt)

    raise last or ProviderError("没有可用的 provider", retryable=False)


async def run(
    session: AsyncSession,
    *,
    task_key: str,
    system: str,
    prompt: str,
    schema: dict[str, Any],
    ruleset: RulesetName = RulesetName.GENERATION,
    interactive: bool = False,
    citation_validator: CitationValidator | None = None,
) -> ValidatedResult:
    config, route = await routing.resolve(session, task_key)
    await budget.check(session, interactive=interactive, provider=config)

    engine = await load_engine(session, ruleset)
    # 必须一次喂进去：分两次 redact 会让两边的编号各自从 1 开始，
    # 合并映射表时键相撞，还原出来是另一个实体。
    batch = engine.redact_many([system, prompt])
    redacted_system_text, redacted_prompt_text = batch.texts
    mapping = batch.mapping

    prompt_hash = hashlib.sha256(redacted_prompt_text.encode()).hexdigest()
    started = time.perf_counter()
    current_prompt = redacted_prompt_text
    used_config = config
    tokens_in = tokens_out = 0
    error_text: str | None = None

    try:
        for attempt in range(MAX_CORRECTION_RETRIES + 1):
            response, used_config = await _call_with_retry(
                session,
                config,
                CompletionRequest(
                    system=redacted_system_text,
                    prompt=current_prompt,
                    model=config.model,
                    temperature=route.temperature,
                    max_tokens=route.max_tokens,
                ),
            )
            tokens_in += response.tokens_in
            tokens_out += response.tokens_out

            restored = engine.restore(response.text, mapping)
            try:
                payload = validate(extract_json(restored), schema)
            except ValidationFailure as failure:
                if attempt == MAX_CORRECTION_RETRIES:
                    error_text = f"schema: {failure.reason}"
                    raise
                current_prompt = correction_prompt(response.text, failure.reason)
                continue

            reason = await (citation_validator or NullCitationValidator()).check(payload)
            if reason is not None:
                error_text = f"citation: {reason}"
                raise ValidationFailure(reason)

            confidence = payload.get("confidence")
            break
    except ProviderError as exc:
        error_text = str(exc)
        raise
    finally:
        call = LLMCall(
            provider_config_id=used_config.id,
            model=used_config.model,
            task_key=task_key,
            prompt_hash=prompt_hash,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=estimate_cost(used_config.model, tokens_in, tokens_out),
            latency_ms=int((time.perf_counter() - started) * 1000),
            ruleset=ruleset,
            redaction_applied=bool(mapping),
            redaction_hits=batch.hits or None,
            status="error" if error_text else "ok",
            error=error_text,
        )
        session.add(call)
        await session.flush()

    return ValidatedResult(
        payload=payload,
        confidence=float(confidence) if isinstance(confidence, int | float) else None,
        llm_call_id=call.id,
    )


async def embed(session: AsyncSession, *, texts: list[str]) -> tuple[list[list[float]], int]:
    """embedding 走同一套路由与留痕，但用 embedding 规则集（宽松，保留业务术语）。"""
    config, _ = await routing.resolve(session, EMBEDDING_TASK_KEY)
    await budget.check(session, interactive=False, provider=config)

    engine = await load_engine(session, RulesetName.EMBEDDING)
    # 所有 chunk 共享一套编号：同一实体在不同 chunk 里代号一致，向量更稳。
    batch = engine.redact_many(texts)

    started = time.perf_counter()
    prompt_hash = hashlib.sha256("".join(batch.texts).encode()).hexdigest()
    tokens_in = 0
    error_text: str | None = None

    try:
        response = await build_provider(config).embed(
            EmbeddingRequest(texts=batch.texts, model=config.model)
        )
        tokens_in = response.tokens_in
    except ProviderError as exc:
        # 失败也要留痕，否则合规证据缺一半（spec §8.2）。
        error_text = str(exc)
        raise
    finally:
        session.add(
            LLMCall(
                provider_config_id=config.id,
                model=config.model,
                task_key=EMBEDDING_TASK_KEY,
                prompt_hash=prompt_hash,
                tokens_in=tokens_in,
                tokens_out=0,
                cost=estimate_cost(config.model, tokens_in, 0),
                latency_ms=int((time.perf_counter() - started) * 1000),
                ruleset=RulesetName.EMBEDDING,
                redaction_applied=bool(batch.mapping),
                redaction_hits=batch.hits or None,
                status="error" if error_text else "ok",
                error=error_text,
            )
        )
        await session.flush()

    return response.vectors, response.tokens_in
