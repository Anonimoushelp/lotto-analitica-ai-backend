import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import SQLAlchemyError

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.repositories.lottery_draw_repository import LotteryDrawRepository
from app.repositories.lottery_repository import LotteryRepository


class FailingSession:
    def __init__(self):
        self.added = []
        self.deleted = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.refresh_calls = 0

    def add(self, value):
        self.added.append(value)

    def delete(self, value):
        self.deleted.append(value)

    def commit(self):
        self.commit_calls += 1
        raise SQLAlchemyError("forced transaction failure")

    def rollback(self):
        self.rollback_calls += 1

    def refresh(self, value):
        self.refresh_calls += 1


def test_saas_plan_models_enforce_unique_codes_and_quota_keys():
    plan_table = Plan.__table__
    quota_table = PlanQuota.__table__
    quota_uniques = {
        tuple(constraint.columns.keys())
        for constraint in quota_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert plan_table.c.code.nullable is False
    assert quota_table.c.plan_id.nullable is False
    assert quota_table.c.quota_code.nullable is False
    assert quota_table.c.limit_value.nullable is False
    assert plan_table.c.code.unique is True
    assert ("plan_id", "quota_code") in quota_uniques


def test_lottery_requires_tenant_and_enforces_tenant_scoped_code_uniqueness():
    table = Lottery.__table__
    unique_constraints = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert table.c.tenant_id.nullable is False
    assert table.c.code.nullable is False
    assert ("tenant_id", "code") in unique_constraints


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


@pytest.mark.parametrize(
    "repository_action",
    [
        "create_draw",
        "delete_draw",
        "create_lottery",
        "update_lottery",
        "delete_lottery",
    ],
)
def test_repository_transaction_failure_rolls_back(repository_action):
    db = FailingSession()

    if repository_action == "create_draw":
        draw = LotteryDraw()
        with pytest.raises(SQLAlchemyError):
            LotteryDrawRepository.create(db=db, draw=draw)
        assert db.added == [draw]
    elif repository_action == "delete_draw":
        draw = LotteryDraw()
        with pytest.raises(SQLAlchemyError):
            LotteryDrawRepository.delete(db=db, draw=draw)
        assert db.deleted == [draw]
    elif repository_action == "create_lottery":
        lottery = Lottery()
        with pytest.raises(SQLAlchemyError):
            LotteryRepository.create(db=db, lottery=lottery)
        assert db.added == [lottery]
    elif repository_action == "update_lottery":
        lottery = Lottery()
        with pytest.raises(SQLAlchemyError):
            LotteryRepository.update(db=db, lottery=lottery)
    else:
        lottery = Lottery()
        with pytest.raises(SQLAlchemyError):
            LotteryRepository.delete(db=db, lottery=lottery)
        assert db.deleted == [lottery]

    assert db.commit_calls == 1
    assert db.rollback_calls == 1
    assert db.refresh_calls == 0
