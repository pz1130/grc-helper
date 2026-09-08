"""模型价格表（美元 / 百万 token）。

价格会变，运维应定期核对。未知模型返回 0 而不是抛异常——
成本统计不准可以接受，让整条流水线挂掉不可接受。
"""

_PRICES: dict[str, tuple[float, float]] = {
    # model: (input_per_mtok, output_per_mtok)
    "claude-opus-5": (15.0, 75.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "deepseek-chat": (0.27, 1.1),
    "qwen-max": (1.6, 6.4),
    "text-embedding-3-large": (0.13, 0.0),
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price = _PRICES.get(model)
    if price is None:
        return 0.0
    in_rate, out_rate = price
    return tokens_in / 1_000_000 * in_rate + tokens_out / 1_000_000 * out_rate
