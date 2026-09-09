from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.plan_quota import PlanQuota


def pytest_collection_modifyitems(session, config, items):
    target_modules = {
        "test_draw_permission_matrix",
        "tests.test_draw_permission_matrix",
    }
    for item in items:
        module = item.module
        if module.__name__ not in target_modules:
            continue
        engine = module.engine
        PlanQuota.__table__.create(bind=engine, checkfirst=True)
        Lottery.__table__.create(bind=engine, checkfirst=True)
        LotteryDraw.__table__.create(bind=engine, checkfirst=True)
