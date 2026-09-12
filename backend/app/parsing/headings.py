"""标题仲裁：同一份文档的几种读法里，挑自洽的那一种。

**为什么不能是全局规则。** `numbering.py::is_list_item` 原来写死「带点的单段编号
= 正文列表项」，它的 docstring 自己写着"实测**这批文件**里 41 条带点编号全部是
列表项"。实测两个方向都是真的：

    关掉它   08_HKMA 1→47   16_KBC 4→132   17_AlRayan 0→82   18_Bangkok 2→17
    但也会   01_BCBS 42→148   04_EBA 66→254        ← 现状才是对的

区别不在编号长什么样，在**这批编号凑不凑得成一棵树**：HKMA 的 1/1.1/1.2/2/3/3.1…
父子齐全、逐级递增；BCBS 的 1. 2. 3. 反复出现、没有任何子号挂上去。这是一份文档
内部就能看出来的事，不需要跨文档的经验值。

四个维度**相乘**而不是取平均：标题集必须在每个维度上都站得住，任何一维塌了
整体就不成立。取平均会让"没有子号所以父子维度满分"把重复率的低分补回来——
BCBS 那组平均能到 0.80，相乘是 0.33。
"""

from collections.abc import Sequence

Label = str | tuple[int, ...]


def _parts(label: Label) -> tuple[int, ...]:
    if isinstance(label, tuple):
        return label
    return tuple(int(piece) for piece in label.split(".") if piece)


def _unique_ratio(parts: list[tuple[int, ...]]) -> float:
    """同一个编号出现多次，多半是正文列表项在反复重来。"""
    return len(set(parts)) / len(parts)


def _parent_ratio(parts: list[tuple[int, ...]]) -> float:
    """子号的父亲必须在它之前出现过。没有子号时这一维不参与评分。"""
    seen: set[tuple[int, ...]] = set()
    total = hit = 0
    for part in parts:
        if len(part) > 1:
            total += 1
            if part[:-1] in seen:
                hit += 1
        seen.add(part)
    return hit / total if total else 1.0


def _ascending_ratio(parts: list[tuple[int, ...]]) -> float:
    """同一层的兄弟应当逐个递增。回退和跳号都算不自洽。"""
    last: dict[tuple[int, ...], int] = {}
    total = hit = 0
    for part in parts:
        parent, index = part[:-1], part[-1]
        previous = last.get(parent)
        if previous is not None:
            total += 1
            if index == previous + 1:
                hit += 1
        last[parent] = index
    return hit / total if total else 1.0


def _starts_at_one(parts: list[tuple[int, ...]]) -> float:
    tops = [part[0] for part in parts if len(part) == 1]
    return 1.0 if not tops or tops[0] == 1 else 0.5


def consistency_score(labels: Sequence[Label]) -> float:
    """这批编号凑成一棵树的程度，0–1。空集是 0。"""
    parts = [_parts(label) for label in labels]
    parts = [part for part in parts if part]
    if not parts:
        return 0.0
    return (
        _unique_ratio(parts)
        * _parent_ratio(parts)
        * _ascending_ratio(parts)
        * _starts_at_one(parts)
    )


# 两种读法的自洽度差在这个范围内，就算打平，改看谁解释得多。
TIE = 0.05
# 低于这个分数的读法一律不采纳——宁可当作"这份文档没有编号结构"，
# 让格式兜底或塌树闸门去处理，也不要建一棵错的树。
FLOOR = 0.5


def choose_heading_set(candidates: Sequence[Sequence[Label]]) -> Sequence[Label]:
    """几种读法里挑一种；都不自洽就返回空。

    打平时选**解释得多**的那个：一条标题的集合天然满分，但它什么也没说明。
    """
    scored = [(consistency_score(candidate), candidate) for candidate in candidates]
    scored = [(score, candidate) for score, candidate in scored if score >= FLOOR]
    if not scored:
        return []
    best = max(score for score, _ in scored)
    contenders = [candidate for score, candidate in scored if score >= best - TIE]
    return max(contenders, key=len)


# ── `N.` 到底是标题还是列表项 ────────────────────────────────
# 上面那个通用自洽度分在真实文档上**不管用**：实测 15 份 PDF，它救回 3 份却打坏
# 3 份原本正确的（EBA 66→0、BNM 66→0、BCBS 37→222）。原因是它给**未过滤的原始
# 编号流**打分，而真实文档里混着目录、页眉和正文噪声，重复率一高，正确答案
# 也被判成不自洽。
#
# 真正分得开的是另一件事：**这些 `N.` 有没有子号挂上去。** 实测：
#
#     0%      01_BCBS(147 个) / 01b(168) / 02(89)   一个都没有 → 列表项
#     2%      04_EBA(234 个里 5 个)                            → 列表项
#     11–14%  18_Bangkok / 06_BOT / 10_Raya
#     39–100% 17_AlRayan / 09_BBB / 13_BNM / 16_KBC / 08_HKMA(7/7) → 标题
#
# 章节标题天然会有下级，操作步骤不会。这是**结构**性质，不是文风性质。
PARENTHOOD_THRESHOLD = 0.30


def parenthood_ratio(labels: Sequence[Label]) -> float:
    """单段编号里，有子号挂上去的占多少。没有单段编号时返回 0。"""
    parts = [_parts(label) for label in labels]
    parts = [part for part in parts if part]
    singles = sorted({part for part in parts if len(part) == 1})
    if not singles:
        return 0.0
    parents = {part[:-1] for part in parts if len(part) > 1}
    return sum(1 for single in singles if single in parents) / len(singles)


def acts_as_headings(labels: Sequence[Label]) -> bool:
    """这批单段编号该当成章节标题，还是正文列表项。"""
    return parenthood_ratio(labels) >= PARENTHOOD_THRESHOLD
