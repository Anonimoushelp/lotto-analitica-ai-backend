from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lottery_draw import LotteryDraw
from app.schemas.data_quality import (
    DataQualityAuditResponse,
    DataQualityDiscrepancy,
    DataQualityReconcileRequest,
    DataQualityReconcileResponse,
    DataQualityRuleResult,
)


class DataQualityService:
    @staticmethod
    def audit(db: Session, lottery_id: int | None = None) -> DataQualityAuditResponse:
        statement = select(LotteryDraw).order_by(LotteryDraw.draw_date.desc())
        if lottery_id is not None:
            statement = statement.where(LotteryDraw.lottery_id == lottery_id)
        draws = list(db.scalars(statement).all())

        discrepancies: list[DataQualityDiscrepancy] = []
        rule_stats = {
            "NUMBERS_VALID": [0, 0],
            "NO_DUPLICATES": [0, 0],
            "DATE_VALID": [0, 0],
        }
        flagged_ids: set[int] = set()

        for draw in draws:
            numbers = draw.main_numbers or []
            valid_range = len(numbers) > 0 and all(isinstance(n, int) and n > 0 for n in numbers)
            if valid_range:
                rule_stats["NUMBERS_VALID"][0] += 1
            else:
                rule_stats["NUMBERS_VALID"][1] += 1
                flagged_ids.add(draw.id)
                discrepancies.append(DataQualityDiscrepancy(
                    id=f"DQ-{draw.id}-NUMBERS_VALID",
                    draw_id=draw.id,
                    lottery_id=draw.lottery_id,
                    draw_number=draw.draw_number,
                    draw_date=draw.draw_date,
                    rule_id="NUMBERS_VALID",
                    description="Los números principales deben ser enteros positivos.",
                    current_main_numbers=numbers,
                    current_bonus_numbers=draw.bonus_numbers,
                ))

            unique = len(numbers) == len(set(numbers))
            if unique:
                rule_stats["NO_DUPLICATES"][0] += 1
            else:
                rule_stats["NO_DUPLICATES"][1] += 1
                flagged_ids.add(draw.id)
                discrepancies.append(DataQualityDiscrepancy(
                    id=f"DQ-{draw.id}-NO_DUPLICATES",
                    draw_id=draw.id,
                    lottery_id=draw.lottery_id,
                    draw_number=draw.draw_number,
                    draw_date=draw.draw_date,
                    rule_id="NO_DUPLICATES",
                    description="El sorteo contiene números principales repetidos.",
                    current_main_numbers=numbers,
                    current_bonus_numbers=draw.bonus_numbers,
                ))

            if draw.draw_date is not None:
                rule_stats["DATE_VALID"][0] += 1
            else:
                rule_stats["DATE_VALID"][1] += 1
                flagged_ids.add(draw.id)

        rules = [
            DataQualityRuleResult(rule_id="NUMBERS_VALID", name="Números válidos", passed=rule_stats["NUMBERS_VALID"][0], failed=rule_stats["NUMBERS_VALID"][1], severity="CRITICAL"),
            DataQualityRuleResult(rule_id="NO_DUPLICATES", name="Sin números duplicados", passed=rule_stats["NO_DUPLICATES"][0], failed=rule_stats["NO_DUPLICATES"][1], severity="CRITICAL"),
            DataQualityRuleResult(rule_id="DATE_VALID", name="Fecha válida", passed=rule_stats["DATE_VALID"][0], failed=rule_stats["DATE_VALID"][1], severity="WARNING"),
        ]
        total = len(draws)
        clean = total - len(flagged_ids)
        score = round((clean / total) * 100, 2) if total else 100.0
        return DataQualityAuditResponse(
            audit_id=f"DQ-AUDIT-{uuid4().hex[:12].upper()}",
            executed_at=datetime.now(timezone.utc),
            lottery_id=lottery_id,
            total_draws=total,
            clean_draws=clean,
            flagged_draws=len(flagged_ids),
            score=score,
            rules=rules,
            discrepancies=discrepancies,
        )

    @staticmethod
    def reconcile(db: Session, discrepancy_id: str, payload: DataQualityReconcileRequest) -> DataQualityReconcileResponse:
        parts = discrepancy_id.split("-")
        if len(parts) < 3 or not parts[1].isdigit():
            raise ValueError("Invalid discrepancy id")
        draw_id = int(parts[1])
        draw = db.get(LotteryDraw, draw_id)
        if draw is None:
            raise LookupError("Draw not found")

        if payload.strategy == "MANUAL_VALUE":
            if payload.custom_main_numbers is None:
                raise ValueError("custom_main_numbers is required for MANUAL_VALUE")
            draw.main_numbers = payload.custom_main_numbers
            draw.bonus_numbers = payload.custom_bonus_numbers
        elif payload.strategy == "PRESERVE_PRIMARY":
            pass
        elif payload.strategy == "PRESERVE_CONFLICTING":
            if payload.custom_main_numbers is None:
                raise ValueError("custom_main_numbers is required for PRESERVE_CONFLICTING")
            draw.main_numbers = payload.custom_main_numbers
            draw.bonus_numbers = payload.custom_bonus_numbers

        metadata = dict(draw.metadata_json or {})
        metadata["last_reconciliation"] = {
            "discrepancy_id": discrepancy_id,
            "strategy": payload.strategy,
            "notes": payload.notes,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }
        draw.metadata_json = metadata
        db.commit()
        db.refresh(draw)

        return DataQualityReconcileResponse(
            discrepancy_id=discrepancy_id,
            draw_id=draw.id,
            status="RESOLVED",
            updated_database_record=True,
            draw={
                "id": draw.id,
                "lottery_id": draw.lottery_id,
                "draw_number": draw.draw_number,
                "draw_date": draw.draw_date.isoformat(),
                "main_numbers": draw.main_numbers,
                "bonus_numbers": draw.bonus_numbers,
                "metadata_json": draw.metadata_json,
            },
            notes=payload.notes,
        )
