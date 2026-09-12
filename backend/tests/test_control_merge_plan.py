"""合并计划：先算清楚会转挂什么、会丢弃什么，再让人决定（OQ-8）。"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.controls.models import Control


async def _control(db_session, code: str, statement: str = "S") -> Control:
    control = Control(code=code, title=f"T {code}", statement=statement)
    db_session.add(control)
    await db_session.flush()
    return control


async def test_a_control_can_point_at_the_one_it_was_merged_into(db_session):
    winner = await _control(db_session, "C-0001")
    loser = await _control(db_session, "C-0002")

    loser.merged_into_id = winner.id
    loser.status = "merged"
    await db_session.flush()

    assert loser.merged_into_id == winner.id


async def test_the_merge_target_must_exist(db_session):
    loser = await _control(db_session, "C-0003")
    loser.merged_into_id = 9_999_999
    with pytest.raises(IntegrityError):
        await db_session.flush()
