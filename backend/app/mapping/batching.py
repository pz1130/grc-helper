"""框架项 → 批次；控制点全量渲染。"""

from dataclasses import dataclass
from typing import Any

from app.common.batching import group_by_top_level
from app.errors import AppError

MAX_BATCH_CHARS = 12000
MAX_CONTROL_CONTEXT_CHARS = 60000


class ControlContextTooLarge(AppError):
    code = "control_context_too_large"


@dataclass(frozen=True)
class Batch:
    items: list[Any]
    section: str


def _render_item(item: Any) -> str:
    return (
        f"[framework_item_id={item.id}] {item.code} — {item.title}\n"
        f"{item.description or ''}\n"
    )


def render_items(batch: Batch) -> str:
    lines = [f"# Section: {batch.section}", ""]
    for item in batch.items:
        lines.append(_render_item(item))
    return "\n".join(lines)


def build_batches(items: list[Any], *, max_chars: int = MAX_BATCH_CHARS) -> list[Batch]:
    groups = group_by_top_level(
        items,
        level_of=lambda item: item.level,
        render_size=lambda item: len(_render_item(item)),
        max_chars=max_chars,
    )
    return [Batch(list(group), group[0].code) for group in groups if group]


def render_controls(controls: list[Any]) -> str:
    """全量控制点。超限直接失败——静默截断会让差距结论悄悄退化。"""
    parts = [
        f"[control_id={control.id}] {control.code} — {control.title}\n"
        f"{control.statement or ''}\n"
        for control in controls
    ]
    text = "\n".join(parts)
    if len(text) > MAX_CONTROL_CONTEXT_CHARS:
        raise ControlContextTooLarge(
            f"控制点全集渲染后 {len(text)} 字符，超过上限 {MAX_CONTROL_CONTEXT_CHARS}"
            f"（当前 {len(controls)} 个控制点）。映射任务需要看到全部控制点才能断言差距，"
            f"不做截断；请引入候选控制点检索后再运行。"
        )
    return text
