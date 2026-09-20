"""Phase 377 regression coverage for prolonged cross-provider recovery cycles."""

from datetime import date

from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.services.statistical_service import StatisticalService
from tests.test_phase_375_prolonged_cycles import SessionLocal, seed_draw


def stats(db: Session, lottery_id: int, source: str) -> dict:
    return StatisticalService.overview(db=db, lottery_id=lottery_id, source=source)


def seed_lottery(db: Session, code: str) -> Lottery:
    lottery = Lottery(name=code, code=code, country="Colombia", currency="COP")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def test_phase_377_failed_correction_then_cross_provider_reimport_keeps_single_current_state(db: Session, monkeypatch):
    lottery = seed_lottery(db, "PH377-A")
    baloto = seed_draw(db, lottery.id, "37701", date(2026, 9, 1), [101, 102, 103], "baloto-colombia")
    original_commit = Session.commit
    calls = {"count": 0}

    def fail_once(self):
        if self is db and calls["count"] == 0:
            calls["count"] += 1
            raise RuntimeError("simulated recovery failure")
        return original_commit(self)

    monkeypatch.setattr(Session, "commit", fail_once)
    try:
        try:
            LotteryDrawService.update_draw(
                db=db, draw_id=baloto.id,
                update_data={"draw_number": "37702", "draw_date": date(2026, 9, 2), "main_numbers": [111, 112, 113]},
            )
        except RuntimeError:
            db.rollback()
    finally:
        monkeypatch.setattr(Session, "commit", original_commit)

    LotteryDrawService.update_draw(
        db=db, draw_id=baloto.id,
        update_data={"draw_number": "37702", "draw_date": date(2026, 9, 2), "main_numbers": [111, 112, 113]},
    )
    persisted = db.get(LotteryDraw, baloto.id)
    assert persisted is not None
    assert persisted.main_numbers == [111, 112, 113]
    assert stats(db, lottery.id, "baloto-colombia")["number_frequency"] == {111: 1, 112: 1, 113: 1}
    assert db.query(LotteryDraw).filter(LotteryDraw.source == "baloto-colombia").count() == 1


def test_phase_377_recovery_delete_and_reimport_does_not_restore_deleted_provider_state(db: Session):
    db = SessionLocal()
    try:
        lottery_a = seed_lottery(db, "PH377-B")
        lottery_b = seed_lottery(db, "PH377-C")
    deleted = seed_draw(db, lottery_a.id, "37710", date(2026, 9, 10), [301, 302, 303], "miloto-colombia")
    seed_draw(db, lottery_b.id, "37710", date(2026, 9, 10), [401, 402, 403], "miloto-colombia")

    LotteryDrawService.delete_draw(db=db, draw_id=deleted.id)
    assert db.get(LotteryDraw, deleted.id) is None
    assert stats(db, lottery_a.id, "miloto-colombia")["number_frequency"] == {}
    assert stats(db, lottery_b.id, "miloto-colombia")["number_frequency"] == {401: 1, 402: 1, 403: 1}

    reimported = seed_draw(db, lottery_a.id, "37711", date(2026, 9, 11), [501, 502, 503], "miloto-colombia")
    assert reimported.id != deleted.id
    assert stats(db, lottery_a.id, "miloto-colombia")["number_frequency"] == {501: 1, 502: 1, 503: 1}
    assert stats(db, lottery_b.id, "miloto-colombia")["number_frequency"] == {401: 1, 402: 1, 403: 1}


def test_phase_377_stale_session_after_cross_provider_recovery_reads_current_statistics_only(db: Session):
    db = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH377-D")
        draw = seed_draw(db, lottery.id, "37720", date(2026, 9, 20), [601, 602, 603], "baloto-colombia")
        stale = SessionLocal()
        try:
            assert stale.get(LotteryDraw, draw.id) is not None
        LotteryDrawService.update_draw(
            db=db, draw_id=draw.id,
            update_data={"draw_number": "37721", "draw_date": date(2026, 9, 21), "main_numbers": [701, 702, 703]},
        )
        stale.expire_all()
        current = stale.get(LotteryDraw, draw.id)
        assert current is not None
        assert current.main_numbers == [701, 702, 703]
        assert stats(db, lottery.id, "baloto-colombia")["number_frequency"] == {701: 1, 702: 1, 703: 1}
    finally:
        stale.close()
