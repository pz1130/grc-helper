"""候选生成的纯逻辑测试；向量查询在 test_conflicts_router.py 里连库验。"""

from app.conflicts.clustering import MIN_SIMILARITY, keep_cross_document
from app.relations.clustering import Pair


def test_the_starting_threshold_is_below_the_duplicates_one():
    # M6 的 0.90 要求「几乎是同一条」；冲突只要求「在谈同一件事」，门槛应更低。
    from app.relations.clustering import MIN_SIMILARITY as DUPLICATES_THRESHOLD

    assert MIN_SIMILARITY == 0.85
    assert MIN_SIMILARITY < DUPLICATES_THRESHOLD


def test_pairs_inside_one_document_are_dropped():
    pairs = [Pair(1, 2, 0.95), Pair(1, 3, 0.91)]
    # 控制点 1 与 2 同属文件 10；1 与 3 分属 10 与 11。
    docs = {1: {10}, 2: {10}, 3: {11}}

    assert keep_cross_document(pairs, docs) == [Pair(1, 3, 0.91)]


def test_a_control_spanning_two_documents_still_pairs_across():
    # 控制点 1 横跨两份文件，与只在文件 10 的控制点 2 之间仍算跨文件。
    docs = {1: {10, 11}, 2: {10}}

    assert keep_cross_document([Pair(1, 2, 0.9)], docs) == [Pair(1, 2, 0.9)]


def test_a_control_without_any_source_is_dropped():
    # 没有支撑条款就没有原文可比，留着只会在第二级炸掉。
    docs = {1: {10}, 2: set()}

    assert keep_cross_document([Pair(1, 2, 0.99)], docs) == []
