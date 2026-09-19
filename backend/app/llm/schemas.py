from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm.models import ProviderKind, RulesetName


class ProviderCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: ProviderKind
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(min_length=1)
    base_url: str | None = None
    is_fallback: bool = False
    monthly_budget: float | None = None


class ProviderUpdateIn(BaseModel):
    name: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    enabled: bool | None = None
    is_fallback: bool | None = None
    monthly_budget: float | None = None


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: ProviderKind
    model: str
    base_url: str | None
    enabled: bool
    is_fallback: bool
    monthly_budget: float | None
    api_key_masked: str


class RoutingIn(BaseModel):
    task_key: str = Field(min_length=1, max_length=64)
    provider_config_id: int
    temperature: float = 0.0
    max_tokens: int = 4096


class BulkRoutingIn(BaseModel):
    """把一个 provider 绑到某 capability 下所有已实现的任务上。

    capability 必须显式传：一次调用只绑一类，绝不让聊天模型顺手把 embedding
    也绑走（见 app/llm/tasks.py 的说明）。
    """

    provider_config_id: int
    capability: Literal["chat", "embedding"]
    temperature: float = 0.0
    max_tokens: int = 4096


class TaskSpecOut(BaseModel):
    key: str
    capability: str
    implemented: bool


class RoutingOut(RoutingIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class RedactionRuleIn(BaseModel):
    ruleset: RulesetName
    pattern_type: str = Field(pattern="^(regex|dictionary)$")
    pattern: str = Field(min_length=1)
    replacement_prefix: str = Field(min_length=1, max_length=32)
    enabled: bool = True
    order_index: int = 100
    note: str | None = None


class RedactionRuleOut(RedactionRuleIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class PreviewIn(BaseModel):
    ruleset: RulesetName
    text: str


class PreviewOut(BaseModel):
    redacted: str
    hits: dict[str, int]


class ThresholdsIn(BaseModel):
    auto_accept_threshold: float = Field(ge=0.0, le=1.0)
    force_manual_threshold: float = Field(ge=0.0, le=1.0)
    review_sample_rate: float = Field(ge=0.0, le=1.0)
    monthly_budget_usd: float = Field(ge=0.0)


class ThresholdsOut(ThresholdsIn):
    pass
