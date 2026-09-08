"""可逆脱敏管道（spec §6.2）。

占位符格式 [[PREFIX_N]]。方括号定界让 restore 可以做朴素字符串替换而不会
出现 IP_1 污染 IP_10 的前缀冲突。
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.models import RedactionRule, RulesetName


@dataclass(frozen=True)
class RedactionResult:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)  # 占位符 → 原文
    hits: dict[str, int] = field(default_factory=dict)     # 前缀 → 不同实体数


class RedactionEngine:
    def __init__(self, rules: list[RedactionRule]) -> None:
        self._rules = sorted(
            (r for r in rules if r.enabled), key=lambda r: (r.order_index, r.id or 0)
        )

    def _compile(self, rule: RedactionRule) -> re.Pattern[str] | None:
        if rule.pattern_type == "regex":
            return re.compile(rule.pattern)
        if rule.pattern_type == "dictionary":
            terms = [t.strip() for t in rule.pattern.splitlines() if t.strip()]
            if not terms:
                return None
            # 长词优先，避免"开发银行"抢在"新开发银行"前面命中
            terms.sort(key=len, reverse=True)
            return re.compile("|".join(re.escape(t) for t in terms))
        raise ValueError(f"未知的 pattern_type: {rule.pattern_type}")

    def redact(self, text: str) -> RedactionResult:
        mapping: dict[str, str] = {}
        reverse: dict[str, str] = {}   # 原文 → 占位符，保证同值同代号
        counters: Counter[str] = Counter()

        for rule in self._rules:
            pattern = self._compile(rule)
            if pattern is None:
                continue
            prefix = rule.replacement_prefix

            def _sub(match: re.Match[str]) -> str:
                original = match.group(0)
                if original in reverse:
                    return reverse[original]
                counters[prefix] += 1
                placeholder = f"[[{prefix}_{counters[prefix]}]]"
                reverse[original] = placeholder
                mapping[placeholder] = original
                return placeholder

            text = pattern.sub(_sub, text)

        return RedactionResult(text=text, mapping=mapping, hits=dict(counters))

    def restore(self, text: str, mapping: dict[str, str]) -> str:
        for placeholder, original in mapping.items():
            text = text.replace(placeholder, original)
        return text


async def load_engine(session: AsyncSession, ruleset: RulesetName) -> RedactionEngine:
    rules = list(
        await session.scalars(
            select(RedactionRule)
            .where(RedactionRule.ruleset == ruleset, RedactionRule.enabled.is_(True))
            .order_by(RedactionRule.order_index)
        )
    )
    return RedactionEngine(rules)
