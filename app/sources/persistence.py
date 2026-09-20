from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.services.lottery_draw_service import LotteryDrawService
from app.sources.contracts import CanonicalDraw
from app.sources.ingestion import IngestionEnvelope, ingest_draws
from app.sources.protocols import LotterySourceAdapter
from app.repositories.lottery_draw_repository import LotteryDrawRepository


@dataclass(frozen=True, slots=True)
class IngestionResult:
    created: int
    updated: int
    skipped: int


def _result_groups(draw: CanonicalDraw) -> list[dict[str, Any]]:
    return [
        {
            "group_code": group_code,
            "position": position,
            "value": value,
            "numeric_value": int(value) if value.isdigit() else None,
        }
        for group_code, values in draw.groups.items()
        for position, value in enumerate(values, start=1)
    ]


def persist_ingestion(
    db: Session,
    lottery_id: int,
    envelopes: list[IngestionEnvelope],
) -> IngestionResult:
    created = updated = skipped = 0

    for envelope in envelopes:
        draw = envelope.draw
        existing = LotteryDrawRepository.get_by_ingestion_key(
            db=db,
            ingestion_key=envelope.idempotency_key,
        )
        payload = {
            "draw_number": draw.draw_number,
            "draw_date": draw.draw_date,
            "draw_datetime": draw.draw_datetime,
            "result_groups": _result_groups(draw),
            "source": draw.metadata.provider,
            "source_type": draw.metadata.source_type,
            "source_reference": draw.metadata.reference,
            "raw_payload": draw.raw_payload,
            "ingestion_key": envelope.idempotency_key,
        }

        if existing is None:
            LotteryDrawService.create_draw(
                db=db,
                lottery_id=lottery_id,
                **payload,
            )
            created += 1
            continue

        changed = any(
            getattr(existing, field) != value
            for field, value in payload.items()
            if field != "result_groups"
        )
        current_groups = [
            {
                "group_code": item.group_code,
                "position": item.position,
                "value": item.value,
                "numeric_value": item.numeric_value,
            }
            for item in existing.results
        ]
        groups = payload["result_groups"]
        if current_groups != groups:
            changed = True

        if not changed:
            skipped += 1
            continue

        LotteryDrawService.update_draw(
            db=db,
            draw_id=existing.id,
            update_data=payload,
        )
        updated += 1

    return IngestionResult(created=created, updated=updated, skipped=skipped)


def ingest_and_persist(
    db: Session,
    lottery_id: int,
    adapter: LotterySourceAdapter,
) -> IngestionResult:
    envelopes = ingest_draws(adapter)
    return persist_ingestion(db=db, lottery_id=lottery_id, envelopes=envelopes)
