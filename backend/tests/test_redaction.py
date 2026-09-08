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
# 形如 SVC_88 的系统账号号——企业里极常见，而且长得和占位符内部一模一样
ACCT_RULE = _rule(r"\b[A-Z]{2,}_\d+\b", "ACCT", order=20)


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


# ── 不变量 1：一次调用里编号全局唯一，多段文本不得撞号 ──────────


def test_redact_many_shares_numbering_across_texts():
    """分两次 redact 会让两边都从 IP_1 开始，合并映射表时直接撞掉一个。"""
    engine = RedactionEngine([IP_RULE])
    batch = engine.redact_many(["堡垒机 192.168.1.1", "请核查 10.20.30.40"])

    assert batch.texts == ["堡垒机 [[IP_1]]", "请核查 [[IP_2]]"]
    assert batch.mapping == {"[[IP_1]]": "192.168.1.1", "[[IP_2]]": "10.20.30.40"}


def test_redact_many_restores_each_text_to_its_own_entity():
    engine = RedactionEngine([IP_RULE])
    batch = engine.redact_many(["堡垒机 192.168.1.1", "请核查 10.20.30.40"])

    assert engine.restore("查 [[IP_2]] 的日志", batch.mapping) == "查 10.20.30.40 的日志"
    assert engine.restore("查 [[IP_1]] 的日志", batch.mapping) == "查 192.168.1.1 的日志"


def test_same_entity_in_two_texts_gets_one_placeholder():
    engine = RedactionEngine([IP_RULE])
    batch = engine.redact_many(["主机 10.0.0.1", "还是 10.0.0.1"])

    assert batch.texts == ["主机 [[IP_1]]", "还是 [[IP_1]]"]
    assert len(batch.mapping) == 1
    assert batch.hits == {"IP": 1}


# ── 不变量 2：后续规则不得扫进已生成的占位符 ────────────────────


def test_later_rule_does_not_eat_earlier_placeholder():
    """[[IP_1]] 内部的 IP_1 长得就像系统账号号，规则必须扫不进去。"""
    engine = RedactionEngine([IP_RULE, ACCT_RULE])
    result = engine.redact("主机 10.0.0.1 由账号 SVC_88 管理")

    assert result.text == "主机 [[IP_1]] 由账号 [[ACCT_1]] 管理"
    assert "[[[[" not in result.text
    assert result.mapping == {"[[IP_1]]": "10.0.0.1", "[[ACCT_1]]": "SVC_88"}


def test_reversible_even_when_a_rule_could_match_placeholders():
    engine = RedactionEngine([IP_RULE, ACCT_RULE])
    original = "主机 10.0.0.1 由账号 SVC_88 管理，备机 10.0.0.2"
    result = engine.redact(original)

    assert engine.restore(result.text, result.mapping) == original


@pytest.mark.parametrize(
    "texts",
    [
        ["主机 10.0.0.1 账号 SVC_88"],
        ["堡垒机 192.168.1.1", "跳板机 10.20.30.40"],
        ["新开发银行的 10.0.0.1", "账号 ADM_7 归 开发银行 管"],
        ["", "10.0.0.1", "没有敏感信息"],
        ["重复 SVC_88 重复 SVC_88", "别处也有 SVC_88"],
    ],
)
def test_property_redact_many_then_restore_is_identity(texts):
    """spec §6.2 硬约束的加强版：规则集里含有能匹配占位符形状的规则时也必须可逆。"""
    engine = RedactionEngine([DICT_RULE, IP_RULE, ACCT_RULE])
    batch = engine.redact_many(texts)

    for original, redacted in zip(texts, batch.texts, strict=True):
        assert engine.restore(redacted, batch.mapping) == original
