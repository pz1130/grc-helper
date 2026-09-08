import re

import pytest

from app.llm.models import RedactionRule, RulesetName
from app.llm.redaction import RedactionEngine


def _rule(pattern: str, prefix: str, *, pattern_type: str = "regex", order: int = 10):
    return RedactionRule(
        ruleset=RulesetName.GENERATION,
        pattern_type=pattern_type,
        pattern=pattern,
        replacement_prefix=prefix,
        enabled=True,
        order_index=order,
    )


IP_RULE = _rule(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "IP")
DICT_RULE = _rule("新开发银行\n开发银行", "ORG", pattern_type="dictionary", order=5)


def test_redact_replaces_match_with_placeholder():
    engine = RedactionEngine([IP_RULE])
    result = engine.redact("跳板机地址是 10.20.30.40，请勿外传。")
    assert "10.20.30.40" not in result.text
    assert "[[IP_1]]" in result.text


def test_roundtrip_restores_exactly():
    engine = RedactionEngine([IP_RULE])
    original = "主机 10.0.0.1 与备机 10.0.0.2 双活。"
    result = engine.redact(original)
    assert engine.restore(result.text, result.mapping) == original


def test_same_value_maps_to_same_placeholder():
    """同一实体必须同一代号，否则模型会以为是两个不同实体。"""
    engine = RedactionEngine([IP_RULE])
    result = engine.redact("10.0.0.1 与 10.0.0.1 是同一台机器")
    assert result.text.count("[[IP_1]]") == 2
    assert len(result.mapping) == 1


def test_placeholder_numbering_does_not_collide_on_prefix():
    """IP_1 与 IP_10 不能互相污染——方括号定界保证这一点。"""
    engine = RedactionEngine([IP_RULE])
    text = " ".join(f"10.0.0.{i}" for i in range(1, 12))
    result = engine.redact(text)
    assert engine.restore(result.text, result.mapping) == text


def test_dictionary_rule_prefers_longer_term():
    engine = RedactionEngine([DICT_RULE])
    result = engine.redact("新开发银行的制度")
    assert result.text == "[[ORG_1]]的制度"
    assert result.mapping["[[ORG_1]]"] == "新开发银行"


def test_disabled_rule_is_ignored():
    rule = _rule(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "IP")
    rule.enabled = False
    engine = RedactionEngine([rule])
    assert engine.redact("10.0.0.1").text == "10.0.0.1"


def test_hits_are_counted_per_prefix():
    engine = RedactionEngine([IP_RULE])
    result = engine.redact("10.0.0.1 10.0.0.2 10.0.0.1")
    assert result.hits == {"IP": 2}   # 两个不同实体


def test_restore_handles_llm_output_containing_placeholders():
    """模型返回的文本里带占位符，还原后必须是真实内容。"""
    engine = RedactionEngine([IP_RULE])
    result = engine.redact("请检查 10.0.0.1")
    llm_output = f"建议核查 {list(result.mapping)[0]} 的访问日志。"
    assert engine.restore(llm_output, result.mapping) == "建议核查 10.0.0.1 的访问日志。"


def test_text_without_matches_is_unchanged():
    engine = RedactionEngine([IP_RULE])
    result = engine.redact("这段话里没有任何敏感信息")
    assert result.text == "这段话里没有任何敏感信息"
    assert result.mapping == {}


@pytest.mark.parametrize(
    "original",
    [
        "",
        "纯中文没有敏感信息",
        "10.0.0.1",
        "前 10.0.0.1 中 192.168.1.1 后",
        "重复 10.0.0.1 重复 10.0.0.1 重复 10.0.0.1",
        "边界情况 10.0.0.1，紧跟标点。",
    ],
)
def test_property_redact_then_restore_is_identity(original):
    """spec §6.2 硬约束：脱敏必须可逆。这条测试不许删。"""
    engine = RedactionEngine([IP_RULE, DICT_RULE])
    result = engine.redact(original)
    assert engine.restore(result.text, result.mapping) == original
