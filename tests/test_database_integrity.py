from sqlalchemy import UniqueConstraint

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw


def test_lottery_code_is_unique_and_required():
    column = Lottery.__table__.c.code

    assert column.unique is True
    assert column.nullable is False


def test_lottery_draw_requires_lottery_and_enforces_unique_number_and_date():
    table = LotteryDraw.__table__
    unique_constraints = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert table.c.lottery_id.nullable is False
    assert table.c.draw_number.nullable is False
    assert table.c.draw_date.nullable is False
    assert ("lottery_id", "draw_number") in unique_constraints
    assert ("lottery_id", "draw_date") in unique_constraints


def test_lottery_draw_foreign_key_cascades_on_lottery_delete():
    foreign_keys = list(LotteryDraw.__table__.c.lottery_id.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "lotteries.id"
    assert foreign_keys[0].ondelete == "CASCADE"


def test_lottery_relationship_uses_delete_orphan_cascade():
    relationship = Lottery.__mapper__.relationships["draws"]

    assert relationship.cascade.delete is True
    assert relationship.cascade.delete_orphan is True
